# BIST Çok Faktörlü Model: Düzeltilmiş Veriyle Test

> **Repo notu:** Rapor özgün haliyle bırakıldı. Atıf yapılan bazı dosyalar bu repoda yok:
> `data/vintages/` (İş Yatırım arşivi, lisans), `data/universe/delisted_candidates.csv` (BIST
> listesinden türetilmiş), `data/reports/pit_model/paper_portfolio_latest.csv` (hisse adı içeren
> model seçimi; tavsiye gibi okunmaması için). Toplu sonuç tabloları `results/pit_model/` altında.

Tarih: 1 Kasım 2026. Veri: İş Yatırım 2026-11-01 arşivi, KAP yayın tarihleri, TÜİK TÜFE.
Dönem: Ağustos 2016 – Ekim 2026, 122 ay. Yatırım tavsiyesi değildir.

## Sonuç

Önceden sabitlenen Value + Momentum modeli, veri sorunları düzeltildiğinde piyasayı yenmiyor.

| Ölçü (masraf sonrası) | Değer |
|---|---|
| Yıllık getiri, TL | %32,3 |
| Piyasa değeri ağırlıklı evren, TL | %32,5 |
| USD/TRY yıllık artış | %32,0 |
| Yıllık getiri, USD | %0,2 |
| Piyasa değeri ağırlıklı evrene fark | yılda +%0,3, t = 0,08 |
| %95 güven aralığı | yılda −%6,6 ile +%5,8 |
| Eşit ağırlıklı evrene fark | yılda +%1,5, t = 0,34 |

Modelin alfa üretmediğini kanıtlamış değiliz: güven aralığı geniş. Ama alfa ürettiğine dair kanıt da yok.

## Eski sonuç nereye gitti

Aynı kurallar, her adımda bir düzeltme eklenerek çalıştırıldı. Kıyas: piyasa değeri ağırlıklı evren.

| Adım | Yıllık fark | t | Değişim |
|---|---:|---:|---:|
| A. Düzeltilmemiş veri, bugünün Yıldız Pazar'ı | +%10,7 | 2,74 | |
| B0. Aralık/TTM ve yayın tarihi düzeltmesi | +%10,0 | 2,62 | −0,7 |
| B. Sinyal hesaplanamayan aylarda pozisyon almama | +%7,6 | 2,27 | −2,4 |
| C. Yıldız yerine bugünkü tüm hisseler | +%2,9 | 0,78 | −4,7 |
| Ana model. Borsadan çıkanlar da dahil | +%0,3 | 0,08 | −2,6 |

Değişim sütunu adımların sırasına bağlıdır, kesin paylar olarak okunmamalı.

- **En büyük kayıp evren seçiminden geliyor.** Bugünün Yıldız Pazar'ı geçmişe uygulanınca kazananlar önceden seçilmiş oluyor.
- **Aralık düzeltmesi tek başına az etkili.** Veri hatası büyük ama bu kural setinde getiriyi az değiştiriyor.
- **Sinyalsiz aylar sonucu şişiriyordu.** 2023-03 ile 2024-02 arasında çoğu şirketin TTM verisi yok. İlk kod bunu fark etmeden portföyü 3 bankaya indiriyordu. Bu adımı bağımsız kod incelemesi yakaladı.
- **Son adım büyük ölçüde gürültü.** Kıyas endeksleri neredeyse hiç değişmiyor. Fark, SODA, TRKCM ve ANACM gibi birleşen şirketlerin 2016–2021'de başka isimlerin yerini almasından geliyor. Birkaç isim değişince yılda 2,6 puan oynaması, sonucun ne kadar kırılgan olduğunu gösteriyor.

## Veri bulguları

**1. İş Yatırım geçmiş kolonları değiştiriyor.** TMS 29 raporlayan şirketlerde (XI_29 grubu) her dönem için tek değer tutuluyor ve yeni raporların karşılaştırmalı rakamlarıyla üzerine yazılıyor:

- Ara dönem bilançolar değişmiyor.
- Ara dönem gelir ve nakit akışı, bir yıl sonraki aynı dönemin satın alma gücüne taşınıyor.
- Aralık kolonları, gelir ve bilanço dahil, sonraki mali yılın son raporunun satın alma gücüne taşınıyor.

