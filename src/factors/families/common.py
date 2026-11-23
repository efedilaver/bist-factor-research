"""Shared helpers for profile-aware factor families."""

from __future__ import annotations

import numpy as np
import pandas as pd

CLASSIC_EV_PROFILES = {"industrial", "holding", "reit"}
BANK_VALUE_PROFILES = {"bank", "katilim_bank"}
INSURANCE_VALUE_PROFILES = {"insurance"}


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric series aligned to the frame index."""
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def positive(values: pd.Series) -> pd.Series:
    """Keep strictly positive numeric values and null out invalid denominators."""
    numeric_values = pd.to_numeric(values, errors="coerce")
    return numeric_values.where(numeric_values > 0)


def profile_mask(frame: pd.DataFrame, profile_column: str, profiles: set[str]) -> pd.Series:
    """Return a boolean mask for normalized profile names."""
    if profile_column not in frame.columns:
        return pd.Series(False, index=frame.index)
    normalized = frame[profile_column].astype("string").str.lower()
    return normalized.isin(profiles).fillna(False)


def yoy_growth(frame: pd.DataFrame, column: str) -> pd.Series:
    """Calculate four-quarter year-over-year growth per symbol."""
    values = numeric(frame, column)
    if "symbol" not in frame.columns:
        return values.pct_change(4, fill_method=None).replace([np.inf, -np.inf], np.nan)
    return (
        values.groupby(frame["symbol"].astype("string"), sort=False)
        .pct_change(4, fill_method=None)
        .replace([np.inf, -np.inf], np.nan)
    )


def rolling_stability(frame: pd.DataFrame, column: str, window: int) -> pd.Series:
    """Calculate rolling standard deviation per symbol."""
    values = numeric(frame, column)
    if "symbol" not in frame.columns:
        return values.rolling(window=window, min_periods=4).std()
    return (
        values.groupby(frame["symbol"].astype("string"), sort=False)
        .rolling(window=window, min_periods=4)
        .std()
        .reset_index(level=0, drop=True)
    )
