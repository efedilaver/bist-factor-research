"""Registry and selection helpers for İş Yatırım company profiles."""

from __future__ import annotations

from functools import lru_cache
import unicodedata

import pandas as pd

from .bank import BankProfile
from .base import BaseProfile
from .holding import HoldingProfile
from .industrial import IndustrialProfile
from .insurance import InsuranceProfile
from .katilim_bank import KatilimBankProfile
from .leasing import LeasingProfile
from .reit import REITProfile


@lru_cache(maxsize=1)
def list_profiles() -> tuple[BaseProfile, ...]:
    """Return the registered profiles in priority order."""
    return (
        KatilimBankProfile(),
        BankProfile(),
        InsuranceProfile(),
        HoldingProfile(),
        REITProfile(),
        LeasingProfile(),
        IndustrialProfile(),
    )


def get_profile(name: str) -> BaseProfile:
    """Return a profile by name."""
    normalized = str(name).strip().lower()
    for profile in list_profiles():
        if profile.name == normalized:
            return profile
    raise KeyError(f"Unknown profile: {name}")


def _ascii_upper(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return text.upper()


def _symbol_from_frame(frame: pd.DataFrame) -> str | None:
    symbol_attr = frame.attrs.get("symbol")
    if symbol_attr:
        return str(symbol_attr).strip().upper()
    if frame.empty:
        return None
    for column in ("SYMBOL", "symbol"):
        if column in frame.columns and not frame[column].dropna().empty:
            return str(frame[column].dropna().iloc[0]).strip().upper()
    return None


@lru_cache(maxsize=2048)
def _sector_context(symbol: str | None) -> tuple[str, str]:
    if not symbol:
        return ("", "")
    try:
        from src.data.sector import load_sector_mapping
    except Exception:
        return ("", "")

    try:
        mapping = load_sector_mapping()
    except Exception:
        return ("", "")
    if mapping.empty or "ticker" not in mapping.columns:
        return ("", "")

    row = mapping.loc[mapping["ticker"].astype(str).str.upper() == symbol.upper()]
    if row.empty:
        return ("", "")
    first = row.iloc[0]
    return (_ascii_upper(first.get("sector")), _ascii_upper(first.get("sub_sector")))


def _keyword_score(keywords: tuple[str, ...], value: str) -> int:
    if not value or not keywords:
        return 0
    return sum(1 for keyword in keywords if _ascii_upper(keyword) in value)


def _profile_sort_key(
    profile: BaseProfile,
    frame: pd.DataFrame,
    financial_group: str | None,
    sector: str,
    sub_sector: str,
    priority: int,
) -> tuple[int, int, int, int, int]:
    score = profile.score_frame(frame)
    sector_bonus = 8 * _keyword_score(profile.sector_keywords, sector)
    sector_bonus += 8 * _keyword_score(profile.sub_sector_keywords, sub_sector)
    group_bonus = 1 if profile.matches_group(financial_group) else 0
    priority_bonus = len(list_profiles()) - priority
    return (score + sector_bonus, sector_bonus, group_bonus, len(profile.raw_item_code_to_field), priority_bonus)


def select_profile_from_frame(frame: pd.DataFrame, financial_group: str | None = None) -> BaseProfile:
    """Select the best matching profile from a raw wide dataframe."""
    profiles = list_profiles()
    sector, sub_sector = _sector_context(_symbol_from_frame(frame))
    scored = sorted(
        enumerate(profiles),
        key=lambda item: _profile_sort_key(item[1], frame, financial_group, sector, sub_sector, item[0]),
        reverse=True,
    )
    best = scored[0][1]
    if best.score_frame(frame) <= 0:
        for profile in profiles:
            if _keyword_score(profile.sector_keywords, sector) or _keyword_score(profile.sub_sector_keywords, sub_sector):
                return profile
        return IndustrialProfile()
    return best
