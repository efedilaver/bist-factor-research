# Ayrıntılar

README'nin kısa tuttuğu her şey burada: tam sonuç tabloları, ne işe yaramadığı, sınırlar, yöntem, yeniden üretme ve veri kaynakları.

## Aşama 2 sonuçları (Kasım 2026)

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

Tek kural değiştirilerek yapılan 14 duyarlılık testinin hiçbiri anlamlı değil. En iyi ikisi şunlar: yalnız değer (+%4,2, t = 1,34) ve en likit 50 şirket (+%5,1, t = 1,60). 60 baz puan masrafla fark −%1,4'e düşüyor. Ayrıntılar: [`reports/PIT_Model_Raporu.md`](../reports/PIT_Model_Raporu.md), [`results/pit_model/`](../results/pit_model/).

| Sinyal (aylık Spearman IC, en likit 100) | IC | t |
|---|---:|---:|
| Düşük volatilite | 0,078 | 3,49 |
| Değer bileşik | 0,062 | 3,05 |
| Nakit akışı getirisi | 0,055 | 3,32 |
| Defter/piyasa | 0,052 | 3,33 |
| Son ay getirisi | 0,036 | 2,59 |
| ROA | 0,002 | 0,13 |
| Momentum 12-1 | −0,013 | −0,74 |

## Aşama 1 sonuçları: faktör aileleri (Ağustos 2026 çalıştırmaları; düzeltilmemiş veri)

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

Bu tablo [yönetici raporundan](../reports/BIST_Faktor_Arastirmasi_Yonetici_Raporu.pdf) alındı. Rapor, şirket düzeyindeki skor dosyasından en az 10 gözlemli dönemlerle yeniden hesaplandı. 6 aylık t değerlerine Newey-West düzeltmesi uygulandı. Repodaki [`results/factor_validation/factor_ic_summary.csv`](../results/factor_validation/factor_ic_summary.csv) ise filtresiz ve düzeltmesiz hesaplamadır. Bu yüzden rakamlar farklıdır ve sonuç hesaplama seçimine duyarlıdır. Filtresiz dosyada İstikrar'ın 6 aylık t değeri 3,72 (eşiği geçiyor gibi), Değer'inki 2,92 (geçmiyor gibi). Düzeltilmiş hesapta tersine dönüyor: İstikrar 3,17, Değer 3,27. Değer'in 3 aylık sonucu iki hesapta da eşiğin üstünde (3,61 ve 3,73). Şirket düzeyindeki skor dosyası repoda olmadığı için düzeltilmiş hesap buradan yeniden üretilemiyor.

Portföy tarafında Değer'in sıralama gücü eşit ağırlıklı getiriye dönüşmedi. 6 aylık en güçlü ve en zayıf dilim farkı ortalamada −%1,1, medyanda +%7,6. Diğer faktörler kontrol edildiğinde Değer'in regresyon t değeri 0,69'a (3 ay) ve 0,01'e (6 ay) düştü.

## Ne işe yaramadı ve neden

- İlk aşamanın Değer sonucu portföye taşınmadı. Sıralama gücü vardı, ama birkaç aşırı yükselen pahalı hisse ortalamayı domine etti. Düzeltilmiş veride değer tek başına +%4,2 fark verdi (t = 1,34). Sonuç anlamlı değil.
- Momentum için kanıt bulunmadı. IC −0,013 (t = −0,74). Yalnız momentum varyantı kıyasın yılda %5,8 gerisinde kaldı.
- Banka ve sigorta için kanıt üretilemedi. Evrende 8 banka, 1 katılım bankası ve 6 sigorta şirketi var. Profile özel kalite skorlarında hiç geçerli IC dönemi çıkmadı; az şirket sayısı olası bir neden, ama ayrıca incelenmedi.
- Sonuç birkaç isme duyarlı. Ana modelle bir önceki adım arasındaki 2,6 puanlık fark büyük ölçüde SODA, TRKCM ve ANACM gibi birleşen şirketlerden geliyor. Son iki ay (Ağustos–Eylül 2026 sinyalleri) çıkarılınca fark yılda −%1,0'a dönüyor.
- Leasing ve faktoring şirketleri desteklenmiyor. İş Yatırım bu şirketler için finansal tablo satırı döndürmüyor.

## Sınırlar

