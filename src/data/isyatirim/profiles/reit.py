"""Real-estate investment trust profile for Is Yatirim statements."""

from __future__ import annotations

from .base import BaseProfile


class REITProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="reit",
            supported_financial_groups=("XI_29", "UFRS", "UFRS_K"),
            raw_item_code_to_field={
                "1AA": "CASH",
                "1BL": "TOTAL_ASSETS",
                "2O": "EQUITY",
                "3Z": "NET_INCOME",
                "2AA": "SHORT_TERM_DEBT",
                "2BA": "LONG_TERM_DEBT",
                "3DF": "EBIT",
                "4CAB": "DEPRECIATION",
                "4C": "OPERATING_CASH_FLOW",
                "4CB": "FREE_CASH_FLOW",
                "3C": "SALES",
            },
            selection_markers=("1BF", "3C", "3DF", "4C"),
            sub_sector_keywords=("GAYRIMENKUL YATIRIM ORTAKLIKLARI", "GAYRİMENKUL YATIRIM ORTAKLIKLARI"),
        )
