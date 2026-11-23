"""Build a month-end panel where every field was knowable on the signal date."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.isyatirim.profiles import select_profile_from_frame
from src.pit.financials import BASIS_IAS29, build_legacy_ttm, build_pit_financials

STALE_DAYS = 200
MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21
LIQUIDITY_WINDOW = 63
RISK_WINDOW = 252
MARKET_CAP_SMOOTHING_DAYS = 3
MAX_DAILY_RETURN = 0.6
LIMIT_UP_RETURN = 0.095
ENDED_MARGIN_DAYS = 10
PANEL_START = pd.Timestamp("2016-08-01")

PRICE_COLUMNS = ["symbol", "date", "close", "dolar_hacim", "pd", "pd_usd", "dd_deger", "end_deger"]
SCALED_FIELDS = [
    "net_income",
    "equity",
    "ebit",
    "ebitda",
    "operating_cash_flow",
    "free_cash_flow",
    "total_assets",
    "net_debt",
    "sales",
    "gross_profit",
]


def drop_untraded_rows(prices: pd.DataFrame, last_trade_dates: pd.Series | None = None) -> pd.DataFrame:
    """Remove the flat zero-volume rows the source adds while a stock is halted or after it delists."""
    traded = pd.to_numeric(prices["dolar_hacim"], errors="coerce").gt(0) & pd.to_numeric(prices["close"], errors="coerce").gt(0)
    keep = traded
    if last_trade_dates is not None:
        cutoff = prices["symbol"].map(last_trade_dates)
        keep = keep & (cutoff.isna() | (prices["date"] <= cutoff))
    return prices.loc[keep]


def load_prices(vintage_dir: Path | str, last_trade_dates: pd.Series | None = None) -> pd.DataFrame:
    """Load every archived daily price file with the columns the panel needs."""
    frames: list[pd.DataFrame] = []
    for path in sorted((Path(vintage_dir) / "prices").glob("*.parquet")):
        frame = pd.read_parquet(path)
        frames.append(frame.loc[:, [column for column in PRICE_COLUMNS if column in frame.columns]])
    prices = pd.concat(frames, ignore_index=True)
    prices["date"] = pd.to_datetime(prices["date"])
    prices = drop_untraded_rows(prices, last_trade_dates)
    return prices.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"]).reset_index(drop=True)


def load_fundamentals(
    vintage_dir: Path | str,
    *,
    cpi: pd.Series,
    legacy: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return per-period fundamentals for every archived company and any build failures."""
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, str]] = []
    for path in sorted((Path(vintage_dir) / "financials").glob("*.parquet")):
        symbol = path.stem
        try:
            raw = pd.read_parquet(path)
            metadata = json.loads(path.with_suffix(".json").read_text())
            group = metadata.get("selected_financial_group") or ""
            raw.attrs["isyatirim_profile"] = select_profile_from_frame(raw, financial_group=group).name
            if legacy:
                frame = build_legacy_ttm(symbol, raw, financial_group=group)
            else:
                frame = build_pit_financials(symbol, raw, financial_group=group, cpi=cpi)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    return pd.concat(frames, ignore_index=True), pd.DataFrame(failures, columns=["symbol", "error"])


def _month_ends(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    last = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).last()
    return [pd.Timestamp(item) for item in last.values if pd.Timestamp(item) >= PANEL_START]


def _known_cpi(cpi: pd.Series, signal_date: pd.Timestamp) -> float:
    """Return the latest CPI published by the signal date (last month's print)."""
    known = cpi.loc[: signal_date - pd.offsets.MonthEnd(1)]
    return float(known.iloc[-1]) if not known.empty else np.nan


def asof_fundamentals(
    fundamentals: pd.DataFrame,
    signal_date: pd.Timestamp,
    *,
    cpi: pd.Series,
) -> pd.DataFrame:
    """Return each company's latest statement published strictly before the signal date."""
    published = fundamentals.loc[fundamentals["publish_date"].dt.normalize() < signal_date]
    # A late filing of an old period must not replace a newer statement.
    latest = published.sort_values(["period", "publish_date"], kind="mergesort").groupby("symbol").tail(1).copy()
    latest = latest.loc[(signal_date - latest["publish_date"]).dt.days <= STALE_DAYS]
    if "pit_basis" in latest.columns:
        scale = pd.Series(1.0, index=latest.index)
        mask = latest["pit_basis"].eq(BASIS_IAS29)
        scale.loc[mask] = _known_cpi(cpi, signal_date) / latest.loc[mask, "period"].map(cpi)
        for field in SCALED_FIELDS:
            if field in latest.columns:
                latest[field] = pd.to_numeric(latest[field], errors="coerce") * scale
    return latest.set_index("symbol")


