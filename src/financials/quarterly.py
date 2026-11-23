"""Quarterly conversion helpers for financial snapshots."""

from __future__ import annotations

import pandas as pd

from src.utils.constants import BASE_SNAPSHOT_COLUMNS

INCOME_COLUMNS = [
    "net_income",
    "ebit",
    "depreciation",
    "ebitda",
    "operating_cash_flow",
    "free_cash_flow",
]


def _convert_ytd_to_quarterly(ytd_snapshot: pd.DataFrame) -> pd.DataFrame:
    """Convert YTD income values into quarterly values within each fiscal year."""
    result = ytd_snapshot.copy()
    if result.empty:
        return result

    if not result["period"].is_monotonic_increasing:
        result = result.sort_values("period", kind="mergesort").reset_index(drop=True)

    result["_fiscal_year"] = result["period"].dt.year
    quarterly_groups: list[pd.DataFrame] = []

    for _, group in result.groupby("_fiscal_year", sort=False):
        group = group.reset_index(drop=True)
        for column in INCOME_COLUMNS:
            ytd_values = pd.to_numeric(group[column], errors="coerce")
            quarterly_values = ytd_values.copy()
            if len(ytd_values) >= 2:
                quarterly_values.iloc[1:] = (
                    ytd_values.iloc[1:].to_numpy() - ytd_values.iloc[:-1].to_numpy()
                )
            group[column] = quarterly_values
        quarterly_groups.append(group)

    result = pd.concat(quarterly_groups, ignore_index=True)
    result = result.drop(columns=["_fiscal_year"], errors="ignore")
    return result[BASE_SNAPSHOT_COLUMNS]
