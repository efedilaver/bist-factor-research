"""Profile-aware multi-factor helpers combining financial and market data."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.data.market import load_market_price_cache
from src.factors.families import (
    INVESTMENT_FACTOR_COLUMNS,
    QUALITY_FACTOR_COLUMNS,
    STABILITY_FACTOR_COLUMNS,
    VALUE_FACTOR_COLUMNS,
    add_investment_factors,
    add_quality_factors,
    add_stability_factors,
    add_value_factors,
)
from src.utils.symbols import canonical_symbol

MARKET_SNAPSHOT_COLUMNS = [
    "market_anchor_date",
    "market_date",
    "is_point_in_time_safe",
    "market_lag_days",
    "close",
    "dolar_bazli_fiyat",
    "volume",
    "dolar_hacim",
    "pd",
    "pd_usd",
    "hao_pd",
    "hao_pd_usd",
]

MULTIFACTOR_COLUMNS = (
    MARKET_SNAPSHOT_COLUMNS
    + VALUE_FACTOR_COLUMNS
    + QUALITY_FACTOR_COLUMNS
    + INVESTMENT_FACTOR_COLUMNS
    + STABILITY_FACTOR_COLUMNS
)

MULTIFACTOR_PROFILE_COLUMN_MAP = {
    "industrial": MULTIFACTOR_COLUMNS,
    "holding": MULTIFACTOR_COLUMNS,
    "reit": MULTIFACTOR_COLUMNS,
    "bank": MARKET_SNAPSHOT_COLUMNS + ["earnings_yield", "book_to_price"],
    "katilim_bank": MARKET_SNAPSHOT_COLUMNS + ["earnings_yield", "book_to_price"],
    "insurance": MARKET_SNAPSHOT_COLUMNS + ["earnings_yield", "book_to_price"],
}


def _normalize_financial_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "symbol" not in result.columns or "period" not in result.columns:
        raise KeyError("financial factor frame must contain symbol and period columns")
    result["symbol"] = result["symbol"].map(canonical_symbol)
    result["period"] = pd.to_datetime(result["period"], errors="coerce")
    if "publish_date" in result.columns:
        result["publish_date"] = pd.to_datetime(result["publish_date"], errors="coerce")
    return result.sort_values(["symbol", "period"], kind="mergesort").reset_index(drop=True)


def _normalize_market_frame(frame: pd.DataFrame, symbol: str | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["symbol", "date"])
    result = frame.copy()
    if "symbol" not in result.columns:
        if symbol is None:
            raise KeyError("market price frame must contain symbol when no symbol is provided")
        result.insert(0, "symbol", canonical_symbol(symbol))
    if "date" not in result.columns:
        raise KeyError("market price frame must contain date")
    result["symbol"] = result["symbol"].map(canonical_symbol)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["symbol", "date"])
    result = result.drop_duplicates(subset=["symbol", "date"], keep="last")
    return result.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def _load_market_prices_for_symbols(symbols: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        cached = load_market_price_cache(symbol)
        if cached is not None and not cached.empty:
            frames.append(_normalize_market_frame(cached, symbol))
    if not frames:
        return pd.DataFrame(columns=["symbol", "date"])
    return pd.concat(frames, ignore_index=True)


def _coerce_market_prices(
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None,
    symbols: list[str],
) -> pd.DataFrame:
    if market_prices is None:
        return _load_market_prices_for_symbols(symbols)
    if isinstance(market_prices, pd.DataFrame):
        return _normalize_market_frame(market_prices)
    frames = [_normalize_market_frame(frame, symbol) for symbol, frame in market_prices.items()]
    if not frames:
        return pd.DataFrame(columns=["symbol", "date"])
    return pd.concat(frames, ignore_index=True)


def merge_market_prices_asof(
    financial_factors: pd.DataFrame,
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Attach first market row available after financial statements are published."""
    financial = _normalize_financial_frame(financial_factors)
    if "publish_date" not in financial.columns:
        financial["publish_date"] = pd.NaT
    financial["market_anchor_date"] = financial["publish_date"].dt.normalize() + pd.Timedelta(days=1)
    symbols = financial["symbol"].dropna().astype(str).drop_duplicates().tolist()
    prices = _coerce_market_prices(market_prices, symbols)
    if prices.empty:
        result = financial.copy()
        for column in MARKET_SNAPSHOT_COLUMNS:
            if column not in result.columns:
                result[column] = pd.NaT if column in {"market_anchor_date", "market_date"} else np.nan
        result["is_point_in_time_safe"] = False
        return result

    keep_columns = ["symbol", "date"] + [
        column
        for column in MARKET_SNAPSHOT_COLUMNS
        if column not in {"market_anchor_date", "market_date", "is_point_in_time_safe", "market_lag_days"}
        and column in prices.columns
    ]
    prices = prices.loc[:, keep_columns].sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)

    merged_frames: list[pd.DataFrame] = []
    for symbol, group in financial.groupby("symbol", sort=False):
        price_group = prices.loc[prices["symbol"].eq(symbol)].copy()
        if price_group.empty:
            merged = group.copy()
            for column in MARKET_SNAPSHOT_COLUMNS:
                if column not in merged.columns:
                    merged[column] = pd.NaT if column in {"market_anchor_date", "market_date"} else np.nan
            merged["is_point_in_time_safe"] = False
            merged_frames.append(merged)
            continue

        valid = group.loc[group["market_anchor_date"].notna()].copy()
        missing = group.loc[group["market_anchor_date"].isna()].copy()
        frames: list[pd.DataFrame] = []
        if not valid.empty:
            matched = pd.merge_asof(
                valid.sort_values("market_anchor_date", kind="mergesort"),
                price_group.sort_values("date", kind="mergesort"),
                left_on="market_anchor_date",
                right_on="date",
                by="symbol",
                direction="forward",
                allow_exact_matches=True,
            )
            frames.append(matched.rename(columns={"date": "market_date"}))
        if not missing.empty:
            for column in MARKET_SNAPSHOT_COLUMNS:
                if column not in missing.columns:
                    missing[column] = pd.NaT if column in {"market_anchor_date", "market_date"} else np.nan
            frames.append(missing)

        merged = pd.concat(frames, ignore_index=True) if frames else group.copy()
        merged["is_point_in_time_safe"] = merged["market_date"].notna()
        merged["market_lag_days"] = (
            pd.to_datetime(merged["market_date"], errors="coerce")
            - pd.to_datetime(merged["publish_date"], errors="coerce")
        ).dt.days
        merged_frames.append(merged)

    result = pd.concat(merged_frames, ignore_index=True)
    for column in MARKET_SNAPSHOT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NaT if column in {"market_anchor_date", "market_date"} else np.nan
    result["is_point_in_time_safe"] = result["is_point_in_time_safe"].fillna(False).astype(bool)
    return result.sort_values(["symbol", "period"], kind="mergesort").reset_index(drop=True)


