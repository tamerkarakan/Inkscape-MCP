# DeepSeek için Teslim Brief'i — Inkscape MCP kodlaması

> **Sen (DeepSeek-V4-Pro) kodu yazacaksın; Claude + Codex review edecek.** Bu brief, kodu
> **review'dan ilk geçişte** geçecek şekilde yazman için gereken her şeyi veriyor: bağlayıcı
> kontrat, kullanacağın yer-gerçeği, düşmemen gereken tuzaklar ve kabul kriterleri.

---

## ⚠️ ÖNCE BUNU OKU — okuyacağın (ve okumayacağın) dosyalar

Kafan karışmasın diye **yalnızca şu 4 kaynağı oku:**
1. **`brief-for-deepseek.md`** — bu dosya (yönlendirme).
2. **`architecture-v1.md`** — BAĞLAYICI KONTRAT (asıl spec: 17 gerçek + 15 karar).
3. **`reference/`** (tamamı) — yer-gerçeği: action envanteri (`core-actions.txt`, `action-list-full.txt`) + golden fixture'lar (`fixtures/`).
4. **`review-rubric.md`** — nasıl review edileceğin (47 kontrol). Bunu bilerek yaz; "teaching to the test" değil, doğru mühendislik.

**ŞUNLARI OKUMA** (tarihsel diyalog/provenance — eski/yanlış varsayımlar ve tartışma içerir, kafa karıştırır):
- `README.md` ← senin ilk vizyonun; **`tool-rect` hatası burada**, tekrar okuma.
- `codex-readme.md`, `claude-readme.md`
- `claudan-codexe-eleştiri*.md`, `codexten-clauda-eleştri.md`, `codexten-claude-eleştiri-2.md` (Claude↔Codex tartışması)

> Tek geçerli kaynak **`architecture-v1.md`**'dir. Herhangi bir çelişkide **kontrat kazanır.**

---

## 0. Durum (kısa hikâye, çünkü bağlam önemli)

Senin yazdığın ilk `README.md`, harika bir vizyondu **ama mimari çekirdeği yanlış bir varsayıma
dayanıyordu:** "şekilleri `tool-rect;transform-scale:...` gibi `--actions` zincirleriyle çiz."
Gerçek binary ile test edildi: **Inkscape 1.4.2'de `tool-rect` diye bir action YOK; hiçbir `tool-*`
yok; primitif geometri yaratan HİÇBİR action yok** (1072 action tarandı). Yani o mekanizma
çalışmıyor — uydurma bir action yüzeyiydi.

Bunun üzerine Claude ↔ Codex çok turlu bir tasarım diyaloğu yürüttü, her iddia binary'de
doğrulandı ve ortak bir kontratta (`architecture-v1.md`) yakınsadı. **Senden istenen: o kontratı
uygulamak.** Tek kural: **uydurma, doğrula** (aşağıdaki `reference/` tam da bunun için).

---

## 1. Bağlayıcı kontrat: `architecture-v1.md`

