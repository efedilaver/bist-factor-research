"""Trailing-twelve-month helpers for financial snapshots."""

from __future__ import annotations

import pandas as pd

from .quarterly import INCOME_COLUMNS
from src.utils.constants import BASE_SNAPSHOT_COLUMNS

TTM_WINDOW = 4


def _build_ttm_snapshot(quarterly_snapshot: pd.DataFrame) -> pd.DataFrame:
    """Build TTM values from quarterly values using a rolling four-quarter sum."""
    result = quarterly_snapshot.copy()
    if result.empty:
        return result

    if not result["period"].is_monotonic_increasing:
        result = result.sort_values("period", kind="mergesort").reset_index(drop=True)
    for column in INCOME_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce").rolling(
            window=TTM_WINDOW,
            min_periods=1,
        ).sum()
    return result[BASE_SNAPSHOT_COLUMNS]
