"""Holding-company profile for Is Yatirim statements."""

from __future__ import annotations

from .base import BaseProfile


class HoldingProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="holding",
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
                "3D": "GROSS_PROFIT",
                "1AB": "SHORT_TERM_FINANCIAL_INVESTMENTS",
                "1BC": "LONG_TERM_FINANCIAL_INVESTMENTS",
                "1BD": "EQUITY_METHOD_INVESTMENTS",
                "3HAC": "EQUITY_METHOD_INCOME",
                "3HC": "FINANCING_EXPENSES",
                "4CAI": "CAPEX",
            },
            selection_markers=("1BD", "3HAC", "4C", "4CB"),
            sub_sector_keywords=("HOLDING", "HOLDİNG", "YATIRIM ŞİRKETLERİ"),
        )
