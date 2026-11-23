"""Stability factor-family calculations."""

from __future__ import annotations

import pandas as pd

from .common import CLASSIC_EV_PROFILES, numeric, profile_mask, rolling_stability

STABILITY_FACTOR_COLUMNS = [
    "margin_stability",
    "earnings_stability",
    "roic_stability",
]


def add_stability_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
    stability_window: int = 8,
) -> pd.DataFrame:
    """Add rolling stability factors for classic operating-company profiles."""
    result = frame.copy()
    classic_mask = profile_mask(result, profile_column, CLASSIC_EV_PROFILES)
    ebit_margin = numeric(result, "ebit_margin")
    margin_base = ebit_margin.where(ebit_margin.notna(), numeric(result, "operating_profit_margin"))

    result["margin_stability"] = rolling_stability(
        result.assign(_margin_base=margin_base),
        "_margin_base",
        stability_window,
    ).where(classic_mask)
    result["earnings_stability"] = rolling_stability(result, "net_income", stability_window).where(classic_mask)
    result["roic_stability"] = rolling_stability(result, "roic", stability_window).where(classic_mask)
    return result
