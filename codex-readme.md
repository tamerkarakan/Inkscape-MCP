# Inkscape MCP - Codex Tasarim Notu

Bu dosya, mevcut `README.md` icin Codex bakisiyla daha uygulanabilir bir mimari oneridir. Amac tum Inkscape yuzeyini ilk gunden yuzlerce MCP tool olarak acmak degil; once kucuk, guvenli, testli ve genisletilebilir bir cekirdek kurmaktir.

## Kisa Degerlendirme

Mevcut `README.md` iyi bir vizyon belgesi. Python secimi mantikli, hedef Inkscape yolu yerel makinede dogrulandi, `inkscape.com --version` Inkscape 1.4.2 donduruyor, gomulu Python 3.12.9 var ve `--action-list` 1072 satirlik action listesi veriyor.

Benim asil farkim kapsam yonetimi olurdu: 100+ mikro-tool ile baslamak yerine, agentlarin guvenilir sekilde kullanabilecegi 10-15 composable tool ile baslardim. Daha sonra action ve extension kapsami otomatik kesif, allowlist ve testlerle buyutulebilir.

## Dil ve Cati Secimi

Birincil dil Python olmali.

Gerekceler:

- Inkscape portable paketinde Python zaten geliyor.
- SVG/XML islemleri Python ile sade ve test edilebilir.
- Inkscape'in extension ekosistemi Python/inkex etrafinda.
- MCP Python SDK, stdio tabanli yerel kullanim icin yeterli bir baslangic saglar.

TypeScript iyi bir alternatif olabilir, ama bu projede ilk tercih olmazdi. TypeScript MCP ekosistemi guclu olsa da Inkscape tarafindaki `inkex` ve extension dunyasina dogrudan yakinligi Python kadar iyi degil.

## Transport Karari

Ilk transport `stdio` olmali. Claude Desktop, Codex, yerel agentlar ve CLI testleri icin en basit ve en az riskli yol budur.

Uzak veya web tabanli kullanim gerekiyorsa hedef `Streamable HTTP` olmali. HTTP+SSE yeni mimari hedef olarak degil, ancak eski istemci uyumlulugu gerekiyorsa legacy destek olarak dusunulmeli.

## Mimari Ilke

Iki ana katman oneririm:

1. MCP/API katmani
   - Tool input schema'larini dogrular.
   - Dosya sandbox kurallarini uygular.
   - Sonuclari agent dostu JSON/text formatina cevirir.

2. Inkscape/SVG adapter katmani
   - Basit SVG uretim ve duzenleme isleri icin dogrudan XML/SVG DOM kullanir.
   - Render, export, query, path boolean, text-to-path gibi Inkscape'e ozgu islerde `inkscape.com` CLI cagirir.
   - `inkex` entegrasyonunu ikinci faz adapter olarak ekler.

Bu ayrim onemli: her basit dikdortgen veya metin ekleme icin Inkscape process calistirmak gereksiz pahali ve kirilgan olabilir. Ama Inkscape'in gercek degeri olan export, path, font, filter ve extension davranislarinda CLI kullanilmalidir.

## MVP Tool Katalogu

Ilk surumde su araclar yeterli olur:

| Tool | Amac |
|---|---|
| `document_create` | Yeni SVG olusturur |
| `document_open` | Guvenli dizinden SVG acar |
| `document_save` | Aktif SVG'yi kaydeder |
| `document_info` | Boyut, viewBox, layer/element ozetini dondurur |
| `element_create` | Rect, circle, ellipse, line, path, text gibi temel element ekler |
| `element_update` | Secili/ID'li elementin attribute/style bilgilerini gunceller |
| `element_delete` | ID ile element siler |
| `element_query` | ID, tip, selector veya bbox bilgisi sorgular |
| `selection_set` | Oturum secimini ID listesi olarak tutar |
| `export_file` | PNG/SVG/PDF gibi formatlara disari aktarir |
| `render_preview` | Aktif SVG'nin PNG onizlemesini uretir |
| `run_inkscape_actions` | Sadece allowlist icindeki action zincirlerini calistirir |
| `extension_list` | Mevcut extension metadata listesini verir |
| `extension_run` | Allowlist icindeki extension'i parametre dogrulayarak calistirir |

Bu katalog kucuk gorunur ama agent icin daha kullanislidir. `element_create` ve `element_update` gibi genel araclar, yuzlerce kucuk tool'a gore daha az protokol karmasasi yaratir.

## Resource Tasarimi

