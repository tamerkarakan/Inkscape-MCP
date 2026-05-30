# Bug-Fix Kaydı + main'e Geçiş Talimatı

> Bu dosya: `feat/v1-prototype` üzerinde Claude'un kapattığı showstopper'ın kaydı, kalan
> küçük açıklar, "workflow/rubric neden dalda yoktu" netleştirmesi ve **DeepSeek'in main'e
> geçiş talimatı**. Tarih: 2026-05-30.

---

## 1. Kapatılan showstopper — `tool_run_actions` NameError (commit `a2a5a90`, Claude)

**Bug:** `src/inkscape_mcp/tools.py:735`, async refactor'da **silinen** `_run_inkscape_sync`'i
çağırmaya devam ediyordu (tanım yok, import yok) → **her path-op çağrısında `NameError`.** Yani
`run_actions` (path-union/difference/intersection/exclusion, set_attribute, transform) **runtime'da
tamamen bozuktu.**

**Neden oldu:** `query`/`export`/`render` `await _run_inkscape(...)`'e geçirildi ama `run_actions`
satır 735 atlandı. (Bu, tekrarlayan "yazdı/refactor etti ama tek call-site'ı bağlamadı" örüntüsü.)

**Neden testler kaçırdı:** `test_path_union_id_behavior` / `test_path_difference_operation`
inkscape binary'sini **DOĞRUDAN** `subprocess` ile çağırıyordu, production handler'ı
(`tool_run_actions`) **değil**. Yani handler hiç test edilmiyordu → 87 test yeşilken handler kırıktı.

**Fix:**
```python
# tools.py — run_actions ana yürütme çağrısı
await _run_inkscape(
    ["--actions=" + action_str, str(state.svg_path)],
    config,
    timeout=config.export_timeout,
)
```
+ Regresyon testi: `tests/e2e/test_real_inkscape.py::test_run_actions_handler_path_union` —
`tool_run_actions`'ı **handler üzerinden** çağırır (pre-fix NameError verirdi).

**Doğrulama (gerçek binary ile koşuldu):** **88 test geçiyor**; `run_actions` path-union handler'ı
uçtan uca çalışıyor (c1 yok oluyor, r1 kalıyor, id_map doğru).

---

## 2. Kalan gerçek-ama-küçük açıklar (sonraki tur — showstopper DEĞİL)

| Madde | Açık | Yapılacak |
|---|---|---|
| 9 | `outputSchema` deklare edilmemiş (structuredContent dönüyor) | FastMCP tool'larına output schema / return-type şeması ekle |
| 3 | `revision` in-memory; sunucu restart'ında 1'e döner | Diske bağla (içerik-etag / sidecar) ya da en azından belge mtime'ından türet |
| 12 | `transform` DOM yerine Inkscape CLI'de | `transform=DOM baseline` (lxml ile x/y bake); CLI'yi doğrulama/ileri işler için bırak |
| 9 | Resources zayıf — runtime'da yalnız `capabilities` görünüyor | SVG ve preview resource'larını (template) gerçekten kaydet |
| — | Arada bir >30s Inkscape cold-start timeout (flaky) | Warm-up çağrısı veya tek seferlik retry düşün |

> Not (statik review yanılgısı): conformance workflow "15 blocker" raporladı ama runtime
> doğrulaması gösterdi ki `inputSchema` ve `annotations` **var ve doğru** (FastMCP runtime'da
> üretiyor; statik grep göremiyor). Gerçek showstopper bir taneydi (yukarıdaki NameError) ve kapandı.

---

## 3. "Workflow/rubric neden dalda yoktu" — netleştirme (DeepSeek suçlu DEĞİL)

- `feat/v1-prototype`, **`fbb45f9`'dan** dallandı (DeepSeek `9546219`'un parent'ı = `fbb45f9`).
- `review-rubric.md` (`fa033c4`) ve conformance workflow (`c8a1760`) `fbb45f9`'dan **SONRA** main'e
  eklendi → ikisi de `9546219`'un atası **değil**, yani o dalda hiç yoklardı.
- **DeepSeek hiçbir şey silmedi** (`.claude/`/`reference/` üzerinde deletion = 0, doğrulandı).
- **Kök sebep:** benim brief'imdeki *"baseline `fbb45f9` üzerinde dallan"* talimatı. DeepSeek doğru
  uyguladı; kusur bende. Çözüldü: `main`, `feat`'e merge edildi (`30f8ced`).

### ⚠️ DeepSeek için ileriye dönük hijyen notu (suçlama değil)
- Yeni dalı **her zaman güncel `main`'den** aç (eski bir baseline commit'ten değil).
- `.claude/`, `reference/` ve tasarım dosyalarına (`*.md`) **dokunma**; kodu yalnız `src/` + `tests/`.

---

## 4. main'e geçiş (DeepSeek yapacak)

`feat/v1-prototype`, `main`'i (`8bd345c`) zaten içeriyor (`30f8ced` merge'iyle), bu yüzden
**fast-forward** olur — çakışma yok:

```bash
git checkout main
git merge feat/v1-prototype     # fast-forward; main, feat'in HEAD'ine ilerler
# (istenirse) git push
```

Sonrası: kalan küçük açıklar (Bölüm 2) yeni bir dalda — **güncel `main`'den dallanarak** — ele alınır.

---

*Kayıt: Claude (Opus 4.8). Fix `a2a5a90`, 88 test geçiyor. Branch-base teşhisi git ile doğrulandı.*
