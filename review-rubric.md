# Inkscape MCP — Uygunluk Review Rubric'i (v1)

> **Ne için:** DeepSeek'in `architecture-v1.md`'ye göre yazacağı kodu denetlemek için somut,
> test-edilebilir kontrol listesi. Her kontrol: **ne olmalı · nasıl doğrulanır (grep/davranış) ·
> kırmızı bayraklar.** `🔬`-temelli kontroller `reference/` golden'larına bağlıdır.
>
> **Nasıl kullanılır:**
> - **Manuel kapı:** Hiçbir 🔴 **blocker** açık kalmadan PR merge edilmez.
> - **`/code-review max|ultra`** → genel bug/cleanup (bu rubric'i context olarak ver).
> - **Conformance workflow'um** → her maddeyi koda karşı denetler (bu dosya = girdisi).
> - **`/security-review`** → C bölümü (sandbox, enjeksiyon, shell).
> - **`/verify`** → D bölümündeki davranış testleri (özellikle F5 birim, F8 id-map) gerçek binary'de.
>
> **Severity:** 🔴 blocker (merge engeller) · 🟠 major (düzeltilmeli) · 🟡 minor (iyileştirme).
> **Toplam: 47 kontrol — 29 🔴 · 15 🟠 · 3 🟡.**

| Bölüm | 🔴 | 🟠 | 🟡 |
|---|---|---|---|
| A. Durum & Tutarlılık | 5 | 1 | 0 |
| B. Motorlar & Adresleme | 6 | 2 | 0 |
| C. CLI Güvenlik & Escape-hatch | 9 | 6 | 1 |
| D. MCP Yüzeyi & Doğruluk | 9 | 6 | 2 |

---

## A. Durum & Tutarlılık (lock / revision / dosya-otorite)

### 🔴 Madde 1 — Tek doğruluk kaynağı = dosya
- **Olmalı:** Tüm query/export/path_op/render diskten okur; mutasyon diske atomik yazar; bellekteki Inkscape/`--shell` belgesi **otorite değil**.
- **Doğrula:** Query/export handler'ı işlem öncesi `file-open`/reload yapıyor mu? Uzun-ömürlü in-memory tree/shell'den servis ediyorsa 🔴. Davranış: dosya dışarıdan değişince query güncel değeri dönmeli. Grep: `file-open`,`reload`,`self.tree`,`cached`.
- **🚩** in-memory tree/shell'i otorite saymak · write-back cache · iki "güncel" kopya belirsizliği.

### 🔴 Madde 1/F10 — DOM yazınca `--shell` belleği bayat
- **Olmalı:** DOM diske yazınca açık `--shell` belgesi bayat sayılır → her CLI işlemi öncesi shell'de `file-open`/reload **veya** mutasyonlar da shell içinde.
- **Doğrula:** Shell wrapper'da invalidation/reload kancası var mı? Yoksa 🔴. Davranış: DOM ile fill değiştir→yaz→shell query → yeni değer yansımalı. Grep: `shell`,`reload`,`stale`,`invalidate`.
- **🚩** shell belgesini reload'suz tekrar kullanmak · DOM↔shell arası sinyal yokluğu · reload'u sadece dokümante edip kodlamamak.

### 🔴 Madde 2 — Belge başına lock/mutex
- **Olmalı:** Aynı belgede DOM-write/file-open/export/path-op/save/preview **serileştirilir**; lock anahtarı = normalize edilmiş yol (global tek lock değil).
- **Doğrula:** Per-doc lock map'i (`locks[path]=Lock()`) var mı? Hiç yoksa 🔴, tek global ise 🟠. Tüm mutasyon+export+path-op+preview `async with lock` içinde mi? Anahtar `realpath`+casefold mı (Windows)? Davranış: 2 eşzamanlı mutasyon → ikincisi bekler. Grep: `Lock`,`async with`,`acquire`,`realpath`.
- **🚩** kilit yok · bazı işlemler (export) lock dışında · anahtar normalize edilmemiş · finally'de release atlanmış (deadlock).

### 🔴 Madde 3 — Revision/etag (optimistic concurrency)
- **Olmalı:** Belge başına monotonik revision; her mutasyon artırır; tool'lar opsiyonel `expected_revision` alır; stale → controlled error (isError, **JSON-RPC error değil**); resource'lar `revision` içerir.
- **Doğrula:** `revision += 1` her mutasyonda mı? `expected_revision` schema'da + gerçekten kontrol ediliyor mu? Stale'de mutasyon **uygulanmıyor** mu? structuredContent'te revision dönüyor mu? Davranış: rev=5, expected=4 → controlled error + revision değişmedi. Grep: `expected_revision`,`revision`,`stale`,`isError`.
- **🚩** revision artmıyor/sadece save'de · expected_revision yok sayılıyor · stale'de önce uygulayıp sonra hata · stale'i JSON-RPC error yapmak · revision'ı diske bağlamayıp restart'ta sıfırlamak.

### 🔴 Madde 3/F8+14 — Silinmiş id ≠ stale revision
- **Olmalı:** Yok olmuş id'ye (path-union sonrası c1) gelen mutasyon, revision uyumlu **olsa bile** ayrı bir "id-not-found/destroyed" controlled error döner.
- **Doğrula:** id-lookup başarısızlığı revision-staleness'ten **farklı** error kodu mu? Davranış: `after-object-to-path-then-union` baz alıp c1'e set-attribute → revision güncel olsa da id-not-found. Grep: `id_not_found`,`destroyed`,`id_map`.
- **🚩** yok olmuş id'yi sadece revision'a bakıp kabul · id-not-found ile stale'i aynı sınıfa toplamak · id-map üretmemek.

### 🟠 Madde 2+7 — Cancel/reload lock altında
- **Olmalı:** Komut takılınca kill+"unknown"+dosyadan reopen; bu lock'u **tutarken** olur; reload sonrası revision dosyadan türetilir.
- **Doğrula:** Kill yolu lock'u erken bırakıyorsa 🟠; kill sonrası eski bellek kullanılıyorsa 🔴. Grep: `kill`,`unknown`,`reopen` lock kapsamında.
- **🚩** kill'i lock dışında yapmak · kill sonrası bellek state'iyle devam · timeout'ta süreci asılı bırakmak (deadlock).

---

## B. Motorlar & Adresleme (DOM yaratım vs Inkscape işlem)

### 🔴 F3 — Şekil yaratan action ÇAĞRILMAZ
- **Olmalı:** Kod tabanında `tool-rect`/`tool-*`/`create-*`/`draw-*` gibi **uydurma** action adı yok; allowlist sadece `reference/`'ta gerçekten var olan adları içerir; yaratım isteği DOM motoruna gider.
- **Doğrula:** Koddaki tüm action string'lerini `reference/action-list-full.txt`'e karşı doğrula. Şu regex match ederse 🔴: `tool-rect|tool-ellipse|create-rect|create-ellipse|draw-path|draw-rect|new-rect`. Yaratım handler'ında subprocess **olmamalı**.
- **🚩** allowlist'e var olmayan ad · yaratımdan Inkscape çağrısı · `--shell` string'ine şekil action'ı · oracle'a karşı test yok.

### 🔴 F4 — Yaratım yalnız lxml/inkex (Inkscape çalışmadan)
- **Olmalı:** element_create/document_create lxml DOM (veya in-process inkex); çıktı `after-inkex-create-rect.svg` golden'ına **property** bazında eşleşir.
- **Doğrula:** Yaratım modülünde `lxml.etree`/`inkex` var, subprocess **yok**. Golden byte-snapshot değil property-assert. Grep: yaratım yolunda `Popen`/`run` olmamalı.
- **🚩** yaratımı CLI'a delege · atomik olmayan DOM yazımı · byte-snapshot golden · string concat ile SVG (namespace bozulması).

### 🔴 F7 — Action'lar selection-tabanlı (önce `select-by-id`)
- **Olmalı:** Her selection-tabanlı action'ın (transform-*, path-*, object-set-attribute) hemen önünde `select-by-id:<id>`; çok-operandlı path-union için her operand ayrı `select-by-id`.
- **Doğrula:** Action zinciri kurucu, her action'dan önce `select-by-id` üretiyor mu? `after-object-to-path-then-union` zinciri: `select-by-id:r1;select-by-id:c1;object-to-path;path-union`. select-by-id'siz zincir → 🔴.
- **🚩** select-by-id'siz zincir (sessiz no-op) · deprecated `select` kullanımı · path-union'a tek operand · selection temizlenmeden iki mutasyon karışması.

### 🟠 F9 — transform-translate `transform` attr eklemez, x/y bake eder
- **Olmalı:** Translate sonucu `transform=` attr **içermez**; x/y doğrudan güncellenir (DOM baseline bunu taklit etmeli).
- **Doğrula:** Çıktıda `transform=` substring'i varsa 🟠. `after-transform-translate.svg`: r1 x 10→110, transform yok. DOM translate rect→x+dx, circle→cx+dx.
- **🚩** `transform=translate(...)` eklemek · circle'da cx/cy yerine yanlış attr · byte-snapshot · negatif/taşma ele alınmamış.

### 🔴 Madde 4 — Yaratım + basit update = DOM; atomik yazma
- **Olmalı:** element_create + element_update lxml DOM; temp+`os.replace` ile atomik; CLI'a gitmez.
- **Doğrula:** Dispatcher element_update'i DOM'a yönlendiriyor mu? Yazma `tempfile`+`os.replace` mı? CLI çağrısı yalnız query/export/render/path_op'ta mı? 
- **🚩** element_update → object-set-attribute (CLI) · doğrudan hedefe yazma · yaratım/update farklı motorlara · regex/string ile manipülasyon.

### 🔴 Madde 5 — Inkscape CLI yalnız query/export/render/path-boolean/font→path
- **Olmalı:** Bu liste dışı (özellikle yaratım/update) CLI çağırmaz; argümanlar **liste** olarak, `shell=True` yok; path boolean gerçek action adları (`path-union` vb.).
- **Doğrula:** Tüm Inkscape çağrı noktaları yalnız izinli handler'lardan mı geliyor? `shell=True` grep → boş. font→path doğru action mı?
- **🚩** yaratım için CLI · shell=True/string concat · uydurma path action · yanlış font→path action.

### 🟠 Madde 6 — ID-merkezli; kalıcı selection yok
- **Olmalı:** Tool'lar nesneyi ID ile hedefler; kalıcı `selection` state saklanmaz; her çağrı ephemeral `select-by-id` replay.
- **Doğrula:** Sunucu-ömrü boyunca yaşayan `self.selection`/`selected_ids` alanı varsa 🟠. Replay + gerekirse `select-clear` var mı?
- **🚩** kalıcı selection state · API'nin "selection sakla" beklemesi · deprecated `select` · path-union'da operand sırası garantisiz.

### 🔴 Madde 12 — Motor yönlendirme: bir tool tek motor
- **Olmalı:** element_update=DOM, transform=DOM baseline, path_op/export/render/query=Inkscape; aynı tool iki motora **dağılmaz** (fallback yok).
- **Doğrula:** Merkezi dispatcher her tool tipine tek motor atıyor mu? Bir tool içinde "önce DOM, olmazsa Inkscape" dallanması varsa 🔴. transform DOM baseline mı (Inkscape transform-translate'e gitmiyor)?
- **🚩** transform → Inkscape · tool içi çift-motor fallback · query/export DOM'da taklit · dağıtık/hardcode yönlendirme · element_update → CLI.

---

## C. CLI Güvenlik & Escape-hatch (`--shell` / `run_actions` / cancellation / sandbox)

### 🟠 Madde 7/F10 — `--shell` opsiyonel, default process-per-call
- **Olmalı:** v1 default = çağrı-başına subprocess; `--shell` yalnız açık flag ile.
- **Doğrula:** Motor router default branch'i `Popen`/`run` mı? `--shell` flag arkasında mı? Default shell ise 🔴(→🟠).
- **🚩** her şeyi shell'e yönlendirip baseline'ı kurmamak · shell'i default açık · prototip kanıtlanmadan shell'i varsayılana terfi.

### 🔴 Madde 7 — Cancel/restart sertliği
- **Olmalı:** Takılınca child kill (Windows tree-kill) + state "unknown" + dosyadan reopen.
- **Doğrula:** Timeout handler'da kill + unknown bayrağı + reopen var mı? Davranış: hang simülasyonu → PID ölü + sonraki işlem dosyadan açıyor. Sadece exception atan → 🔴.
- **🚩** sadece exception, child zombi · reset'siz tekrar kullanım · unknown işaretleyip reload'suz devam.

### 🔴 Madde 8 — Action-adı ALLOWLIST (denylist değil)
- **Olmalı:** `run_actions` yalnız server-side, headless-safe **allowlist**'ten; `action-list-full.txt` snapshot'ına bağlı; liste dışı → reddedilir.
- **Doğrula:** `if name not in ALLOWED_ACTIONS: reject` var mı? Davranış: `tool-rect`/`window-open` reddedilir. Denylist veya allowlist yokluğu → 🔴.
- **🚩** denylist · runtime'da agent girdisiyle genişletme · snapshot'a bağlamama.

### 🔴 Madde 8 — Per-action argüman şeması
- **Olmalı:** Her allowlist girişinin argüman şeması var (`core-actions.txt` usage'ları referans: `object-set-attribute:ad,değer`, `transform-translate:dx,dy`); şema-dışı reddedilir.
- **Doğrula:** Her giriş validator/şema taşıyor mu? Davranış: transform-translate'e sayısal-olmayan/`;` içeren argüman reddedilir. Sadece ad-allowlist → 🔴.
- **🚩** generic tek validator · argümanı ham geçirme · gömülü `;`/zincir enjeksiyonuna izin.

### 🔴 Madde 8 — Path sandbox + yolları SUNUCU üretir
- **Olmalı:** Agent yol vermez, mantıksal ad verir; sunucu workspace-root altında gerçek yolu üretir; `export-filename`/`file-open`/`file-rebase` argümanları agent ham girdisinden **gelmez**; `realpath`+symlink/traversal reddi.
- **Doğrula:** Yol-alan action argümanı server-resolve mu? Davranış: `export-filename:C:\Windows\evil.png` veya `../../` → reddedilir/server-yoluyla değiştirilir. Agent string'ini doğrudan konkatlayan → 🔴.
- **🚩** agent yolunu sadece validate edip kullanma · prefix-string karşılaştırması (realpath yok) · workspace dışı mutlak/UNC yol.

### 🔴 Madde 8/F13 — GUI action'ları reddet
- **Olmalı:** `window-*`, `file-open-window`, `active-window-*`, `*-on-canvas`, `window-crash` allowlist'**te yok** ve reddedilir.
- **Doğrula:** Allowlist bu adları içermiyor. Davranış: `run_actions("window-open")` → çalıştırılmadan controlled error.
- **🚩** GUI action'ı allowlist'e koyup runtime hatasına bırakmak · `window-crash`'i engellememek.

### 🟠 Madde 8/F12 — `--actions-file` `;` ayracı
- **Olmalı:** actions-file `;` ile ayrılır (satır-başı değil); server allowlist'ten geçmiş action'ları `;`.join ile yazar.
- **Doğrula:** Birleştirici `';'.join` mı? Newline-only format → 🟠.
- **🚩** newline ayraç · agent ham metnini yazma · argümandaki gömülü `;` enjeksiyonu.

### 🟠 F11 — `--batch-process` KULLANILMAZ
- **Olmalı:** Saf `--actions`/`--shell`/`--export-*`; `--batch-process` yok.
- **Doğrula:** `grep '--batch-process'` → boş olmalı. Varsa 🟠.
- **🚩** "kararlılık için" batch eklemek · GUI uyarılarını yanlış bayrakla bastırmak.

### 🔴 F5/Madde 15 — query px → user-unit çevrimi (C tarafı tekrar; D'de de var)
- **Olmalı:** `--query-all` px döndürür; server `/ (svg_width_px/viewBox_width)` ile user-unit'e çevirir; ham px sızmaz.
- **Doğrula:** Query handler bölme faktörüyle düzeltiyor mu? Davranış: mm-SVG'de x=10 user → query 37.7953px → handler **10** dönmeli. Çiplak px → 🔴.
- **🚩** ham px dönmek · sabit 96/25.4 varsaymak · sadece faktör=1 SVG ile test (bug maskelenir).

### 🔴 Madde 10 — Timeout zorunlu (işlem-tipine duyarlı)
- **Olmalı:** Her subprocess timeout ile; export/trace ≠ query tek global timeout.
- **Doğrula:** `subprocess.run(timeout=...)` + tip-bazlı `TIMEOUTS` map var mı? `timeout=None` → 🔴.
- **🚩** timeout yok (sonsuz hang) · tek global timeout · timeout'ta kill yok.

### 🔴 Madde 10 — Child-kill zorunlu
- **Olmalı:** Timeout/iptal'de child (Windows'ta süreç ağacı) kesin öldürülür; orphan yok.
- **Doğrula:** `TimeoutExpired` yakalanınca `Popen.kill()` (+ tree-kill) çağrılıyor mu? try/finally garantisi? Davranış: hang → PID ölü.
- **🚩** TimeoutExpired'ı yakalayıp kill'siz devam · Windows'ta sadece parent kill · kill happy-path'te (finally değil).

### 🟠 Madde 10 — Temp-cleanup zorunlu
- **Olmalı:** Temp dosya/dizinler her sonuçta (başarı/hata/timeout) temizlenir; atomik replace fail'de controlled error + cleanup.
- **Doğrula:** `tempfile.*` try/finally/context-manager ile mi? Davranış: export'ta hata → workspace'te temp kalmamalı.
- **🚩** sadece happy-path silme · exception'da mkdtemp kalması · replace fail'de yarım temp.

### 🔴 Güvenlik — `shell=True` ASLA + args liste
- **Olmalı:** Hiçbir subprocess `shell=True` yok; argümanlar **liste**; string concat ile komut kurma yok.
- **Doğrula:** `grep 'shell=True'` → boş. `os.system`/`os.popen`/`' '.join(cmd)` → 🔴. Davranış: `export-filename` içine `; rm` → tek argüman, ek komut çalışmaz.
- **🚩** shell=True · os.system/popen · argümanı tek string geçmek.

### 🟠 Güvenlik — Atomik yazma (temp+replace)
- **Olmalı:** Temp'e yaz → `os.replace` (Windows) ile atomik taşı; yarım dosya görünmez.
- **Doğrula:** `os.replace` + temp-write deseni var mı? Doğrudan `open(target,'w')` → 🟠. Davranış: yazma ortasında hata → hedef bozulmamış.
- **🚩** in-place yazma · `os.rename` (Windows'ta hedef-var hatası) · replace fail'de eski içerik kaybı.

### 🟠 Güvenlik — Yıkıcı işlem politikası
- **Olmalı:** delete/file-rebase/overwrite-export/path-union → `destructiveHint` + server policy (`require_confirmation_for_destructive`) + client destekliyorsa elicitation, yoksa controlled error. Elicitation **tek zorunlu mekanizma değil**.
- **Doğrula:** Yıkıcı tool'da destructive annotation + policy gate var mı? Davranış: policy açık + elicitation yok → controlled error. Sadece elicitation'a bel bağlamak → 🟠.
- **🚩** destructive annotation yok · sadece elicitation · destek yokken sessizce çalıştırma.

### 🟡 Güvenlik — Hata mesajları FS sızdırmaz
- **Olmalı:** Mutlak yol/iç dizin/ham stderr/traceback agent'a sızmaz; sanitize edilir.
- **Doğrula:** `str(exception)`/stderr ham mı dönüyor? Davranış: workspace-dışı denemede mesajda mutlak yol görünmemeli.
- **🚩** ham str(exception)/stderr · mutlak yol metinde · traceback client'a.

---

## D. MCP Yüzeyi & Doğruluk (schema / annotations / id-map / birim / test)

### 🔴 Madde 9 — inputSchema (her tool)
- **Olmalı:** Her tool geçerli JSON Schema inputSchema (type=object, properties, required, `additionalProperties:false`); server-üretimi alanlar (yollar, id-map iç state) **istenmez**.
- **Doğrula:** tools/list'te her inputSchema Draft-2020-12 parse oluyor mu? Geçersiz girdi dispatch'tan **önce** reddediliyor mu? Grep: `additionalProperties:false`.
- **🚩** inputSchema yok/boş · additionalProperties açık · dosya yolu agent girdisi (Madde 8 ihlali) · şema var ama runtime validasyon yok.

### 🔴 Madde 9 — outputSchema + structuredContent
- **Olmalı:** Her tool outputSchema yayınlar VE başarıda `structuredContent` döner (şemaya valid); yalnız text content yetersiz.
- **Doğrula:** Tool çağır → structuredContent var + `jsonschema.validate` geçer mi? Sadece `{'content':[...]}` dönen mutation/query → 🔴.
- **🚩** sadece text content · outputSchema↔structuredContent uyumsuzluğu · id-map text'e gömülü.

### 🔴 Madde 9 — Annotations doğruluğu
- **Olmalı:** query/render/export → `readOnlyHint:true`,`destructiveHint:false`; delete/path_op(union) → `destructiveHint:true`; idempotent olanlar → `idempotentHint:true`; hepsi `openWorldHint:false` (lokal).
- **Doğrula:** annotations tablosunu Madde 12 ile çapraz kontrol: query/export readOnly **true**, union/delete destructive **true**. readOnly tool'un dosyaya yazması çelişki → 🔴. Annotations yoksa → 🔴.
- **🚩** mutasyona readOnly:true (en tehlikeli) · union/delete'e destructive yok · annotations atlanmış · openWorldHint:true.

### 🔴 Madde 9 — isError (iş) vs JSON-RPC error (protokol)
- **Olmalı:** Geçersiz id/stale revision/silinmiş-id/sandbox-dışı yol/Inkscape başarısızlığı → `isError:true`+content (protokol-başarılı). Yalnız hatalı method/şema → JSON-RPC error.
- **Doğrula:** (a) olmayan tool → JSON-RPC error; (b) olmayan element id ile query → `result.isError==true`. Domain hatasını raw raise eden handler şüpheli.
- **🚩** domain hatası JSON-RPC error olarak · Inkscape non-zero exit yutulup başarılı görünmek · tüm hatalar tek yola indirgenmiş.

### 🟠 Madde 9 — SVG + preview + action-list resources
- **Olmalı:** En az 3 resource: SVG (revision'lı), preview (PNG), action-list/capabilities (`action-list-full.txt`=1072'den).
- **Doğrula:** resources/list bunları listeliyor mu? SVG resource'da revision var mı? action-list içeriği 1072 ile tutarlı mı (spot-check)? Hiç resource yoksa → 🟠.
- **🚩** bunları tool yapmak (resource yüzeyi eksik) · SVG'de revision yok · action-list elle yazılmış.

### 🟠 Madde 11 — Preview default payload DEĞİL
- **Olmalı:** Mutasyon tool'ları image content **döndürmez**; `preview_available`+`preview_resource` döner; gerçek image yalnız `render_preview`/`create_and_preview`.
- **Doğrula:** element_update/transform/path_op çağır → `content`'te `type==image` **yok**, structuredContent'te preview_resource var. Mutasyonda base64/PNG üreten kod → 🟠.
- **🚩** her mutasyonda otomatik PNG · inline image (resource_link yok) · render_preview ayrı tool yok.

### 🟡 Madde 11 — Preview boyut limiti + resource_link
- **Olmalı:** Image boyut limiti; aşılırsa inline yerine resource_link.
- **Doğrula:** `MAX_PREVIEW_BYTES` + resource_link devri var mı? Limitsiz base64 → 🟡.
- **🚩** limitsiz base64 · limit aşımında hata (resource_link'e düşmüyor).

### 🟠 Madde 13 — DOM golden (kendi deterministik çıktımız)
- **Olmalı:** DOM üretimi (create/update/DOM-transform) için golden testler; bunlar **bizim** çıktımız (Inkscape round-trip değil); `after-inkex-create-rect.svg` ile hizalı.
- **Doğrula:** Golden DOM çıktısı mı (Inkscape değil)? after-inkex... DOM golden; after-shell/after-transform Inkscape-yeniden-yazımı → DOM golden olarak **kullanılmaz**.
- **🚩** DOM golden yok · Inkscape-yeniden-yazılmış fixture'ı DOM golden yapmak · non-deterministik (timestamp/random id) golden.

### 🟠 Madde 13 — Gerçek Inkscape E2E
- **Olmalı:** Gerçek `inkscape.com` 1.4.2 ile query/export/render E2E (mock değil); binary sürümüne pinli.
- **Doğrula:** Gerçek subprocess çağıran E2E var mı (binary yoksa skip-marker, ama tamamen mock değil)? query E2E px'i (F5) sonra user-unit'e çeviriyor mu?
- **🚩** her şey mock · sürüm pin yok · query E2E user-unit çevrimini test etmiyor.

### 🔴 Madde 13 — Visual smoke = property assertion; BYTE-SNAPSHOT YASAK
- **Olmalı:** Inkscape SVG çıktısı byte-byte/tam-string snapshot ile **test edilmez** (Inkscape namedview/namespace/id ekler, attr sırası yeniden yazar); property assertion (fill, x, node sayısı).
- **Doğrula:** `assertEqual(full_svg, golden)`/`toMatchSnapshot` Inkscape çıktısında → 🔴. XML parse edip node/attr assert mı?
- **🚩** Inkscape çıktısı tam-string snapshot · namedview/namespace beklenen çıktıya dahil · attr sırasına bağımlı karşılaştırma.

### 🟠 Madde 13 — Lock & concurrency testi
- **Olmalı:** Madde 2 lock'u testle: aynı belgede eşzamanlı çağrılar serileşiyor mu, revision tutarlı artıyor mu.
- **Doğrula:** Paralel/threaded 2 çağrı + bozulmama + lock'un birini beklettiği test var mı? Lock var ama testsiz → 🟠.
- **🚩** lock kodu var test yok · global lock granülaritesi · sahte test (gerçek paralellik yok).

### 🟠 Madde 13 — Windows atomic-replace testi
- **Olmalı:** `os.replace` ile atomik; Windows'a özgü: hedef Inkscape tarafından tutulurken davranış, fail'de controlled error + cleanup.
- **Doğrula:** temp+`os.replace` var mı? Test: replace'te hata → orijinal bozulmaz + temp temizlenir. Bare `open(path,'w')` → 🔴 risk.
- **🚩** doğrudan hedefe yazma · `os.rename` (POSIX varsayımı) · fail'de temp kalması · Windows testi yok.

### 🔴 Madde 14 — Her tool id-preserving | id-changing etiketli
- **Olmalı:** Tool registry'de etiket; F8 ile **doğru**: object-to-path(tek)/group-ungroup/transform=preserving; path-union/difference/delete=changing.
- **Doğrula:** Etiket F8 ile çapraz: transform=preserving (`after-transform-translate`), union=changing (`after-object-to-path-then-union`: c1 yok). Yanlış etiket → 🔴.
- **🚩** etiket yok · union'ı preserving · transform'u changing · yanlış sabit etiket.

### 🔴 Madde 14 — id-changing tool'lar GERÇEK id-map döner
- **Olmalı:** structuredContent'te `{survived:{old→new}, destroyed:[...], created:[...]}`; gerçek SVG sonucundan **türetilir** (sabit/boş değil). union: destroyed:[c1], survived r1, created:[].
- **Doğrula:** base-input → object-to-path+union gerçek çalıştır; id-map'i fixture ile karşılaştır (destroyed=c1). Hep boş/hardcoded → 🔴. id-map op-öncesi/sonrası id kümelerini diff'liyor mu?
- **🚩** id-map boş/null · hardcoded · c1 destroyed raporlanmıyor · id-map text'e gömülü.

### 🔴 Madde 14 — Silinmiş-id update = AYRI controlled error
- **Olmalı:** Yok olmuş id'ye update, stale-revision'dan **ayrı** error code/type (isError, JSON-RPC değil).
- **Doğrula:** union(c1 yok)→c1 güncelle → "unknown id" (stale değil). İki ayrı error sınıfı var mı (`ErrUnknownId` vs `ErrStaleRevision`)? Tek genele indirgeme → 🔴.
- **🚩** silinmiş-id ile stale aynı koda map · sessiz no-op · JSON-RPC error · sadece etag, id-varlık kontrolü yok.

### 🔴 Madde 15/F5 — Tüm tool I/O user-unit
- **Olmalı:** Girdi/çıktı user-unit; server px'i `/ (svg_width_px/viewBox_width)` ile çevirir; ham px sızmaz; element_update girdisi user-unit → DOM'a user-unit.
- **Doğrula:** mm-SVG ile query → x=10 user (px 37.7953 değil). **Tuzak:** base-input.svg faktör=1.0 (bug'ı maskeler) → mm/farklı-viewBox fixture şart. Çevrim faktörü viewBox'tan türetiliyor mu?
- **🚩** ham px · sabit 96/25.4 · sadece dpi · faktör=1 SVG ile test · element_update girdisini px sanmak.

### 🟡 Madde 15 — info resource viewBox/width_px/faktör döner
- **Olmalı:** info/document-info resource'u viewBox + width_px + px↔user-unit faktörünü döner.
- **Doğrula:** info'da viewBox/width_px/factor var mı, belgeyle tutarlı mı? base-input: viewBox `0 0 200 200`, width_px=200, factor=1.0.
- **🚩** faktör dönmüyor · çok-değer/transform'da yanlış · info resource yok.

---

## Araç → bölüm eşlemesi (review akışı)

| Araç | Birincil bölümler |
|---|---|
| **Manuel blocker kapısı** | Hepsi — 29 🔴'nin sıfır açık |
| **`/code-review max\|ultra`** | Genel bug/cleanup (bu rubric context) + B, D doğruluk |
| **Conformance workflow'um** | Tüm 47 madde, koda karşı (grep + davranış) |
| **`/security-review`** | C tamamı (allowlist, arg-şema, path-sandbox, shell, FS-leak) |
| **`/verify`** | D davranış testleri gerçek binary'de: F5 birim, F8 id-map, lock/concurrency, Windows atomic-replace |

---

*Üretim: `architecture-v1.md` (15 karar + 17 gerçek) + `reference/` golden'ları, 4-ajanlı fan-out
ile. 🔬 kontroller yerel `inkscape.com` 1.4.2 çıktılarına bağlı. Tarih: 2026-05-29.*
