"""Date conversion helpers used across the project."""

from __future__ import annotations

import pandas as pd

PERIOD_SEPARATOR = "/"


def period_parts(period: object) -> tuple[int, int]:
    """Split a `YYYY/MM` period string into year and month-like parts."""
    year_text, month_text = str(period).split(PERIOD_SEPARATOR, 1)
    return int(year_text), int(month_text)


def period_to_timestamp(period: object) -> pd.Timestamp:
    """Convert a `YYYY/MM` period string into a month-end timestamp."""
    year, month = period_parts(period)
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def quarter_end_timestamp(year: int | float, period: int | float) -> pd.Timestamp:
    """Map a fiscal year/period pair to a quarter-end timestamp."""
    year_value = int(year)
    period_value = int(period)
    month_map = {1: 3, 2: 6, 3: 9, 4: 12}
    if period_value not in month_map:
        raise ValueError(f"Unsupported fiscal period: {period_value}")
    return pd.Timestamp(year=year_value, month=month_map[period_value], day=1) + pd.offsets.MonthEnd(0)

