"""Local replacement for the external `isyatirimhisse` financial fetcher."""

from __future__ import annotations

from .client import IsYatirimClient
from .fetch import fetch_financials
from .diagnostics import describe_company, describe_company_profile
from .mapper import (
    FINANCIAL_GROUP_ALIASES,
    FINANCIAL_GROUP_ORDER,
    FINANCIAL_ITEM_CODES,
    ITEM_CODE_TO_METRIC,
)
from .parser import parse_mali_tablo_payload

__all__ = [
    "IsYatirimClient",
    "fetch_financials",
    "describe_company",
    "describe_company_profile",
    "FINANCIAL_GROUP_ALIASES",
    "FINANCIAL_GROUP_ORDER",
    "FINANCIAL_ITEM_CODES",
    "ITEM_CODE_TO_METRIC",
    "parse_mali_tablo_payload",
]
