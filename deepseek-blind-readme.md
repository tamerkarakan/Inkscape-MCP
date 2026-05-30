# Inkscape MCP Server — Tasarım Belgesi

> Inkscape 1.4.2 için Model Context Protocol (MCP) sunucusu.
> Yapay zeka asistanlarının Inkscape CLI aracılığıyla SVG üretmesi, düzenlemesi,
> sorgulaması ve çoklu formatta dışa aktarması için köprü.

---

## İçindekiler

1. [Dil ve Çatı Seçimi](#1-dil-ve-çatı-seçimi)
2. [Mimari Tasarım](#2-mimari-tasarım)
3. [Transport Katmanı](#3-transport-katmanı)
4. [Hata Yönetimi](#4-hata-yönetimi)
5. [Güvenlik Tasarımı](#5-güvenlik-tasarımı)
6. [Test Yapısı Planı](#6-test-yapısı-planı)
7. [Doğrulanmış Inkscape Yetenekleri (Ground Truth)](#7-doğrulanmış-inkscape-yetenekleri-ground-truth)

---

## 1. Dil ve Çatı Seçimi

### Önerilen: Python 3.12+ + `mcp` resmi SDK

| Aday | MCP Desteği | Gerekçe |
|---|---|---|
| **Python + `mcp`** | Resmi Python SDK (`pip install mcp`) | Inkscape ile aynı ekosistem; `inkex` kütüphanesine doğrudan erişim; subprocess yönetimi basit; tek bağımlılıkla kurulum |
| TypeScript + `@modelcontextprotocol/sdk` | Resmi Node.js SDK | Güçlü tip sistemi, ancak `inkex` erişimi yok; Node.js ayrı kurulum gerektirir |
| Go / Rust | Topluluk SDK'ları | Derlenmiş binary avantajı, ancak Inkscape Python eklenti ekosisteminden kopuk |

### Gerekçe

1. **`inkex` doğrudan entegrasyonu:** Inkscape'in tüm uzantı altyapısı Python/`inkex` ile yazılmıştır. MCP sunucusu, Inkscape kurulumundaki `share/inkscape/extensions` dizinini `PYTHONPATH`'e ekleyerek `inkex.elements`, `inkex.command` ve tüm yerleşik uzantıları doğrudan import edebilir.
2. **Alt süreç modeli doğal:** Python'un `subprocess.Popen` ile `inkscape.com --shell` etkileşimli modda çalıştırmak, stdin/stdout üzerinden stateful oturum yönetimi için idealdir.
3. **Tek bağımlılık:** `pip install mcp` dışında sistem bağımlılığı yoktur. Inkscape zaten Python 3.12.9 gömülü olarak gelir.
4. **MCP Python SDK kararlılığı:** `mcp` paketi, JSON-RPC 2.0, Tool/Resource/Prompt üçlüsü, stdio ve SSE transport'larının tamamını destekler.

### Paket Yapısı

```
inkscape_mcp/
├── pyproject.toml
├── src/
│   └── inkscape_mcp/
│       ├── __init__.py
│       ├── server.py          # MCP server giriş noktası (stdio transport)
│       ├── session.py         # InkscapeShellSession — inkscape --shell süreç yönetimi
│       ├── tools.py           # MCP Tool tanımları ve handler'ları
│       ├── resources.py       # MCP Resource tanımları (inkx:// URI)
│       ├── prompts.py         # MCP Prompt şablonları
│       ├── actions.py         # Action zinciri oluşturucu / ayrıştırıcı
│       ├── normalize.py       # CLI çıktısı → JSON normalizer
│       ├── security.py        # Yol doğrulama, komut kaçış önleme
│       └── exceptions.py      # Hata hiyerarşisi
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── README.md
```

---

## 2. Mimari Tasarım

### 2.1 Genel Katmanlı Mimari

```
┌──────────────────────────────────────────────────────────────┐
│                     MCP Client (AI Asistan)                   │
└──────────────────────┬───────────────────────────────────────┘
                       │  JSON-RPC 2.0 (stdio)
┌──────────────────────▼───────────────────────────────────────┐
│                   MCP Protocol Layer                          │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │ Tool Router  │   │  Resource    │   │  Prompt Provider │   │
│  │              │   │  Provider    │   │                  │   │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────────┘   │
│         │                  │                   │               │
│  ┌──────▼──────────────────▼───────────────────▼───────────┐   │
│  │              Command Translation Layer                  │   │
│  │  ┌──────────────────┐   ┌─────────────────────────┐    │   │
│  │  │  Action Builder   │   │  Response Normalizer    │    │   │
│  │  │ param → shell cmd │   │  ham çıktı → typed obj  │    │   │
│  │  └────────┬─────────┘   └───────────┬─────────────┘    │   │
│  └───────────┼─────────────────────────┼──────────────────┘   │
└──────────────┼─────────────────────────┼──────────────────────┘
               │                         │
┌──────────────▼─────────────────────────▼──────────────────────┐
│                  Inkscape Interface Layer                      │
│  ┌─────────────────────────┐  ┌──────────────────────────┐    │
│  │  Shell Session (birincil)│  │  Tek Çağrı Modu (yedek) │    │
│  │  inkscape.com --shell    │  │  inkscape.com --pipe     │    │
│  │  stateful, stdin/stdout  │  │  stateless, fire/forget  │    │
│  └─────────────────────────┘  └──────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  inkex Kütüphanesi (isteğe bağlı, in-process)            │ │
│  │  SVG parse/manipülasyonu, uzantı çalıştırma              │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 MCP Tool Tasarım Deseni

Her MCP tool'u üç bileşenden oluşur:

```
Tool Definition (JSON Schema)
       │
       ▼
Action Chain Builder
       │  Kullanıcı parametresi → Inkscape shell komut(lar)ı zinciri
       ▼
Response Normalizer
       │  Inkscape ham stdout/stderr → yapılandırılmış yanıt
       ▼
MCP Response (content[] veya isError)
```

**Örnek: `shape_rectangle` tool'u**

```python
# tools.py
def register_shape_rectangle(mcp: Server, session_manager: SessionManager):
    @mcp.tool()
    async def shape_rectangle(
        x: float, y: float, width: float, height: float,
        rx: float | None = None, ry: float | None = None,
        fill: str | None = None,
        stroke: str | None = None,
        stroke_width: float | None = None,
    ) -> ToolResult:
        """Mevcut SVG dokümanına bir dikdörtgen ekler."""
        session = session_manager.get_current()
        commands = [
            "tool-rect",
        ]
        if rx is not None or ry is not None:
            # rx/ry shell'de ayrı bir komut zinciri olarak uygulanır
            pass
        # Shell'e gönder, yanıtı normalize et
        output = await session.send_commands(commands)
        return normalize_creation_result(output)
```

### 2.3 MCP Resource Tasarım Deseni

Mevcut Inkscape oturum durumunu salt-okunur kaynaklar olarak sunar:

| Resource URI | MIME Type | İçerik |
|---|---|---|
| `inkscape://session/current-svg` | `image/svg+xml` | Aktif SVG dokümanının tam XML içeriği |
| `inkscape://session/selection` | `application/json` | Seçili nesnelerin ID listesi |
| `inkscape://session/geometry` | `application/json` | Tüm nesnelerin bounding box'ları |
| `inkscape://session/actions` | `application/json` | Kullanılabilir action'lar kataloğu |
| `inkscape://session/document-info` | `application/json` | Sayfa boyutu, birim, DPI, katman sayısı |

Resource'lar **her okumada canlı** güncellenir — session'ın o anki durumunu yansıtır.

### 2.4 MCP Prompt Tasarım Deseni

Tekrarlayan iş akışlarını hızlandırmak için önceden tanımlanmış prompt şablonları:

| Prompt Adı | Açıklama |
|---|---|
| `create-logo` | Logo tasarımı iş akışı: artboard → şekil → metin → hizalama → dışa aktar |
| `create-diagram` | Diyagram/akış şeması: kutu → ok → etiket → gruplama → dışa aktar |
| `trace-bitmap` | Bitmap izleme: içe aktar → trace → path basitleştir → dışa aktar |
| `batch-export` | Toplu dışa aktarım: bir SVG'den çoklu format/çözünürlük |
| `svg-optimize` | SVG temizleme: plain SVG, vacuum defs, gereksiz öznitelik temizliği |

Prompt'lar argüman olarak bir SVG dosya yolu alır ve ilgili tool çağrılarını sırayla yapar.

### 2.5 Oturum (Session) Yönetimi

İki çalışma modu için session yönetimi:

#### Mod A: Stateful Shell Session (Birincil)

```python
@dataclass
class InkscapeShellSession:
    """Bir inkscape --shell alt sürecini sarar."""
    session_id: str
    process: asyncio.subprocess.Process  # inkscape.com --shell
    work_dir: Path                        # Geçici çalışma dizini
    current_svg: Path | None              # Açık olan SVG dosyası
    selection: list[str]                  # Seçili nesne ID'leri
    created_at: float
    last_used: float

    async def send_command(self, command: str) -> str:
        """Shell'e tek komut gönderir, stdout çıktısını döndürür."""
        ...

    async def send_commands(self, commands: list[str]) -> list[str]:
        """Birden çok komutu sırayla gönderir."""
        ...
```

- `inkscape.com --shell` tek bir uzun ömürlü alt süreç olarak çalışır
- Komutlar stdin'e yazılır, yanıtlar stdout'tan okunur
- Doküman durumu komutlar arasında korunur
- Her MCP bağlantısı için bir shell session'ı oluşturulur
- `--app-id-tag=mcp-{uuid}` ile çoklu eşzamanlı session izolasyonu

#### Mod B: Stateless Tek Çağrı (Yedek)

Shell gerektirmeyen basit işlemler için:
- `inkscape.com --query-all input.svg` — doğrudan çağrı, çıktı parse edilir
- `inkscape.com --pipe --query-all` — stdin'den SVG oku, sorgula
- `inkscape.com --export-type=png --export-filename=- input.svg` — stdout'a dışa aktar

### 2.6 İletişim Akışı (Örnek)

```
AI: "Bu SVG'deki kırmızı dikdörtgeni mavi yap ve PNG olarak kaydet"

1. MCP: document_open("input.svg")
   → Shell: "file-open:input.svg"
   ← "OK"

2. MCP: query_all_geometry()
   → Shell: "query-all"
   ← "rect1,10,10,100,50\ncircle1,150,80,40,40"
   → normalize → [{id: "rect1", x:10, y:10, w:100, h:50}, ...]

3. MCP: selection_set(["rect1"])
   → Shell: "select:rect1"
   ← "OK"

4. MCP: style_set_attribute("fill", "blue")
   → Shell: "object-set-attribute:fill,blue"
   ← "OK"

5. MCP: export_png("output.png")
   → Shell: "export-filename:output.png;export-type:png;export-do"
   ← (dosya oluşturuldu)

6. AI'ya yanıt: "rect1'in rengi mavi yapıldı, output.png olarak dışa aktarıldı."
```

---

## 3. Transport Katmanı

### 3.1 stdio Transport (Birincil)

MCP standardındaki en basit ve en güvenilir transport:

```json
{
  "mcpServers": {
    "inkscape": {
      "command": "python",
      "args": ["-m", "inkscape_mcp.server"],
      "env": {
        "INKSCAPE_BIN": "E:/Downloads/zip/inkscape-1.4.2_2025-05-13_f4327f4-x64/inkscape/bin/inkscape.com",
        "INKSCAPE_TIMEOUT": "30",
        "INKSCAPE_MAX_SVG_MB": "50"
      }
    }
  }
}
```

- Sunucu `sys.stdin.buffer` / `sys.stdout.buffer` üzerinden JSON-RPC 2.0 mesajlarını okur/yazar
- Her satır bir JSON-RPC mesajıdır (newline-delimited JSON)
- `mcp` SDK'sı bu işi otomatik halleder

### 3.2 SSE Transport (Planlanan)

Uzak sunucu kullanımı veya web tabanlı IDE entegrasyonu için:

```python
# server.py içinde
mcp.run(transport="sse")  # localhost:8000/sse ve /messages endpoint'leri
```

### 3.3 Process Yaşam Döngüsü

```
Başlatma:
  [MCP Client] ──spawn──▶ [python -m inkscape_mcp.server]
                                │
                                ├─ inkscape.com --version (binary doğrulama)
                                ├─ inkscape.com --action-list (action kataloğu oluşturma)
                                └─ hazır → "initialize" yanıtı

Çalışma:
  [MCP Client] ──tools/call──▶ [server] ──shell cmd──▶ [inkscape.com --shell]
              ◄──result────── [server] ◄──stdout────── [inkscape.com --shell]

Kapanma:
  [MCP Client] ──kapanma──▶ [server] ──quit────▶ [inkscape.com --shell]
                                     ──SIGTERM──▶ (5 sn içinde kapanmazsa)
                                     ──temp temizliği
```

---

## 4. Hata Yönetimi

### 4.1 Kritik Bulgu: Inkscape Her Zaman 0 ile Çıkar

Testlerle doğrulanan davranış:
- `inkscape.com nonexistent.svg` → exit code **0**, hata stderr'de
- `inkscape.com --actions="nonexistent-action"` → exit code **0**, hata stderr'de

**Sonuç:** Hata tespiti için **stderr ayrıştırması zorunludur.** Exit code güvenilir değildir.

### 4.2 Hata Hiyerarşisi

```python
class InkscapeError(Exception):
    """Tüm Inkscape MCP hatalarının tabanı."""
    exit_code: int = 0  # Inkscape'ten gelen orijinal kod değil, bizim atadığımız

class InkscapeNotFoundError(InkscapeError):
    """inkscape.com binary'si bulunamadı."""
    pass

class InkscapeProcessError(InkscapeError):
    """Alt süreç başlatılamadı veya beklenmedik şekilde öldü."""
    pass

class InkscapeTimeoutError(InkscapeError):
    """Komut zaman aşımına uğradı (varsayılan: 30 saniye)."""
    pass

class InkscapeActionError(InkscapeError):
    """Geçersiz action adı veya argümanı."""
    def __init__(self, action: str, stderr: str):
        self.action = action
        super().__init__(f"Action '{action}' failed: {stderr}")

class InkscapeExportError(InkscapeError):
    """Dışa aktarım başarısız (dosya yazılamadı, format desteklenmiyor, vb.)."""
    pass

class InkscapeFileError(InkscapeError):
    """Dosya açılamadı / okunamadı."""
    pass

class InkscapeSecurityError(InkscapeError):
    """Güvenlik denetimi başarısız (izin verilmeyen dizin, vb.)."""
    pass
```

### 4.3 Stderr Ayrıştırma Stratejisi

```python
def parse_stderr(stderr: str) -> InkscapeError | None:
    """Inkscape stderr çıktısını tarar, bilinen hata kalıplarını arar."""
    patterns = [
        (r"could not find action for: (\S+)", InkscapeActionError),
        (r"cannot be opened!", InkscapeFileError),
        (r"doesn't exist", InkscapeFileError),
        (r"failed to create document", InkscapeFileError),
    ]
    for pattern, error_cls in patterns:
        if m := re.search(pattern, stderr):
            return error_cls(m.group(0))
    if stderr.strip():
        return InkscapeError(stderr.strip())
    return None
```

### 4.4 MCP'ye Hata İletimi

Tüm yakalanan hatalar MCP yanıtında `isError: true` ile döndürülür:

```json
{
  "isError": true,
  "content": [{
    "type": "text",
    "text": "Action 'nonexistent-action' failed: InkscapeApplication::parse_actions: could not find action for: nonexistent-action.\n\nDid you mean one of: none-available? Run 'action_list' resource to see all valid actions."
  }]
}
```

Hata mesajları **düzeltici eylem önerisi** içerir (mümkün olduğunda).

---

## 5. Güvenlik Tasarımı

### 5.1 Tehdit Modeli

| Tehdit | Risk | Önlem |
|---|---|---|
| **Yol traversal** — AI'ın `../../etc/passwd` yazması | Yüksek | Tüm dosya yolları `allowed_directories` ile sınırlandırılır; `..` içeren yollar reddedilir |
| **Komut enjeksiyonu** — action parametresine `; rm -rf /` | Yüksek | Shell komutları **asla** shell üzerinden birleştirilmez; `inkscape --shell` stdin'ine ham string yazılır |
| **DoS — dev SVG** — 500 MB SVG gönderme | Orta | `max_svg_size_bytes` (varsayılan 50 MB) aşılırsa okuma reddedilir |
| **DoS — sonsuz döngü** — karmaşık path işlemi | Orta | Her komut için 30 saniye timeout |
| **Session'lar arası sızıntı** | Orta | Her session için `--app-id-tag` ile izole Inkscape örneği; temp dizinler ayrı |
| **Binary değiştirme** — sahte inkscape.com | Düşük | Başlangıçta `--version` çıktısı doğrulanır |

### 5.2 Güvenlik Yapılandırması

```python
@dataclass
class SecurityConfig:
    # Dosya sistemi
    allowed_directories: list[Path]      # Yalnızca bu dizinler ve alt dizinleri
    deny_path_traversal: bool = True     # '..' reddet

    # Boyut limitleri
    max_svg_size_bytes: int = 52_428_800       # 50 MB
    max_export_size_bytes: int = 104_857_600   # 100 MB

    # Zaman aşımı
    command_timeout_seconds: int = 30

    # Format kısıtlaması
    allowed_export_formats: tuple = (
        "svg", "png", "pdf", "ps", "eps", "emf", "wmf", "xaml"
    )

    # Session
    max_concurrent_sessions: int = 5
    session_ttl_seconds: int = 3600      # 1 saat
```

### 5.3 Komut Enjeksiyonu Önleme (Detay)

```python
# GÜVENLİ: Stdin'e doğrudan yazma
async def send_shell_command(self, command: str) -> str:
    """Inkscape --shell stdin'ine komut yazar. Shell yorumlaması YOKTUR."""
    # command = "object-set-attribute:fill,red"
    self._process.stdin.write((command + "\n").encode())
    await self._process.stdin.drain()
    return await self._read_response()

# Action parametresi validasyonu
_ACTION_NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9._-]*$')
_ACTION_ARG_RE  = re.compile(r'^[a-zA-Z0-9._:,=/\- ]*$')

def validate_action(name: str, arg: str | None = None) -> None:
    if not _ACTION_NAME_RE.match(name):
        raise InkscapeSecurityError(f"Invalid action name: {name}")
    if arg is not None and not _ACTION_ARG_RE.match(arg):
        raise InkscapeSecurityError(f"Invalid action argument: {arg}")
```

---

## 6. Test Yapısı Planı

### 6.1 Test Piramidi

```
            ┌──────────┐
            │   E2E    │  ~%10   Gerçek Inkscape binary ile tam zincir
            │  Tests   │         (CI'da opsiyonel, INKSCAPE_E2E=1)
           ┌┴──────────┴┐
           │ Integration │  ~%30   MCP transport + mock subprocess
           │    Tests    │
          ┌┴─────────────┴┐
          │  Unit Tests    │  ~%60   Action builder, normalizer, security,
          │                │         session manager, error parser
          └────────────────┘
```

### 6.2 Birim Testler (Unit)

**Hedef:** ≥%80 satır kapsamı

| Test Modülü | Kapsam |
|---|---|
| `test_actions.py` | Action builder: parametre → shell komut zinciri dönüşümü; tüm kenar durumları |
| `test_normalize.py` | Response normalizer: ham stdout → typed dict/list; tüm `--query-all`, `--query-x -Y -W -H` formatları |
| `test_security.py` | Yol doğrulama, `..` reddi, action adı regex, boyut limiti |
| `test_session.py` | Session yaşam döngüsü: oluşturma, komut gönderme, timeout, temizlik |
| `test_errors.py` | Stderr ayrıştırma: tüm bilinen hata kalıpları için doğru exception üretimi |
| `test_exceptions.py` | Exception hiyerarşisi: her exception'ın `isError` serileştirmesi |

**Framework:** `pytest` + `pytest-cov`

```python
# tests/unit/test_actions.py
class TestActionBuilder:
    def test_rectangle_basic(self):
        """Dikdörtgen → tool-rect komutu"""
        result = build_rectangle_actions(x=10, y=20, w=100, h=50)
        assert result == ["tool-rect"]

    def test_rectangle_with_color(self):
        """Renkli dikdörtgen → tool-rect + object-set-attribute"""
        result = build_rectangle_actions(x=0, y=0, w=50, h=50, fill="#FF0000")
        assert "object-set-attribute:fill,#FF0000" in result

    def test_invalid_color_raises(self):
        """Geçersiz renk → ValidationError"""
        with pytest.raises(ValidationError, match="color"):
            build_rectangle_actions(x=0, y=0, w=10, h=10, fill="zzz")

# tests/unit/test_normalize.py
class TestResponseNormalizer:
    def test_query_all_output(self):
        """--query-all ham çıktısı → [{id, x, y, w, h}]"""
        raw = "svg1,10,10,80,60\nrect1,10,10,30,40\ncircle1,50,30,40,40"
        result = normalize_query_all(raw)
        assert len(result) == 3
        assert result[0] == {"id": "svg1", "x": 10, "y": 10, "w": 80, "h": 60}

    def test_query_single_axis(self):
        """--query-x ham çıktısı → float"""
        raw = "10\n"
        result = normalize_query_axis(raw)
        assert result == 10.0

# tests/unit/test_errors.py
class TestStderrParser:
    def test_action_not_found(self):
        stderr = "InkscapeApplication::parse_actions: could not find action for: bad-action"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeActionError)

    def test_file_not_found(self):
        stderr = "ink_file_open: '/tmp/nonexistent.svg' cannot be opened!"
        err = parse_stderr(stderr)
        assert isinstance(err, InkscapeFileError)

    def test_clean_stderr_returns_none(self):
        assert parse_stderr("") is None
```

### 6.3 Entegrasyon Testleri (Integration)

**Kapsam:** MCP Tool çağrısı → Action Builder → **mock subprocess** → Response Normalizer zinciri

**Framework:** `pytest` + `pytest-asyncio` + `unittest.mock`

```python
# tests/integration/test_mcp_tools.py
@pytest.mark.asyncio
async def test_shape_rectangle_tool(mcp_test_client, mock_shell_session):
    """shape_rectangle tool'u tüm katmanlardan başarıyla geçer."""
    mock_shell_session.expect_commands(["tool-rect"])
    mock_shell_session.respond(["OK"])

    result = await mcp_test_client.call_tool("shape_rectangle", {
        "x": 10, "y": 20, "width": 100, "height": 50
    })
    assert result["isError"] is not True

@pytest.mark.asyncio
async def test_export_png_error_propagation(mcp_test_client, mock_shell_session):
    """Hata MCP isError olarak iletilir."""
    mock_shell_session.expect_commands(["export-filename:/invalid/path.png;...;export-do"])
    mock_shell_session.respond_with_error("cannot be opened!")

    result = await mcp_test_client.call_tool("export_png", {
        "output_path": "/invalid/path.png"
    })
    assert result["isError"] is True
    assert "cannot be opened" in result["content"][0]["text"]

@pytest.mark.asyncio
async def test_resource_current_svg(mcp_test_client, mock_shell_session):
    """Resource current-svg canlı SVG içeriğini döndürür."""
    mock_shell_session.mock_current_svg("<svg>...</svg>")
    result = await mcp_test_client.read_resource("inkscape://session/current-svg")
    assert "<svg>" in result
```

### 6.4 Uçtan Uca Testler (E2E)

**Kapsam:** Gerçek `inkscape.com` binary'si ile tam zincir. CI'da `INKSCAPE_E2E=1` ile opsiyonel.

**Framework:** `pytest` + gerçek Inkscape

```python
# tests/e2e/test_real_inkscape.py
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("INKSCAPE_E2E"),
    reason="INKSCAPE_E2E=1 required"
)
class TestRealInkscapeE2E:
    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        inkscape_bin = os.environ["INKSCAPE_BIN"]
        self.session = InkscapeShellSession(
            session_id="e2e-test",
            inkscape_bin=inkscape_bin,
            work_dir=tmp_path,
        )

    def test_shell_create_rectangle_and_query(self):
        """Shell'de dikdörtgen oluştur, geometri sorgula, dışa aktar."""
        # Yeni belge, dikdörtgen oluştur
        self.session.send_command("file-new")
        self.session.send_command("tool-rect")
        # Geometri sorgula
        result = self.session.send_command("query-all")
        assert result  # boş değil

    def test_shell_modify_and_export(self, tmp_path):
        """Nesne özniteliğini değiştir ve dışa aktar."""
        svg_path = tmp_path / "test.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
            '<rect id="r1" x="0" y="0" width="50" height="50" fill="red"/></svg>'
        )
        self.session.send_command(f"file-open:{svg_path}")
        self.session.send_command("select:r1")
        self.session.send_command("object-set-attribute:fill,blue")
        self.session.send_command(f"export-filename:{tmp_path / 'out.svg'}")
        self.session.send_command("export-type:svg")
        self.session.send_command("export-do")

        out = tmp_path / "out.svg"
        assert out.exists()
        assert "fill=\"blue\"" in out.read_text()

    def test_pipe_query(self, tmp_path):
        """--pipe ile stdin'den SVG okuyup sorgulama."""
        import subprocess
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect id="r" x="5" y="10" w="20" h="30"/></svg>'
        result = subprocess.run(
            [INKSCAPE_BIN, "--pipe", "--query-all"],
            input=svg, capture_output=True, text=True,
        )
        assert "r,5,10,20,30" in result.stdout

    def test_export_to_stdout(self, tmp_path):
        """--export-filename=- ile stdout'a SVG dışa aktarım."""
        svg_path = tmp_path / "in.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="30" fill="green"/></svg>'
        )
        import subprocess
        result = subprocess.run(
            [INKSCAPE_BIN, "--export-type=svg", "--export-plain-svg",
             "--export-filename=-", str(svg_path)],
            capture_output=True, text=True,
        )
        assert 'fill="green"' in result.stdout, f"stdout: {result.stdout[:200]}"
```

### 6.5 Test Fixtures

```
tests/fixtures/
├── empty.svg                    # Boş doküman
├── basic_shapes.svg             # rect + circle + ellipse + line + text
├── complex_scene.svg            # Katmanlar, gruplar, klonlar, filtreler
├── text_samples.svg             # Çeşitli font/ebat/hizalama
├── paths_collection.svg         # Path operasyonları test verisi
├── large_document.svg           # ~1000 nesne (performans testi)
├── multi_page.pdf               # Çok sayfalı PDF (--pages testi)
└── malformed/                   # Negatif testler
    ├── invalid_xml.svg
    ├── missing_namespace.svg
    └── binary_not_svg.png
```

### 6.6 CI/CD Test Matrisi

| İşletim Sistemi | Python | Inkscape | Test Seviyesi |
|---|---|---|---|
| Ubuntu 24.04 | 3.12 | 1.4 (apt) | Unit + Integration + E2E |
| Windows 11 | 3.12 (gömülü) | 1.4.2 (portable) | Unit + Integration + E2E |
| macOS 14 | 3.12 | 1.4 (Homebrew) | Unit + Integration |
| Tümü | 3.12 | — | Lint (ruff), Type check (mypy) |

### 6.7 Çalıştırma Komutları

```bash
# Birim testler
pytest tests/unit/ -v --cov=src/inkscape_mcp --cov-report=term

# Entegrasyon testleri
pytest tests/integration/ -v

# E2E testler (yalnızca Inkscape kurulu ortamda)
INKSCAPE_E2E=1 INKSCAPE_BIN="E:/Downloads/zip/.../inkscape.com" pytest tests/e2e/ -v

# Tam test paketi
pytest -v

# Lint + type check
ruff check src/ tests/
mypy src/
```

---

## 7. Doğrulanmış Inkscape Yetenekleri (Ground Truth)

> Tüm maddeler `inkscape.com` binary'si ile birebir test edilmiştir.
> **Inkscape sürümü:** 1.4.2 (f4327f4, 2025-05-13), Windows 11 x64.

### 7.1 Çalışma Modları

| Mod | Bayrak | Davranış | Doğrulandı |
|---|---|---|---|
| Batch actions | `--actions="a1;a2"` | Semicolon ile ayrılmış action zinciri çalıştırır, çıkar | ✅ |
| Action dosyası | `--actions-file=PATH` | Satır başına bir action olan dosyadan okur | ✅ |
| Interactive shell | `--shell` | stdin'den komut okur, stdout'a yanıt verir; **stateful** (doküman komutlar arası korunur) | ✅ |
| Pipe (stdin) | `--pipe` | SVG'yi stdin'den okur | ✅ |

### 7.2 Sorgulama (Query)

| Bayrak | Çıktı Formatı | Doğrulandı |
|---|---|---|
| `--query-all` | `id,x,y,width,height` (her nesne bir satır) | ✅ |
| `--query-id=ID1[,ID2]` | Belirtili ID'lere filtreler | ✅ |
| `--query-x` | X koordinatı (tek float) | ✅ |
| `--query-y` | Y koordinatı (tek float) | ✅ |
| `--query-width` | Genişlik (tek float) | ✅ |
| `--query-height` | Yükseklik (tek float) | ✅ |

Doğrulanmış örnek çıktı (`--query-all`):
```
svg1,10,10,80,60
rect1,10,10,30,40
circle1,50,30,40,40
```

### 7.3 Dışa Aktarım (Export)

| Format | Bayrak | stdout'a aktarım (`-`) | Doğrulandı |
|---|---|---|---|
| SVG | `--export-type=svg` | ✅ | ✅ |
| Plain SVG | `--export-type=svg --export-plain-svg` | ✅ | ✅ |
| PNG | `--export-type=png` | ❌ (binary) | ✅ |
| PDF | `--export-type=pdf` | ❌ | ✅ |
| PS/EPS | `--export-type=ps` / `eps` | ❌ | ✅ |
| EMF/WMF/XAML | `--export-type=emf` vb. | ❌ | ✅ |

Ek export seçenekleri: `--export-dpi`, `--export-width`, `--export-height`, `--export-background`, `--export-background-opacity`, `--export-id`, `--export-id-only`, `--export-area`, `--export-area-page`, `--export-area-drawing`, `--export-margin`, `--export-text-to-path`, `--export-pdf-version`, `--export-ps-level`, `--export-png-compression`, `--export-png-antialias`, `--export-png-color-mode`, `--export-overwrite`, `--export-ignore-filters`.

### 7.4 Shell Modu Komut Formatı

Shell modunda komutlar **her satıra bir komut** olacak şekilde stdin'e yazılır. Semicolon ile zincirleme shell modunda kullanılmaz.

```
> file-open:C:/path/to/file.svg
> select:rect1
> object-set-attribute:fill,orange
> query-height
40
> export-filename:C:/path/to/out.svg
> export-type:svg
> export-do
> quit
```

### 7.5 Kritik Davranış Notları

1. **Exit code her zaman 0:** Hata olsa bile. Hata tespiti için stderr parse edilmelidir.
2. **`object-set-attribute` argüman formatı:** `attribute_name,value` — virgülden sonra boşluk yok.
3. **Shell state'i:** `file-open` ile açılan doküman, `quit` yapılana veya başka bir `file-open` çağrılana kadar korunur.
4. **Export sırası:** `export-filename`, `export-type`, `export-do` sırasıyla çağrılmalıdır.
5. **Desteklenen giriş formatları:** SVG, SVGZ, PDF, EPS, PS, AI, CDR, DXF, PNG, JPEG, BMP, TIFF, GIF, WMF, EMF, XAML, VSD, FIG ve daha fazlası (~60 format).

### 7.6 Action Kataloğu (Önemli Olanlar)

| Kategori | Action Adı | Açıklama |
|---|---|---|
| **Dosya** | `file-new`, `file-open`, `file-close`, `file-rebase` | Doküman yönetimi |
| **Seçim** | `select`, `select-all`, `select-clear`, `select-invert` | Nesne seçimi |
| **Sil/Çoğalt** | `delete`, `delete-selection`, `duplicate` | Temel düzenleme |
| **Dönüşüm** | `object-flip-horizontal`, `object-flip-vertical`, `object-rotate-90-cw`, `object-rotate-90-ccw` | Döndürme/çevirme |
| **Hizalama** | `object-align`, `object-distribute`, `object-rearrange` | Hizalama/dağıtım |
| **Öznitelik** | `object-set-attribute`, `object-set-property` | SVG özniteliği atama |
| **Path** | `object-stroke-to-path`, `object-to-path` | Dönüşüm |
| **Clip/Mask** | `object-set-clip`, `object-release-clip`, `object-set-mask`, `object-release-mask` | Kırpma/maskeleme |
| **Grup** | `group`, `ungroup`, `object-set-clip-group` | Gruplama |
| **Klon** | `clone`, `clone-unlink`, `clone-link`, `clone-unlink-recursively` | Klonlama |
| **Export** | `export-filename`, `export-type`, `export-do`, `export-dpi`, `export-width`, `export-height`, `export-area`, `export-background`, `export-background-opacity`, `export-plain-svg`, `export-text-to-path`, `export-overwrite` | Dışa aktarım zinciri |
| **Efektler** | `effect.interpolate`, `effect.voronoi`, `effect.extrude`, `effect.distribute-along-path`, `effect.long-shadow`, `effect.pattern-along-path` | Yerleşik efektler |
| **Filtreler** | `org.inkscape.effect.filter.*` | 100+ SVG filtresi |
| **Bitmap** | `org.inkscape.effect.bitmap.*` | 30+ bitmap efekti |
| **Renk** | `org.inkscape.color.*` | Renk dönüşümleri |
| **Diğer** | `vacuum-defs`, `fit-canvas-to-selection`, `object-trace`, `no-convert-baseline`, `convert-dpi-method` | Yardımcı işlemler |

---

## Ek A: Geliştirme Yol Haritası

### Phase 1 — Çekirdek (MVP)

- [ ] `server.py`: MCP stdio transport, tool/resource/prompt kaydı
- [ ] `session.py`: `InkscapeShellSession` — `inkscape --shell` alt süreç yönetimi
- [ ] `actions.py`: Action zinciri oluşturucu
- [ ] `normalize.py`: CLI çıktısı normalizer
- [ ] `security.py`: Yol doğrulama, boyut limiti, timeout
- [ ] `exceptions.py`: Hata hiyerarşisi + stderr ayrıştırıcı
- [ ] 8 temel tool:
  - `document_open`, `document_create`
  - `shape_rectangle`, `shape_ellipse`, `shape_text`
  - `export_png`, `export_svg`
  - `query_geometry`

### Phase 2 — Tam Tool Seti

- [ ] Path işlemleri (union, difference, stroke-to-path, vb.)
- [ ] Dönüşüm işlemleri (translate, scale, rotate, skew, flip)
- [ ] Hizalama/dağıtım (align, distribute, remove-overlaps)
- [ ] Renk/stil (fill, stroke, opacity, filter)
- [ ] Gruplama, katman, klon yönetimi
- [ ] Tüm export formatları (PDF, EPS, PS, EMF, WMF, XAML)

### Phase 3 — Resource ve Prompt

- [ ] 5 resource (`current-svg`, `selection`, `geometry`, `actions`, `document-info`)
- [ ] 5 prompt (`create-logo`, `create-diagram`, `trace-bitmap`, `batch-export`, `svg-optimize`)

### Phase 4 — Test ve Dokümantasyon

- [ ] ≥%80 birim test kapsamı
- [ ] Entegrasyon test paketi
- [ ] E2E testleri
- [ ] Claude Desktop için örnek konfigürasyon

---

## Lisans

MIT License

---

*Son güncelleme: 2026-05-29 — Inkscape 1.4.2 (f4327f4), MCP Python SDK*
