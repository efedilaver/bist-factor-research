"""Merge financial snapshots with report-date metadata."""

from __future__ import annotations

import pandas as pd

from src.utils.dates import quarter_end_timestamp


def merge_report_dates(financial_snapshot: pd.DataFrame, report_dates: pd.DataFrame) -> pd.DataFrame:
    """Attach `publish_date` rows from report dates to a financial snapshot."""
    snapshot = financial_snapshot.copy()
    dates = report_dates.copy()

    dates["stock_code"] = dates["stock_code"].astype(str).str.upper()
    snapshot["symbol"] = snapshot["symbol"].astype(str).str.upper()

    dates["year"] = pd.to_numeric(dates["year"], errors="coerce").astype("Int64")
    dates["period"] = pd.to_numeric(dates["period"], errors="coerce").astype("Int64")
    dates = dates.dropna(subset=["year", "period"])
    dates["period"] = [
        quarter_end_timestamp(year, period)
        for year, period in zip(dates["year"], dates["period"])
    ]
    dates = (
        dates.sort_values("publish_date", kind="mergesort")
        .drop_duplicates(subset=["stock_code", "period"], keep="first")
        .reset_index(drop=True)
    )

    snapshot = snapshot.drop(columns=["publish_date"], errors="ignore")

    merged = snapshot.merge(
        dates[["stock_code", "period", "publish_date"]],
        how="left",
        left_on=["symbol", "period"],
        right_on=["stock_code", "period"],
    )

    return merged.drop(columns=["stock_code"], errors="ignore")
