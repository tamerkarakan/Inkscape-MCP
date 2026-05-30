# Inkscape MCP — Mimari v1 (ortak sözleşme)

> **Bu nedir:** Claude ↔ Codex tasarım diyaloğunun (README → codex-readme → 1./2./3. tur
> eleştiriler) yakınsadığı **uygulanabilir teknik sözleşme.** "Kim haklı" tartışması bitti;
> bu belge yapılacak işin kontratıdır.
>
> **Sentez:** Claude'un *gerçek binary'ye göre tasarla* ampirik zemini + Codex'in *küçük,
> testlenebilir, dosya-merkezli MVP* disiplini + 2.–3. turda eklenen lock / revision /
> cancellation / id-map / birim-sözleşmesi maddeleri.
>
> **Okuma kuralı (önceki turların dersi):** İki şeyi tipografik olarak ayırıyoruz —
> **🔬 DOĞRULANMIŞ GERÇEK** (yerel `inkscape.com` 1.4.2 binary'sinde test edildi) vs
> **🧭 TASARIM KARARI** (mühendislik tercihi; gerçek değil). Karıştırılmayacak.

---

# Bölüm 1 — 🔬 Doğrulanmış Inkscape Gerçekleri

Hepsi yerel `inkscape.com` (Inkscape **1.4.2**, f4327f4, 2025-05-13) üzerinde çalıştırılarak teyit edildi.

| # | Gerçek | Nasıl doğrulandı |
|---|---|---|
| F1 | Sürüm 1.4.2; gömülü **Python 3.12.9**; **inkex 1.4.0** bundle'da | `--version`, `bin\python.exe` |
| F2 | **1072 action** mevcut | `--action-list` = 1072 satır |
| F3 | **Şekil yaratan action YOK** — `tool-rect`/`tool*`/`create-rect`/`draw-path` yok; primitif geometri yaratan hiçbir action yok | 1072 action tarandı; `--shell` banner'ı: "Only actions that don't require a desktop may be used" |
| F4 | Yeni geometri **yalnızca SVG XML / inkex** ile üretilir | inkex `Rectangle.new(...)`+`svg.add()` → `<rect/>` (Inkscape süreci çalışmadan) |
| F5 | `--query-all` çıktısı **CSS pixel (96 dpi)** — user-unit/mm DEĞİL | mm SVG: x=10→`37.7953` (çarpan 96/25.4); px SVG: 10→10. Genel çarpan = `svg_width_px / viewBox_width` |
| F6 | Export PNG/PDF **headless** (Cairo, display'siz) çalışır | PNG/PDF üretildi |
| F7 | `transform-*`, `path-*` boolean, `object-set-attribute` **mevcut** nesnede çalışır; action'lar **selection-tabanlı** (önce `select-by-id`) | `object-to-path`+`path-union` tek `<path>`; `fill=purple` yazıldı |
| F8 | **ID davranışı operasyona göre değişir:** `object-to-path`(tek)/`group`+`ungroup`/`transform-translate` → id **korunur**. `path-union` → nesneler tek `<path>`'e iner, **en alttaki operandın id'si (r1) kalır, diğerleri (c1) yok olur** (rastgele id üretilmez). `group` ara wrapper'ı **yeni `g1`** alır | her adımda çıkan SVG incelendi |
| F9 | `transform-translate` `transform` attr eklemeden **x/y'yi doğrudan günceller** | `x:20→30, y:20→40`, transform attr yok |
| F10 | `--shell` tek süreci ayakta tutar; **belge durumu komutlar arası korunur** | `file-open→query→mutate→export-do→file-close` tek oturum |
| F11 | `--batch-process` daha fazla GUI stack açar (GTK uyarıları); saf `--actions`/`--shell`/`--export-*` daha temiz | banner + GTK uyarı farkı gözlendi |
| F12 | `--actions-file` ayraç olarak **`;`** bekler (satır-başı-action değil) | satır-başı format yanlış parse etti |
| F13 | `window-*`, `file-open-window`, çoğu extension prefs **headless'ta başarısız** | `window-open` → "Not in gui mode!" |
| F14 | inkex in-process import ~**285ms**; Inkscape subprocess cold-start ~**767ms** | ölçüldü |
| F15 | `--app-id-tag` bir **GUI instance** içindir, batch'te geçersiz; izolasyon **temp/workspace** ile sağlanır | batch süreç her çağrıda biter |
| F16 | Extension dosyaları: **177 `.inx` / 337 `.py`** (recursive); 159/165 (top-level). Sayı yanlış metrik — önemli olan **kaçının headless çalıştığı** | dosya sayımı + org.* action analizi |
| F17 | MCP'de güncel transport yalnızca **stdio + Streamable HTTP**; "HTTP+SSE" eski/deprecated (2025-03-26) | MCP spec |
| F18 | **Exit code güvenilmez:** runtime/action hatası (bilinmeyen action, yok dosya, shell action hatası) → **exit 0** (hata stderr'de); ama CLI-argüman hatası (bilinmeyen flag) → **exit 1**. Hata tespiti stderr-parse ile yapılır | `--actions=bogus`→0, `--bogus`→1 doğrulandı (DeepSeek kör §4.1 + binary re-verify) |
| F19 | **Doğrulanmış format/komut detayları:** `--query-all`→`id,x,y,width,height` (satır/nesne), `--query-x/y/width/height`→tek float; `object-set-attribute:attr,value` (virgül sonrası boşluksuz); export sırası `export-filename→export-type→export-do`; `--pipe` stdin'den SVG okur; `--export-filename=-` SVG/plain-SVG'yi stdout'a verir (binary PNG/PDF için geçmez) | DeepSeek kör §7 + binary |

> **Tek cümlelik kapsam sınırı:** Inkscape CLI yeni geometri **yaratamaz**; yalnızca mevcut SVG'yi
> **seçer, dönüştürür, birleştirir (boolean), sorgular, render/export eder.** Yaratım = DOM/inkex.

---

# Bölüm 2 — 🧭 V1 Bağlayıcı Mimari Kararlar (15 madde)

Bunlar **kararlar**dır (gerçek değil). Hepsi Bölüm 1'deki gerçeklerle tutarlı olacak şekilde seçildi.

### Motor modeli
**2 gerçek motor + 2 destek alt-sistemi.** (Bunları "4 katman" diye süslemek bir hataydı.)
- **Yaratım motoru** — lxml/DOM ile sıfırdan geometri + atomik yazma. *(F3/F4 zorunlu kılar.)*
- **İşlem motoru** — Inkscape CLI (`--shell` veya process-per-call): query/export/render/path-boolean/font→path. *(F5–F13.)*
- **Destek: capability introspection** — `actions.list/describe`, `capabilities.json`, headless-safe allowlist. *(F2/F3 halüsinasyonunu önler.)*
- **Destek: görsel geri besleme** — talep üzerine PNG render (image content).

### Sözleşme maddeleri

1. **Tek doğruluk kaynağı:** workspace içindeki SVG **dosyası.** Bellekteki Inkscape state'ine güvenilmez.
2. **Belge başına lock/mutex:** aynı belgede DOM-write / `file-open` / export / path-op / save / preview **serileştirilir.** (Async MCP server + retry → aynı anda çağrı olabilir; bu *doğruluk* meselesi, ölçeklenme değil.)
3. **Belge başına revision/etag:** her mutasyon revision'ı artırır; mutasyon tool'ları opsiyonel `expected_revision` alır; stale → controlled error; resource'lar `revision` içerir.
4. **Yaratım + basit update:** lxml/DOM (deterministik, hızlı, parse'ı kolay).
5. **Inkscape CLI:** query, export, render, path boolean, font→path ve doğrulanmış işlemler için.
6. **Adresleme: ID-merkezli.** Selection kalıcı kavram değil; yalnızca ephemeral `select-by-id` replay (F7).
7. **`--shell`:** desteklenen **performans yolu**, v1'in **zorunlu varsayılan motoru değil**; state-sync prototipi (bkz. Bölüm 3) kanıtlanınca varsayılana terfi eder. Baseline = process-per-call. **Cancel davranışı sert tanımlı:** komut takılırsa süreç öldürülür, document state "unknown" sayılır, **dosyadan yeniden açılır.**
8. **`run_actions` (escape-hatch):** action-adı allowlist **+ her action için argüman şeması + path sandbox + yolları SUNUCU üretir** (agent mantıksal ad verir). Sadece ad-allowlist yetmez.
9. **MCP v1 minimumu:** `inputSchema`, `outputSchema`/`structuredContent`, **tool annotations** (`readOnly`/`destructive`/`idempotent`/`openWorldHint`), **iş hatası (`isError`) vs protokol hatası (JSON-RPC error)** ayrımı, **SVG/preview/action-list resources.**
10. **Cancellation altyapısı v1:** timeout / child-kill / temp-cleanup **zorunlu** (iç operasyon iptali). MCP protokol `notifications/cancelled` entegrasyonu: SDK/client destekliyorsa v1, desteklemiyorsa aynı altyapı timeout/controlled-abort olarak kullanılır, protokol-cancel **Faz 1.1**.
11. **Preview birinci sınıf ama default payload değil:** mutasyon tool'ları `preview_available`/`preview_resource` döner; image content **talep üzerine** (`render_preview`); yalnız `create_and_preview` gibi workflow tool'ları otomatik preview döner. Boyut limiti + `resource_link`.
12. **Motor yönlendirme (net kural):** `element_update`=**DOM**; `transform`=**DOM baseline**; `path_op`/`export`/`render`/`query`=**Inkscape**. Aynı tool iki motora dağıtılmaz.
13. **Test stratejisi:** DOM golden (kendi deterministik çıktımız) · gerçek Inkscape **E2E** (render/export/query) · visual smoke (property assertion; Inkscape çıktısını **snapshot'lama** — namedview/id'leri yeniden yazar) · sandbox/path-traversal · action-arg validator · state-replay · **lock/concurrency** · **Windows atomic-replace** (aşağıda).
14. **🔬-temelli — ID kararlılığı + id-map:** her tool **`id-preserving`** veya **`id-changing`** etiketlenir; `id-changing` tool'lar `structuredContent`'te **id-map** `{survived:{old→new}, destroyed:[...], created:[...]}` döner; silinmiş id'ye gelen update → etag-staleness'ten **ayrı** bir controlled error sınıfı. *(F8 zorunlu kılar; revision/etag bu failure mode'u kapatmaz.)*
15. **🔬-temelli — Birim/koordinat sözleşmesi:** **tüm tool I/O'su user-unit** (viewBox uzayı); sunucu `--query-all`'in döndürdüğü **px**'i içeride user-unit'e çevirir (`/ (svg_width_px / viewBox_width)`), ham px sızmaz; `info` resource'u `viewBox`/`width_px`/dönüşüm faktörünü döner. *(F5 zorunlu kılar.)*

### Güvenlik (2/3/8 + bunlar)
- Workspace-scope (env root) · path normalize + symlink/traversal testi.
- `shell=True` **asla**; CLI argümanları **liste** olarak.
- Atomik yazma (temp + rename); başarısızlıkta controlled error + temp cleanup.
- İşlem-tipine duyarlı timeout (export/trace tek global timeout'a sığmaz).
- **Hata tespiti stderr-parse ile** (F18): bilinen stderr kalıpları (`could not find action for`, `cannot be opened`, `doesn't exist` …) → tipli controlled error; exit code'a güvenme. *(DeepSeek kör §4.3 kalıp tablosu başlangıç seti.)*
- **Başlangıç varsayılanları** (pin'lenecek, mutlak değil; işlem-tipine duyarlı kurala tabi): command_timeout 30s · max_svg 50MB · max_export 100MB · max_concurrent_sessions 5 · session_ttl 3600s. *(DeepSeek kör README katkısı.)*
- Yıkıcı işlem politikası: **annotation + server policy** (`require_confirmation_for_destructive`) + client destekliyorsa **elicitation**, desteklemiyorsa controlled error. (Elicitation tek-zorunlu mekanizma değil.)
- Hata mesajları dosya sistemi hakkında gereksiz bilgi sızdırmaz.

---

# Bölüm 3 — Sonraki Faz & Araştırma

### Faz-sonrası MCP yüzeyi (v1 kabul kriteri DEĞİL)
`progress` · `elicitation` (opsiyon olarak v1'de) · `completions` · resource `subscriptions` · `prompts`.
Gerekçe: önce çekirdek tool semantiği + dosya/state modeli kanıtlanmalı.

### Ertelenen yetenekler
- **inkex sidecar** (path matematiği, bezier, ileri API) — gömülü `python.exe` alt-süreç olarak. *(⚠️ "tüm path/transform API'si GTK/Cairo'suz çalışır" iddiası DOĞRULANMADI; prototiple kanıtlanmalı.)*
- **`inkex_api_search` / source-intelligence** — kapsam riski (inkex API ≠ extension runtime; "kaynakta gördüm → çalışır" yanılgısı). v1 yerine **doğrulanmış action listesi + `capabilities.json` + elle küratörlü headless-safe allowlist.**
- **Streamable HTTP + çok-kullanıcı** — ancak o zaman `Mcp-Session-Id` + process havuzu + belge↔süreç eşlemesi.
- Capabilities'e dayalı **otomatik tool/resource üretimi.**
- `capabilities.json` **binary-sürümüne pinlenir**; allowlist snapshot'a bağlanır; E2E snapshot'a assert eder (CLI çıktı formatı sürümler arası değişir). *(C maddesi — yeni eksen değil, 5/8/9 + Faz-0 rafinasyonu.)*

### 🔓 Prototipten ÖNCE kapatılması gereken açık problemler
Bunlar "çözüldü" değil — kod yazmadan **küçük bir prototiple sınanmalı:**
1. **DOM ↔ `--shell` state senkronizasyonu** *(en kritik):* DOM diske yazınca `--shell`'in açık belleği bayatlar. Kural: dosya tek doğruluk → her CLI işlemi öncesi `file-open`/reload (performans kazancını kısmen geri verir) **veya** mutasyonlar da `--shell` içinde. Hangisi? Ölç.
2. **Windows dosya davranışı:** DOM temp+replace sırasında Inkscape dosyayı okuyorsa? Export sırasında üzerine yazma çakışması? `file-open→file-close` handle'ı gerçekten serbest bırakıyor mu? Atomik replace başarısızlığında cleanup?
3. **`--shell` cancel/restart sağlamlığı** (madde 7 davranışı).
4. **Headless-safe extension/action allowlist'i** — ampirik olarak hangi action/extension display'siz çalışıyor (F13'ü genişlet).
5. **Görsel geri beslemenin agent-faydası** — PNG render, agent'ın hatayı `query`'den daha iyi teşhis etmesini gerçekten sağlıyor mu? (Ölçülmemiş varsayım.)

### Önerilen ilk prototip kapsamı (riskleri erken eritmek için)
`document_create` + `element_create` (DOM) + `query` + `export` + `render_preview` + `run_actions(path_op)`,
**lock + revision** ile, **Windows'ta**, **gerçek E2E** testiyle. Bu minimal set en riskli 5 varsayımı
(DOM/shell sync, birim, id-map, Windows handle, selection-replay) bir arada sınar.

---

*Provenans: README.md (DeepSeek vizyonu) → codex-readme.md (Codex MVP notu) → claudan-codexe-eleştiri\[-2/-3\].md
(Claude) ↔ codexten-claude-eleştiri\[-2\].md (Codex) → bağımsız hakem (gpt-5.5/xhigh). 🔬 gerçekler
yerel `inkscape.com` 1.4.2 ile doğrulandı. Tarih: 2026-05-29. Durum: **v1 sözleşmesi — prototiple sınanacak.***

*Ek (kör yeniden-test sonrası): F18, F19 ve başlangıç varsayılanları, DeepSeek'in binary-erişimli kör tasarım denemesinden — binary ile teyit edilerek — kontrata alınmıştır. (Kör deneme `tool-rect` keystone'unu yine kaçırdı; ama bu empirik ayrıntıları doğru üretti.)*