def build_monthly_panel(
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    *,
    cpi: pd.Series,
    company_keys: pd.Series,
    sectors: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the monthly panel and the benchmark series indexed by signal date."""
    close = prices.pivot_table(index="date", columns="symbol", values="close")
    volume = prices.pivot_table(index="date", columns="symbol", values="dolar_hacim")
    # Share count can update a day before the price adjusts, which spikes market cap for one day.
    market_cap = prices.pivot_table(index="date", columns="symbol", values="pd").rolling(MARKET_CAP_SMOOTHING_DAYS, min_periods=1).median()
    market_cap_usd = prices.pivot_table(index="date", columns="symbol", values="pd_usd").rolling(MARKET_CAP_SMOOTHING_DAYS, min_periods=1).median()
    dates = close.index
    positions = {date: index for index, date in enumerate(dates)}

    filled = close.ffill()
    returns = close.pct_change(fill_method=None)
    returns = returns.where(returns.abs() < MAX_DAILY_RETURN)
    market = returns.mean(axis=1)
    last_trade = close.apply(lambda column: column.last_valid_index())

    momentum = filled.shift(MOMENTUM_SKIP) / filled.shift(MOMENTUM_LOOKBACK) - 1
    momentum = momentum.where(close.notna().rolling(MOMENTUM_LOOKBACK, min_periods=1).sum() >= 200)
    one_month = filled / filled.shift(MOMENTUM_SKIP) - 1
    volatility = returns.rolling(RISK_WINDOW, min_periods=200).std()
    max_return = returns.rolling(MOMENTUM_SKIP, min_periods=15).max()
    covariance = returns.rolling(RISK_WINDOW, min_periods=200).cov(market)
    beta = covariance.div(market.rolling(RISK_WINDOW, min_periods=200).var(), axis=0)
    median_volume = volume.rolling(LIQUIDITY_WINDOW, min_periods=45).median()
    recent_trades = close.notna().rolling(5, min_periods=1).sum()

    month_ends = _month_ends(dates)
    tradable = [date for date in month_ends if positions[date] + 1 < len(dates)]
    rows: list[pd.DataFrame] = []
    for signal_date in month_ends:
        position = positions[signal_date]
        has_entry = position + 1 < len(dates)
        entry_date = dates[position + 1] if has_entry else pd.NaT
        frame = pd.DataFrame(
            {
                "market_cap": market_cap.loc[signal_date],
                "market_cap_usd": market_cap_usd.loc[signal_date],
                "adv_usd": median_volume.loc[signal_date],
                "momentum": momentum.loc[signal_date],
                "one_month": one_month.loc[signal_date],
                "volatility": volatility.loc[signal_date],
                "max_return": max_return.loc[signal_date],
                "beta": beta.loc[signal_date],
                "recent_trades": recent_trades.loc[signal_date],
            }
        )
        frame["entry_return"] = returns.loc[entry_date] if has_entry else np.nan
        frame["entry_limit_up"] = frame["entry_return"].ge(LIMIT_UP_RETURN)
        frame["traded_at_entry"] = close.loc[entry_date].notna() if has_entry else False
        frame = frame.join(asof_fundamentals(fundamentals, signal_date, cpi=cpi))
        frame["signal_date"] = signal_date
        frame["entry_date"] = entry_date
        if has_entry:
            later = [date for date in tradable if date > signal_date]
            # The newest holding period closes at the last available price.
            exit_date = dates[positions[later[0]] + 1] if later else dates[-1]
            frame["forward_return"] = filled.loc[exit_date] / filled.loc[entry_date] - 1
            ended = last_trade.reindex(frame.index) < exit_date
            still_recent = last_trade.reindex(frame.index) >= dates[-1] - pd.Timedelta(days=ENDED_MARGIN_DAYS)
            frame["ended_in_window"] = ended & ~still_recent
            frame["trades_later"] = last_trade.reindex(frame.index) > entry_date
        else:
            frame["forward_return"] = np.nan
            frame["ended_in_window"] = False
            frame["trades_later"] = False
        rows.append(frame.rename_axis("ticker").reset_index())

    panel = pd.concat(rows, ignore_index=True)
    panel["company_key"] = panel["ticker"].map(company_keys).fillna(panel["ticker"])
    panel["sector"] = panel["ticker"].map(sectors).fillna("unknown")

    index_level = prices.groupby("date")["end_deger"].median()
    usd_level = prices.groupby("date")["dd_deger"].median()
    entries = [dates[positions[date] + 1] for date in tradable] + [dates[-1]]
    benchmarks = pd.DataFrame(
        {
            "xu100_price_return": [index_level[b] / index_level[a] - 1 for a, b in zip(entries[:-1], entries[1:])],
            "usdtry_return": [usd_level[b] / usd_level[a] - 1 for a, b in zip(entries[:-1], entries[1:])],
        },
        index=pd.DatetimeIndex(tradable, name="signal_date"),
    )
    return panel, benchmarks
