# BIST Veri Platformu — Tasarım Belgesi (v0, 2026-11-14)

> Not: Bu belge bu repodaki araştırmadan çıkan derslerle yazılmış, **henüz uygulanmamış** bir
> sonraki adım tasarımıdır. Repoya kişisel ayrıntılar ve bazı erişim notları çıkarılarak alındı.

Bu belge, gelecekteki tüm BIST finans araştırmalarında kullanılacak veri sisteminin
sıfırdan kurulması için başlangıç belgesidir. Bu repodaki araştırmadan
ve BIST Datastore incelemesinden çıkan bulguları içerir. Uygulamaya başlayan kişi
önce bu belgeyi, sonra "Açık kararlar" bölümünü okumalıdır.

---

## 1. Amaç

- Araştırmalardan bağımsız, tek, güvenilir ve **point-in-time (PIT)** doğru bir veri katmanı.
- Araştırma kodu veriye yalnızca kütüphanenin API'si üzerinden erişir; kaynaklara (İş Yatırım,
  KAP, Datastore) doğrudan dokunmaz.
- Kod, testler ve belgeler kamuya açık olabilir; **lisanslı ham veri asla repoya girmez**.

İlk kullanıcı araştırma: bedelsiz sermaye artırımı olay çalışması (volatilite, bireysel ilgi,
opsiyon). Ama tasarım ona özel olmamalı.

## 2. Değişmez ilkeler

1. **Ham veri değişmezdir.** İndirilen her dosya olduğu gibi, indirme zamanıyla (vintage)
   saklanır. Üzerine yazılmaz. Neden: İş Yatırım geçmiş sütunları sonradan revize edilmiş
   değerlerle eziyor (bkz. §4.2); bunu ancak tarihli kopyalar yakalar.
2. **Her olgunun iki zamanı vardır:** `valid_time` (neyi anlatıyor: dönem/gün) ve
   `knowledge_time` (kamuya ne zaman açıklandı / sistemimize ne zaman girdi).
   API her sorguda `as_of` kabul eder; geleceği görme hatası yapısal olarak engellenir.
3. **Kanonik tablolar kaynaktan bağımsızdır.** Her satır `source` ve `raw_file_id` taşır
   (soy kütüğü / lineage). Kaynak değişirse yalnızca adaptör değişir.
4. **Kaynaklar birbirini doğrular.** Örtüşen veride (fiyatlar, olay tarihleri) uzlaştırma
   raporu üretilir; uyuşmazlıklar sessizce düzeltilmez, raporlanır.
5. **Artımlı ve kaldığı yerden devam eden** indirme ve derleme. İkinci çalıştırma yalnızca
   yeni dosyaları işler.
6. **Kaynak sınırlı çalışma.** Hedef makine: 8 çekirdek, 8 GB RAM, sıradan bir dizüstü. Bkz. §7.
7. **Her ayrıştırıcının farklı yıllardan gerçek örnek dosyalarla testi vardır** (alan adları
   zamanla değişiyor, bkz. §4.1).

## 3. Mimari

```
kaynak  ──(adaptör: download)──>  raw/  ──(adaptör: parse)──>  staged/  ──(build)──>  canonical/  ──>  api
                                    │                                                      │
                                 catalog (manifest: her ham dosyanın kaydı)          checks / reconcile raporları
```

