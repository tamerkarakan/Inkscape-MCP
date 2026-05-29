# Inkscape MCP Server

> **Model Context Protocol (MCP)** sunucusu olarak Inkscape — Yapay zeka asistanlarının Inkscape ile SVG üretmesi, düzenlemesi ve dışa aktarması için köprü.

---

## İçindekiler

1. [Proje Vizyonu](#1-proje-vizyonu)
2. [Hedef Inkscape Sürümü ve Yetenekleri](#2-hedef-inkscape-sürümü-ve-yetenekleri)
3. [Dil Seçimi ve Gerekçesi](#3-dil-seçimi-ve-gerekçesi)
4. [Mimari Tasarım](#4-mimari-tasarım)
5. [MCP Araç (Tool) Katalogu](#5-mcp-araç-tool-katalogu)
6. [MCP Resource ve Prompt Tasarımı](#6-mcp-resource-ve-prompt-tasarımı)
7. [Transport Katmanı](#7-transport-katmanı)
8. [Güvenlik Tasarımı](#8-güvenlik-tasarımı)
9. [Test Mimarisi](#9-test-mimarisi)
10. [Geliştirme Yol Haritası](#10-geliştirme-yol-haritası)
11. [Alternatif Tasarım Kararları ve Risk Analizi](#11-alternatif-tasarım-kararları-ve-risk-analizi)

---

## 1. Proje Vizyonu

**Amaç:** Yapay zeka asistanlarının (Claude, ChatGPT, vs.) bir MCP sunucusu aracılığıyla Inkscape'i tam yetkinlikle kullanabilmesini sağlamak.

**Kapsam:**
- SVG dokümanı oluşturma (yeni belge, template tabanlı)
- Mevcut SVG'leri açma, düzenleme, kaydetme
- Şekil, path, metin, grup, katman işlemleri
- Dönüşüm (transform), hizalama (align), dağıtım (distribute)
- Renk, dolgu (fill), kontur (stroke), filtre, LPE işlemleri
- PNG/SVG/PDF/EPS/PS/EMF/WMF/XAML dışa aktarım
- Import formatları: EPS, Postscript, JPEG, PNG, BMP, TIFF, PDF
- Nesne sorgulama (bounding box, geometri)
- Uzantı (extension) yönetimi ve çalıştırma
- Seçim / seçim temizleme yönetimi

**Non-goals (ilk sürümde kapsam dışı):**
- Gerçek zamanlı fare/klavye simülasyonu
- Inkscape GUI'sinin uzaktan kontrolü (--with-gui olmadan batch mod yeterli)
- Inkscape eklenti yazma/geliştirme

---

## 2. Hedef Inkscape Sürümü ve Yetenekleri

| Özellik | Detay |
|---|---|
| **Sürüm** | Inkscape 1.4.2 (f4327f4, 2025-05-13) |
| **Dağıtım** | Portable (Windows x64) |
| **Python** | 3.12.9 (gömülü) |
| **CLI Arayüzü** | `inkscape.com` (Windows) / `inkscape` (Linux) |
| **Batch Mod** | `--batch-process` — GUI'yi işlem sonunda kapatır |
| **Actions** | 1072 adet `--actions` ile çağrılabilir komut |
| **Action Chain** | `--actions="action1;action2;action3"` ile zincirleme |
| **Action File** | `--actions-file=FILENAME` ile dosyadan okuma |
| **Pipe** | `--pipe` ile stdin'den SVG okuma |
| **Export** | `-o` / `--export-filename` ile 9 formata dışa aktarım |
| **Query** | `--query-id` / `--query-all` / `-X -Y -W -H` bayrakları |
| **Extension API** | `inkex` kütüphanesi (Python), 353 eklenti |

---

## 3. Dil Seçimi ve Gerekçesi

### 3.1 Aday Diller

| Dil | MCP SDK | Inkscape Entegrasyonu | Tip Güvenliği | Platform |
|---|---|---|---|---|
| **TypeScript / Node.js** | `@modelcontextprotocol/sdk` (v1.29.0) | CLI subprocess (stdin/stdout) | ✅ Güçlü | ✅ Çapraz |
| **Python** | `mcp` (resmi Python SDK) | CLI subprocess + `inkex` doğrudan import | Orta (type hints) | ✅ Çapraz |
| **Go** | `mcp-go` (topluluk) | CLI subprocess | ✅ Güçlü | ✅ Çapraz (derleme) |
| **Rust** | `mcp-rs` (topluluk) | CLI subprocess | ✅ Güçlü | ✅ Çapraz (derleme) |

### 3.2 Önerilen: Python (Birincil) + TypeScript (Yedek Strateji)

**Python'un seçilme gerekçeleri:**

1. **Doğrudan `inkex` entegrasyonu:** Inkscape'in 353 uzantısının yazıldığı `inkex` kütüphanesi, MCP sunucusu içinde `PYTHONPATH` ayarlanarak doğrudan kullanılabilir. Bu sayede:
   - SVG parse/manipülasyonu için `inkex.elements` doğrudan kullanılır
   - Uzantıları alt süreç açmadan (in-process) çalıştırma imkanı
   - `inkex.command` ile Inkscape CLI'sine yapılandırılmış çağrı

2. **Ek sistem bağımlılığı yok:** Inkscape zaten Python 3.12.9 ile geliyor. MCP sunucusu da Python ile yazılırsa, `pip install mcp` dışında bağımlılık olmaz.

3. **SVG domain bilgisi:** Python'un `lxml`, `xml.etree` gibi kütüphaneleri SVG manipülasyonu için idealdir.

4. **Resmi MCP Python SDK:** `mcp` paketi, `@modelcontextprotocol/sdk` ile aynı protokol uyumluluğunu sağlar.

**Ne zaman TypeScript'e geçilir:**
- MCP Python SDK'da kritik bug / protokol uyumsuzluğu bulunursa
- stdio transport performansı Python'da yetersiz kalırsa
- Streaming HTTP transport (SSE) gereksinimi ağır basarsa

### 3.3 Çalışma Zamanı Yapılandırması

```
inkscape_mcp/
├── pyproject.toml          # Python proje tanımı, bağımlılıklar
├── src/
│   └── inkscape_mcp/
│       ├── __init__.py
│       ├── server.py        # MCP Server ana giriş noktası
│       ├── inkscape_cli.py  # Inkscape CLI subprocess yönetimi
│       ├── svg_tools.py     # inkex tabanlı SVG manipülasyonu
│       ├── resources.py     # MCP Resource tanımları
│       └── prompts.py       # MCP Prompt tanımları
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/            # Test SVG dosyaları
└── README.md
```

---

## 4. Mimari Tasarım

### 4.1 Katmanlı Mimari

```
┌─────────────────────────────────────────────────────────┐
│                     MCP Client (AI)                     │
│              (Claude Desktop / CLI / IDE)               │
└─────────────────┬───────────────────────────────────────┘
                  │  JSON-RPC 2.0 (stdio / HTTP SSE)
┌─────────────────▼───────────────────────────────────────┐
│                  MCP Protocol Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Tool Router │  │  Resource    │  │    Prompt     │  │
│  │  (tools/)    │  │  Provider    │  │   Provider    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘  │
│         │                 │                  │           │
│  ┌──────▼─────────────────▼──────────────────▼────────┐  │
│  │              Command Translation Layer             │  │
│  │  ┌────────────────┐  ┌──────────────────────────┐  │  │
│  │  │  Action Builder │  │   Response Normalizer    │  │  │
│  │  │  (arg → --action)│  │  (stdout → typed object) │  │  │
│  │  └───────┬─────────┘  └──────────┬───────────────┘  │  │
│  └──────────┼───────────────────────┼──────────────────┘  │
└─────────────┼───────────────────────┼─────────────────────┘
              │                       │
┌─────────────▼───────────────────────▼─────────────────────┐
│                 Inkscape Interface Layer                   │
│  ┌──────────────────┐  ┌──────────────────────────────┐   │
│  │  CLI Subprocess   │  │    inkex Library (in-proc)  │   │
│  │  (inkscape.com)   │  │    SVG parse / manipulate   │   │
│  │  --batch-process  │  │    Extension runner          │   │
│  └──────────────────┘  └──────────────────────────────┘   │
└───────────────────────────────────────────────────────────┘
```

### 4.2 Katman Açıklamaları

#### Layer 1: MCP Protocol Layer
- **Tool Router:** Her MCP tool çağrısını uygun handler'a yönlendirir
- **Resource Provider:** Geçerli SVG dokümanı, aktif seçim, katman listesi gibi kaynakları `inkx://` URI şeması ile sunar
- **Prompt Provider:** "Logo oluştur", "Diyagram çiz" gibi yaygın iş akışları için şablon prompt'lar

#### Layer 2: Command Translation Layer
- **Action Builder:** Doğal parametreleri Inkscape `--actions` zincirine çevirir
  - Örn: `create_rectangle(x=10, y=20, w=100, h=50)` → `tool-rect;transform-translate:10,20;transform-scale:100,50`
- **Response Normalizer:** Inkscape CLI'nin ham çıktılarını yapılandırılmış JSON'a çevirir
  - Örn: `--query-all` SVG bounding box çıktısını `[{id, x, y, w, h}]` formatına dönüştürür

#### Layer 3: Inkscape Interface Layer
- **CLI Subprocess Modu (Birincil):** 1072 action'ın tümünü `--batch-process` ile kapsar
- **inkex Modu (İkincil):** SVG parse, element manipülasyonu, uzantı çalıştırma için `PYTHONPATH` ile Inkscape'in Python'una erişir

### 4.3 Veri Akışı (Örnek: Dikdörtgen oluştur ve PNG dışa aktar)

```
AI: "create a red rectangle and export as PNG"
  │
  ▼
MCP Tool Call: inkscape_create_rectangle(width=200, height=100, fill="#FF0000")
  │
  ▼
Action Builder:
  actions = "tool-rect;transform-scale:200,100;object-set-attribute:fill,#FF0000"
  │
  ▼
CLI Subprocess:
  inkscape.com --batch-process --actions="...;export-filename:output.png;export-do"
  │
  ▼
Response Normalizer:
  { "status": "success", "output_file": "output.png", "dimensions": "200x100" }
  │
  ▼
AI receives structured response
```

### 4.4 Session (Oturum) Yönetimi

Her MCP bağlantısı için stateful bir session yönetilir:

```python
@dataclass
class InkscapeSession:
    session_id: str
    working_dir: Path          # Geçici çalışma dizini
    current_svg: Path | None   # Aktif SVG dosyası
    selection: list[str]       # Seçili nesne ID'leri
    clipboard: Path            # Session panosu (geçici SVG)
    export_history: list[Path] # Dışa aktarım geçmişi
    created_at: float
    last_access: float
```

Session başına bir `--app-id-tag` ile izole Inkscape örneği çalıştırılır, böylece aynı anda birden fazla AI oturumu birbirini etkilemez.

### 4.5 Hata Yönetimi Stratejisi

```
InkscapeError (base)
├── InkscapeNotFoundError     # inkscape.com bulunamadı
├── InkscapeTimeoutError      # İşlem zaman aşımı (default: 30s)
├── InkscapeActionError       # Geçersiz action / argüman
├── InkscapeExportError       # Dışa aktarım başarısız
├── InkscapeParseError        # SVG parse hatası
└── InkscapeSessionError      # Oturum durumu hatası
```

Tüm hatalar MCP `isError: true` olarak AI'ya iletilir, hata mesajı düzeltici eylem önerisi içerir.

---

## 5. MCP Araç (Tool) Katalogu

### 5.1 Doküman İşlemleri

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `document_create` | `template: str?` | Yeni SVG dokümanı oluştur |
| `document_open` | `file_path: str` | Mevcut SVG'yi aç |
| `document_save` | `file_path: str?` | SVG olarak kaydet |
| `document_save_as` | `file_path: str, format: str` | Belirtilen formatta kaydet |
| `document_close` | — | Dokümanı kapat |
| `document_info` | — | Doküman meta bilgileri (boyut, DPI, katman sayısı) |

### 5.2 Temel Şekil Oluşturma

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `shape_rectangle` | `x, y, width, height, rx?, ry?, fill?, stroke?, stroke_width?` | Dikdörtgen |
| `shape_ellipse` | `cx, cy, rx, ry, fill?, stroke?, stroke_width?` | Elips / Daire |
| `shape_polygon` | `points: [{x, y}], fill?, stroke?, stroke_width?` | Çokgen |
| `shape_star` | `cx, cy, corners, spoke_ratio, rounded?, fill?` | Yıldız |
| `shape_spiral` | `cx, cy, turns, divergence, inner_radius?` | Spiral |
| `shape_line` | `x1, y1, x2, y2, stroke?, stroke_width?` | Çizgi |
| `shape_text` | `x, y, text: str, font_family?, font_size?, fill?` | Metin |

### 5.3 Path (Yol) İşlemleri

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `path_create` | `d: str, fill?, stroke?, stroke_width?` | SVG path verisiyle path oluştur |
| `path_union` | `object_ids: [str]` | Seçili path'leri birleştir |
| `path_difference` | `object_ids: [str]` | Path farkı al |
| `path_intersection` | `object_ids: [str]` | Path kesişimi al |
| `path_exclusion` | `object_ids: [str]` | Path dışlama (XOR) |
| `path_division` | `object_ids: [str]` | Path bölme |
| `path_simplify` | `object_id: str, threshold?` | Path noktalarını azalt |
| `path_reverse` | `object_id: str` | Path yönünü ters çevir |
| `path_stroke_to_path` | `object_id: str` | Konturu path'e çevir |
| `path_inset` | `object_id: str, distance: float` | Path'i içe/içe daralt |
| `path_outset` | `object_id: str, distance: float` | Path'i dışa genişlet |

### 5.4 Seçim ve Gezinme

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `selection_set` | `object_ids: [str]` | Belirtilen nesneleri seç |
| `selection_add` | `object_ids: [str]` | Seçime ekle |
| `selection_remove` | `object_ids: [str]` | Seçimden çıkar |
| `selection_clear` | — | Seçimi temizle |
| `selection_all` | `mode: str` | Tümünü seç (all/layers/no-layers/groups/no-groups) |
| `selection_invert` | — | Seçimi ters çevir |
| `selection_by_class` | `class_name: str` | CSS sınıfına göre seç |
| `selection_by_selector` | `selector: str` | CSS seçici ile seç |
| `selection_by_element` | `element: str` | SVG elementi türüne göre seç (rect, circle, path…) |

### 5.5 Dönüşüm (Transform)

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `transform_translate` | `dx: float, dy: float, object_ids?` | Öteleme |
| `transform_scale` | `sx: float, sy: float?, object_ids?` | Ölçekleme |
| `transform_rotate` | `degrees: float, cx?, cy?, object_ids?` | Döndürme |
| `transform_skew_x` | `degrees: float, object_ids?` | X ekseninde eğme |
| `transform_skew_y` | `degrees: float, object_ids?` | Y ekseninde eğme |
| `transform_flip_horizontal` | `object_ids?` | Yatay çevir |
| `transform_flip_vertical` | `object_ids?` | Dikey çevir |
| `transform_remove` | `object_ids?` | Tüm dönüşümleri kaldır |
| `transform_matrix` | `a, b, c, d, e, f: float, object_ids?` | Afin matris uygula |

### 5.6 Hizalama ve Dağıtım

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `align_objects` | `horizontal: str?, vertical: str?, relative_to: str?` | Nesneleri hizala |
| `distribute_objects` | `mode: str` | Nesneleri dağıt |
| `arrange_objects` | `mode: str` | Yeniden düzenle (grid, exchange, randomize, unclump) |
| `remove_overlaps` | `h_gap: float, v_gap: float` | Örtüşmeleri kaldır |

### 5.7 Z-Sıralaması ve Gruplama

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `object_raise` | `object_ids?` | Bir adım yukarı |
| `object_lower` | `object_ids?` | Bir adım aşağı |
| `object_raise_to_top` | `object_ids?` | En üste taşı |
| `object_lower_to_bottom` | `object_ids?` | En alta taşı |
| `group_create` | `object_ids?` | Seçili nesneleri grupla |
| `group_ungroup` | `object_ids?` | Grubu çöz |
| `group_ungroup_pop` | `object_ids?` | Gruptan çıkar |

### 5.8 Renk ve Stil

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `style_set_fill` | `color: str, opacity?, object_ids?` | Dolgu rengi ata |
| `style_set_stroke` | `color: str, width?, opacity?, object_ids?` | Kontur rengi/kalınlığı ata |
| `style_set_opacity` | `opacity: float, object_ids?` | Opaklık ata |
| `style_remove_fill` | `object_ids?` | Dolguyu kaldır |
| `style_remove_stroke` | `object_ids?` | Konturu kaldır |
| `style_swap_fill_stroke` | `object_ids?` | Dolgu/Kontur değiştir |
| `style_set_attribute` | `attribute: str, value: str, object_ids?` | SVG özniteliği ata |
| `style_remove_filter` | `object_ids?` | Filtreyi kaldır |

### 5.9 Metin İşlemleri

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `text_set_content` | `text: str, object_id: str` | Metin içeriğini değiştir |
| `text_set_font` | `font_family: str, font_size?, object_id?` | Font ailesi/boyutu |
| `text_align` | `alignment: str, object_ids?` | Metin hizalama (left/center/right/justify) |
| `text_put_on_path` | `text_id: str, path_id: str` | Metni path'e yerleştir |
| `text_remove_from_path` | `text_id: str` | Metni path'den çıkar |
| `text_flow_into_frame` | `text_id: str, frame_id: str` | Metni çerçeveye akıt |
| `text_convert_to_path` | `text_id: str` | Metni path'e dönüştür |

### 5.10 Katman İşlemleri

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `layer_create` | `name: str, position?` | Yeni katman oluştur |
| `layer_delete` | `layer_id: str` | Katmanı sil |
| `layer_rename` | `layer_id: str, name: str` | Katmanı yeniden adlandır |
| `layer_move_to` | `object_ids: [str], layer_id: str` | Nesneleri katmana taşı |
| `layer_set_visible` | `layer_id: str, visible: bool` | Görünürlük |
| `layer_set_locked` | `layer_id: str, locked: bool` | Kilitleme |
| `layer_list` | — | Katman listesini döndür |

### 5.11 Klon ve Sembol İşlemleri

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `clone_create` | `object_id: str` | Klon oluştur |
| `clone_unlink` | `clone_id: str` | Klon bağını kopar |
| `clone_relink` | `clone_id: str` | Klonu panodakine yeniden bağla |
| `clone_select_original` | `clone_id: str` | Orijinal nesneyi seç |

### 5.12 Dışa Aktarım (Export)

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `export_png` | `output_path: str, width?, height?, dpi?, area_mode?, object_ids?, background?` | PNG dışa aktar |
| `export_svg` | `output_path: str, plain_svg?, object_ids?` | SVG dışa aktar |
| `export_pdf` | `output_path: str, text_to_path?, pdf_version?, object_ids?` | PDF dışa aktar |
| `export_eps` | `output_path: str, text_to_path?, ps_level?, object_ids?` | EPS dışa aktar |
| `export_batch` | `exports: [{format, output_path, options}]` | Toplu dışa aktarım |

### 5.13 Sorgulama (Query)

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `query_geometry` | `object_ids: [str]?` | Nesne geometrisi (x, y, w, h) |
| `query_all_geometry` | — | Tüm nesnelerin geometrisi |
| `query_selection` | — | Seçili nesnelerin listesi |
| `query_document_size` | — | Sayfa boyutu (width, height, unit) |
| `query_style` | `object_id: str` | Nesne stil bilgisi (fill, stroke, opacity…) |

### 5.14 Uzantı Çalıştırma

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `extension_list` | — | Mevcut uzantıları listele |
| `extension_run` | `extension_id: str, params: dict?` | Uzantıyı çalıştır |
| `extension_info` | `extension_id: str` | Uzantı hakkında bilgi |

### 5.15 Yardımcı Araçlar

| Tool Adı | Parametreler | Açıklama |
|---|---|---|
| `clipboard_copy` | `object_ids?: [str]` | Panoya kopyala |
| `clipboard_paste` | `x?, y?` | Panodan yapıştır |
| `object_delete` | `object_ids?: [str]` | Nesneleri sil |
| `object_duplicate` | `object_ids?: [str]` | Nesneleri çoğalt |
| `object_lock` | `object_ids?: [str]` | Nesneleri kilitle |
| `object_unlock` | `object_ids?: [str]` | Nesne kilitlerini aç |
| `object_hide` | `object_ids?: [str]` | Nesneleri gizle |
| `object_unhide` | `object_ids?: [str]` | Gizli nesneleri göster |
| `undo` | — | Geri al |
| `redo` | — | İleri al |
| `canvas_fit_to_selection` | — | Sayfayı seçime sığdır |
| `vacuum_defs` | — | Kullanılmayan defs'leri temizle |
| `snap_inspect` | `x: float, y: float` | Grid/snap bilgisi sorgula |

---

## 6. MCP Resource ve Prompt Tasarımı

### 6.1 Resources

MCP Resources, mevcut Inkscape durumunu AI'ya salt-okunur olarak sunar:

| URI Şeması | MIME Type | Açıklama |
|---|---|---|
| `inkscape://session/current-svg` | `image/svg+xml` | Aktif SVG dokümanı (ham XML) |
| `inkscape://session/selection` | `application/json` | Seçili nesne listesi |
| `inkscape://session/layers` | `application/json` | Katman hiyerarşisi |
| `inkscape://session/document-info` | `application/json` | Doküman meta verisi |
| `inkscape://session/action-list` | `application/json` | Kullanılabilir action'lar listesi |
| `inkscape://session/extension-list` | `application/json` | Kullanılabilir uzantılar |
| `inkscape://session/clipboard-preview` | `image/png` | Pano içeriğinin PNG önizlemesi |

### 6.2 Prompts

Hazır prompt şablonları, AI'ların yaygın iş akışlarını hızlıca başlatmasını sağlar:

| Prompt Adı | Açıklama |
|---|---|
| `create-logo` | Logo tasarımı için adım adım Inkscape komutları |
| `create-diagram` | Diyagram/akış şeması oluşturma |
| `create-infographic` | Bilgi grafiği tasarımı |
| `trace-bitmap` | Bitmap izleme (trace) iş akışı |
| `batch-export` | Toplu dışa aktarım iş akışı |
| `svg-optimize` | SVG temizleme ve optimizasyon |
| `create-icon-set` | İkon seti oluşturma |

---

## 7. Transport Katmanı

### 7.1 Desteklenen Transport Yöntemleri

| Transport | Kullanım Alanı | Durum |
|---|---|---|
| **stdio** | Claude Desktop, CLI testleri | ✅ Birincil |
| **HTTP + SSE** | Uzak sunucu, web IDE entegrasyonu | 🔄 Planlanan |
| **Streamable HTTP** | MCP 2025 spesifikasyonu | 🔄 Planlanan |

### 7.2 stdio Transport (Birincil)

```json
{
  "mcpServers": {
    "inkscape": {
      "command": "python",
      "args": ["-m", "inkscape_mcp.server"],
      "env": {
        "INKSCAPE_PATH": "E:/Downloads/zip/inkscape-1.4.2_2025-05-13_f4327f4-x64/inkscape/bin/inkscape.com",
        "INKSCAPE_PYTHONPATH": "E:/Downloads/zip/inkscape-1.4.2_2025-05-13_f4327f4-x64/inkscape/share/inkscape/extensions",
        "INKSCAPE_TIMEOUT": "30"
      }
    }
  }
}
```

### 7.3 Process Yaşam Döngüsü

```
[MCP Client] ──start──▶ [Python MCP Server] ──spawn──▶ [inkscape.com --app-id-tag=mcp-{id}]
     │                        │                                  │
     │  initialize            │                                  │
     │◄───────────────────────│                                  │
     │  tools/list            │                                  │
     │◄───────────────────────│                                  │
     │  tools/call            │                                  │
     │──────────────────────▶ │──actions="..."─────────────────▶│
     │                        │◄────stdout/stderr───────────────│
     │◄──── result ──────────│                                  │
     │                        │                                  │
     │  [shutdown]            │──SIGTERM───────────────────────▶│
```

---

## 8. Güvenlik Tasarımı

### 8.1 Tehdit Modeli

| Tehdit | Risk Seviyesi | Önlem |
|---|---|---|
| AI keyfi dosya yazma/okuma | 🔴 Yüksek | `--allowed-dirs` ile çalışma dizini kısıtlaması |
| Komut enjeksiyonu | 🔴 Yüksek | Action parametrelerinde sıkı validasyon, shell=True kullanılmaması |
| AI sistem komutu çalıştırma | 🔴 Yüksek | Inkscape CLI argümanlarına beyaz liste kontrolü |
| Kaynak tüketimi (DoS) | 🟡 Orta | 30s timeout, maksimum 50MB SVG boyutu |
| Oturumlar arası veri sızıntısı | 🟡 Orta | `--app-id-tag` ile izolasyon, temp dizin temizliği |
| Hassas bilgi sızdırma | 🟢 Düşük | AI'nın okuyabileceği dosyalar sadece çalışma dizininde |

### 8.2 Sandbox Modeli

```python
# config.py
@dataclass
class SecurityConfig:
    allowed_directories: list[Path]       # Sadece bu dizinlerde okuma/yazma
    max_svg_size_bytes: int = 52_428_800  # 50 MB
    max_export_size_bytes: int = 104_857_600  # 100 MB
    command_timeout_seconds: int = 30
    allow_shell_commands: bool = False    # Kesinlikle False
    allowed_export_formats: list[str] = field(default_factory=lambda: [
        "svg", "png", "pdf", "eps", "ps", "emf", "wmf", "xaml"
    ])
    session_max_count: int = 5
    session_ttl_seconds: int = 3600       # 1 saat
```

---

## 9. Test Mimarisi

### 9.1 Test Piramidi

```
           ┌─────────┐
           │  E2E    │  ~%10  — Gerçek Inkscape ile uçtan uca
           │  Tests  │
          ┌┴─────────┴┐
          │Integration│  ~%30  — MCP protokol + CLI mock
          │   Tests   │
         ┌┴───────────┴┐
         │  Unit Tests  │  ~%60  — Action builder, response normalizer
         └──────────────┘
```

### 9.2 Test Katmanları

#### 9.2.1 Birim Testleri (Unit)

- **Kapsam:** `ActionBuilder`, `ResponseNormalizer`, `SecurityConfig`, `InkscapeSession`
- **Framework:** `pytest` + `pytest-cov`
- **Mock:** Inkscape CLI çağrıları mock'lanır
- **Hedef:** ≥%80 satır kapsamı

```python
# tests/unit/test_action_builder.py
def test_build_rectangle_action():
    builder = ActionBuilder()
    result = builder.create_rectangle(x=10, y=20, width=100, height=50, fill="#FF0000")
    assert "tool-rect" in result
    assert "transform-translate:10,20" in result
    assert "object-set-attribute:fill,#FF0000" in result

def test_build_invalid_color_raises():
    builder = ActionBuilder()
    with pytest.raises(ValidationError, match="Invalid color"):
        builder.create_rectangle(x=0, y=0, width=10, height=10, fill="not-a-color")
```

#### 9.2.2 Entegrasyon Testleri (Integration)

- **Kapsam:** MCP araç çağrısı → Action Builder → mock CLI → Response Normalizer zinciri
- **Framework:** `pytest` + `pytest-asyncio`
- **Mock:** Inkscape subprocess çıktısı mock'lanır, MCP transport'ı test edilir

```python
# tests/integration/test_mcp_tools.py
@pytest.mark.asyncio
async def test_create_rectangle_tool(mcp_test_client):
    """Bir rectangle tool çağrısının tüm katmanlardan geçişi."""
    response = await mcp_test_client.call_tool("shape_rectangle", {
        "x": 10, "y": 20, "width": 100, "height": 50
    })
    assert response["status"] == "success"
    assert "object_id" in response

@pytest.mark.asyncio
async def test_tool_error_propagation(mcp_test_client):
    """Hata durumunda isError dönüşü."""
    response = await mcp_test_client.call_tool("export_png", {
        "output_path": "/invalid/path.png"
    })
    assert response["isError"] is True
```

#### 9.2.3 Uçtan Uca Testler (E2E)

- **Kapsam:** Gerçek Inkscape süreci ile tam zincir testi
- **Framework:** `pytest` + gerçek Inkscape CLI
- **Ortam:** `INKSCAPE_E2E=1` ortam değişkeni ile etkinleştirilir, CI'da opsiyonel

```python
# tests/e2e/test_real_inkscape.py
@pytest.mark.e2e
@pytest.mark.skipif(not os.environ.get("INKSCAPE_E2E"), reason="E2E tests require Inkscape")
class TestRealInkscape:
    def test_create_rectangle_and_export_png(self, tmp_path):
        """Gerçek Inkscape ile dikdörtgen oluştur ve PNG çıkar."""
        server = InkscapeMCPServer(inkscape_path=INKSCAPE_PATH)
        result = server.execute_tool("shape_rectangle", {
            "x": 10, "y": 20, "width": 100, "height": 50, "fill": "#FF0000"
        })
        export = server.execute_tool("export_png", {
            "output_path": str(tmp_path / "output.png"), "width": 200
        })
        assert Path(export["output_path"]).exists()
        assert Path(export["output_path"]).stat().st_size > 0
```

### 9.3 Test Fixtures

```
tests/fixtures/
├── empty.svg                    # Boş SVG dokümanı
├── basic_shapes.svg             # Temel şekiller
├── complex_scene.svg            # Katmanlı, gruplu, klonlu sahne
├── text_samples.svg             # Çeşitli metin örnekleri
├── paths_collection.svg         # Path operasyonları için test verisi
├── large_document.svg           # Performans testi (>1000 nesne)
└── malformed/                   # Hata durumu testleri
    ├── invalid_xml.svg
    ├── missing_namespace.svg
    └── corrupted.svg
```

### 9.4 CI/CD Test Matrisi

| Ortam | Python | Inkscape | Test Seviyesi |
|---|---|---|---|
| Ubuntu 24.04 | 3.12 | 1.4 (apt) | Unit + Integration + E2E |
| Windows 11 | 3.12 (gömülü) | 1.4.2 (portable) | Unit + Integration + E2E |
| macOS 14 | 3.12 | 1.4 (Homebrew) | Unit + Integration |

### 9.5 Performans Testleri

```python
# tests/performance/test_benchmarks.py
def test_large_document_query_benchmark(benchmark, large_svg_session):
    """1000+ nesneli dokümanda query_all_geometry performansı."""
    result = benchmark(large_svg_session.query_all_geometry)
    assert len(result) > 1000
    # Benchmark threshold: < 2 seconds

def test_concurrent_session_isolation():
    """5 eşzamanlı session'ın birbirini etkilemediğini doğrula."""
    ...
```

---

## 10. Geliştirme Yol Haritası

### Phase 0 — Altyapı Kurulumu (Week 1)

- [x] Proje dizini oluşturma
- [ ] `pyproject.toml` ile proje iskeleti
- [ ] `pytest`, `ruff`, `mypy` geliştirme araçları
- [ ] Git repo ve `.gitignore`
- [ ] CI pipeline (GitHub Actions)

### Phase 1 — Çekirdek MCP Sunucusu (Week 2–3)

- [ ] `server.py`: MCP Python SDK ile stdio transport
- [ ] `inkscape_cli.py`: Inkscape CLI subprocess yönetimi
- [ ] `ActionBuilder`: Parametrik araç → Inkscape action zinciri dönüşümü
- [ ] `ResponseNormalizer`: Ham CLI çıktısı → JSON dönüşümü
- [ ] `SecurityConfig` ve temel validasyon
- [ ] `InkscapeSession` yönetimi
- [ ] 5 temel tool ile MVP:
  - `document_create`
  - `shape_rectangle`
  - `shape_text`
  - `export_png`
  - `query_geometry`

### Phase 2 — Tam Araç Seti (Week 4–5)

- [ ] Doküman işlemleri (6 araç)
- [ ] Temel şekiller (7 araç)
- [ ] Path işlemleri (11 araç)
- [ ] Seçim ve gezinme (9 araç)
- [ ] Dönüşüm (9 araç)
- [ ] Hizalama/dağıtım (4 araç)
- [ ] Z-sıralaması/gruplama (6 araç)
- [ ] Renk/stil (8 araç)
- [ ] Metin (7 araç)
- [ ] Katman (7 araç)
- [ ] Klon/sembol (4 araç)
- [ ] Dışa aktarım (5 araç)
- [ ] Sorgulama (5 araç)
- [ ] Uzantı (3 araç)
- [ ] Yardımcı (14 araç)

### Phase 3 — Resource & Prompt Desteği (Week 6)

- [ ] Resource provider (7 resource)
- [ ] Prompt provider (7 prompt)
- [ ] `inkx://` URI şeması implementasyonu
- [ ] SVG dokümanı stream etme desteği

### Phase 4 — Test ve Dokümantasyon (Week 7–8)

- [ ] ≥%80 birim test kapsamı
- [ ] Entegrasyon test paketi
- [ ] E2E testleri (CI'da opsiyonel)
- [ ] Performans benchmark'ları
- [ ] API dokümantasyonu (her tool için)
- [ ] Kullanım örnekleri (örnek prompt zincirleri)

### Phase 5 — Gelişmiş Özellikler (Week 9+)

- [ ] HTTP + SSE transport desteği
- [ ] `inkex` kütüphanesi ile in-process SVG manipülasyonu
- [ ] Streaming export (büyük dosyalar için chunk'lanmış çıktı)
- [ ] Paralel session desteği (çoklu AI oturumu)
- [ ] Inkscape eklenti geliştirme araçları (MCP üzerinden `.inx` oluşturma)
- [ ] Claude Desktop için hazır konfigürasyon paketi
- [ ] Docker imajı (CI/CD ortamlarında kullanım için)

---

## 11. Alternatif Tasarım Kararları ve Risk Analizi

### 11.1 Alternatif: Sıfırdan SVG Manipülasyonu

**Yaklaşım:** Inkscape CLI'sini hiç kullanmadan, tamamen `lxml` / `cairosvg` ile SVG üretmek.

| Avantaj | Dezavantaj |
|---|---|
| Inkscape bağımlılığı yok | Inkscape'in tüm özelliklerini yeniden implemente etmek gerekir |
| Daha hızlı (subprocess yok) | Path operasyonları, Boolean, LPE gibi karmaşık işlemler yok |
| Daha taşınabilir | Inkscape'e özgü SVG uzantıları kaybolur |

**Karar:** Bu yaklaşım REDDEDİLDİ. Inkscape MCP'nin değer teklifi, Inkscape'in 1072 action'lık yetkinliğini sunmaktır.

### 11.2 Alternatif: D-Bus / IPC Üzerinden Inkscape Kontrolü

**Yaklaşım:** Inkscape'i D-Bus (Linux) veya COM (Windows) üzerinden süreçler arası kontrol etmek.

| Avantaj | Dezavantaj |
|---|---|
| Durum bilgisi korunur | Inkscape GUI modunda çalışmalı (`--with-gui`) |
| Daha az subprocess spawn | Platform bağımlı (D-Bus sadece Linux) |
| Gerçek zamanlı event'ler | Karmaşık kurulum, hata ayıklama zor |

**Karar:** Birincil yöntem CLI subprocess olarak kaldı. D-Bus, Phase 5'te Linux'a özel bir hızlandırma olarak değerlendirilebilir.

### 11.3 Alternatif: TypeScript Birincil Dil

**Yaklaşım:** TypeScript/Node.js ile yazılmış MCP sunucusu.

**Neden Python seçildi:**
- `inkex` kütüphanesine doğrudan erişim (TypeScript'te bu imkansız)
- Inkscape ile aynı Python ekosistemi (353 uzantı Python ile yazılmış)
- Tek bir `pip install` ile kurulum (Node.js + npm ayrıca gerekmez)

**Geçiş stratejisi:** Eğer Python MCP SDK'da kritik sorunlar çıkarsa, TypeScript fallback olarak `src-ts/` dizininde paralel geliştirilebilir.

### 11.4 Risk Matrisi

| Risk | Olasılık | Etki | Azaltma |
|---|---|---|---|
| Inkscape CLI çıktı formatı değişikliği | Orta | Orta | Response normalizer'da sürüm algılama, snapshot testleri |
| MCP Python SDK breaking change | Düşük | Yüksek | Bağımlılık sabitleme (`==X.Y.Z`), TS fallback |
| Windows/Linux CLI farklılıkları | Orta | Orta | CI'da çift-platform test, abstraction layer |
| Inkscape `--batch-process` performans sorunu | Düşük | Orta | Action zincirlerini optimize etme, `--actions-file` kullanımı |
| Büyük SVG'lerde bellek tükenmesi | Düşük | Yüksek | Boyut limiti (50MB), streaming parse |

---

## Ek A: Inkscape CLI Hızlı Referans

```bash
# Temel kullanım
inkscape.com --batch-process --actions="action1;action2" input.svg -o output.png

# Yeni belge oluşturma
inkscape.com --batch-process --actions="file-new" -o output.svg

# Dikdörtgen oluşturma ve dışa aktarma
inkscape.com --batch-process --actions="tool-rect;export-filename:out.png;export-do"

# Nesne sorgulama
inkscape.com --query-all input.svg
# Çıktı: rect1,10,20,100,50  (id,x,y,w,h)

# Action zinciri örneği
inkscape.com input.svg --batch-process \
  --actions="select-by-id:rect1;transform-rotate:45;export-filename:out.png;export-do"
```

## Ek B: MCP Protokol Mesaj Örnekleri

### Tool Listesi Yanıtı (kısaltılmış)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "shape_rectangle",
        "description": "Create a rectangle shape in the current SVG document",
        "inputSchema": {
          "type": "object",
          "properties": {
            "x": { "type": "number", "description": "X position of top-left corner" },
            "y": { "type": "number", "description": "Y position of top-left corner" },
            "width": { "type": "number", "description": "Rectangle width" },
            "height": { "type": "number", "description": "Rectangle height" },
            "fill": { "type": "string", "description": "Fill color (CSS color value)" },
            "stroke": { "type": "string", "description": "Stroke color (CSS color value)" },
            "stroke_width": { "type": "number", "description": "Stroke width" }
          },
          "required": ["x", "y", "width", "height"]
        }
      }
    ]
  }
}
```

### Tool Çağrı Yanıtı (başarılı)

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{
      "type": "text",
      "text": "Rectangle created successfully.\nObject ID: rect-abc123\nDimensions: 100x50 at (10, 20)"
    }]
  }
}
```

### Tool Çağrı Yanıtı (hata)

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "isError": true,
    "content": [{
      "type": "text",
      "text": "Error: Invalid color value '#GGG000'. CSS color expected (e.g., '#FF0000', 'red', 'rgb(255,0,0)')"
    }]
  }
}
```

---

## Lisans

MIT License — Inkscape topluluğuyla uyumlu açık kaynak lisansı.

---

*Son güncelleme: 2026-05-29 — Inkscape 1.4.2, MCP SDK v1.29.0, Python 3.12.9*
