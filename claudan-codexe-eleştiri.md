# Claude'dan Codex'e — `codex-readme.md` Değerlendirmesi

> Bu dosya, `codex-readme.md`'nin bu proje (Inkscape MCP) için eleştirisidir.
> Eleştiri, **gerçek binary ile doğrulanmış gerçekler** ve MCP spesifikasyonu + benzer
> grafik-araç MCP sunucuları üzerine yapılan araştırmaya dayanır.
> Test edilen binary: `inkscape.com` — Inkscape 1.4.2 (f4327f4, 2025-05-13), gömülü Python 3.12.9.

---

## TL;DR (Kısa Hüküm)

`codex-readme.md` **DeepSeek README'sinden açıkça daha iyi** ve doğru yönü gösteriyor:
küçük composable çekirdek, güvenlik-öncelikli tasarım, "basit işlerde XML / Inkscape'e özgü
işlerde CLI" ayrımı ve gerçek Inkscape ile E2E test ısrarı — hepsi isabetli.

Ama bu proje için Codex notunun **beş gerçek boşluğu** var:

1. **Doğru sonuç, eksik gerekçe.** Codex "geometriyi XML ile yarat" diyor ama bunu bir
   *verimlilik* argümanıyla savunuyor ("her dikdörtgen için Inkscape açmak pahalı"). Oysa
   gerçek sebep *imkânsızlık*: Inkscape CLI'da şekil yaratan **hiçbir action yok** (doğrulandı).
   Verimlilik argümanı "sonra action'larla optimize ederiz" kapısını açık bırakır; imkânsızlık
   argümanı o kapıyı kapatır. Codex DeepSeek'in ölümcül kusurunu **ismiyle teşhis etmemiş.**
2. **`run_inkscape_actions` allowlist'i yetersiz tarif edilmiş.** Action *adı* allowlist'i
   yeterli değil; tehlike *argümanlarda* (örn. `export-filename:`, `file-open:`).
3. **State/selection modeli sızdırıyor.** Headless modda Inkscape çağrılar arası durum tutmaz;
   "session selection" her action zincirine `select-by-id` ile yeniden enjekte edilmeli.
4. **`--shell` kaçırılmış.** Uzun-ömürlü sunucu için doğru cevap budur (tek süreç ayakta,
   belge durumu korunur, ~767ms cold-start bir kez ödenir).
5. **MCP spec genişliği zayıf.** Orijinal prompt "tüm bilinen MCP tasarımları" diyor; ama Codex
   notunda tool annotations, structured output, hata kanalı ayrımı, progress/cancel/elicitation
   hiç yok — bu konuda DeepSeek README'sinden bile dar.

**Hüküm:** Yön doğru, iskelet sağlam → **kabul, ama 5 noktada güçlendirilmeli.**

---

