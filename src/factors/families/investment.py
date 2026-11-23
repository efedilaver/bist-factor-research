"""Investment factor-family calculations."""

from __future__ import annotations

import pandas as pd

from .common import CLASSIC_EV_PROFILES, numeric, profile_mask, yoy_growth

INVESTMENT_FACTOR_COLUMNS = [
    "working_capital",
    "working_capital_growth_yoy",
    "capex_growth_yoy",
]


def add_investment_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add profile-aware investment and balance-sheet expansion factors."""
    result = frame.copy()
    classic_mask = profile_mask(result, profile_column, CLASSIC_EV_PROFILES)

    working_capital = numeric(result, "current_assets") - numeric(result, "current_liabilities")
    result["working_capital"] = working_capital.where(classic_mask)
    result["working_capital_growth_yoy"] = yoy_growth(
        result.assign(working_capital=working_capital),
        "working_capital",
    ).where(classic_mask)
    result["capex_growth_yoy"] = yoy_growth(result.assign(capex=numeric(result, "capex").abs()), "capex").where(
        classic_mask
    )
    return result