Kanıt: Ağustos 2026 önbelleği ile Kasım 2026 arşivi arasındaki oranlar TÜFE oranlarıyla eşleşiyor. Örneğin bilançoda 1,070, TÜFE Haziran/Mart 2026 ile aynı.

Düzeltme: `src/pit/financials.py` kolonları kendi dönemine geri deflate ediyor.

| Kontrol | Sonuç |
|---|---|
| Aralıkta sıçrayıp sonra düşen şirket payı, 2024 | ham veride %89 (sanayi/holding/GYO), düzeltilmişte %0,5 (tüm arşiv) |
| Aralıkta sıçrayıp sonra düşen şirket payı, 2025 | ham veride %15 (sanayi/holding/GYO), düzeltilmişte %1,3 (tüm arşiv) |
| İki arşiv arasında değişen değerlerden %1 içinde geri dönen: aktif, özkaynak | %97 |
| Aynı ölçü: net kâr | %96 |
| Aynı ölçü: faaliyet kârı (EBIT) | %93 |
| Aynı ölçü: faaliyet nakit akışı | %82 |

Faaliyet nakit akışında değişenlerin %14'ü %5'ten, %9'u %20'den fazla sapıyor. Bunlar enflasyon dışı gerçek yeniden düzenlemeler ve deflate ile ayrıştırılamıyor; geçmişe sızma küçük de olsa sürüyor. Nakit akışını değer skorundan çıkarmak sonucu değiştirmedi (yılda 0,0).

**2. Geri getirilemeyen pencere.** Aralık 2022 ile 2023 ara dönem akışlarının nominal orijinalleri kaybolmuş. Tahmin edilmedi, boş bırakıldı. Bu yüzden model 2023-03 ile 2024-03 arasında 13 ay pozisyon almıyor, eşit ağırlıklı evren tutuyor. İş Yatırım her yeni raporda kolonları yeniden yazdığı için eski değerler ancak tarihli kopyayla korunabiliyor; `scripts/download_pit_vintage.py` bunu yapıyor.

**3. Yayın tarihi boşlukları.** KAP kodu ile hisse kodu farklı olan 25 şirket eşleşmiyordu (TSK=TSKB, SEK=SKBNK, OYA=OYYAT ve benzeri). Ad üzerinden eşleşme eklendi. Model evreninde yayın tarihlerinin %97,1'i gerçek, %2,9'u tahmin. 2026'da tahmin payı %13,5, çünkü KAP tablosu 2026-08-06'da bitiyor.

**4. Eski rapordaki "sızıntı yok" ifadesi geçerli değil.** `reports/BIST_Faktor_Arastirmasi_Yonetici_Raporu.pdf` yalnızca fiyat tarihini yayın tarihiyle karşılaştırıyor; değerlerin sonradan değiştirildiğini görmüyor. O rapordaki sonuçlar bu raporla değerlendirilmeli.

**5. Borsadan çıkanlar.** 74 kod bulundu (delisting 52, birleşme 19, iflas 3). Sadece 13'ü 1 milyon dolarlık hacim sınırını aşmış. Hacim sınırı sayesinde modelin evreninde hayatta kalma hatası sanıldığından dar. Tamlık tahmini yaklaşık %95.