- **raw/**: `raw/<source>/<dataset>/<vintage=YYYY-MM-DD>/<orijinal_dosya_adı>`
- **catalog**: her ham dosya için `file_id, source, dataset, url/ürün, downloaded_at, sha256,
  size, parser_version, status`. DuckDB tablosu veya parquet.
- **staged/**: kaynağa özgü ama tiplenmiş, sütun adları normalize edilmiş parquet.
- **canonical/**: kaynaktan bağımsız şemalar (§5), yıl/ay bölümlü parquet.
- **Sorgu motoru**: DuckDB (parquet üzerinde, sunucusuz). pandas yalnızca küçük sonuçlar için.
- **Veri dizini repo dışında**, ortam değişkeniyle: `BISTDATA_HOME` (öneri: `~/bistdata`).

Önerilen paket yerleşimi:

```
bistdata/
  sources/        datastore/, isyatirim/, kap/, evds/, bist_files/   (her biri: download.py, parse.py, tests)
  catalog.py      ham dosya kaydı, sha256, vintage
  schemas/        kanonik tablo şemaları (pyarrow / pandera)
  build/          staged -> canonical derleme adımları
  reconcile/      kaynaklar arası karşılaştırma
  checks/         veri kalitesi kontrolleri
  api.py          load_prices(), load_financials(as_of=...), load_events(), load_options(), ...
  cli.py          bistdata download|build|check|status
```

## 4. Kaynak envanteri

### 4.1 Borsa İstanbul Datastore (resmî, `datastore.borsaistanbul.com`)

Giriş gerekli; kullanım koşulları üçüncü kişilerle paylaşımı kısıtlıyor → ham dosyalar git'e girmez,
türetilmiş çıktıların paylaşımı ayrıca kontrol edilmeli.

Genel uyarılar (ürün sayfalarından):
- 30.11.2015 BISTECH geçişi: dosya desenleri bu tarihten sonra değişti.
- "Alan adları zaman içinde farklılık gösterebilir."
- 27.07.2020: TL pay endekslerinden iki sıfır atıldı; VİOP endeks sözleşmeleri değişti.
- CSV ondalık ayırıcısı nokta, binlik ayırıcısı virgül.

| Ürün (product-type id) | Ücret | Dosya | Önemli alanlar | Kullanım |
|---|---|---|---|---|
| Pay — Gün Sonu Fiyat ve İşlem Hacmi (3196) | ücretsiz | `PP_GUNSONUFIYATHACIM.M.YYYYMM.csv` aylık | TARIH, ISLEM KODU, PAZAR, **BIST 100 ENDEKS, BIST 30 ENDEKS** (bayrak), GECICI DURDURMA, ONCEKI KAPANIS, **ACILIS FIYATI**, EN DUSUK, EN YUKSEK, KAPANIS, **BEKLEYEN EN IYI ALIS/SATIS**, A.O.F, TOPLAM ISLEM HACMI/ADEDI, **REFERANS FIYAT**, seans bazlı hacimler, **ACIGA SATIS** hacim/adet, özel işlem bildirimleri | Ham OHLC, spread, tavan/taban tespiti, açığa satış, **PIT pazar ve endeks üyeliği** |
| VİOP — Gün Sonu Fiyat ve İşlem Hacmi (3208) | ücretsiz | `VIOP_GUNSONU_FIYATHACIM.M.YYYYMM.csv`, `VIOP_AS_...` (akşam seansı) | SOZLESME KODU, SOZLESME TIPI/SINIFI, DAYANAK VARLIK, **UZLASMA FIYATI**, OHLC, BEKLEYEN EN IYI ALIS/SATIS, AOF, ISLEM HACMI, PRIM HACMI, **ACIK POZISYON** | Opsiyon örtük volatilitesi, vadeli. Uyarı: işlem görmeyen opsiyonda uzlaşma fiyatı model fiyatıdır. |
| Birincil Halka Arzlar — Paylar (3190) | ücretsiz | `hisseYYYY.zip` | Halka arz fiyatı/oranı, hasılat, satış yöntemi, halka arz ve işlem başlama tarihi, **yurtiçi bireysel / kurumsal / yurtdışı yatırımcı sayısı** | IPO olayları, bireysel ilgi göstergesi |
| Aylık Müşteri / Fon / Portföy İşlemleri (3130) | ücretsiz | `PP_MFTHACIM.M.YYYYMM.zip` | Yatırımcı türü, alış/satış, ay, hacim | Piyasa geneli yatırımcı türü akışı |
| Sermaye Artırımı, Temettü ve Benzeri Şirket Bilgileri (100463) | **abonelik** (Şirket Verileri grubu) | `SERMAYE_ARTIRIMI_YYYYMMDD.csv` günlük | BASLANGIC TARIHI, PAY KODU, önceki/ulaşılacak sermaye, bedelli (rüçhanlı/kısıtlı) TL ve %, **iç kaynaklardan bedelsiz TL ve %**, temettüden bedelsiz, birleşme, pay başı brüt/net temettü | Kurumsal olaylar (yalnızca başlangıç tarihi; duyuru/SPK onayı yok) |
| Sermaye Artırımları haftalık/aylık (100460/100461), Temettü (100462), Değerleme Oranları (100464/100465) | abonelik | | | Opsiyonel |
| Açığa Satış (Aylık) (3155), Yabancı İşlemleri (3153), Pay bazında hacim (3152, 3156, 3157) | abonelik (Pay Bazında Veriler) | | | Opsiyonel; günlük açığa satış zaten 3196'da |
| Gün Sonu Düzeltilmiş Fiyat (3245) | e-posta ile talep | | | Gerekirse |
| Gün İçi İşlem/Emir Defteri, ITCH, gün içi endeks | abonelik, büyük | | | Kapsam dışı (şimdilik) |
| Bilanço ve Gelir Tabloları 2000–2009 (100580), Şirket Yıllıkları 1998–2008 | ? | girişsiz listede dosya yok | | **2009 sonrası mali tablo Datastore'da yok** |

Kategori sayfaları: Pay `category/100856/group/100864`, VİOP `category/100857/group/100854`,
Halka arz `category/7560/group/100872`, Endeks ve Borçlanma kategorileri incelenmedi.

### 4.2 İş Yatırım (resmî olmayan uç noktalar)

- **HisseTekil** (`.../Common/Data.aspx/HisseTekil`): günlük. Düzeltilmiş (`hgdg_kapanis`,
  `hgdg_min`, `hgdg_max`) ve ham (`hg_kapanis`, `hg_min`, `hg_max`) seriler; `hg_aof` =
  ağırlıklı ortalama fiyat (**açılış değil; açılış fiyatı yok**); hacim; dolar bazlı fiyat ve kur;
  `pd` / `pd_usd` (piyasa değeri), `hao_pd` (halka açık piyasa değeri), `sermaye`.
  **Ham/düzeltilmiş oranı düzeltme faktörünü verir** → bedelsiz/bölünme günleri fiyattan tespit
  edilebilir.
- **MaliTablo** (`.../Common/Data.aspx/MaliTablo`): çeyreklik mali tablolar; istek başına en
  fazla 4 dönem; mali grup kodları (ör. `XI_29` = UFRS/TMS 29 raporlayanlar). Mevcut repoda
  sektör profilleri var (banka, katılım bankası, sigorta, holding, GYO, leasing, sanayi).
- **Kritik tuzak (mevcut repoda kanıtlandı):** İş Yatırım geçmiş dönem sütunlarını son
  yayınlanan karşılaştırmalı (restated) değerle **eziyor**. TMS 29 (enflasyon muhasebesi)
  ilk raporu FY2023; Aralık 2022 ve 2023 ara dönem akışları yatırımcıların gördüğü haliyle
  geri getirilemiyor. Bu yüzden: tarihli vintage arşivi zorunlu; as-reported değerler
  vintage'lardan ve KAP'tan kurulmalı; geri getirilemeyen değerler tahmin edilmemeli,
  boş + `basis` etiketiyle tutulmalı (`nominal / transition / ias29 / unrecoverable`).
- Resmî API değil: değişebilir, kapanabilir, kullanım koşulları belirsiz. Örtüşen veride
  Datastore birincil olmalı.

### 4.3 KAP (`kap.org.tr`, resmî)

- `api/disclosure/members/byCriteria`: bildirim listesi, **dakika hassasiyetinde yayın zamanı**,
  konu (subject) filtreleri. Mevcut repoda finansal rapor yayın tarihleri bununla çekiliyor.
- Gerekenler: finansal rapor yayın zamanları (mali tabloların `knowledge_time`'ı), kurumsal
  olaylar (bedelsiz: yönetim kurulu kararı, SPK başvurusu/onayı, bölünme tarihi; temettü;
  birleşme; işlem sırası kapanması), şirket kimlik/kod değişiklikleri.
- Uzun vade: 2009 sonrası mali tablolar için **KAP XBRL** adaptörü (resmî, as-reported,
  zaman damgalı). İş Yatırım'a bağımlılığı bitirir.

### 4.4 MKK Veri Analiz Platformu (VAP, `www.vap.org.tr`, resmî)

- **İzin durumu:** Sitenin telif metni kopyalamayı ve saklamayı yazılı izne bağlıyor. Sistemli
  çekim için MKK'dan ayrıca izin alınmalı; ham VAP verisi hiçbir durumda yeniden dağıtılmaz.
- Toplayıcı yalnız izin alındıktan sonra, düşük hızla çalışmalı.

| Seri | Kırılım | Sıklık / başlangıç |
|---|---|---|
| BİST Endeksleri Bazında Portföy Değerleri | 9 endeks × yerli/yabancı × yatırımcı sayısı / portföy değeri | Aylık, 2005-12 |
| Portföy Dilimi Bazında Yatırımcı Sayıları | Portföy büyüklüğü dilimi × kıymet türü × uyruk | Aylık |
| REKS – Risk Eğilim Endeksi | Tüm, yerli, yabancı, yerli gerçek, yerli tüzel, fonlar, nitelikli | Haftalık, 2010-04 (cuma verisi, pazar yayını) |
| Fiili Dolaşım Raporu | **Hisse bazında**: toplam pay, işlem gören pay, fiili dolaşım payı ve oranı | Günlük; 2026-09-11'de yöntem kırılması (SPK ilke kararı) |
| Yerli Yabancı (Pay Senedi) Analizi | Piyasa geneli yerli/yabancı nominal ve portföy payı | Haftalık, 2005-11; 10 iş günü gecikmeli |
| İl / yaş / uyruk bazında yatırımcı sayıları; MKK Kâr, Ciro, Temettü endeksleri; dönemsel finansal oranlar | | Aylık / çeyreklik |

- **Açık sorular:** hisse bazında yatırımcı sayısı açık sayfalarda yok; endeks serisinde üyeliğin
  dönemin üyelerine göre mi (PIT) belirlendiği belirsiz — doğrulanmadan PIT kabul edilmemeli.
- Kanonik tablo önerisi: `investor_counts` (anahtar: kapsam [endeks/dilim/hisse], tarih, uyruk;
  değerler: yatırımcı sayısı, portföy değeri; `knowledge_time` = yayın tarihi).

### 4.5 Diğer

- **TCMB EVDS**: kur, faiz, TÜFE, beklenti anketleri (API anahtarı gerekir). Mevcut araştırmada TÜFE, TÜİK rakamlarını aktaran ikincil sitelerden derlendi (dosya repoda yok).
- **BIST dosyaları**: `Pazarlar.xlsx`, `Sektörler.xlsx` (mevcut ayrıştırıcılar var; ama bunlar
  **bugünün** sınıflandırması — PIT için Datastore gün sonu dosyasındaki PAZAR alanı kullanılmalı),
  `IslemSirasiKapananSirketler.xls` (işlemden kaldırılanlar).
- **Gelecek (kapsam dışı ama şemada yeri olmalı)**: MKK yatırımcı sayıları ve fiili dolaşım
  oranı, Google Trends (normalize edildiği için vintage'ı zorunlu), sosyal medya.

## 5. Kanonik tablolar (v1)

| Tablo | Anahtar | İçerik | Birincil kaynak |
|---|---|---|---|
| `securities` | security_id | Kod geçmişi (yeniden adlandırma), ISIN, unvan, işlem başlama/bitiş, kaldırılma nedeni, halef kod | Datastore gün sonu + BIST xls + KAP |
| `trading_calendar` | date | İşlem günleri, yarım günler | Datastore gün sonu |
| `prices_daily` | security_id, date | Ham OHLC, AOF, hacim, adet, en iyi alış/satış, referans fiyat, durdurma, açığa satış, seans hacimleri, `source` | Datastore (2015-12 sonrası), İş Yatırım yedek |
| `membership_daily` | security_id, date | Pazar, BIST30/BIST100 üyeliği | Datastore gün sonu |
| `corporate_actions` | action_id | Tür (bedelsiz/bedelli/temettü/bölünme/birleşme), oranlar, **duyuru, SPK onayı, hak kullanım** tarihleri ve zaman damgaları | KAP + Datastore 100463 (varsa) + fiyat sıçramaları |
| `adjustment_factors` | security_id, date | Kümülatif düzeltme faktörü, nedeni | `corporate_actions`'tan hesap; İş Yatırım oranıyla uzlaştırma |
| `shares_outstanding` / `market_cap` | security_id, date | Ödenmiş sermaye, pay sayısı, piyasa değeri, halka açık piyasa değeri | İş Yatırım, KAP |
| `financials` | security_id, period, item, vintage | As-reported kalemler, `knowledge_time`, `basis`, profil | İş Yatırım vintage'ları → (ileride) KAP XBRL |
| `report_events` | security_id, period | Rapor yayın zamanı | KAP |
| `options_daily`, `futures_daily` | contract, date | Uzlaşma, OHLC, alış/satış, hacim, açık pozisyon, dayanak, vade, kullanım fiyatı, tip | Datastore VİOP |
| `ipos` | security_id | Datastore halka arz alanları | Datastore 3190 |
| `investor_flows` | ay, yatırımcı türü | Datastore 3130 | |
| `macro_series` | series, date | knowledge_time ile | EVDS, TÜİK |

API'de düzeltilmiş fiyat bir **görünüm**dür: `prices_daily` × `adjustment_factors` (as_of'a göre).

## 6. Kalite ve uzlaştırma kontrolleri

- OHLC tutarlılığı (low ≤ open/close ≤ high), negatif/sıfır fiyat, yinelenen satır, eksik işlem günü.
- Datastore ham kapanış ↔ İş Yatırım `hg_kapanis` farkı (tolerans, rapor).
- Fiyattaki düzeltme sıçramaları ↔ `corporate_actions` olayları (eşleşmeyen her iki yön raporlanır).
- Tavan/taban kilidi: high == low == referans × (1 ± limit).
- Kod değişiklikleri ve işlemden kaldırılanların fiyat serilerinin sürekliliği (hayatta kalma yanlılığı).
- Mali tablolarda vintage'lar arası revizyon raporu.
- Her derleme sonunda tablo başına satır sayısı, tarih aralığı, null oranı özeti (`bistdata status`).

## 7. Kaynak kullanımı

- İndirme: sıralı, hız sınırlı (≥1 sn aralık), retry/backoff, kaldığı yerden devam.
- İşleme: dosya dosya / ay ay akış; tüm veri asla belleğe alınmaz.
- DuckDB: `memory_limit='1.5GB'`, `threads=2`. Uzun işler `nice -n 19` ile arka planda.
- Hedef: ilk tam derleme < 30 dk, artımlı güncelleme < 1 dk.

## 8. Bu repodan taşınacaklar

(`data/` altındaki dosyalar kamuya açık repoda yok; yerel kopyadan taşınır.)

Sıfırdan mimari, ama zor kazanılmış bilgi korunur. Taşırken testleriyle birlikte taşı.

| Modül | Neden değerli |
|---|---|
| `src/data/isyatirim/client.py`, `parser.py`, `mapper.py`, `profiles/*` | MaliTablo istek mantığı, mali grup eşlemesi, sektör profilleri |
| `src/pit/financials.py` | TMS 29 / restatement kurtarma mantığı, `basis` etiketleri |
| `scripts/download_pit_vintage.py`, `data/vintages/2026-11-01` | Mevcut tek vintage — **yeni sistemin raw/ arşivine ilk vintage olarak alınmalı** |
| `src/data/kap/*` | KAP istemcisi, rapor tarihi ayrıştırma |
| `src/data/market/client.py` | HisseTekil sütun eşlemesi |
| `src/data/markets.py`, `src/data/sector/classification.py` | Excel ayrıştırıcıları |
| `data/universe/delisted_candidates.csv` | Elle doğrulanmış kaldırılma listesi |
| `src/utils/symbols.py` | Kod normalizasyonu |

Araştırma katmanı (`src/factors`, `src/pit/portfolio.py`) bu repoda kalır
ve sonra yeni API'ye geçirilir.

## 9. Aşamalar ve kabul kriterleri

- **M0 — İskelet**: paket, `BISTDATA_HOME`, catalog, CLI (`status`), CI benzeri test çalıştırma,
  `.gitignore` (raw/ ve lisanslı veri). *Kabul*: boş sistemde `bistdata status` çalışır, testler geçer.
- **M1 — Datastore pay gün sonu**: ayrıştırıcı (2016 ve 2026 örnekleriyle test), `prices_daily`,
  `securities` (ilk sürüm), `trading_calendar`, `membership_daily`. *Kabul*: 2015-12 → bugün tüm
  aylar derlenir; kontroller raporu üretilir.
- **M2 — İş Yatırım fiyatları + düzeltme**: HisseTekil adaptörü, `adjustment_factors`,
  Datastore↔İş Yatırım uzlaştırma raporu. *Kabul*: düzeltilmiş getiriler İş Yatırım düzeltilmiş
  serisiyle tolerans içinde; sapmalar listelenmiş.
- **M3 — KAP olayları**: `report_events`, `corporate_actions` (bedelsiz öncelikli: 3 tarih),
  fiyat sıçramasıyla eşleştirme. *Kabul*: 20 olay elle doğrulanmış; eşleşme oranı raporlanmış.
- **M4 — Mali tablolar (PIT)**: MaliTablo adaptörü + vintage arşivi + `financials` (basis,
  knowledge_time). *Kabul*: bu repodaki PIT sonuçları yeni API ile yeniden üretilebilir.
- **M5 — VİOP, halka arz, yatırımcı akışları**: `options_daily`, `futures_daily`, `ipos`,
  `investor_flows`. *Kabul*: BIST30 opsiyonları için örnek bir günün IV yüzeyi hesaplanabilir.
- **M6 — Belgeler**: veri sözlüğü, kaynak/lisans notları, örnek notebook.

## 10. Açık kararlar

1. **Ayrı repo mu?** Öneri: evet — `bist-data` reposu, `bistdata` paketi; bu repo ve sonraki
   araştırma repoları onu editable kurar. Veri `~/bistdata` altında, repo dışında.
2. **Datastore abonelikleri** (Şirket Verileri: sermaye artırımı/temettü) alınacak mı? Öneri:
   önce KAP + fiyat sıçramasıyla dene, eşleşme kötüyse değerlendir.
3. **Datastore indirmesi**: dosyalar hesap sahibi tarafından elle indirilir; ilk adım farklı
   yıllardan örnek dosyalar.
4. **Mali tablolar için KAP XBRL** M4'e mi, sonraya mı? Öneri: M4'te İş Yatırım + vintage,
   XBRL ayrı bir sonraki aşama.
5. Şema doğrulama kütüphanesi: pandera mı, pyarrow şemaları mı? Öneri: pyarrow şemaları + kendi
   kontrolleri (bağımlılık az).

## 11. Kapsam dışı (şimdilik)

Gün içi veri / ITCH, gerçek zamanlı akış, web arayüzü, bulut depolama, Google Trends ve sosyal
medya toplayıcıları (şemada yer ayrılır, toplayıcı yazılmaz).