- Hayatta kalma yanlılığı. Aşama 1'in evreni bugünkü Yıldız Pazar listesi; borsadan çıkan pay yok. Aşama 2'ye 74 çıkmış kod eklendi (52 kottan çıkma, 19 birleşme, 3 iflas). Ancak şirketlerin geçmişte hangi pazarda olduğu bilinmiyor. Evrenin tamlığı yaklaşık %95 olarak tahmin ediliyor.
- TMS 29 kaynaklı ileriye bakma riski. İş Yatırım önbelleğinde 2022 yıl sonundan itibaren Aralık kolonları, sonraki raporların TMS 29'a göre yeniden ifade edilmiş rakamlarıyla üzerine yazılmış. `src/pit/financials.py` bu kolonları kendi dönemine geri deflate ediyor. Ama düzeltme eksik kalıyor:
  - Aralık 2022 ve 2023 ara dönem akışlarının nominal orijinalleri geri getirilemiyor. Bu dönem boş bırakıldı; model 2023-03 ile 2024-03 arasında 13 ay faktör pozisyonu almıyor, eşit ağırlıklı evreni tutuyor.
  - İki arşiv arasında değişen değerlerin %1 içinde geri döndürülebilen payı aktif ve özkaynakta %97, net kârda %96, faaliyet kârında %93, faaliyet nakit akışında yalnız %82. Nakit akışında küçük bir sızıntı sürüyor.
  - Aşama 1 sonuçları bu düzeltmeden önce üretildi.
- Yayın gecikmesi. Takvim dışı mali yılı olan 13 kod çıkarıldıktan sonra Q4 raporlarının %8,9'u dönem sonundan 90 günden geç yayımlandı (her şirket-dönemin ilk bildirimi, 5.310 rapor). Bunun çoğu 2023 yıl sonundan geliyor (%62,2); diğer yıllarda oran %1–2,4. Q1–Q3'te oran %0,2–2,6. O 13 kod dahil edilirse Q4 oranı %10,3 oluyor. Model sabit gecikme varsaymıyor, KAP yayın tarihini kullanıyor. Model evreninde tarihlerin %97,1'i gerçek KAP tarihi. PIT veri setinin tamamında ise satırların yaklaşık %80'i KAP'tan geliyor, kalanı tahmin (`results/pit_model/publish_date_coverage.csv`). Kaynak: [`results/kap_yayin_gecikmesi.txt`](../results/kap_yayin_gecikmesi.txt).
- Nominal TL ve enflasyon. Aşama 1 getirileri nominal TL; maliyet ve likidite içermiyor. Aşama 2'de masraf var, piyasa etkisi yok. Sonuçlar USD/TRY ve kıyasla birlikte okunmalı.
- Sektör eşlemesi kaba ve tek tarihli. Banka, holding ve GYO aynı "Mali Kuruluşlar" sektöründe.
- Gerçek bir test dönemi yok. Tüm dönem araştırma sırasında görüldü. Bundan sonrası için öneri ileriye dönük kayıt tutmak.
- Kısa pozisyon, vergi ve temettü stopajı modellenmedi.
- Yatırım tavsiyesi değildir. Hiçbir işlem yapılmadı.

## Araştırma disiplini

- Kurallar sonuçtan önce yazıldı. Evren, skor, portföy kuralları, korkuluklar ve maliyet varsayımı ikinci aşamanın sonuçları görülmeden sabitlendi ve değiştirilmedi. Sonradan veri geçerliliği gerekçesiyle eklenen beş kural raporda ayrıca listeleniyor. Bunların bir kısmının getiri etkisi önceden biliniyordu; bu açıkça yazıldı. Kanıt, raporun kendisidir. Repo araştırma bittikten sonra oluşturuldu; commit tarihleri ön kaydın kanıtı değildir.
- Düzeltmeler tek tek eklendi. Her veri düzeltmesi aynı kural setine sırayla eklenip etkisi ayrı ayrı ölçüldü (README'deki grafik).
- Çoklu test bilinci. İlk aşamada 7 aile × 3 ufuk = 21 test için Bonferroni eşiği (|t| ≥ 3,25) kullanıldı. İkinci aşamada ilk turdaki 27 deneme ve 19 senaryo birlikte sayıldı. Bu sayı hesaba katılınca en iyi varyant bile eşiğin çok altında kalıyor.
- İstatistik. Aşama 1 yönetici raporundaki yeniden hesaplamada, 6 aylık ufukta örtüşen getiri pencereleri için Newey-West düzeltmesi kullanıldı. 10'dan az gözlemli dönemler de IC ortalamasından çıkarıldı. Koddaki IC hattı (`src/factors/ic.py`) bunu henüz yapmıyor: varsayılan olarak 3 gözlemli dönemleri kabul ediyor ve örtüşme düzeltmesi yok. Bu yüzden `results/factor_validation/` altındaki dosyalar düzeltmesiz rakamları gösteriyor.
- Bağımsız inceleme. Sinyalsiz aylarda portföyün üç bankaya inmesi hatasını bağımsız bir kod incelemesi yakaladı.
- Eski sonuç geri çekildi. İlk aşamanın raporundaki "ileriye dönük veri sızıntısı yok" ifadesi yanlıştı. Rapor silinmedi; yanlış olduğu yeni raporda yazıldı.

## Repo yapısı

```
README.md
docs/AYRINTILAR.md                            bu dosya
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
  figures/                                    README grafikleri (scripts/grafikler.py üretir)
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

Lisans: kod [MIT lisansı](../LICENSE) ile paylaşılıyor. Kodun indirdiği ve işlediği veriler için her veri kaynağının kendi kullanım koşulları geçerlidir; MIT lisansı bu verileri kapsamaz.
