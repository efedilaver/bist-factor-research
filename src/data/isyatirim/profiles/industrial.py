"""Industrial-company profile for İş Yatırım statements."""

from __future__ import annotations

from .base import BaseProfile


class IndustrialProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="industrial",
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
                "1D": "SALES",
                "3C": "SALES",
                "3CA": "COST_OF_SALES",
                "3D": "GROSS_PROFIT",
                "3DA": "SELLING_MARKETING_EXPENSES",
                "3DB": "GENERAL_ADMIN_EXPENSES",
                "3DC": "RESEARCH_DEVELOPMENT_EXPENSES",
                "4BB": "FINANCING_EXPENSES",
                "4BD": "EXPORT_REVENUE",
                "4CAI": "CAPEX",
                "1A": "CURRENT_ASSETS",
                "1AC": "TRADE_RECEIVABLES",
                "1AF": "INVENTORY",
                "1BG": "PROPERTY_PLANT_EQUIPMENT",
                "2A": "CURRENT_LIABILITIES",
                "2AAGAA": "TRADE_PAYABLES",
            },
            selection_markers=("1BL", "3DF", "4CAB", "4C", "4CB"),
            sector_keywords=("İMALAT",),
        )