Ilk kaynaklar:

| Resource | Icerik |
|---|---|
| `inkscape://session/current-svg` | Aktif SVG XML |
| `inkscape://session/preview.png` | Son render edilen PNG onizleme |
| `inkscape://session/document-info` | Dokuman metadata |
| `inkscape://session/elements` | Element agaci ozeti |
| `inkscape://system/action-list` | Inkscape action listesi |
| `inkscape://system/extensions` | Extension listesi |

## Guvenlik

Bu proje icin guvenlik mimarinin merkezinde olmali.

Kurallar:

- Butun okuma/yazma islemleri `allowed_dirs` icinde kalmali.
- Path normalize edilmeli ve symlink/path traversal durumlari test edilmeli.
- `shell=True` kullanilmamali.
- CLI argumanlari liste olarak verilmeli.
- `run_inkscape_actions` sadece allowlist ile calismali.
- Maksimum SVG boyutu, maksimum cikti boyutu ve timeout zorunlu olmali.
- Her session kendine ait gecici dizin kullanmali.
- Hata mesajlari dosya sistemi hakkinda gereksiz hassas bilgi sizdirmamali.

## Test Plani

Testler sadece mock seviyesinde kalmamali; gercek Inkscape ile render/export dogrulamasi sart.

1. Unit test
   - Path sandbox dogrulamasi
   - Tool schema validasyonu
   - SVG DOM create/update/delete
   - Action allowlist ve argument escaping
   - Response parser

2. Integration test
   - MCP tool call -> handler -> adapter zinciri
   - Mock CLI ile hata ve timeout durumlari
   - Session izolasyonu

3. E2E test
   - Gercek `inkscape.com` ile SVG -> PNG export
   - Query geometry dogrulamasi
   - Text/path export smoke testi
   - Extension list okuma

4. Golden test
   - Beklenen SVG ciktilari fixture olarak tutulur.
   - XML canonicalization ile anlamsiz attribute sirasi farklari ayiklanir.

5. Visual smoke test
   - PNG ciktisi bos mu?
   - Beklenen boyutta mi?
   - En azindan temel pixel/renk kontrolleri tutuyor mu?

## Gelistirme Fazlari

### Faz 0 - Gercekleri Sabitle

- Inkscape path autodetect.
- `--version`, `--action-list`, Python path ve extension dizini inventory.
- Bu inventory sonucunu test fixture veya snapshot olarak kaydet.

### Faz 1 - Minimal MCP Server

- `stdio` transport.
- `document_create`, `document_open`, `document_save`, `document_info`.
- `render_preview` ve `export_file`.
- Basit allowed-dir sandbox.

### Faz 2 - SVG DOM Cekirdegi

- `element_create`, `element_update`, `element_delete`, `element_query`.
- Stable ID uretimi.
- XML canonicalization ve golden testler.

### Faz 3 - Inkscape CLI Adapter

- Query/export/action calistirma.
- Timeout ve stderr normalizasyonu.
- `run_inkscape_actions` icin allowlist.

### Faz 4 - Extension ve inkex

- Extension metadata parse.
- Allowlist ile `extension_run`.
- Gerekiyorsa `inkex` in-process adapter.

### Faz 5 - Uzak Transport ve Buyume

- Streamable HTTP.
- Coklu session.
- Daha genis tool katalogu.
- Action listesine dayali otomatik tool/resource uretimi.

## Mevcut README Icin Duzeltme Notlari

- `HTTP + SSE` yeni hedef gibi yazilmamali; `Streamable HTTP` ana uzak transport olmali.
- 353 extension iddiasi netlestirilmeli. Yerel klasorde 159 `.inx`, 165 `.py`, toplam 342 dosya goruldu; sayim kriteri belirsiz.
- Tum Inkscape action'larini dogrudan tool yapmak yerine once allowlist ve escape hatch modeli kurulmasi daha guvenli.
- `inkex` cok degerli ama MVP'nin merkezine konursa kurulum ve davranis karmasasi artabilir.
- Test plani mutlaka gercek Inkscape ile E2E render/export kaniti icermeli.

## Sonuc

Ben olsam bu projeyi "Inkscape'in tamamini MCP'ye dokelim" diye degil, "agentlar icin guvenli ve dogrulanabilir bir SVG/Inkscape isleme cekirdegi kuralim" diye baslatirdim. Kucuk ama saglam cekirdek kurulduktan sonra Inkscape'in 1072 action'lik yuzeyi kontrollu sekilde acilabilir.
