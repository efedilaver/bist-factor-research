"""Value factor-family calculations."""

from __future__ import annotations

import pandas as pd

from src.factors.financial import safe_divide

from .common import (
    BANK_VALUE_PROFILES,
    CLASSIC_EV_PROFILES,
    INSURANCE_VALUE_PROFILES,
    numeric,
    positive,
    profile_mask,
)

VALUE_FACTOR_COLUMNS = [
    "enterprise_value",
    "ebit_ev",
    "ebitda_ev",
    "fcf_yield",
    "earnings_yield",
    "book_to_price",
]


def add_value_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add profile-aware valuation ratios."""
    result = frame.copy()
    classic_mask = profile_mask(result, profile_column, CLASSIC_EV_PROFILES)
    value_mask = classic_mask | profile_mask(result, profile_column, BANK_VALUE_PROFILES | INSURANCE_VALUE_PROFILES)

    market_cap = positive(numeric(result, "pd"))
    enterprise_value = positive(market_cap + numeric(result, "net_debt"))
    result["enterprise_value"] = enterprise_value.where(classic_mask)
    result["ebit_ev"] = safe_divide(numeric(result, "ebit"), enterprise_value).where(classic_mask)
    result["ebitda_ev"] = safe_divide(numeric(result, "ebitda"), enterprise_value).where(classic_mask)
    result["fcf_yield"] = safe_divide(numeric(result, "free_cash_flow"), market_cap).where(classic_mask)
    result["earnings_yield"] = safe_divide(numeric(result, "net_income"), market_cap).where(value_mask)
    result["book_to_price"] = safe_divide(numeric(result, "equity"), market_cap).where(value_mask)
    return result
