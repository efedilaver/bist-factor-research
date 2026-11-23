"""Compatibility mapping for legacy industrial-company item codes."""

from __future__ import annotations

from typing import Final

from .profiles import get_profile

INDUSTRIAL_PROFILE = get_profile("industrial")

# Supported financial group fallbacks. The legacy numeric values are retained as
# aliases so existing callers can keep using the old wrapper contract.
FINANCIAL_GROUP_ORDER: Final[tuple[str, ...]] = INDUSTRIAL_PROFILE.supported_financial_groups
FINANCIAL_GROUP_ALIASES: Final[dict[str, str]] = {
    "1": "XI_29",
    "2": "UFRS",
    "3": "UFRS_K",
    "XI_29": "XI_29",
    "UFRS": "UFRS",
    "UFRS_K": "UFRS_K",
}

# Canonical metric names mapped to the default industrial-company raw item codes.
FINANCIAL_ITEM_CODES: Final[dict[str, str]] = {
    canonical_field: raw_code
    for canonical_field, raw_code in INDUSTRIAL_PROFILE.canonical_to_raw_map().items()
    if canonical_field in {
        "NET_INCOME",
        "TOTAL_ASSETS",
        "EQUITY",
        "SALES",
        "CASH",
        "SHORT_TERM_DEBT",
        "LONG_TERM_DEBT",
        "EBIT",
        "DEPRECIATION",
        "OPERATING_CASH_FLOW",
        "FREE_CASH_FLOW",
    }
}

# Reverse lookup is occasionally useful for diagnostics and tests.
ITEM_CODE_TO_METRIC: Final[dict[str, str]] = {
    code: metric for metric, code in FINANCIAL_ITEM_CODES.items()
}