def add_profile_multifactor_families(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
    stability_window: int = 8,
) -> pd.DataFrame:
    """Add profile-aware value, quality, investment, and stability factor families."""
    result = add_value_factors(frame, profile_column=profile_column)
    result = add_quality_factors(result, profile_column=profile_column)
    result = add_investment_factors(result, profile_column=profile_column)
    result = add_stability_factors(
        result,
        profile_column=profile_column,
        stability_window=stability_window,
    )
    return result


def build_multifactor_frame(
    financial_factors: pd.DataFrame,
    *,
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None = None,
    profile_column: str = "selected_profile",
    stability_window: int = 8,
) -> pd.DataFrame:
    """Return financial factors enriched with market-linked multi-factor families."""
    if not isinstance(financial_factors, pd.DataFrame):
        raise TypeError("build_multifactor_frame() expects a financial factor DataFrame.")
    if financial_factors.empty:
        result = financial_factors.copy()
        for column in MULTIFACTOR_COLUMNS:
            if column not in result.columns:
                result[column] = pd.Series(dtype="float64")
        return result

    result = merge_market_prices_asof(financial_factors, market_prices)
    result = add_profile_multifactor_families(
        result,
        profile_column=profile_column,
        stability_window=stability_window,
    )
    return result


def select_multifactor_columns_for_profile(
    profile: str | None,
    *,
    include_identifiers: bool = True,
) -> list[str]:
    """Return profile-supported multi-factor family columns."""
    normalized_profile = str(profile or "").strip().lower()
    factor_columns = MULTIFACTOR_PROFILE_COLUMN_MAP.get(normalized_profile, MARKET_SNAPSHOT_COLUMNS)
    if not include_identifiers:
        return list(factor_columns)
    return ["symbol", "period", "selected_profile", "financial_group"] + list(factor_columns)


def get_multifactor_profile_view(
    factors: pd.DataFrame,
    profile: str | None = None,
    *,
    profile_column: str = "selected_profile",
    include_identifiers: bool = True,
) -> pd.DataFrame:
    """Return a profile-aware view hiding unsupported multi-factor columns."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("get_multifactor_profile_view() expects a factors DataFrame.")

    selected_profile = profile
    if selected_profile is None and profile_column in factors.columns:
        profiles = factors[profile_column].dropna().astype("string").str.lower().unique().tolist()
        if len(profiles) == 1:
            selected_profile = profiles[0]

    selected_columns = select_multifactor_columns_for_profile(
        selected_profile,
        include_identifiers=include_identifiers,
    )
    available_columns = [column for column in selected_columns if column in factors.columns]
    return factors.loc[:, available_columns].copy()
