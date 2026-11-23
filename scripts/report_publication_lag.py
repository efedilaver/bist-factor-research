#!/usr/bin/env python3
"""KAP finansal rapor yayın gecikmesini dönem sonuna göre özetler.

Her şirket-dönem için ilk KAP bildirimi alınır; gecikme, dönem sonundan yayın gününe kadar geçen
takvim günüdür. Çıktı, sabit bir "dönem sonu + N gün" varsayımının ne kadar güvenli olduğunu gösterir.

    python scripts/report_publication_lag.py --input data/report_dates.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PERIOD_END = {1: "-03-31", 2: "-06-30", 3: "-09-30", 4: "-12-31"}
# src/pit/report_dates.py'deki kuralın KAP koduna uygulanmış hali: medyan gecikmesi 120 günü aşan kodların mali yılı takvim dışıdır.
OFF_CALENDAR_MEDIAN_LAG_DAYS = 120


def first_filings(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["publish_date"] = pd.to_datetime(frame["publish_date"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    frame = frame[frame["period"].isin(PERIOD_END)].dropna(subset=["year", "publish_date"])
    frame["year"] = frame["year"].astype(int)
    frame["period"] = frame["period"].astype(int)
    period_end = pd.to_datetime(frame["year"].astype(str) + frame["period"].map(PERIOD_END))
    frame["lag_days"] = (frame["publish_date"].dt.normalize() - period_end).dt.days
    return (
        frame.sort_values("publish_date")
        .groupby(["stock_code", "year", "period"], as_index=False)
        .first()
    )


def drop_off_calendar(filings: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    median_lag = filings.groupby("stock_code")["lag_days"].median()
    off = sorted(median_lag.index[median_lag > OFF_CALENDAR_MEDIAN_LAG_DAYS])
    return filings.loc[~filings["stock_code"].isin(off)], off


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "report_dates.csv")
    parser.add_argument("--threshold", type=int, default=90, help="gecikme eşiği (gün)")
    args = parser.parse_args()

    all_filings = first_filings(pd.read_csv(args.input))
    all_q4 = all_filings.loc[all_filings["period"].eq(4), "lag_days"]
    filings, off_calendar = drop_off_calendar(all_filings)
    print(
        f"Takvim dışı mali yıl nedeniyle çıkarılan kod sayısı: {len(off_calendar)} "
        f"(bunlar dahil Q4 geç payı: {(all_q4 > args.threshold).mean():.3f}, {len(all_q4)} rapor)\n"
    )
    late = filings["lag_days"] > args.threshold

    by_period = filings.assign(late=late).groupby("period").agg(
        filings=("lag_days", "size"), median_lag=("lag_days", "median"), late_share=("late", "mean")
    )
    print(f"Dönem sonundan {args.threshold} günden geç yayımlanan ilk raporların payı:\n")
    print(by_period.round(3).to_string())

    q4 = filings.loc[filings["period"].eq(4)].assign(late=late)
    by_year = q4.groupby("year").agg(filings=("late", "size"), late_share=("late", "mean"))
    print("\nYıl sonu (Q4) raporları, mali yıla göre:\n")
    print(by_year.loc[by_year["filings"] >= 50].round(3).to_string())


if __name__ == "__main__":
    main()
