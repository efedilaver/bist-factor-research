"""Financial leasing and factoring profile for Is Yatirim statements."""

from __future__ import annotations

from .base import BaseProfile


class LeasingProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="leasing",
            supported_financial_groups=("UFRS", "UFRS_K", "XI_29"),
            raw_item_code_to_field={
                "1A": "CASH",
                "1Z": "TOTAL_ASSETS",
                "2O": "EQUITY",
                "3Z": "NET_INCOME",
            },
            selection_markers=("1ACE", "1ACF", "2AAH", "2AAI"),
            sub_sector_keywords=(
                "FINANSAL KIRALAMA",
                "FİNANSAL KİRALAMA",
                "FAKTORING",
                "FAKTORİNG",
                "FINANSMAN",
                "FİNANSMAN",
            ),
        )
