# Inkscape MCP — Claude Tasarım Belgesi

> Aynı prompta ("Inkscape için MCP yaz; dil/çatı seçimi, mimari ve test yapısının tasarım
> kriterleri ve hedefleri") benim cevabım. DeepSeek README'si bir **vizyon** belgesidir;
> Codex notu bir **pragmatik düzeltme**dir. Bu belge ise **gerçek binary ile doğrulanmış**
> bir mühendislik tasarımıdır.
>
> **Temel tez:** Bu sunucu "Inkscape'in 1072 action'ını AI'ya dökmek" projesi değildir.
> Çünkü Inkscape CLI **geometri yaratamaz**. Bu, *agentlar için güvenli ve doğrulanabilir bir
> SVG yaratım/işleme çekirdeği* projesidir; Inkscape ise bu çekirdeğin **render/dönüşüm motoru**dur.

---

## 0. Doğrulanmış Zemin (her tasarım kararı buna oturur)

Aşağıdakilerin tamamı yerel `inkscape.com` 1.4.2 (f4327f4, 2025-05-13) binary'si üzerinde
çalıştırılarak teyit edildi — tahmin değil.

| İddia | Durum | Kanıt |
|---|---|---|
| Sürüm 1.4.2, gömülü Python 3.12.9, inkex 1.4.0 | ✅ doğru | `--version`, `bin\python.exe --version` |
| 1072 action mevcut | ✅ doğru | `--action-list` = 1072 satır |
| **Şekil yaratan action (`tool-rect`, `create-rect`, `draw-path`...) YOK** | ❌ **yok** | 1072 action tarandı; sıfır `tool*`, geometri-yaratan sıfır action |
| `--query-all` → `id,x,y,w,h` (CSV) | ✅ çalışır | `svg1,10,20,170,60` döndü |
| Export (PNG/PDF) headless (Cairo, display'siz) | ✅ çalışır | PNG 1563 bayt üretildi |
| `transform-*`, `path-*` boolean, `object-set-attribute` | ✅ çalışır (**mevcut** nesnede) | `object-to-path`+`path-union` tek `<path>`'e birleşti; `fill=purple` yazıldı |
| `--shell` belge durumunu komutlar arası korur | ✅ çalışır | `file-open→query→mutate→export-do→file-close` tek oturumda |
| inkex in-process sıfırdan geometri üretir | ✅ çalışır | `Rectangle.new(...)` + `svg.add()` → `<rect/>` (Inkscape süreci hiç çalışmadan) |
| `window-*`, `file-open-window`, tutorial-*, çoğu extension prefs | ❌ GUI gerekir | `window-open` → "Not in gui mode!" |
| Extension dosyaları: **177 `.inx` / 337 `.py`** (recursive) | ⚠️ "353" yanlış | dosya sayımı |

> **Kapsam sınırı, tek cümlede:** *Inkscape CLI yeni geometri YARATAMAZ; yalnızca mevcut SVG'yi
> SEÇER, DÖNÜŞTÜRÜR, BIRLEŞTIRIR (boolean), SORGULAR ve RENDER/EXPORT eder.* Yaratım yalnızca
> SVG XML / inkex iledir.

Bu tek gerçek, DeepSeek mimarisinin merkezini (Action Builder → `tool-rect`) çürütür ve aşağıdaki
her kararı belirler.

---

## 1. Hedefler ve Kapsam

**Hedef:** Bir AI agent'ın güvenle ve **doğrulanabilir** biçimde SVG üretip düzenlemesini,
Inkscape'in gerçek katma değerini (yüksek-kaliteli render/export, path boolean, font→path,
trace, extension'lar) kullanmasını sağlamak.

**Kapsam (v1):** SVG belge yaşam döngüsü · DOM ile element yaratma/güncelleme/silme · sorgulama
(geometri/stil/ağaç) · path boolean · export (png/svg/pdf/...) · render önizleme · allowlist'li
action escape-hatch · action/inkex introspection.

**Non-goals (v1):** Canlı Inkscape GUI kontrolü · gerçek-zamanlı fare/klavye · `--app-id-tag`
ile kalıcı GUI instance (batch'te geçersiz) · uzak çok-kullanıcılı transport (sonraki faz).

**Tasarım ilkeleri:**
1. **Yarat ≠ İşle.** Yaratım DOM'da, işleme Inkscape'te.
2. **Az ama composable tool** (~10-12), yüzlerce mikro-tool değil.
3. **Her tool annotation + structured output taşır.** ("Tüm bilinen MCP tasarımları" briefi.)
4. **Görsel geri besleme birinci sınıftır.** Agent yaptığını görmeli.
5. **Agent tahmin etmez, introspect eder.** Zekâ katmanı halüsinasyonu keser.
6. **Güvenlik mimarinin içinde, üstüne yama değil.**
7. **Her şey gerçek binary ile E2E doğrulanır.** Mock yalnızca yardımcı.

---

## 2. Dil ve Çatı Seçimi: Python (+ inkex sidecar)

**Birincil dil: Python.** Gerekçeler (Codex ve DeepSeek ile aynı sonuç, ama bir nüans ekliyorum):

- Inkscape portable paketi **gömülü Python 3.12.9 + inkex 1.4.0** ile geliyor (doğrulandı).
- Geometri yaratımının gerçek motoru `inkex`/`lxml`'dir ve bunlar Python.
- MCP resmi Python SDK (`mcp`) stdio için yeterli ve olgun.

**Nüans — inkex'i ana sürece import ETME (DeepSeek'in hatası, Codex'in haklı uyarısı):**
inkex'i sunucunun kendi yorumlayıcısına import etmek sürüm kilitlenmesi ve global-state/`sys.argv`
tabanlı extension modeliyle çakışma riski getirir. Bunun yerine:
- **Saf XML yaratım** için `lxml` ile doğrudan DOM (bağımlılık hafif, deterministik).
- **inkex'in zengin API'si gerektiğinde** (path matematiği, bezier, birim/transform, bbox),
  Inkscape'in **gömülü `python.exe`'sini** `PYTHONPATH=...\extensions` ile bir **sidecar/alt-süreç**
  olarak çalıştır. inkex'in **import edilip sıfırdan geometri üretmesi doğrulandı** (~285ms); ancak
  *tüm* path/transform API'sinin GTK/Cairo olmadan çalıştığı iddiası henüz **prototiple teyit
  edilmedi** — "(doğrulandı)" damgasını burada kullanmak fazla cömertti, Faz-5'te kanıtlanmalı.

> **Maliyet ölçümü (doğrulandı):** Inkscape subprocess cold-start ~767ms; gömülü python+inkex
> import ~285ms (~2.7× daha hafif). Bu yüzden yaratım/mutasyon **in-process/sidecar Python**'da,
> ağır render `--shell`'de.

**TypeScript** iyi bir MCP ekosistemine sahip ama Inkscape/inkex dünyasına Python kadar yakın
değil — bu projede birincil olmaz.

---

## 3. Mimari: 2 Motor + 2 Destek Katmanı

```
┌──────────────────────────────────────────────────────────────────────┐
│  KATMAN 1 — MCP Protokol (stdio)                                       │
│  tipli tool'lar · annotations · inputSchema/outputSchema ·            │
│  structuredContent · isError(iş) vs JSON-RPC error(protokol) ·         │
│  resources(+subscribe) · prompts · progress · cancel · elicitation     │
└───────────────┬───────────────────────────────────────────────────────┘
                │  Tüm tool'lar nesneyi AÇIK ID ile adresler. State DOSYADA yaşar.
   ┌────────────┴───────────┬──────────────────┬───────────────────────┐
   ▼                        ▼                  ▼                       ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ K2 YARATIM    │  │ K3 İŞLEM MOTORU  │  │ K4 ZEKÂ KATMANI │  │  GÖRSEL GERİ-     │
│ lxml/inkex    │  │ inkscape --shell │  │ list_actions    │  │  BESLEME          │
│ DOM · sıfırdan│  │ kalıcı süreç:    │  │ describe_action │  │  render→PNG       │
│ geometri ·    │  │ export · path-   │  │ inkex_api_search│  │  image content    │
│ atomik yazma  │  │ boolean · render │  │ (halüsinasyon   │  │  (resource_link,  │
│ (temp+rename) │  │ · query · font→  │  │  önler)         │  │   boyut limiti)   │
│               │  │ path · extension │  │                 │  │                   │
└──────────────┘  └──────────────────┘  └─────────────────┘  └──────────────────┘
```

> **Dürüstlük notu (öz-eleştiri sonrası):** Aslında **2 gerçek motor** var — K2 (DOM yaratım) ve
> K3 (`--shell` işlem). K4 (zekâ) ve görsel geri besleme, K3 üstündeki **read-only tool gruplarıdır**,
> eş-ağırlıkta "katman" değil. İlk başlıktaki "DeepSeek 3, Codex 2 → ben 4" ifadesi katman sayısını
> bir skor tablosuna çevirmişti; bu bir over-engineering kokusuydu, geri aldım. Yine de bu iki
> destek kaygısını ayrı vurgulamamın sebebi:

- DeepSeek tek "Inkscape Interface" altında CLI'yı *yaratım motoru* sandı → çöktü.
- Codex iki motoru (DOM yaratım + CLI işlem) tek "adapter"da topladı ve **zekâ katmanını**
  ön plana çıkarmadı — oysa tüm `tool-rect` faciası bir API halüsinasyonuydu; introspection bunu önler.

**K2 — Yaratım motoru:** Yeni rect/circle/ellipse/line/path/text → `lxml` DOM'a enjekte edilir,
kararlı ID üretilir, **atomik yazma** (temp + rename) ile diske yazılır. CLI'dan yaratım beklenmez.

**K3 — İşlem motoru:** Tek `inkscape.com --shell` süreci ayakta tutulur. `file-open → ...actions...
→ export-do → file-close` döngüsü. `--batch-process` **kullanılmaz** (gereksiz GUI stack + GTK
uyarısı; saf `--actions`/`--shell`/`--export-*` tercih).

> ⚠️ **Öz-eleştiri düzeltmesi:** İlk taslakta "havuz halinde paralel istek için" yazmıştım — bu
> hataydı. Doğrulanan gerçek `--shell`'in **tek** süreç/tek komut-kanalı olduğudur; v1 transport'u
> da stdio tek-kullanıcı yereldir, yani **paralel istek ihtiyacı yok.** "Süreç havuzu" erken
> optimizasyon/over-engineering olur. Havuz yalnızca ileride Streamable HTTP + çok-kullanıcı
> gelirse (N ayrı süreç + belge↔süreç eşlemesiyle) düşünülür.

**K4 — Zekâ katmanı:** `list_actions`/`describe_action`/`inkex_api_search`. (FreeCAD MCP'nin
`source_search` deseninin Inkscape uyarlaması — agent gerçek yüzeyi keşfeder, uydurmaz.)

**State modeli:** **ID-merkezli, dosya-tabanlı, headless.** Inkscape canlı durum tutmadığından
"selection" kalıcı bir kavram değildir; her action zincirine `select-by-id` olarak **replay** edilir.
Belge bir workspace dosyasıdır; her tool dosya/doküman ID'si alır.

> ⚠️ **Açık problem (öz-eleştiri — "çözdüm" demek yanlıştı):** İlk taslakta bunu "Codex'in çözümsüz
> bıraktığı sızıntıyı kapattım" diye sundum; oysa asıl zor nokta tanımsız kaldı. K2 in-process lxml
> DOM'u **diske** yazarken, K3'ün `--shell`'de açık tuttuğu belge **bayatlar.** Gerçek karar şu olmalı:
> *tek doğruluk kaynağı diskteki dosyadır* → her K3 işlemi öncesi `file-open`/reload ile senkronlanır
> (bu, "`--shell` durumu korur" performans kazancını **kısmen geri verir**) **veya** mutasyonlar da
> `--shell` içinde yapılıp DOM yalnızca ilk yaratımda kullanılır. Aynı sebeple `element_update`'in
> K2 mi K3 mü kullanacağı net bir kurala bağlanmalı. Bu senkronizasyon disiplini, kod yazmadan
> **bir prototiple sınanmalı** — şu an "çözülmüş" değil, "kararı verilecek" durumda.

---

## 4. Tool Kataloğu (composable, ~12 — hepsi annotation + outputSchema)

| Tool | Adresleme | `readOnly` | `destructive` | `idempotent` | Motor |
|---|---|---|---|---|---|
| `document_create` | — | ✗ | ✗ | ✗ | K2 |
| `document_open` | yol | ✗ | ✗ | ✓ | K2 |
| `document_save` / `save_as` | dok. | ✗ | ✓(overwrite) | ✓ | K2 |
| `element_create` | — (ID döner) | ✗ | ✗ | ✗ | **K2 (DOM)** |
| `element_update` | **ID** | ✗ | ✗ | ✓ | K2 / K3 |
| `element_delete` | **ID** | ✗ | **✓** | ✓ | K2 |
| `query` (geometry/style/tree/doc-info) | ID? | **✓** | ✗ | ✓ | K3 (`--query-all`) |
| `path_op` (union/difference/intersection/exclusion/division/simplify/stroke-to-path) | ID'ler | ✗ | ✓ | ✗ | K3 |
| `transform` (translate/scale/rotate/flip/matrix) | ID'ler | ✗ | ✗ | ✗ | K3 |
| `export` (png/svg/pdf/eps/ps) | dok. | ✗ | ✗ | ✓ | K3 (`export-do`) |
| `render_preview` (→ **image content**) | dok. | **✓** | ✗ | ✓ | K3 |
| `run_actions` (allowlist + **arg validatör**) | string | ✗ | ✓ | ✗ | K3 |
| `list_actions` / `describe_action` | — | **✓** | ✗ | ✓ | K4 |

**Tasarım notları:**
- Benzer fiiller **tek enum tool**'da: 6 ayrı boolean yerine `path_op(operation=...)`.
- `openWorldHint`: Inkscape kapalı/yerel alan → neredeyse hepsinde **`false`** (yalnız web'den
  font/trace kaynağı çeken extension'larda `true`).
- **Structured output:** tüm `query`/`list` tool'ları `outputSchema` + `structuredContent` döner
  (geriye-uyum için aynı JSON bir text bloğunda da). DeepSeek'in Ek B düz-metin yanıtları yetersiz.
- `run_actions` bir **kaçış kapısı**dır: 1072 action'a erişim verir ama (a) action-adı allowlist,
  (b) **her action için argüman şeması**, (c) yolları **sunucu** üretir (agent değil). `--actions-file`
  ayraç tuzağı (`;` bekler, satır-başı değil) sarmalanır.

---

## 5. Resources & Prompts

**Resources** (salt-okunur, `inkscape://` — tek ve tutarlı şema; DeepSeek'in `inkx://`/`inkscape://`
çelişkisi giderildi):

| URI | İçerik |
|---|---|
| `inkscape://doc/{id}/svg` | Aktif SVG (XML) |
| `inkscape://doc/{id}/preview.png` | Son render |
| `inkscape://doc/{id}/tree` | Element ağacı özeti (id/tip/bbox) |
| `inkscape://doc/{id}/info` | Boyut/viewBox/birim/katman |
| `inkscape://system/actions` | Doğrulanmış action listesi |
| `inkscape://system/extensions` | **Headless-güvenli** extension listesi |

`resources/subscribe` + `notifications/resources/updated` ile SVG değişince canlı önizleme senkronu.
Büyük SVG/PNG her yanıta **gömülmez**; `resource_link` ile talep üzerine verilir (bağlam koruması).

**Prompts** (kullanıcı-tetikli iş akışları): `create-logo`, `create-diagram`, `trace-bitmap`,
`batch-export`, `svg-optimize`. Argümanlar için `completions` (font, extension_id, mevcut id'ler).

---

## 6. Transport

| Transport | v1 | Not |
|---|---|---|
| **stdio** | ✅ Birincil | Tek-kullanıcı yerel; Inkscape zaten yerelde. stdout'a SADECE MCP mesajı; Inkscape print/uyarısı **asla** stdout'a sızmamalı (subprocess çıktısı yakalanıp result'a paketlenir, loglar stderr'e). |
| **Streamable HTTP** | 🔜 Sonraki faz | Uzak/çok-kullanıcı. `Mcp-Session-Id` header, resumability, 127.0.0.1 bind + Origin doğrulama. |
| ~~HTTP + SSE~~ | ❌ Hedef değil | **DeepSeek'in hatası:** HTTP+SSE yeni değil, **eski ve DEPRECATED** (2025-03-26). Yerini Streamable HTTP aldı. Sadece eski client geriye-uyumu için. |

---

## 7. Güvenlik

- **Workspace-scope:** tüm okuma/yazma `WORKSPACE_ROOT` (env) içinde; path normalize +
  symlink/traversal testleri.
- **Yolları sunucu üretir:** agent mantıksal ad verir (`logo.png`), sunucu workspace içinde gerçek
  yola çevirir. `export-filename`/`file-open` hedefini agent **belirleyemez**.
- **`shell=True` asla;** CLI argümanları **liste** olarak; `run_actions`'ta per-action argüman
  validasyonu (sadece ad-allowlist yetmez — tehlike argümanda).
- **Atomik yazma** (temp + rename) — yarı-yazılmış dosya yok.
- **İşlem-tipine duyarlı timeout** (export/trace 30s'yi aşar; tek global timeout yanlış) + boyut
  limitleri + `--shell` süreç havuzu temizliği (kazara `quit`/`window-crash` gönderilmez).
- **Yıkıcı işlemler için elicitation onayı** (delete, overwrite) + doğru annotation (client
  auto-approve kararı verebilsin).
- Hata mesajları dosya sistemi hakkında gereksiz bilgi sızdırmaz.
- **`--app-id-tag` ile "izolasyon" YANLIŞ** (DeepSeek): batch'te süreç biter, app-id-tag GUI
  instance'ı içindir. İzolasyon **ayrı workspace + ayrı dosya** ile sağlanır.

---

## 8. Test Mimarisi

**İlke (Codex ile hizalı, genişletilmiş):** Mock testler geliştiricinin *hayalini* doğrular;
**gerçek binary ile E2E zorunlu.** DeepSeek'in `test_build_rectangle_action` örneği `tool-rect`
assert ediyordu — yani test bile yanlış varsayımı kodluyordu; geçmesi gerçeği değil mock'u doğrular.

| Seviye | Kapsam | Araç |
|---|---|---|
| **Unit** | DOM create/update/delete, path-math, sandbox/path-traversal, action arg validasyonu, response parser | `pytest`, mock |
| **Golden** | **Kendi ürettiğimiz** SVG (deterministik) — XML canonicalization ile | `pytest` |
| **Integration** | tool → handler → motor zinciri; mock CLI ile hata/timeout; state replay; session izolasyonu | `pytest-asyncio` |
| **E2E (gerçek Inkscape)** | SVG→PNG export, `--query-all` geometri, path-boolean, font→path, `--shell` döngüsü, extension list | gerçek `inkscape.com` |
| **Visual smoke** | PNG **property** assertion: boş değil mi, beklenen boyut/renk var mı (Inkscape çıktısını **snapshot'lama** — kırılgan; namedview/id'leri yeniden yazar) | piksel kontrol |

**Faz 0 (Codex'ten alıyorum, vurguluyorum):** Inkscape path autodetect + `--version`/
`--action-list`/python-path/extension envanteri **snapshot** olarak sabitlenir. Bu adım atlandığı
için DeepSeek `tool-rect` hatasına düştü.

---

## 9. Yol Haritası

| Faz | İçerik |
|---|---|
| **0 — Gerçekleri sabitle** | autodetect, action/inkex envanter snapshot, CI iskeleti |
| **1 — DOM çekirdeği** | `document_*`, `element_create/update/delete` (lxml), kararlı ID, atomik yazma, golden testler, sandbox |
| **2 — İşlem motoru** | `--shell` süreç yönetimi, `query`, `export`, `render_preview`(image), gerçek E2E |
| **3 — Path/transform + escape-hatch** | `path_op`, `transform`, `run_actions` (allowlist + arg validatör), `list_actions`/`describe_action` |
| **4 — MCP genişliği** | annotations (tüm tool), structuredContent, resources(+subscribe), prompts, progress/cancel/elicitation |
| **5 — inkex sidecar + büyüme** | gömülü-python sidecar (path-math, ileri inkex), headless-güvenli extension allowlist |
| **6 — Uzak transport** | Streamable HTTP, çoklu session, süreç havuzu ölçekleme |

---

## 10. DeepSeek ve Codex'e Göre Neyi Değiştirdim (özet)

**DeepSeek README'sine karşı:**
- ❌→✅ Action Builder (`tool-rect`) **silindi**; yaratım **DOM'a** taşındı (action ile şekil yaratılamaz — doğrulandı).
- ❌→✅ "1072 action = ~110 tool" → **~12 composable tool + 1 escape-hatch**.
- ❌→✅ "HTTP+SSE planlanan" → **Streamable HTTP** (HTTP+SSE deprecated).
- ❌→✅ "`--app-id-tag` ile izole örnek" → batch'te geçersiz; **workspace+dosya izolasyonu**.
- ❌→✅ "inkex in-process MVP merkezi" → **sidecar, Faz 5**.
- ➕ annotations, structuredContent, hata-kanalı ayrımı, görsel geri besleme, zekâ katmanı, `--shell`.
- 🔢 "353 extension" → **177 `.inx`/337 `.py`** (ve "headless-güvenli" doğru metrik).

**Codex notuna karşı (ki büyük ölçüde katılıyorum):**
- ➕ Gerekçeyi *"pahalı"*dan **"imkânsız"**a yükselttim (action-yolu kapatıldı).
- ➕ **`--shell`** kalıcı süreç modeli (Codex'te yok).
- ➕ `run_actions` için **per-argüman** güvenlik (sadece ad-allowlist değil).
- 〜 **State replay** mekaniğini gündeme getirdim — ama (öz-eleştiri) DOM↔`--shell` senkronizasyonunu
  *çözmedim*, açık problem olarak işaretledim (bkz. Bölüm 3 uyarısı). Codex'ten ileri ama "çözüldü" değil.
- ➕ **MCP spec genişliği** (annotations/structured/progress/elicitation) — Codex'in *bilinçli minimalizmi*
  açısından bir "eksik" değil, ileriye dönük genişleme katmanı.
- ➕ **Zekâ katmanı** + **görsel geri besleme** öne çıkarıldı (görsel geri beslemenin agent-faydası
  henüz varsayım; ölçülmeli).
- 🔢 Extension: Codex'in **159/165 top-level sayıları doğru**; ben recursive **177/337**'yi ve
  "headless-güvenli" metriğini ekliyorum (Codex'i düzeltmiyorum, tamamlıyorum).

---

## 11. Tek Paragraflık Hüküm

Ben olsam bu projeyi "Inkscape'in tamamını MCP'ye dökelim" diye değil, **"agentlar için güvenli,
doğrulanabilir bir SVG yaratım/işleme çekirdeği kuralım; Inkscape'i render/dönüşüm motoru olarak
kullanalım"** diye kurardım. Yaratım DOM'da (çünkü CLI yaratamıyor — doğrulandı), işleme uzun-ömürlü
`--shell` Inkscape'te, agent zekâ katmanıyla gerçek yüzeyi keşfeder (uydurmaz), her tool annotation
ve yapısal çıktı taşır, her değişiklik görsel olarak geri beslenir ve her şey gerçek binary ile E2E
doğrulanır. Küçük ama sağlam bu çekirdek kurulduktan sonra Inkscape'in geniş action/extension yüzeyi
allowlist'li bir kaçış kapısıyla kontrollü biçimde açılır.

---

*Yazan: Claude (Opus 4.8). Tüm "doğrulanmış" ifadeler yerel `inkscape.com` 1.4.2 binary'si
üzerinde çalıştırılarak teyit edildi. İlgili: `README.md` (DeepSeek vizyonu), `codex-readme.md`
(Codex notu), `claudan-codexe-eleştiri.md` (bu tasarımın Codex eleştirisi). Tarih: 2026-05-29.*
