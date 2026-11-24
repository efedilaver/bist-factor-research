"""README grafiklerini results/ altındaki özet dosyalarından üretir.

Çalıştırma (repo kökünden):  python scripts/grafikler.py
Çıktı: results/figures/*.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
CIKTI = KOK / "results" / "figures"
CIKTI.mkdir(parents=True, exist_ok=True)

MAVI = "#2a78d6"
TURUNCU = "#eb6834"
GRI = "#a3a29c"
METIN = "#0b0b0b"
IKINCIL = "#52514e"
IZGARA = "#e6e5e0"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.edgecolor": IZGARA,
    "axes.labelcolor": IKINCIL,
    "xtick.color": IKINCIL,
    "ytick.color": METIN,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def yuzde(x, isaret=True, ondalik=1):
    on = ("+" if x >= 0 else "−") if isaret else ("" if x >= 0 else "−")
    return on + "%" + f"{abs(x) * 100:.{ondalik}f}".replace(".", ",")


def kaydet(fig, ad):
    fig.savefig(CIKTI / ad, facecolor="white")
    plt.close(fig)
    print("yazıldı:", CIKTI / ad)


# 1) Düzeltmeler adım adım: yıllık fazla getiri ve %95 güven aralığı
ms = pd.read_csv(KOK / "results/pit_model/model_summary.csv")
adimlar = [
    ("bias_A", "Düzeltilmemiş veri,\nbugünkü Yıldız Pazar"),
    ("bias_B0", "+ TMS 29 ve yayın tarihi\ndüzeltmesi"),
    ("bias_B:", "+ sinyal yoksa\npozisyon alma"),
    ("bias_C", "+ bugünkü tüm hisseler"),
    ("PRIMARY", "+ borsadan çıkanlar\n(ana model)"),
]
satirlar = []
for anahtar, etiket in adimlar:
    r = ms[ms["label"].str.startswith(anahtar)].iloc[0]
    satirlar.append((etiket, r.excess_vs_cap_ann, r.ci95_low_vs_cap, r.ci95_high_vs_cap, r.t_vs_cap))

fig, ax = plt.subplots(figsize=(8, 4.2))
for i, (etiket, x, lo, hi, t) in enumerate(satirlar):
    y = len(satirlar) - 1 - i
    renk = TURUNCU if i == len(satirlar) - 1 else MAVI
    ax.plot([lo, hi], [y, y], color=renk, lw=2, solid_capstyle="round", alpha=0.45)
    ax.plot(x, y, "o", ms=9, color=renk, mec="white", mew=2, zorder=3)
    ax.text(hi + 0.008, y, f"{yuzde(x)}  (t = {t:.2f})".replace(".", ","),
            va="center", fontsize=10, color=METIN)
ax.axvline(0, color=IKINCIL, lw=1)
ax.set_yticks(range(len(satirlar)))
ax.set_yticklabels([s[0] for s in reversed(satirlar)])
ax.set_xlim(-0.09, 0.27)
ax.xaxis.set_major_formatter(lambda v, _: yuzde(v, isaret=False, ondalik=0))
ax.set_xlabel("Piyasa değeri ağırlıklı evrene göre yıllık fazla getiri (masraf sonrası, %95 güven aralığı)")
ax.grid(axis="x", color=IZGARA, lw=0.8)
ax.set_axisbelow(True)
ax.tick_params(axis="y", length=0)
kaydet(fig, "duzeltme_adimlari.png")


# 2) Sinyal düzeyinde aylık Spearman IC (düzeltilmiş veri, en likit 100)
ic = pd.read_csv(KOK / "results/pit_model/signal_ic.csv")
adlar = {
    "low_volatility": "Düşük volatilite",
    "value": "Değer (bileşik)",
    "cfo_yield": "Nakit akışı getirisi",
    "book_to_price": "Defter / piyasa",
    "ebit_ev": "FVÖK / FD",
    "earnings_yield": "Kâr getirisi",
    "value_momentum": "Değer + momentum",
    "last_month_return": "Son ay getirisi",
    "roa": "Aktif kârlılığı",
    "momentum_12_1": "Momentum 12-1",
}
ic = ic[ic["signal"].isin(adlar)].sort_values("ic_all")
fig, ax = plt.subplots(figsize=(8, 4.2))
ys = range(len(ic))
renkler = [MAVI if v >= 0 else GRI for v in ic["ic_all"]]
ax.barh(list(ys), ic["ic_all"], color=renkler, height=0.62)
for y, (v, t) in enumerate(zip(ic["ic_all"], ic["t_all"])):
    x = v + 0.002 if v >= 0 else v - 0.002
    ax.text(x, y, f"{v:.3f}  t {t:.1f}".replace(".", ",").replace("-", "−"), va="center",
            ha="left" if v >= 0 else "right", fontsize=9, color=IKINCIL)
ax.set_yticks(list(ys))
ax.set_yticklabels([adlar[s] for s in ic["signal"]])
ax.axvline(0, color=IKINCIL, lw=1)
ax.set_xlim(-0.04, 0.11)
ax.xaxis.set_major_formatter(lambda v, _: f"{v:.2f}".replace(".", ",").replace("-", "−"))
ax.set_xlabel("Aylık Spearman IC ortalaması (düzeltilmiş veri, en likit 100 hisse)")
ax.tick_params(axis="y", length=0)
ax.grid(axis="x", color=IZGARA, lw=0.8)
ax.set_axisbelow(True)
kaydet(fig, "sinyal_ic.png")
