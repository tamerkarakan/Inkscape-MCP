# reference/ — Yer-Gerçeği Corpus (manifest)

Bu klasör, `architecture-v1.md`'deki 🔬 gerçekleri üreten **gerçek binary çıktılarıdır** —
tahmin değil, `inkscape.com` 1.4.2 (f4327f4) ile üretilmiş kanıt. İki amacı var:

1. **Kod yazarken kaynak** (DeepSeek): action adlarını/usage'ı buradan oku, **uydurma.**
   `tool-rect` faciası tam da uydurmaktan çıktı — bu corpus onun panzehiridir.
2. **Review oracle** (Claude/Codex): "after-*" fixture'lar, kodun ürettiği SVG'lerle
   karşılaştırılacak golden örneklerdir.

> ⚠️ "after-*" dosyaları aynı zamanda Inkscape'in **round-trip yeniden-yazımını** gösterir
> (`sodipodi:namedview` ekler, `inkscape:` namespace'leri, attribute sırası). Bu yüzden
> `architecture-v1.md` madde 13: Inkscape çıktısını **byte-byte snapshot'lama** —
> property/visual assertion kullan. Bu fixture'lar o kırılganlığın da kanıtıdır.

## Action envanterleri

| Dosya | Nedir | Üreten komut | Hangi gerçeği destekler | Nasıl kullanılır |
|---|---|---|---|---|
| `action-list-full.txt` | **1072 action**'ın tam dökümü | `inkscape.com --action-list` | F2, F3 | `capabilities.json` kaynağı + Faz-0 snapshot'ı; allowlist bu listeye bağlanır |
| `core-actions.txt` | Çekirdek action yüzeyi (~252 satır) **açıklama + usage string'leriyle** | `--action-list` (org.* efekt yığını filtrelenmiş) | F2, F3, F7 | İnsan-okunur referans; tipli tool'ların hangi action'a map'lendiğini ve argüman formatını buradan al (örn. `object-set-attribute:ad,değer`) |

> `core-actions.txt` içinde dikkat: `select` "(deprecated)" → gerçek olan `select-by-id`;
> `query-all` "x,y,width,height" döndürür; `object-set-attribute`/`object-set-property` mutasyonun
> ana yolu; **hiçbir `tool-*` / şekil-yaratan action yok** (F3 — gözünle doğrula).

## Fixtures (golden oracle + davranış referansı)

Hepsi `base-input.svg`'den türetildi (rect `r1`, circle `c1`, path `p1`).

| Dosya | Üreten komut | Gösterdiği davranış | Gerçek |
|---|---|---|---|
| `base-input.svg` | (elle yazıldı) | Temiz girdi fixture'ı | — |
| `after-object-to-path-then-union.svg` | `select-by-id:r1;select-by-id:c1;object-to-path;path-union` | r1+c1 **tek `<path id="r1">`'e** indi, **`c1` yok oldu**, `p1` dokunulmadı. Yeni id üretilmedi, en-alttaki operandın id'si devralındı. | **F8** (id-changing op → id-map gerekçesi, madde 14) |
| `after-transform-translate.svg` | `select-by-id:r1;transform-translate:100,0` | `r1` x:10→110; **`transform` attr YOK**, x'e bake edildi | **F9** |
| `after-set-attribute-fill.svg` | `select-by-id:r1;object-set-attribute:fill,purple` | `r1` fill=purple (mevcut nesnede mutasyon) | **F7** |
| `after-shell-session-set-fill.svg` | `--shell`: `file-open→select-by-id:c1→object-set-attribute:fill,orange→export-do→file-close` | Tek `--shell` oturumunda belge durumu korundu, `c1` fill=orange | **F10** |
| `after-inkex-create-rect.svg` | in-process **inkex** `Rectangle.new(...)`+`svg.add()` (Inkscape süreci ÇALIŞMADAN) | `<rect id="newrect" style="fill:magenta"/>` eklendi | **F4** (yaratım = DOM/inkex) |

## Eksik olan (bilerek)
PNG/PDF render blob'ları, `--actions-file` scratch'leri ve `--batch-process` çıktısı **silindi** —
export'un çalıştığı F6'da kayıtlı, tekrar-kullanılamaz binary asset'ler corpus'u kirletir.

*Üretim: yerel `inkscape.com` 1.4.2. Tarih: 2026-05-29.*
