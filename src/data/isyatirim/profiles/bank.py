"""Bank-company profile for İş Yatırım statements."""

from __future__ import annotations

from .base import BaseProfile


class BankProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="bank",
            supported_financial_groups=("UFRS", "UFRS_K"),
            raw_item_code_to_field={
                "1A": "CASH",
                "1Z": "TOTAL_ASSETS",
                "2O": "EQUITY",
                "3Z": "NET_INCOME",
                "1AF": "LOANS",
                "1AFD": "NON_PERFORMING_LOANS",
                "1AFE": "LOAN_LOSS_ALLOWANCE",
                "2A": "DEPOSITS",
                "2C": "FUNDS_BORROWED",
                "2NBA": "SUBORDINATED_LOANS",
                "3A": "INTEREST_INCOME",
                "3B": "INTEREST_EXPENSE",
                "3C": "NET_INTEREST_INCOME",
                "3CA": "NET_FEE_COMMISSION_INCOME",
                "3CE": "TOTAL_OPERATING_INCOME",
                "3CF": "PROVISION_EXPENSE",
                "3CG": "OPERATING_EXPENSES",
            },
            selection_markers=("1Z", "1A", "3CE", "3CN"),
            sub_sector_keywords=("BANKALAR",),
        )
