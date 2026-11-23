"""Insurance-company profile for Is Yatirim statements."""

from __future__ import annotations

from .base import BaseProfile


class InsuranceProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="insurance",
            supported_financial_groups=("UFRS", "UFRS_K"),
            raw_item_code_to_field={
                "1A": "CASH",
                "1Z": "TOTAL_ASSETS",
                "2O": "EQUITY",
                "3Z": "NET_INCOME",
                "2A": "SHORT_TERM_DEBT",
                "2J": "LONG_TERM_DEBT",
                "3ZA": "EBIT",
                "3MG": "DEPRECIATION",
                "3AA": "NON_LIFE_NET_EARNED_PREMIUMS",
                "3AAA": "NON_LIFE_NET_WRITTEN_PREMIUMS",
                "3AAAA": "NON_LIFE_GROSS_WRITTEN_PREMIUMS",
                "3BA": "NON_LIFE_NET_CLAIMS",
                "3BD": "NON_LIFE_OPERATING_EXPENSES",
                "3C": "NON_LIFE_TECHNICAL_PROFIT",
                "3DAA": "LIFE_NET_EARNED_PREMIUMS",
                "3DAAA": "LIFE_NET_WRITTEN_PREMIUMS",
                "3DAAB": "LIFE_GROSS_WRITTEN_PREMIUMS",
                "3EA": "LIFE_NET_CLAIMS",
                "3EBC": "LIFE_OPERATING_EXPENSES",
                "3F": "LIFE_TECHNICAL_PROFIT",
                "3K": "TOTAL_TECHNICAL_PROFIT",
                "2E": "CURRENT_TECHNICAL_RESERVES",
                "2MD": "LONG_TECHNICAL_RESERVES",
                "2ED": "CURRENT_OUTSTANDING_CLAIMS_RESERVES",
                "2MDD": "LONG_OUTSTANDING_CLAIMS_RESERVES",
            },
            selection_markers=("3MG", "3ZC", "1NI", "2J", "2M"),
            sub_sector_keywords=("SIGORTA", "SİGORTA"),
        )
