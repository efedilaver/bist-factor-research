# BIST Faktör Araştırması

**Borsa İstanbul'da finansal tablolardan kurulan faktörler (değer, kalite, istikrar ve diğerleri), veri point-in-time doğru kurulduğunda gelecekteki hisse getirilerini öngörüyor mu?**

Bu repo, tek kişilik bir araştırmanın kodunu ve sonuçlarını içeriyor. Araştırma iki aşamada yürüdü. İlk aşamada yedi faktör ailesi bugünkü Yıldız Pazar evreninde test edildi. İkinci aşamada veri kaynağındaki ileriye bakma sorunu bulundu ve düzeltildi. Önceden sabitlenmiş Değer + Momentum modeli bu düzeltilmiş veriyle yeniden test edildi. İlk aşamanın umut verici sonucu ikinci aşamada büyük ölçüde kayboldu. Bu da sonucun bir parçası ve olduğu gibi raporlanıyor.

---

## Kısaca

- **Düzeltilmiş veride model piyasayı yenmedi.** Önceden sabitlenmiş Değer + Momentum portföyü 122 aylık yeniden dengelemede (sinyaller Ağustos 2016 – Eylül 2026, getiriler Ekim 2026'ya kadar), masraf sonrası piyasa değeri ağırlıklı evrene göre yılda **+%0,3** fark yarattı (t = 0,08; %95 güven aralığı −%6,6 ile +%5,8). Dolar bazında yıllık getiri %0,2. Alfa olmadığı kanıtlanmadı; olduğuna dair kanıt da yok.
- **Aynı kurallar düzeltilmemiş veride yılda +%10,7 fark gösteriyordu (t = 2,74).** Düzeltmeler sırayla eklendikçe fark kayboldu. Adımların payı sıraya bağlı, kesin pay olarak okunmamalı; son adım (çıkmış payları eklemek) büyük ölçüde birkaç birleşen şirketten gelen gürültü. En büyük düşüş evren seçiminde: bugünkü Yıldız Pazar listesini geçmişe uygulamak kazananları önceden seçiyor. Sinyalin hesaplanamadığı aylar da sonucu şişiriyordu. İş Yatırım'ın geçmiş kolonları sonraki rakamlarla üzerine yazmasının ise bu kural setinde etkisi küçük.
- **Sinyal düzeyinde iz var, portföyde yok.** Düzeltilmiş veride aylık IC: düşük volatilite 0,078 (t = 3,49), değer bileşiği 0,062 (t = 3,05), momentum 12-1 −0,013. İlk aşamada yedi faktör ailesinden yalnız Değer Bonferroni eşiğini geçmişti (düzeltilmiş hesapta); İstikrar sınırın hemen altındaydı. O sonuç düzeltilmemiş veriye ve hayatta kalanlardan oluşan bir evrene dayanıyor. Bu yüzden bulgu değil, test edilecek hipotez olarak okunmalı.
- **Asıl katkı veri hattı.** Hat İş Yatırım tablolarını ve KAP yayın tarihlerini birleştiriyor. Banka, katılım bankası, sigorta, holding, GYO ve sanayi için ayrı eşleme profilleri kullanıyor. TMS 29 kaynaklı geriye dönük yeniden yazımları tespit edip kolonları kendi dönemine geri çeviriyor. 171 birim testi var.

## Finans açısından neden önemli

Türkiye'de faktör yatırımı için kullanılan veri setlerinin çoğu üç tuzağa açık. Bu çalışma tuzakları veride gösteriyor ve düzeltmelerin bir backtest'i birlikte ne kadar değiştirdiğini ölçüyor:

1. **Veri sağlayıcı geçmişi yeniden yazıyor.** 2023'ten sonra TMS 29 (yüksek enflasyonda finansal raporlama) uygulayan şirketlerde, İş Yatırım her dönem için tek değer tutuyor. Bu değer, yeni raporların karşılaştırmalı rakamlarıyla üzerine yazılıyor. 2024 yılsonunda sanayi, holding ve GYO şirketlerinin %89'unda Aralık kolonu sıçrayıp sonra geri düşüyordu (PIT raporu; düzeltilmiş verinin tamamında oran %0,5). Bu, o tarihte bilinmeyen bilginin geçmişe sızması demek.
2. **Bugünkü pazar listesi geçmişi bilmiyor.** Bugün Yıldız Pazar'da olan şirketleri 2016'ya geri götürmek, sonradan başarılı olanları önceden seçmek demek. Düzeltme sırasındaki en büyük düşüş bu adımda oldu: yıllık fark +%7,6'dan +%2,9'a indi.
3. **Yayın tarihi varsayımı.** "Dönem sonu + 90 gün" kuralı yıl sonu raporlarında güvenli değil. TMS 29'un ilk yılı olan 2023 yıl sonunda raporların %62'si 90 günden geç yayımlandı. Bu düzeltmenin getiri etkisi ayrıca ölçülmedi; TMS 29 düzeltmesiyle aynı adımda (B0) eklendi.

Portföy yöneticisi açısından ders şu: düzeltilmemiş veriyle yapılan bir BIST backtest'i, t istatistiği 2,7 olan ama düzeltmelerden sonra kaybolan bir alfa üretebilir.

## Araştırma disiplini

- **Kurallar sonuçtan önce yazıldı.** Evren, skor, portföy kuralları, korkuluklar ve maliyet varsayımı ikinci aşamanın sonuçları görülmeden sabitlendi ve değiştirilmedi. Sonradan veri geçerliliği gerekçesiyle eklenen beş kural raporda ayrıca listeleniyor. Bunların bir kısmının getiri etkisi önceden biliniyordu; bu açıkça yazıldı. Kanıt, raporun kendisidir. Bu repo tek bir başlangıç commit'iyle oluşturuldu; **commit tarihi ön kaydın kanıtı değildir.**
- **Düzeltmeler tek tek eklendi.** Her veri düzeltmesi aynı kural setine sırayla eklenip etkisi ayrı ayrı ölçüldü (aşağıdaki tablo).
- **Çoklu test bilinci.** İlk aşamada 7 aile × 3 ufuk = 21 test için Bonferroni eşiği (|t| ≥ 3,25) kullanıldı. İkinci aşamada ilk turdaki 27 deneme ve 19 senaryo birlikte sayıldı. Bu sayı hesaba katılınca en iyi varyant bile eşiğin çok altında kalıyor.
- **İstatistik.** Aşama 1 yönetici raporundaki yeniden hesaplamada, 6 aylık ufukta örtüşen getiri pencereleri için Newey-West düzeltmesi kullanıldı. 10'dan az gözlemli dönemler de IC ortalamasından çıkarıldı. Koddaki IC hattı (`src/factors/ic.py`) bunu henüz yapmıyor: varsayılan olarak 3 gözlemli dönemleri kabul ediyor ve örtüşme düzeltmesi yok. Bu yüzden `results/factor_validation/` altındaki dosyalar düzeltmesiz rakamları gösteriyor.
- **Bağımsız inceleme.** Sinyalsiz aylarda portföyün üç bankaya inmesi hatasını bağımsız bir kod incelemesi yakaladı.
- **Eski sonuç geri çekildi.** İlk aşamanın raporundaki "ileriye dönük veri sızıntısı yok" ifadesi yanlıştı. Rapor silinmedi; yanlış olduğu yeni raporda yazıldı.

## Sonuçlar

### Aşama 2: Point-in-time düzeltilmiş model (Kasım 2026)

Ana model: en likit 100 şirket (63 günlük medyan hacim ≥ 1 milyon $, piyasa değeri ≥ 50 milyon $). Skor, sektör nötr değer ile momentum 12-1'in eşit ağırlıklı ortalaması. En iyi %20 alınıyor, aylık yeniden dengeleniyor ve tek yön 30 baz puan masraf düşülüyor. Kıyas, piyasa değeri ağırlıklı evren.

| Adım | Yıllık fark | t |
|---|---:|---:|
| A. Düzeltilmemiş veri, bugünün Yıldız Pazar'ı | +%10,7 | 2,74 |
| B0. Aralık/TTM ve yayın tarihi düzeltmesi | +%10,0 | 2,62 |
| B. Sinyal hesaplanamayan aylarda pozisyon almama | +%7,6 | 2,27 |
| C. Yıldız yerine bugünkü tüm hisseler | +%2,9 | 0,78 |
| **Ana model: borsadan çıkanlar da dahil** | **+%0,3** | **0,08** |

| Ölçü (masraf sonrası) | Değer |
|---|---|
| Yıllık getiri, TL | %32,3 |
| Piyasa değeri ağırlıklı evren, TL | %32,5 |
| USD/TRY yıllık artış | %32,0 |
| Eşit ağırlıklı evrene fark | yılda +%1,5, t = 0,34 |

Tek kural değiştirilerek yapılan 14 duyarlılık testinin hiçbiri anlamlı değil. En iyi ikisi şunlar: yalnız değer (+%4,2, t = 1,34) ve en likit 50 şirket (+%5,1, t = 1,60). 60 baz puan masrafla fark −%1,4'e düşüyor. Ayrıntılar: [`reports/PIT_Model_Raporu.md`](reports/PIT_Model_Raporu.md), [`results/pit_model/`](results/pit_model/).

| Sinyal (aylık Spearman IC, en likit 100) | IC | t |
|---|---:|---:|
| Düşük volatilite | 0,078 | 3,49 |
| Değer bileşik | 0,062 | 3,05 |
| Nakit akışı getirisi | 0,055 | 3,32 |
| Defter/piyasa | 0,052 | 3,33 |
| Son ay getirisi | 0,036 | 2,59 |
| ROA | 0,002 | 0,13 |
| Momentum 12-1 | −0,013 | −0,74 |

### Aşama 1: Faktör aileleri (Ağustos 2026 çalıştırmaları; düzeltilmemiş veri)

Evren: bugünkü Yıldız Pazar, 271 şirket. Bunlardan 265'inin finansalı işlenebildi, 251'i skorlandı; toplam 6.869 şirket-dönem gözlemi var. IC, her şirketin kendi bilanço yayınından sonraki getirisiyle hesaplandı. Bonferroni eşiği |t| ≥ 3,25 (21 test).

| Faktör | 3 ay IC | t | 6 ay IC | t | Eşik |
|---|---:|---:|---:|---:|---|
| Değer | 0,067 | 3,73 | 0,080 | 3,27 | Geçti |
| İstikrar | 0,045 | 2,75 | 0,052 | 3,17 | Kıl payı geçmedi |
| Kalite | 0,028 | 1,53 | 0,034 | 1,59 | Geçmedi |
| Borçluluk | 0,017 | 0,80 | 0,021 | 0,76 | Geçmedi |
| Yatırım | 0,015 | 1,14 | 0,007 | 0,51 | Geçmedi |
| Büyüme | 0,007 | 0,46 | 0,006 | 0,37 | Geçmedi |
| Kârlılık | −0,001 | −0,08 | 0,006 | 0,33 | Geçmedi |

Bu tablo [yönetici raporundan](reports/BIST_Faktor_Arastirmasi_Yonetici_Raporu.pdf) alındı. Rapor, şirket düzeyindeki skor dosyasından en az 10 gözlemli dönemlerle yeniden hesaplandı. 6 aylık t değerlerine Newey-West düzeltmesi uygulandı. Repodaki [`results/factor_validation/factor_ic_summary.csv`](results/factor_validation/factor_ic_summary.csv) ise filtresiz ve düzeltmesiz hesaplamadır. Bu yüzden rakamlar farklıdır ve sonuç hesaplama seçimine duyarlıdır. Filtresiz dosyada İstikrar'ın 6 aylık t değeri 3,72 (eşiği geçiyor gibi), Değer'inki 2,92 (geçmiyor gibi). Düzeltilmiş hesapta tersine dönüyor: İstikrar 3,17, Değer 3,27. Değer'in 3 aylık sonucu iki hesapta da eşiğin üstünde (3,61 ve 3,73). Şirket düzeyindeki skor dosyası repoda olmadığı için düzeltilmiş hesap buradan yeniden üretilemiyor.

Portföy tarafında Değer'in sıralama gücü eşit ağırlıklı getiriye dönüşmedi. 6 aylık en güçlü ve en zayıf dilim farkı ortalamada −%1,1, medyanda +%7,6. Diğer faktörler kontrol edildiğinde Değer'in regresyon t değeri 0,69'a (3 ay) ve 0,01'e (6 ay) düştü.

## Ne işe yaramadı ve neden

- **İlk aşamanın Değer sonucu portföye taşınmadı.** Sıralama gücü vardı, ama birkaç aşırı yükselen pahalı hisse ortalamayı domine etti. Düzeltilmiş veride değer tek başına +%4,2 fark verdi (t = 1,34). Sonuç anlamlı değil.
- **Momentum için kanıt bulunmadı.** IC −0,013 (t = −0,74). Yalnız momentum varyantı kıyasın yılda %5,8 gerisinde kaldı.
- **Banka ve sigorta için kanıt üretilemedi.** Evrende 8 banka, 1 katılım bankası ve 6 sigorta şirketi var. Profile özel kalite skorlarında hiç geçerli IC dönemi çıkmadı; az şirket sayısı olası bir neden, ama ayrıca incelenmedi.
- **Sonuç birkaç isme duyarlı.** Ana modelle bir önceki adım arasındaki 2,6 puanlık fark büyük ölçüde SODA, TRKCM ve ANACM gibi birleşen şirketlerden geliyor. Son iki ay (Ağustos–Eylül 2026 sinyalleri) çıkarılınca fark yılda −%1,0'a dönüyor.
- **Leasing ve faktoring şirketleri desteklenmiyor.** İş Yatırım bu şirketler için finansal tablo satırı döndürmüyor.

## Sınırlar

- **Hayatta kalma yanlılığı.** Aşama 1'in evreni bugünkü Yıldız Pazar listesi; borsadan çıkan pay yok. Aşama 2'ye 74 çıkmış kod eklendi (52 kottan çıkma, 19 birleşme, 3 iflas). Ancak şirketlerin geçmişte hangi pazarda olduğu bilinmiyor. Evrenin tamlığı yaklaşık %95 olarak tahmin ediliyor.
- **TMS 29 kaynaklı ileriye bakma riski.** İş Yatırım önbelleğinde 2022 yıl sonundan itibaren Aralık kolonları, sonraki raporların TMS 29'a göre yeniden ifade edilmiş rakamlarıyla üzerine yazılmış. `src/pit/financials.py` bu kolonları kendi dönemine geri deflate ediyor. Ama düzeltme eksik kalıyor:
  - Aralık 2022 ve 2023 ara dönem akışlarının nominal orijinalleri geri getirilemiyor. Bu dönem boş bırakıldı; model 2023-03 ile 2024-03 arasında 13 ay faktör pozisyonu almıyor, eşit ağırlıklı evreni tutuyor.
  - İki arşiv arasında değişen değerlerin %1 içinde geri döndürülebilen payı aktif ve özkaynakta %97, net kârda %96, faaliyet kârında %93, faaliyet nakit akışında yalnız %82. Nakit akışında küçük bir sızıntı sürüyor.
  - Aşama 1 sonuçları bu düzeltmeden önce üretildi.
- **Yayın gecikmesi.** Takvim dışı mali yılı olan 13 kod çıkarıldıktan sonra Q4 raporlarının %8,9'u dönem sonundan 90 günden geç yayımlandı (her şirket-dönemin ilk bildirimi, 5.310 rapor). Bunun çoğu 2023 yıl sonundan geliyor (%62,2); diğer yıllarda oran %1–2,4. Q1–Q3'te oran %0,2–2,6. O 13 kod dahil edilirse Q4 oranı %10,3 oluyor. Model sabit gecikme varsaymıyor, KAP yayın tarihini kullanıyor. Model evreninde tarihlerin %97,1'i gerçek KAP tarihi. PIT veri setinin tamamında ise satırların yaklaşık %80'i KAP'tan geliyor, kalanı tahmin (`results/pit_model/publish_date_coverage.csv`). Kaynak: [`results/kap_yayin_gecikmesi.txt`](results/kap_yayin_gecikmesi.txt).
- **Nominal TL ve enflasyon.** Aşama 1 getirileri nominal TL; maliyet ve likidite içermiyor. Aşama 2'de masraf var, piyasa etkisi yok. Sonuçlar USD/TRY ve kıyasla birlikte okunmalı.
- **Sektör eşlemesi kaba ve tek tarihli.** Banka, holding ve GYO aynı "Mali Kuruluşlar" sektöründe.
- **Gerçek bir test dönemi yok.** Tüm dönem araştırma sırasında görüldü. Bundan sonrası için öneri ileriye dönük kayıt tutmak.
- **Kısa pozisyon, vergi ve temettü stopajı** modellenmedi.
- Yatırım tavsiyesi değildir. Hiçbir işlem yapılmadı.

## Repo yapısı

```
README.md
LICENSE                                       MIT
reports/
  README.md                                   hangi raporun neyi geçersiz kıldığı
  PIT_Model_Raporu.md                         Aşama 2 raporu (birincil kaynak)
  BIST_Faktor_Arastirmasi_Yonetici_Raporu.pdf Aşama 1 yönetici raporu; kısmen geçersiz, bkz. reports/README.md
docs/
  veri_platformu_spec.md                      sonraki adım: vintage'lı, PIT veri platformu tasarımı (uygulanmadı)
results/
  factor_validation/                          Aşama 1 toplu özetleri (IC, dilim, regresyon; şirket düzeyi yok)
  pit_model/                                  Aşama 2 toplu özetleri (model, sinyal IC, vintage uyumu)
  kap_yayin_gecikmesi.txt                     yayın gecikmesi özeti
src/
  data/isyatirim/       İş Yatırım istemcisi, önbellek, mali grup seçimi
  data/isyatirim/profiles/  sanayi, banka, katılım bankası, sigorta, holding, GYO, leasing profilleri
  data/kap/             KAP istemcisi ve rapor yayın tarihleri
  data/market/          fiyat istemcisi (İş Yatırım HisseTekil)
  data/sector/, markets.py  BIST sektör ve pazar Excel ayrıştırıcıları
  financials/           YTD / çeyreklik / TTM snapshot ve yayın tarihi birleştirme
  factors/              faktör aileleri, skor, IC, dilim, regresyon, metrik envanteri
  pit/                  TMS 29 geri deflate, aylık panel, portföy simülasyonu
  datasets/, analysis/, utils/
scripts/                indirme, kalite raporu, doğrulama, faktör testi, yayın gecikmesi ve PIT model betikleri
tests/                  25 test dosyası, 171 test
```

## Yeniden üretme

Python 3.9 ile test edildi.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m unittest discover -s tests
```

Testler ağ erişimi olmadan çalışır. Yerel veri gerektiren 8 test, veri yoksa atlanır. `tests/test_markets.py`, belirli bir `Pazarlar.xlsx` sürümündeki şirket sayılarını bekliyor; güncel dosyayla bu testler başarısız olabilir.

Kullanılan kaynakların hiçbiri API anahtarı istemiyor; `.env.example` bu yüzden yalnızca bilgi amaçlı. Veri repoda yok ve betiklerle `data/` altına indirilir (git dışında):

1. `data/Pazarlar.xlsx` ve `data/Sektörler.xlsx`: Borsa İstanbul'un pazar ve sektör listeleri, elle indirilir.
2. `python scripts/download_market_financials.py --market "PAY PİYASASI-YILDIZ PAZAR"`: İş Yatırım mali tabloları.
3. `python -c "from src.data.kap import build_report_dates; build_report_dates(2015, 2026)"`: KAP yayın tarihleri (`data/report_dates.csv`). Gecikme özeti: `python scripts/report_publication_lag.py`.
4. `python scripts/download_market_prices.py`: fiyatlar.
5. Aşama 1: `scripts/report_snapshot_quality.py`, `report_factor_quality.py`, `validate_financial_dataset.py`, `report_factor_validation.py`.
6. Aşama 2: `scripts/download_pit_vintage.py --liquid-only`, `validate_pit_financials.py`, `run_pit_model.py`. Model ayrıca `data/universe/delisted_candidates.csv` (çıkmış şirket listesi) ve `data/macro/tufe_2003.csv` (TÜİK TÜFE) dosyalarını bekler. Bunlar repoda yok; biçimleri `scripts/run_pit_model.py` ve `src/pit/financials.py` içinde.

**Önemli:** İş Yatırım geçmiş kolonları sürekli yeniden yazdığı için, bugün indirilen veri raporlardaki 2026-11-01 arşiviyle aynı olmaz. Sonuçlar birebir yeniden üretilemez. Bu dışa aktarma için faktör ve model hesapları yeniden çalıştırılmadı; rakamlar raporlardan ve özet dosyalarından alındı. Yeniden hesaplanan tek şey, yerel KAP tablosundan üretilen yayın gecikmesi özeti.

**Bu dışa aktarmada özgün koda göre yapılan değişiklikler:**

- Yerel veri isteyen üç test dosyasına "veri yoksa atla" koşulu eklendi.
- KAP istemcisinin varsayılan bekleme süresi 0'dan 1 saniyeye çıkarıldı. `download_pit_vintage.py` varsayılanı 3 iş parçacığı ve 0,1 sn yerine 1 iş parçacığı ve 1 sn oldu.
- Paralel indirme hız ölçüm betiği (`benchmark_parallel_fetch.py`) çıkarıldı.
- `scripts/report_publication_lag.py` eklendi.
- `docs/veri_platformu_spec.md` kişisel ayrıntılar çıkarılarak kısaltıldı.

## Veri kaynakları ve lisanslar

| Kaynak | Kullanım | Repoda var mı? |
|---|---|---|
| İş Yatırım (MaliTablo, HisseTekil; resmî olmayan uç noktalar) | mali tablolar, fiyatlar | Hayır. Kullanım koşulları belirsiz, yeniden dağıtılmıyor. |
| KAP (kap.org.tr) | finansal rapor yayın tarihleri | Hayır; yalnız toplu gecikme özeti |
| Borsa İstanbul pazar ve sektör listeleri, işlem sırası kapanan şirketler | evren, sektör, çıkmış şirketler | Hayır |
| TÜİK TÜFE (ikincil sitelerden derlendi; bkz. PIT raporu kaynakları) | TMS 29 geri deflate | Hayır |
| Türetilmiş toplu özetler | IC, dilim, regresyon, model sonuçları | Evet (`results/`); şirket düzeyinde değer içermiyor |

İndirme betikleri kişisel araştırma içindir. KAP istemcisi normal akışta istekler arasında en az 1 sn bekler; hata durumundaki urllib3 yeniden denemeleri bu beklemeye tabi değil. İş Yatırım istemcileri varsayılan olarak tek iş parçacığıyla sıralı çalışır, ama ek bekleme koymaz. Kullanan kişi sağlayıcıların kullanım koşullarına uymakla sorumludur.

Lisans: kod [MIT lisansı](LICENSE) ile paylaşılıyor. Kodun indirdiği ve işlediği veriler için her veri kaynağının kendi kullanım koşulları geçerlidir; MIT lisansı bu verileri kapsamaz.

## Araçlar ve yapay zekâ beyanı

Python (pandas, NumPy, SciPy, pyarrow), unittest. Claude Code araştırma asistanı olarak kullanıldı; tasarım kararları ve yorum yazara ait.

---

## English summary

This repository contains a point-in-time financial data pipeline and factor research for Borsa Istanbul, built on İş Yatırım statements and KAP filing dates with separate mapping profiles for banks, participation banks, insurers, holdings, REITs and industrials. A first pass over seven factor families found that only Value cleared a Bonferroni-adjusted threshold, with Stability just below. That pass, however, used a survivor-only universe and vendor data that later proved to overwrite past columns with restated IAS 29 figures. After correcting for restatements, filing dates, empty-signal months and delisted stocks, a pre-specified Value + Momentum portfolio beat its cap-weighted benchmark by only +0.3% a year (t = 0.08), against +10.7% (t = 2.74) on the uncorrected data. The main contribution is showing how these data biases, corrected step by step, remove an apparent alpha from a Turkish equity backtest; signal-level evidence for value and low volatility remains a hypothesis for forward testing, not a finding.
