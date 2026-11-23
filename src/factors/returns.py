"""Forward return helpers for factor testing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from src.data.market import load_market_price_cache
from src.utils.symbols import canonical_symbol

DEFAULT_FORWARD_HORIZONS = ("1M", "3M", "6M", "12M")


def _normalize_horizon(horizon: str) -> str:
    normalized = str(horizon).strip().lower()
    if not normalized:
        raise ValueError("Forward return horizon must not be empty")
    if normalized.endswith("m"):
        number = int(normalized[:-1])
        return f"{number}m"
    if normalized.endswith("d"):
        number = int(normalized[:-1])
        return f"{number}d"
    raise ValueError(f"Unsupported forward return horizon: {horizon}")


def _horizon_offset(horizon: str) -> pd.DateOffset | pd.Timedelta:
    normalized = _normalize_horizon(horizon)
    if normalized.endswith("m"):
        return pd.DateOffset(months=int(normalized[:-1]))
    return pd.Timedelta(days=int(normalized[:-1]))


def _return_column_name(horizon: str) -> str:
    return f"forward_return_{_normalize_horizon(horizon)}"


def _exit_date_column_name(horizon: str) -> str:
    return f"forward_return_{_normalize_horizon(horizon)}_exit_date"


def _normalize_price_frame(frame: pd.DataFrame, symbol: str | None = None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["symbol", "date", "close"])
    result = frame.copy()
    if "symbol" not in result.columns:
        if symbol is None:
            raise KeyError("market price frame must contain symbol when no symbol is provided")
        result.insert(0, "symbol", canonical_symbol(symbol))
    if "date" not in result.columns or "close" not in result.columns:
        raise KeyError("market price frame must contain date and close columns")
    result["symbol"] = result["symbol"].map(canonical_symbol)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["symbol", "date", "close"])
    result = result.drop_duplicates(subset=["symbol", "date"], keep="last")
    return result.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def _load_prices_for_symbols(symbols: Sequence[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        cached = load_market_price_cache(symbol)
        if cached is not None and not cached.empty:
            frames.append(_normalize_price_frame(cached, symbol))
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "close"])
    return pd.concat(frames, ignore_index=True)


def _coerce_market_prices(
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None,
    symbols: Sequence[str],
) -> pd.DataFrame:
    if market_prices is None:
        return _load_prices_for_symbols(symbols)
    if isinstance(market_prices, pd.DataFrame):
        return _normalize_price_frame(market_prices)
    frames = [_normalize_price_frame(frame, symbol) for symbol, frame in market_prices.items()]
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "close"])
    return pd.concat(frames, ignore_index=True)


def _attach_exit_prices(
    rows: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    horizon: str,
) -> pd.DataFrame:
    target_column = f"_{_normalize_horizon(horizon)}_target_date"
    offset = _horizon_offset(horizon)
    left = rows.copy()
    left[target_column] = pd.to_datetime(left["market_date"], errors="coerce") + offset
    valid = left.loc[left[target_column].notna()].copy()
    missing = left.loc[left[target_column].isna()].copy()
    if valid.empty:
        return left.assign(_exit_date=pd.NaT, _exit_close=pd.NA).drop(columns=[target_column])

    merged_frames: list[pd.DataFrame] = []
    for symbol, group in valid.groupby("symbol", sort=False):
        price_group = prices.loc[prices["symbol"].eq(symbol), ["symbol", "date", "close"]]
        if price_group.empty:
            empty = group.copy()
            empty["_exit_date"] = pd.NaT
            empty["_exit_close"] = pd.NA
            merged_frames.append(empty)
            continue
        merged = pd.merge_asof(
            group.sort_values(target_column, kind="mergesort"),
            price_group.sort_values("date", kind="mergesort"),
            left_on=target_column,
            right_on="date",
            by="symbol",
            direction="forward",
            allow_exact_matches=True,
        )
        merged = merged.rename(columns={"date": "_exit_date", "close": "_exit_close"})
        merged_frames.append(merged)

    if not missing.empty:
        missing["_exit_date"] = pd.NaT
        missing["_exit_close"] = pd.NA
        merged_frames.append(missing)
    return pd.concat(merged_frames, ignore_index=True).drop(columns=[target_column], errors="ignore")


def add_forward_returns(
    factors: pd.DataFrame,
    *,
    horizons: Sequence[str] = DEFAULT_FORWARD_HORIZONS,
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None = None,
    price_column: str = "close",
) -> pd.DataFrame:
    """Add forward returns from each row's point-in-time market date."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("add_forward_returns() expects a factors DataFrame.")
    result = factors.copy()
    if result.empty:
        for horizon in horizons:
            result[_return_column_name(horizon)] = pd.Series(dtype="float64")
            result[_exit_date_column_name(horizon)] = pd.Series(dtype="datetime64[ns]")
        return result
    required_columns = {"symbol", "market_date", price_column}
    missing_columns = sorted(required_columns - set(result.columns))
    if missing_columns:
        raise KeyError(f"Missing forward return columns: {missing_columns}")

    result["symbol"] = result["symbol"].map(canonical_symbol)
    result["market_date"] = pd.to_datetime(result["market_date"], errors="coerce")
    result[price_column] = pd.to_numeric(result[price_column], errors="coerce")
    symbols = result["symbol"].dropna().astype(str).drop_duplicates().tolist()
    prices = _coerce_market_prices(market_prices, symbols)

    for horizon in horizons:
        return_column = _return_column_name(horizon)
        exit_date_column = _exit_date_column_name(horizon)
        if prices.empty:
            result[return_column] = pd.NA
            result[exit_date_column] = pd.NaT
            continue
        merged = _attach_exit_prices(
            result[["symbol", "market_date"]].reset_index(),
            prices,
            horizon=horizon,
        ).set_index("index")
        exit_close = pd.to_numeric(merged["_exit_close"], errors="coerce").reindex(result.index)
        entry_close = pd.to_numeric(result[price_column], errors="coerce")
        result[exit_date_column] = pd.to_datetime(merged["_exit_date"], errors="coerce").reindex(result.index)
        result[return_column] = (exit_close / entry_close.replace(0, pd.NA)) - 1
    return result


def forward_return_columns(horizons: Sequence[str] = DEFAULT_FORWARD_HORIZONS) -> list[str]:
    """Return forward return column names for horizons."""
    return [_return_column_name(horizon) for horizon in horizons]
