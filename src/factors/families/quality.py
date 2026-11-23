"""Quality factor-family calculations."""

from __future__ import annotations

import pandas as pd

from src.factors.financial import safe_divide

from .common import CLASSIC_EV_PROFILES, numeric, positive, profile_mask

QUALITY_FACTOR_COLUMNS = [
    "roic",
    "gross_profitability",
]


def add_quality_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add profile-aware quality ratios."""
    result = frame.copy()
    classic_mask = profile_mask(result, profile_column, CLASSIC_EV_PROFILES)

    invested_capital = positive(numeric(result, "equity") + numeric(result, "net_debt"))
    result["roic"] = safe_divide(numeric(result, "ebit"), invested_capital).where(classic_mask)
    result["gross_profitability"] = safe_divide(numeric(result, "gross_profit"), numeric(result, "total_assets")).where(
        classic_mask
    )
    return result
