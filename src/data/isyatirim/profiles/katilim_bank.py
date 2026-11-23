"""Participation-bank profile for Is Yatirim statements."""

from __future__ import annotations

from .base import BaseProfile


class KatilimBankProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="katilim_bank",
            supported_financial_groups=("UFRS", "UFRS_K"),
            raw_item_code_to_field={
                "1A": "CASH",
                "1Z": "TOTAL_ASSETS",
                "2O": "EQUITY",
                "3Z": "NET_INCOME",
                "1ABF": "LOANS",
                "1ABJ": "NON_PERFORMING_LOANS",
                "1ABK": "LOAN_LOSS_ALLOWANCE",
                "2A": "DEPOSITS",
                "2AAC": "FUNDS_BORROWED",
                "2ABJ": "SUBORDINATED_LOANS",
                "3A": "INTEREST_INCOME",
                "3AAK": "INTEREST_EXPENSE",
                "3AAR": "NET_INTEREST_INCOME",
                "3AAS": "NET_FEE_COMMISSION_INCOME",
                "3ABH": "TOTAL_OPERATING_INCOME",
                "3ABI": "PROVISION_EXPENSE",
                "3ABJ": "OPERATING_EXPENSES",
            },
            selection_markers=("3AAR", "3A", "2A", "1ACE"),
            sub_sector_keywords=("BANKALAR",),
        )
