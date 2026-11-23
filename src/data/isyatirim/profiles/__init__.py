"""Company profiles for İş Yatırım financial statement mappings."""

from __future__ import annotations

from .base import BaseProfile
from .bank import BankProfile
from .holding import HoldingProfile
from .industrial import IndustrialProfile
from .insurance import InsuranceProfile
from .katilim_bank import KatilimBankProfile
from .leasing import LeasingProfile
from .reit import REITProfile
from .registry import get_profile, list_profiles, select_profile_from_frame

__all__ = [
    "BaseProfile",
    "BankProfile",
    "HoldingProfile",
    "IndustrialProfile",
    "InsuranceProfile",
    "KatilimBankProfile",
    "LeasingProfile",
    "REITProfile",
    "get_profile",
    "list_profiles",
    "select_profile_from_frame",
]