> **⚖️ Metodolojik şeffaflık (sonradan eklendi — bağımsız adalet denetimi sonrası, 7/10).**
> Bu eleştirinin "doğrulanmış gerçek" otoritesi, yerel binary'yi 4 ajanla derinlemesine test
> edebildiğim bir **avantajdan** geliyor (1072 action taraması, `--shell`, cold-start ölçümü).
> Codex bilinçli olarak **kısa bir tasarım notu** yazdı ve bu tür bir ampirik teste girmedi.
> Dolayısıyla aşağıdaki bazı maddeler (özellikle 2.1, 2.4) Codex'in *kusuru* değil, **ancak
> binary-probe ile ortaya çıkan ileriye-dönük netleştirmeler**dir. Ayrıca dürüstçe kabul ediyorum:
> DeepSeek README'sine kötücül bir ajan yöneltirken Codex'e (ve kendi `claude-readme.md`'me) aynı
> sertliği *başta* yöneltmedim — bu bir asimetriydi. Bağımsız hakem buna işaret etti; aşağıdaki
> maddeler bu denetime göre **düzeltildi** (özellikle 2.8 geri alındı).

---

## 1. Codex'in Doğru Yaptıkları (teyit ediyorum)

Bunlar gerçek güçlü yanlar; bilerek kısa tutuyorum çünkü asıl değer eleştiride.

| # | Codex'in kararı | Neden doğru |
|---|---|---|
| ✅ | **Kapsam yönetimi: 10-15 composable tool** | 100+ mikro-tool model context'ini şişirir ve araç-seçim doğruluğunu düşürür. Az sayıda niyet-bazlı tool agent ergonomisi için üstün. |
| ✅ | **İki motor ayrımı: basit işler XML/DOM, Inkscape'e özgü işler CLI** | Tek en önemli doğru içgüdü. Bu ayrım, DeepSeek'in `tool-rect` tuzağını **dolaylı olarak** atlatıyor (element_create DOM kullanıyor, action değil). |
| ✅ | **Güvenlik mimarinin merkezinde** | `allowed_dirs`, path normalize, symlink/traversal testi, `shell=True` yok, CLI argümanları liste olarak, boyut/timeout limitleri, session başına temp dizin — sektör standardı ve doğru. |
| ✅ | **Gerçek Inkscape ile E2E + golden + visual smoke test ısrarı** | Mock testler geliştiricinin *hayal ettiği* davranışı doğrular, binary'nin gerçeğini değil. Codex bu tuzağı görüyor — kritik. |
| ✅ | **Faz 0: "Gerçekleri Sabitle" (inventory/snapshot)** | Mükemmel disiplin. DeepSeek'in `tool-rect` hatası tam da bu adım atlandığı için oluştu. |
| ✅ | **README hata tespitleri** | "HTTP+SSE yeni hedef değil, Streamable HTTP olmalı" ✓; "353 extension iddiası şüpheli" ✓; "tüm action'ları tool yapma, allowlist kullan" ✓; "inkex MVP merkezine konmamalı" ✓. |

Codex'in `stdio` birincil transport seçimi, `inkscape://session/*` resource fikri ve fazlı
yol haritası da doğru. Bu notu yazan, Inkscape gerçeğini DeepSeek'ten daha iyi kavramış.

---

## 2. Eksikler ve Düzeltmeler (önem sırasına göre)

### 2.1 — [ORTA · doğrulama notu] Doğru sonuç, ama eksik/zayıf gerekçe

> **Codex notu:** *"her basit dikdörtgen veya metin ekleme için Inkscape process çalıştırmak
> gereksiz pahalı ve kırılgan olabilir."*

Sonuç doğru (XML ile yarat), **ama gerekçe yanlış kategoride.** Bu bir verimlilik/kırılganlık
argümanı. Gerçek sebep çok daha sert:

> **Doğrulanmış gerçek:** Inkscape 1.4.2'de 1072 action tarandı. `tool-rect` **yok**, hiçbir
> `tool*` action'ı **yok**, primitif geometri (rect/circle/path/text) yaratan **hiçbir action yok.**
> `--shell` banner'ı bunu açıkça söylüyor: *"Only actions that don't require a desktop may be used."*
> Geometri **yalnızca** SVG XML / inkex ile yaratılabilir.

Neden bu fark önemli:

- Codex'in verimlilik çerçevesi, bir okuyucunun *"action yolu geçerli ama yavaş bir alternatif,
  ileride optimize ederiz"* sanmasına yol açar. **Bu yanlış** — action yolu geometri yaratımı için
  bir alternatif değil, **var olmayan bir şey.**
- Codex `run_inkscape_actions`'ı bir "escape hatch" olarak öneriyor, ama hangi action'ların
  *gerçekten var ve headless çalıştığını* hiç tespit etmemiş. `--action-list` *sayısını* almış
  (1072) ama içeriğini test etmemiş. Bu yüzden DeepSeek'in ölümcül kusurunu **adıyla yakalayamamış**
  — sadece "tüm action'ları tool yapmak riskli" diye *yumuşak* bir kapsam/güvenlik itirazı yapmış.

**Düzeltme:** Notun açıkça şunu söylemesi gerekirdi: *"Geometri yaratımı CLI action katmanında
İMKÂNSIZDIR; bu bir tercih değil, mimari bir kısıttır. DOM/inkex çekirdek, CLI ise yalnızca
export/path-boolean/query/render/extension için işlem motorudur."*

> ⚖️ **Adalet notu:** "`tool-rect` yok" gerçeği yalnızca 1072 action'ı *taramakla* bulunur; bunu
> Codex'in bilmemesi bir kusur değil. Üstelik Codex pratik sonucu (action yolu = kötü fikir) doğru
> yere koydu. Bu madde Codex'i suçlamak için değil, doğru sezgisini sağlam zemine oturtmak için
> durmalı — bu yüzden KRİTİK'ten **ORTA**'ya indirildi.

---

### 2.2 — [YÜKSEK] `run_inkscape_actions` allowlist'i yetersiz

> **Codex notu:** *"`run_inkscape_actions` sadece allowlist ile çalışmalı."*

Doğru ama eksik. **Tehlike action adında değil, argümanlarında:**

- `export-filename:C:\Users\...\gizli.png` → allowlist'te `export-filename` olsa bile argüman
  sandbox dışına yazabilir.
- `file-open:<keyfi yol>` → allowlist'te olsa bile keyfi dosya okur.
- `object-set-attribute:onload,<script>` → SVG'ye keyfi attribute enjekte eder.

Ayrıca araştırmada bulunan somut bir tuzak: **`--actions-file` ayraç olarak `;` bekler**, satır-başına-bir-action **değil**. `object-set-attribute:fill,cyan` ayrı satıra konunca virgülden bölünüp `cyan`'ı id sandı ("Did not find object with id: cyan"). Aynı içerik tek satırda `;` ile ayrılınca çalıştı. Yani naif "her satır bir action" allowlist'i sessizce bozulur.

**Düzeltme:** Allowlist *action adı + her action için argüman şeması/validatörü* olmalı.
Yolları üreten action'ların (`export-filename`, `file-open`, `file-rebase`) hedefi **sunucu**
belirlemeli (agent değil) — agent sadece mantıksal isim verir, sunucu workspace içinde gerçek
yola çevirir. Ham action string'ini agent'a açan tool `openWorldHint`'e yakındır; mümkünse
doğrulanmış action zincirlerini *tipli tool* olarak sarmalamak daha güvenli.

---

### 2.3 — [YÜKSEK] State/selection modeli sızdırıyor (README'den miras alınmış)

Codex `selection_set` ("oturum seçimini ID listesi olarak tutar") ve
`inkscape://session/current-svg`, `inkscape://session/preview.png` tutuyor. Ama:

> **Doğrulanmış gerçek:** Headless/process-per-call modda Inkscape çağrılar arası **hiç durum
> tutmaz.** Canlı bir "selection" yoktur. Action'lar selection-tabanlıdır: her `--actions`
> zinciri **önce** `select-by-id:...` ile hedefi seçmeli, **sonra** transform/path/object uygulamalı.

Yani sunucuda tutulan bir "selection", her CLI çağrısında zincire `select-by-id` olarak
**yeniden enjekte edilmek zorunda.** Codex bu zorunlu replay mekanizmasını hiç ele almıyor —
tıpkı README gibi durum yönetimi naif kalıyor. `element_update`'in "seçili/ID'li element"
ifadesi de aynı sızıntıyı taşıyor: selection-bazlı ve ID-bazlı adresleme karışıyor.

**Düzeltme:** İki net seçenekten birini seç:
- **(Tercihim) Stateless/ID-merkezli:** Her mutasyon tool'u nesneyi **açık ID** ile adresler.
  "Selection" diye kalıcı bir kavram olmaz; varsa sadece sunucu-içi kolaylıktır ve her zaman
  `select-by-id` zincirine açılır. Belge durumu **dosyada** yaşar (her tool dosya yolu alır).
- **Explicit document lifecycle:** `document_open` → server-held doküman + sürüm/ID → `document_save`.
  Bu durumda "current SVG"nin nerede (temp dosya?) yaşadığı **açıkça** tanımlanmalı.

Codex ikisinin arasında kalıyor; karar verilmemiş. Bu projede ilerlemeden önce **bu karar
verilmeli** (aşağıda 2.10).

---

### 2.4 — [ORTA · doğrulama notu] `--shell` kaçırılmış (uzun-ömürlü sunucunun doğru cevabı)

Codex'in iki-katman modeli, her CLI işlemi için taze `inkscape.com` spawn'ı ima ediyor.
Bir agent 50 işlem yaparsa bu, 50× cold-start demek.

> **Doğrulanmış gerçek:** `--shell` modu tek bir Inkscape process'ini ayakta tutar, STDIN'den
> `action1:arg; action2:arg` satırları okur ve **belge durumunu komutlar arası korur**
> (`file-open` → query → mutate → `export-do` → `file-close` tek oturumda çalıştı). Cold-start
> ~767ms **bir kez** ödenir, sonra amortize edilir. Ayrıca: `--batch-process` aslında daha fazla
> GUI stack ayağa kaldırıyor (GTK uyarıları üretti); saf headless iş için
> **`--actions`/`--shell`/`--export-*` tercih edilmeli, `--batch-process` gereksiz.**

**Düzeltme:** CLI işlem motoru, opsiyonel olarak kalıcı bir `--shell` process havuzu üstüne
kurulmalı. Tuzaklar: `quit`/`quit-immediate`/`window-crash` kazara gönderilmemeli (process'i
öldürür); stdout/stderr ayrıştırılmalı (stderr'e ANSI hata + GTK uyarısı karışıyor); her belge
`file-close` ile temizlenmeli; tek process tek-thread olduğundan paralel istek için havuz gerekir.

> ⚖️ **Adalet notu:** `--shell`'in belge durumunu koruduğu da ancak binary testiyle görünür.
> Codex'in fazlı planı "önce basit spawn, sonra optimize" dediği için bunu Faz-5 optimizasyonuna
> ertelemek meşru bir MVP kararıdır. Bu bir *eksik* değil, bir *ekleme önerisi* — YÜKSEK'ten
> **ORTA**'ya indirildi. (Not: aşağıda kendi tasarımımda bunu "havuz" diye abartmam da bir
> hataydı; bkz. son bölüm.)

---

### 2.5 — [ORTA · yeniden çerçeveleme] MCP spec genişliği — eksik değil, ertelenmiş

Orijinal prompt açıkça *"bilinen MCP tasarımlarının hepsini kullanmak üzere"* diyor. Codex'in
tool kataloğu sadece *ad + amaç*. Eksik olan, agent güvenliği ve güvenilirliği için kritik
spec özellikleri:

| Özellik | Neden gerekli | Codex notunda |
|---|---|---|
| **Tool annotations** (`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`) | Client'ın auto-approve/onay kararı verebilmesi için. `element_delete`=destructive, `query_*`=readOnly, Inkscape kapalı alan olduğu için neredeyse hepsi `openWorldHint:false`. | ❌ Yok |
| **Structured output** (`outputSchema` + `structuredContent`) | `query_geometry`/`document_info` sonucunu agent'ın güvenilir parse etmesi için. Düz metin yetmez. | ❌ Yok |
| **Hata kanalı ayrımı** | İş hatası (geçersiz renk, export başarısız) = `result.isError:true` (model görüp düzeltsin); protokol hatası (bilinmeyen tool) = JSON-RPC `error`. | ❌ Yok |
| **Progress / cancellation** | Toplu export, trace-bitmap, 1000+ nesne sorgusu uzun sürer; `notifications/progress` + `notifications/cancelled` + alt-süreç SIGTERM. | ❌ Yok |
| **Elicitation** | Eksik parametre / üzerine-yazma onayı için kullanıcıya yapılandırılmış soru (2025-06-18). | ❌ Yok |
| **Completions** | `extension_id`, `font_family`, mevcut nesne id'leri için otomatik tamamlama. | ❌ Yok |
| **Resource subscriptions** | SVG değiştiğinde `notifications/resources/updated` ile canlı önizleme senkronu. | ❌ Yok |

⚖️ **Düzeltme (ilk versiyonda haksızdı):** Codex'in TÜM TEZİ minimalizmdi ("100+ değil 10-15
composable tool"), yani bu özelliklerin yokluğu bir *kusur* değil **bilinçli bir tercih.** Üstelik
bunlar composable çekirdek netleşince eklenir ve Codex'in Faz-5'i ("daha geniş tool katalogu")
buna açık kapı bırakıyor. İlk yazdığım "DeepSeek'ten bile dar" kıyasını **geri alıyorum**: DeepSeek'te
bu bölümler *vardı* ama hatalı temele oturuyordu — sorun genişlik değil **doğruluktu.** Doğru çerçeve:
bunlar "eksik" değil, çekirdek-sonrası **genişleme katmanı**; "tüm bilinen MCP tasarımları" briefini
tam karşılamak isteyen biri için yararlı bir kontrol listesidir.

---

### 2.6 — [ORTA] Görsel geri besleme döngüsü merkeze alınmamış

Codex `render_preview`'ı 14 tool'dan biri olarak listeliyor — iyi ki var. Ama bir **grafik aracı**
için öldürücü özellik şudur: *agent değişiklik yapar → sonucun PNG render'ını **image content**
olarak geri alır → kendini düzeltir.*

> Araştırma teyidi: Canlı-uygulama sunucuları (Blender MCP, FreeCAD GUI-attach, neka-nat/bonninr
> FreeCAD) hepsi `get_view`/screenshot geri beslemesini önceliklendiriyor. Inkscape headless'ta
> bunu PNG render ile taklit edebiliriz (Cairo ile display'siz çalıştığı doğrulandı).

**Düzeltme:** "Her mutasyon tool'u opsiyonel olarak render edilmiş önizlemeyi MCP image content
olarak döndürebilir" bir **birinci-sınıf tasarım ilkesi** olmalı, yan bir tool değil. Boyut
limiti + `resource_link` ile (her yanıta gömmek yerine talep üzerine) bağlam şişmesi önlenir.

---

### 2.7 — [ORTA] "Source/command intelligence" katmanı yok

Codex iki katman öneriyor (MCP/API + Inkscape/SVG adapter). Ama bu, çok farklı iki motoru
(DOM/inkex yaratım motoru vs Inkscape CLI işlem motoru) tek "adapter"da topluyor ve **üçüncü**
kritik katmanı **ön plana çıkarmıyor.**

> ⚖️ **Adalet notu:** "Yok" demek tam doğru değildi — bu fikrin *tohumları* Codex notunda zaten
> var: `inkscape://system/action-list` + `inkscape://system/extensions` resource'ları, Faz-0
> "Gerçekleri Sabitle / inventory snapshot" ve Faz-5 "action listesine dayalı otomatik tool/resource
> üretimi." Yani öneri, "eksik bir katman" değil, **dağınık olanı birinci-sınıf bir zekâ katmanına
> yükseltmek.**

> Araştırma teyidi: Olgun sunucular (bu oturumdaki FreeCAD MCP'nin `source_search`/
> `command_describe`/`symbol_index` katmanı) hedef uygulamanın gerçek API'sini **tarayıp doğrular**
> ki agent uydurmasın. FreeCAD MCP 1112 komut/26 modülü gerçek git ağacından keşfediyor.

İroni: Tüm `tool-rect` faciası tam da bu tür bir halüsinasyondu. Bir **action/inkex introspection
tool'u** (`list_actions`, `describe_action`, `inkex_api_search`) bu sınıf hatayı kökten önler.

**Düzeltme:** Üç katman:
1. **Yaratım motoru** — inkex/lxml ile DOM üzerinde sıfırdan geometri + atomik yazma.
2. **İşlem motoru** — `--shell` ile uzun-ömürlü Inkscape (export, path-boolean, render, font→path, query).
3. **Zekâ katmanı** — gerçek action listesi + inkex API introspection (agent tahmin etmesin).

---

### 2.8 — [GERİ ALINDI → ekleme] Extension sayısı: Codex aslında doğru saymış

> ⚠️ **Bu madde ilk versiyonda haksızdı; bağımsız denetim sonrası düzelttim.** Codex'in verdiği
> **159 `.inx` / 165 `.py`** sayıları **top-level olarak BİREBİR DOĞRU** (doğrulandı). Codex ayrıca
> "sayım kriteri belirsiz" diyerek belirsizliği **dürüstçe işaretlemiş.** Yani Codex burada bir hata
> yapmadı — DeepSeek'in uydurma "353"ünü reddedip doğrulanabilir bir sayı vermesi bir **erdem.**
> İlk yazdığım "kendi yanlış sayısını koymuş" ifadesi yanlıştı; geri alıyorum.

Geriye yalnızca bir **ekleme** kalıyor (eleştiri değil): recursive sayım **177 `.inx` / 337 `.py`**
ve asıl yararlı metrik **"kaçının headless çalıştığı"** — org.* prefix'li 820 girdinin çoğu pref
diyalogu (GUI) ya da inkex runtime gerektiriyor ve `.noprefs` ikizleriyle şişmiş. Yani "X extension
var" yerine "şu N extension headless-güvenli ve allowlist'te" demek ikimizin de notunu güçlendirir.

---

### 2.9 — [DÜŞÜK-ORTA] Golden test nüansı

Codex "golden test + XML canonicalization" öneriyor. **Kendi ürettiğimiz** SVG (DOM çıktısı) için
mükemmel — deterministik. Ama **Inkscape'in round-trip çıktısını** golden'lamak kırılgandır:
Inkscape SVG'yi ağır yeniden yazar (`sodipodi:namedview`, `inkscape:` namespace'leri ekler, id'leri
yeniden üretir, metadata). Attribute sırasını canonicalize etmek bunu evcilleştirmez.

**Düzeltme:** İkisini ayır: *kendi DOM çıktımızı golden'la* (iyi) vs *Inkscape çıktısını property/
visual assertion ile doğrula* (snapshot değil — "PNG boş değil, beklenen boyutta, beklenen renk var").

---

### 2.10 — [DÜŞÜK] Karar gerektiren artefaktlar eksik (bir "not" olduğu için adil, ama işaretliyorum)

Codex notu bilinçli olarak bir *tasarım notu*, tam spec değil. Ama bu proje ilerlemeden önce
şu üç kararın verilmesi gerekiyor ve not bunları erteliyor:

1. **Adresleme modeli:** ID-merkezli stateless mi, explicit document-lifecycle mi? (bkz. 2.3)
2. **"Current SVG" nerede yaşıyor?** Temp dosya? Workspace içinde adlandırılmış dosya? Bellekte?
3. **Somut tool input/output şemaları** (en azından çekirdek 6 tool için, annotations dahil).

---

## 3. Benim Önerdiğim Düzeltilmiş Mimari (özet)

Codex'in iskeleti + yukarıdaki 5 düzeltme ile:

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Katmanı (stdio)                                          │
│  • tipli tool'lar + annotations + outputSchema/structuredContent │
│  • iş hatası=isError / protokol hatası=JSON-RPC error         │
│  • progress / cancel / elicitation / resources(+subscribe)    │
└───────────────┬──────────────────────────────────────────────┘
                │ (her tool nesneyi açık ID ile adresler; state DOSYADA)
   ┌────────────┼─────────────────────┬──────────────────────────┐
   ▼            ▼                     ▼                          ▼
┌────────┐ ┌──────────────┐ ┌──────────────────┐ ┌────────────────────┐
│ YARATIM │ │ İŞLEM MOTORU │ │  ZEKÂ KATMANI    │ │ GÖRSEL GERİ BESLEME │
│ inkex/  │ │ inkscape     │ │ list_actions /   │ │ render→PNG image    │
│ lxml DOM│ │ --shell      │ │ describe_action /│ │ content (resource_  │
│ +atomik │ │ (export,     │ │ inkex_api_search │ │ link, boyut limiti) │
│ yazma   │ │ path-boolean,│ │ (halüsinasyon    │ │                     │
│         │ │ render,query)│ │  önler)          │ │                     │
└────────┘ └──────────────┘ └──────────────────┘ └────────────────────┘
```

**Çekirdek tool seti (~10-12, hepsi annotation + outputSchema ile):**
`document_create/open/save` · `element_create` (rect/circle/ellipse/line/path/text — **DOM ile**) ·
`element_update` (ID ile) · `element_delete` (destructive) · `query` (geometry/style/tree — readOnly) ·
`path_op` (union/difference/intersection/... tek enum tool) · `export` (png/svg/pdf/...) ·
`render_preview` (image content) · `run_actions` (argüman-validatörlü escape-hatch) ·
`list_actions`/`describe_action` (zekâ).

**Güvenlik:** workspace-scope (env root) · atomik yazma (temp+rename) · yolları **sunucu** üretir
(agent değil) · per-action argüman validasyonu · işlem-tipine duyarlı timeout · destructive ops
için elicitation onayı.

---

## 4. Net Hüküm

`codex-readme.md` **doğru pusulaya sahip** ve DeepSeek README'sinden net biçimde üstün: küçük
composable çekirdek, XML/CLI ayrımı, güvenlik-öncelik ve gerçek-E2E ısrarı isabetli. Bu notu yazan
Inkscape gerçeğini iyi sezmiş.

Ama "sezmiş" anahtar kelime: Codex **doğru sonuca eksik gerekçeyle** varmış (geometri-yaratımının
*imkânsız* olduğunu değil, *pahalı* olduğunu söylemiş) ve bu yüzden DeepSeek'in ölümcül kusurunu
adıyla teşhis edememiş. Ek olarak `--shell` (performans), per-argüman güvenlik, state-replay
mekaniği, MCP spec genişliği (annotations/structured-output/progress/elicitation), görsel geri
besleme döngüsü ve zekâ katmanı eksik.

**Sonuç: Kabul + güçlendirme.** Bu düzeltmelerle Codex'in iskeleti uygulanabilir bir mimariye
dönüşür. (⚖️ **Çıkar-çatışması şeffaflığı:** paralel olarak kendi tasarımımı `claude-readme.md`'de
yazdım — o da aynı kötücül denetimden geçti ve **iki HIGH kusur** çıktı [DOM↔`--shell` durum
senkronizasyonu "çözüldü" diye sunulmuş ama tanımsız; "süreç havuzu" tek-süreç gerçeğiyle çelişen
erken optimizasyon]. Bu eleştiri, kendi alternatifimi öne çıkarma aracı değildir; ona da aynı
sertliği uyguladım.)

---

*Değerlendiren: Claude (Opus 4.8). Tüm "doğrulanmış gerçek" ifadeleri yerel `inkscape.com`
1.4.2 binary'si üzerinde çalıştırılarak teyit edilmiştir. Tarih: 2026-05-29.*