Bu **kabul kriteri**dir, ilham değil. İçinde:
- **Bölüm 1 — 17 doğrulanmış gerçek (F1–F17):** binary'nin ne yapıp yapamadığı.
- **Bölüm 2 — 15 bağlayıcı karar:** ne inşa edeceğin (motor modeli, tool'lar, güvenlik).
- **Bölüm 3 — sonraki faz + 5 açık problem + ilk prototip kapsamı.**

Kodun bu 15 kararın her birini karşılamalı ve 17 gerçekle çelişmemeli. Review tam olarak bunu
denetleyecek.

---

## 2. Yer-gerçeği: `reference/` (UYDURMA — buradan oku)

`reference/README.md`'yi oku. İçinde:
- **`action-list-full.txt`** (1072 action) + **`core-actions.txt`** (çekirdek yüzey, açıklama +
  **usage string'leriyle**). Tipli tool'ların hangi gerçek action'a map'lendiğini ve argüman
  formatını **buradan** al. Bir action'ın var olduğunu varsayma — listede yoksa yoktur.
- **`fixtures/`** — operasyonların gerçek Inkscape çıktıları (golden oracle). Örn.
  `after-object-to-path-then-union.svg`, `path-union` sonrası `c1`'in **yok olduğunu** kanıtlar.
  Bunlar senin testlerinin beklenen-çıktı referansıdır.

---

## 3. Düşmeyeceğin 7 tuzak (HARD RULES — her biri binary ile kanıtlı)

1. **F3/F4 — Geometriyi action ile YARATMA.** Yeni rect/circle/path/text → **lxml/DOM** (veya
   inkex) ile yaz, dosyaya **atomik** kaydet. CLI'dan şekil yaratmayı bekleme. *(Yaratım motoru.)*
2. **F5/Madde 15 — `--query-all` CSS px (96dpi) döndürür, user-unit DEĞİL.** mm+viewBox'lu belgede
   DOM koordinatıyla **ayrışır** (çarpan = `svg_width_px / viewBox_width`). **Tüm tool I/O'su
   user-unit olmalı**; px'i içeride sen çevir, agent'a ham px sızdırma.
3. **F8/Madde 14 — ID'ler operasyona göre yok olur.** `path-union/difference` girdi nesnelerini
   tek `<path>`'e indirir, **en alttaki operandın id'si kalır, diğerleri silinir.**
   `id-changing` tool'lar `structuredContent`'te **id-map** `{survived,destroyed,created}` döndürsün;
   silinmiş id'ye gelen update → ayrı bir controlled error. (etag bunu yakalamaz.)
4. **F7 — Action'lar selection-tabanlı.** Mevcut nesneye işlem yaparken zincire **önce
   `select-by-id`** koy; selection kalıcı değil, her çağrıda replay et.
5. **F10/F11 — `--batch-process` KULLANMA.** Saf `--actions`/`--shell`/`--export-*` kullan
   (`--batch-process` fazladan GUI stack açar). `--shell` belge durumunu korur ama v1'de **zorunlu
   varsayılan motor değil** (Madde 7); takılırsa süreci öldür, durumu "unknown" say, dosyadan reopen.
6. **F12 — `--actions-file` ayraç olarak `;` bekler**, satır-başı-action DEĞİL. (Yanlış parse eder.)
7. **F13/F15 — GUI gerektiren action'lar headless'ta patlar** (`window-*`, `file-open-window`).
   `--app-id-tag` ile "izolasyon" geçersiz; izolasyon **workspace/temp** ile.

---

## 4. İlk teslim = prototip (tüm sunucu değil)

`architecture-v1.md` Bölüm 3'teki minimal kapsamla başla; en riskli varsayımları bir arada sınar:

> `document_create` + `element_create` (DOM) + `query` + `export` + `render_preview` +
> `run_actions(path_op)`, **belge başına lock + revision** ile, **Windows'ta**, **gerçek Inkscape
> E2E testiyle.**

Bu, DOM↔`--shell` senkronizasyonu, birim dönüşümü, id-map, Windows dosya-handle ve selection-replay
varsayımlarını birlikte test eder. Tüm 110-tool kataloğunu ilk turda yazma.

---

## 5. Review nasıl yapılacak = senin kabul kriterlerin

Kodun şuna göre puanlanacak (bunları baştan karşıla):
- **Conformance:** 15 kararın her birini koddan gösterebilmeli (`/code-review` + spec-conformance
  workflow + `/security-review` + `/verify` ile çapraz denetlenecek).
- **MCP v1 minimumu (Madde 9):** her tool'da `inputSchema` + `outputSchema`/`structuredContent` +
  **annotations** (`readOnly`/`destructive`/`idempotent`/`openWorldHint`); **iş hatası
  (`isError`) ≠ protokol hatası** ayrımı.
- **Güvenlik:** `shell=True` yok; CLI argümanları **liste**; `run_actions` action-adı **+ argüman
  şeması + path sandbox + yolları SUNUCU üretir**; workspace-scope + path-traversal testi.
- **Test (Madde 13):** DOM golden (kendi çıktın) + gerçek Inkscape E2E + visual smoke (property
  assertion, Inkscape çıktısını byte-snapshot'lama) + lock/concurrency + Windows atomic-replace.
- **Dürüstlük:** Bölüm 3'teki **açık problemleri "çözdüm" diye sunma.** Prototiple ölç, sonucu
  raporla. Doğrulanmış gerçek ile tasarım tercihini ayır.

---

## 6. Teslim formatı

- **Önce dal aç:** `git checkout -b feat/v1-prototype` (baseline commit `fbb45f9` üzerinde). Default dala doğrudan commit YAPMA.
- **Tasarım dosyalarına ve `reference/`'a DOKUNMA.** Kodu yalnızca **yeni dizinlere** yaz: `src/inkscape_mcp/` + `tests/`. (Mevcut `.md` dosyaları değiştirilirse review diff'i kirlenir.)
- İşin bitince **branch/PR** olarak teslim et; review `git diff fbb45f9..feat/v1-prototype` üzerinde koşar.
- PR açıklamasında **kısa bir uygunluk tablosu**: "Madde N → şu dosya/fonksiyon → şu test."
- Çalışan E2E + `pytest` yeşil; Inkscape yolu env ile (`INKSCAPE_PATH`).
- `reference/`'ı **kaynak** olarak kullan; fixture'ları golden test beklentisi yap.

---

*Hazırlayan: Claude (Opus 4.8). Dayanak: `architecture-v1.md` (kontrat) + `reference/` (yer-gerçeği).
Tüm F-gerçekleri yerel `inkscape.com` 1.4.2 ile doğrulandı. Tarih: 2026-05-29.*