**6. Sahte fiyat satırları.** Kaynak, durdurulan veya çıkan hisseler için sıfır hacimli düz satırlar üretiyor (ROYAL'de 761 satır). Bunlar temizlendi.

**7. Kodda tarih hatası.** `src/data/market/client.py` ISO tarihleri yanlış okuyordu: `2026-11-01`, 11 Ocak 2026 oluyordu. Düzeltildi ve test eklendi. Aynı fonksiyonu ISO tarihle kullanan eski indirmeler etkilenmiş olabilir.

## Sinyaller

Aylık Spearman IC, top-100 likit evren. Pozitif değer sinyalin sonraki ay getirisiyle aynı yönde olduğunu gösterir.

| Sinyal | IC | t | 2023-02'ye kadar IC | 2024-05 sonrası IC |
|---|---:|---:|---:|---:|
| Düşük volatilite | 0,078 | 3,49 | 0,057 | 0,093 |
| Değer bileşik | 0,062 | 3,05 | 0,050 | 0,077 |
| Defter/piyasa | 0,052 | 3,33 | 0,047 | 0,043 |
| Nakit akışı getirisi | 0,055 | 3,32 | 0,054 | 0,047 |
| Son ay getirisi | 0,036 | 2,59 | 0,027 | 0,092 |
| ROA | 0,002 | 0,13 | −0,001 | 0,026 |
| Momentum 12-1 | −0,013 | −0,74 | −0,028 | 0,014 |

Değer ve düşük volatilite iki rejimde de aynı işarette. Momentum çalışmıyor.

## Duyarlılık

Ana modelin her seferinde tek kuralı değiştirildi. Piyasa değeri ağırlıklı evrene yıllık fark:

| Varyant | Fark | t |
|---|---:|---:|
| Sadece değer | +%4,2 | 1,34 |
| Top 50 likit | +%5,1 | 1,60 |
| İnce portföye izin ver (3 banka dönemi) | +%3,6 | 0,87 |
| Değer + düşük volatilite (sonradan denendi) | +%2,5 | 0,73 |
| Tavan yapan hisseye girme | +%1,3 | 0,40 |
| Top 150 likit | +%0,8 | 0,24 |
| Tutma tamponu yok | +%0,1 | 0,03 |
| Nakit akışı olmadan değer | 0,0 | −0,01 |
| Değer eksikse momentum | 0,0 | −0,01 |
| 60 baz puan işlem maliyeti | −%1,4 | −0,39 |
| Korkuluklar yok | −%2,5 | −0,68 |
| Sadece momentum | −%5,8 | −0,93 |

Hiçbiri anlamlı değil. Bu tablodaki 19 senaryo ve ilk turdaki 27 deneme hesaba katıldığında, en iyi varyant bile çoklu test eşiğinin çok altında. Sadece değer ve top 50 sonuçları test edilecek hipotezdir, bulgu değil.

Son iki ay (Ağustos ve Eylül 2026 sinyalleri, spekülatif hisselerde taban serisi) ana modele yılda yaklaşık 1,3 puan katıyor. Bu aylar çıkarılınca fark yılda −%1,0, t = −0,31.

## Önceden sabitlenen kurallar

- Evren: 63 günlük medyan hacmi en az 1 milyon dolar, piyasa değeri en az 50 milyon dolar olan en likit 100 şirket.
- Skor: sektör nötr değer (EBIT/EV, nakit akışı, kâr, defter getirisi) ve momentum 12-1, eşit ağırlıklı.
- Portföy: en iyi %20'yi al, ilk %40'ın altına düşeni sat, sektör başına en çok %30, eşit ağırlık. Yeniden dengeleme aylık; sinyal ay sonu kapanışı, işlem ertesi gün kapanışı.
- Korkuluk: en yüksek volatiliteli ve en sert sıçramalı %10 ile en düşük ROA'lı %10 ve negatif özkaynak alınmaz.
- Maliyet: tek yön 30 baz puan.

Temel kuralları sonuçları görmeden koydum ve değiştirmedim. Şu kurallar sonradan, veri geçerliliği gerekçesiyle eklendi. Bazılarının getiri etkisini inceleme raporundan biliyordum, yani tam körlemesine değiller:

- Skorlanan pay %50'nin altındaysa veya portföy 10 ismin altına düşüyorsa eşit ağırlıklı evren tutulur.
- Eski dönemin geç dosyası yeni bilançonun yerini alamaz.
- Mali yılı takvim dışı olan 13 hisse (medyan yayın gecikmesi 120 günden fazla: BJKAS, FENER, GSRAY, TSPOR, DOCO ve diğerleri) finansal veri kullanmaz, yani alınmaz.
- Durdurulan pozisyon işlem görene kadar satılamaz.
- Veri sağlayıcının sıfır yazdığı hücreler boş sayılır.

## Sınırlamalar

- **TÜFE:** 2026-06 ile 2026-09 arası aylık değişimlerden zincirlendi; 2026 kümülatif değeriyle tutuyor.
- **Evren üyeliği:** şirket listesi bugünkü liste artı borsadan çıkanlar; o tarihte hangi pazarda olduğu bilinmiyor. Likidite filtresi bunu kısmen kapatıyor.
- **Sektör:** eşleme tek tarihli ve kaba; banka, holding ve GYO aynı "Mali Kuruluşlar" sektöründe. 13 çıkan şirketin sektörünü elle atadım.
- **Birleşme çıkışı:** son fiyattan nakde dönüş varsayıldı. Ardıl hisseye geçiş modellenmedi.
- **Çıkış cezası sonuçsuz:** %30 ve %100 ceza senaryoları sonucu değiştirmedi, çünkü zorunlu çıkan hiçbir şirket o ay evrende değildi. Bu, cezanın önemsiz olduğunu kanıtlamaz; o isimler daha önce likiditeyi kaybetmiş.
- **Taban serisi:** 520 satıştan yalnızca 1'i taban gününe denk geldi, ama tutulan pozisyonlarda toplam likidite kuruması modellenmedi. Masraf sabit, piyasa etkisi yok.
- **Kısa pozisyon, vergi ve temettü stopajı:** yok. `close` temettü düzeltmeli.
- **Bankalar:** TMS 29 uygulamıyor ama sektör eşlemesinde TMS 29 uygulayan holdinglerle aynı grupta. Sektör nötr skor bu farkı gideremiyor.
- **Holding NAV iskontosu:** veri olmadığı için kurulmadı.
- **Gerçek holdout yok:** tüm dönem araştırma sırasında görüldü.

## Önerilen sonraki adım

Geçmişten daha fazla sonuç çıkarmak yerine ileriye dönük kayıt tutmak. `data/reports/pit_model/paper_portfolio_latest.csv`, 2026-10-30 sinyaliyle kuralların seçtiği 18 ismi içeriyor; bu bir tavsiye değil, kayıt başlangıcı. Her ay sonu yeni arşiv alınırsa hem kağıt portföy izlenir hem de ileride gerçek point-in-time veri birikir. Test edilecek hipotezler önceden yazılmalı: sadece değer ve değer + düşük volatilite.

## Çalıştırma

```bash
python3 scripts/download_pit_vintage.py --vintage 2026-11-01 --liquid-only --workers 2
python3 scripts/validate_pit_financials.py
python3 scripts/run_pit_model.py
```

Çıktılar `data/reports/pit_model/` altında. Arşiv `data/vintages/` altında ve git dışında (244 MB).

## Kaynaklar

- TÜFE: [hakedis.org](https://www.hakedis.org/endeksler/tuketici-fiyat-genel-endeksi-ve-degisim-oranlari-2003), [halkarz.com](https://halkarz.com/haberler/tufe-eylul-2026da-yillik-yuzde-29-nokta-73-artti/), [Gazete Oksijen](https://gazeteoksijen.com/ekonomi/eylulde-enflasyon-yillik-yuzde-29-73-aylik-yuzde-1-84-oldu-291680)
- EREGL harici kontrol: [Midas](https://www.getmidas.com/midasin-kulaklari/eregli-demir-celikten-4-ceyrekte-269-milyar-tl-net-kar-p-96610), [Bloomberg HT](https://www.bloomberght.com/eregli-den-3-ceyrekte-800-milyon-lira-net-kr-2362887)
- Eylül–Ekim 2026 düşüşü: [Foreks](https://www.foreks.com/haber/detay/6ae4ba7b422c786f3f7adc78/PICNEWS/tr/borsa-istanbul-da-bist-100-endeksi-ekim-ayinda-yuzde-9-94-dustu-30-10-26/), [Endeks24](https://www.endeks24.com/bist-100den-cikan-hisseler-ekim-2026)
- Borsadan çıkanlar: Borsa İstanbul `IslemSirasiKapananSirketler.xls`, KAP duyuruları; ayrıntı `data/universe/delisted_candidates.csv`
