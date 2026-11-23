"""Signals and long-only portfolio simulation for the monthly panel."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

MIN_SECTOR_GROUP = 4
MIN_VALUE_METRICS = 2
VALUE_METRICS = ("ebit_ev", "cfo_yield", "earnings_yield", "book_to_price")


@dataclass(frozen=True)
class ModelConfig:
    """Rules fixed before results are seen; variants exist only for sensitivity checks."""

    top_n_liquidity: int = 100
    min_adv_usd: float = 1e6
    min_market_cap_usd: float = 5e7
    score: str = "value_momentum"
    buy_fraction: float = 0.20
    hold_fraction: float = 0.40
    min_holdings: int = 10
    sector_cap: float = 0.30
    value_metrics: tuple[str, ...] = VALUE_METRICS
    min_scored_share: float = 0.50
    abstain_below_holdings: int = 10
    fallback_score: str | None = None
    one_way_cost: float = 0.003
    delisting_penalty: float = 0.0
    skip_limit_up: bool = False
    apply_guardrails: bool = True


def _rank_z(values: pd.Series) -> pd.Series:
    ranks = values.rank(pct=True)
    deviation = ranks.std()
    if not deviation or np.isnan(deviation):
        return ranks * np.nan
    return (ranks - ranks.mean()) / deviation


def select_universe(panel: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Keep the most liquid company per month using only data known at the signal date."""
    frame = panel.loc[
        panel["adv_usd"].ge(config.min_adv_usd)
        & panel["market_cap_usd"].ge(config.min_market_cap_usd)
        & panel["recent_trades"].ge(1)
        & panel["momentum"].notna()
        & panel["volatility"].notna()
        & panel["forward_return"].notna()
    ].copy()
    frame = frame.sort_values(["signal_date", "adv_usd"], ascending=[True, False], kind="mergesort")
    frame = frame.drop_duplicates(["signal_date", "company_key"], keep="first")
    frame["_rank"] = frame.groupby("signal_date")["adv_usd"].rank(ascending=False, method="first")
    return frame.loc[frame["_rank"].le(config.top_n_liquidity)].drop(columns="_rank").reset_index(drop=True)


def add_signals(universe: pd.DataFrame, value_metrics: tuple[str, ...] = VALUE_METRICS) -> pd.DataFrame:
    """Add sector-neutral value, momentum, risk, and quality scores."""
    frame = universe.copy()
    frame["earnings_yield"] = frame["net_income"] / frame["market_cap"]
    frame["book_to_price"] = frame["equity"] / frame["market_cap"]
    enterprise_value = (frame["market_cap"] + frame["net_debt"]).where(lambda values: values > 0)
    frame["ebit_ev"] = frame["ebit"] / enterprise_value
    frame["cfo_yield"] = frame["operating_cash_flow"] / frame["market_cap"]
    frame["roa"] = frame["net_income"] / frame["total_assets"]

    by_date = frame.groupby("signal_date")
    neutral: dict[str, pd.Series] = {}
    for metric in value_metrics:
        scored = by_date[metric].transform(_rank_z)
        grouped = scored.groupby([frame["signal_date"], frame["sector"]])
        neutral[metric] = scored - grouped.transform("mean").where(grouped.transform("count").ge(MIN_SECTOR_GROUP), 0.0)
    metrics = pd.DataFrame(neutral)
    frame["value_score"] = metrics.mean(axis=1).where(metrics.notna().sum(axis=1).ge(MIN_VALUE_METRICS))
    frame["value_score"] = frame.groupby("signal_date")["value_score"].transform(_rank_z)
    frame["momentum_score"] = by_date["momentum"].transform(_rank_z)
    frame["value_momentum"] = frame[["value_score", "momentum_score"]].mean(axis=1, skipna=False)
    frame["low_volatility_score"] = -by_date["volatility"].transform(_rank_z)
    frame["quality_score"] = by_date["roa"].transform(_rank_z)
    frame["last_month_score"] = by_date["one_month"].transform(_rank_z)
    frame["value_low_volatility"] = frame[["value_score", "low_volatility_score"]].mean(axis=1, skipna=False)

    frame["risk_excluded"] = frame["volatility"].gt(by_date["volatility"].transform("quantile", 0.9)) | frame[
        "max_return"
    ].gt(by_date["max_return"].transform("quantile", 0.9))
    frame["quality_excluded"] = frame["equity"].le(0).fillna(False) | frame["roa"].lt(
        by_date["roa"].transform("quantile", 0.1)
    ).fillna(False)
    return frame


def _select_holdings(
    group: pd.DataFrame,
    score: str,
    previous: dict[str, float],
    config: ModelConfig,
) -> list[str]:
    ranked = group.dropna(subset=[score]).sort_values(score, ascending=False)
    candidates = ranked.loc[ranked["traded_at_entry"].astype(bool)]
    if config.apply_guardrails:
        candidates = candidates.loc[~candidates["risk_excluded"] & ~candidates["quality_excluded"]]
    if candidates.empty:
        return []
    target = max(config.min_holdings, int(len(ranked) * config.buy_fraction))
    hold_limit = max(target, int(len(ranked) * config.hold_fraction))
    hold_zone = set(ranked["ticker"].iloc[:hold_limit])
    sector_of = dict(zip(ranked["ticker"], ranked["sector"]))
    limit_up = dict(zip(ranked["ticker"], ranked["entry_limit_up"]))
    sector_limit = max(1, math.ceil(target * config.sector_cap))

    selected: list[str] = []
    counts: dict[str, int] = {}

    def admit(ticker: str) -> None:
        sector = sector_of[ticker]
        if len(selected) < target and counts.get(sector, 0) < sector_limit and ticker not in selected:
            selected.append(ticker)
            counts[sector] = counts.get(sector, 0) + 1

    for ticker in candidates["ticker"]:
        if ticker in previous and ticker in hold_zone:
            admit(ticker)
    for ticker in candidates["ticker"]:
        if config.skip_limit_up and ticker not in previous and limit_up[ticker]:
            continue
        admit(ticker)
    return selected


def _rebalance_holdings(
    group: pd.DataFrame,
    previous: dict[str, float],
    config: ModelConfig,
) -> tuple[list[str], bool]:
    """Return the month's names and whether the model had too little data to take a view."""
    score = config.score
    thin = group[score].notna().mean() < config.min_scored_share
    if thin and config.fallback_score:
        score, thin = config.fallback_score, False
    holdings = [] if thin else _select_holdings(group, score, previous, config)
    if thin or len(holdings) < config.abstain_below_holdings:
        return group.loc[group["traded_at_entry"].astype(bool), "ticker"].tolist(), True
    return holdings, False


def simulate(universe: pd.DataFrame, config: ModelConfig, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Simulate monthly rebalancing with drifted weights and proportional costs.

    Rows of `panel` that did not trade on the entry date but trade later are positions
    that cannot be sold yet, so they stay at their drifted weight until trading resumes.
    """
    unsellable: dict[pd.Timestamp, dict[str, float]] = {}
    if panel is not None:
        halted = panel.loc[~panel["traded_at_entry"].astype(bool) & panel["trades_later"].astype(bool)]
        for date, part in halted.groupby("signal_date"):
            unsellable[date] = dict(zip(part["ticker"], part["forward_return"].fillna(0.0)))

    records: list[dict[str, object]] = []
    drifted: dict[str, float] = {}
    for signal_date, group in universe.groupby("signal_date", sort=True):
        forward = group["forward_return"].astype(float)
        if config.delisting_penalty:
            ended = group["ended_in_window"].fillna(False).astype(bool)
            forward = forward.where(~ended, (1 + forward) * (1 - config.delisting_penalty) - 1)
        forward_by_ticker = dict(zip(group["ticker"], forward))

        halted_today = unsellable.get(signal_date, {})
        stuck = {ticker: value for ticker, value in drifted.items() if ticker in halted_today}
        holdings, abstained = _rebalance_holdings(group, drifted, config)
        holdings = [ticker for ticker in holdings if ticker not in stuck]
        free = 1.0 - sum(stuck.values())
        target = {ticker: free / len(holdings) for ticker in holdings} if holdings else {}
        target.update(stuck)
        names = set(target) | set(drifted)
        traded = sum(abs(target.get(name, 0.0) - drifted.get(name, 0.0)) for name in names)
        cost = traded * config.one_way_cost

        realized = {**forward_by_ticker, **{ticker: halted_today[ticker] for ticker in stuck}}
        gross = sum(weight * realized.get(ticker, 0.0) for ticker, weight in target.items())
        drifted = {ticker: weight * (1 + realized.get(ticker, 0.0)) / (1 + gross) for ticker, weight in target.items()}

        caps = group["market_cap_usd"].astype(float)
        records.append(
            {
                "signal_date": signal_date,
                "portfolio_gross": gross,
                "portfolio_net": gross - cost,
                "cost": cost,
                "turnover_one_way": traded / 2,
                "holdings": len(target),
                "universe_size": len(group),
                "abstained": abstained,
                "tickers": ",".join(sorted(target)),
                "equal_weight": float(forward.mean()),
                "cap_weight": float((forward * caps).sum() / caps.sum()),
            }
        )
    return pd.DataFrame(records).set_index("signal_date")


def latest_selection(panel: pd.DataFrame, config: ModelConfig, previous: list[str]) -> pd.DataFrame:
    """Return the names the rules pick on the newest signal date, which has no return yet."""
    frame = panel.loc[panel["signal_date"].eq(panel["signal_date"].max())]
    universe = select_universe(frame.assign(forward_return=0.0), config)
    scored = add_signals(universe, config.value_metrics).assign(traded_at_entry=True)
    holdings, abstained = _rebalance_holdings(scored, {ticker: 0.0 for ticker in previous}, config)
    picked = scored.loc[scored["ticker"].isin(holdings)].sort_values(config.score, ascending=False)
    return picked.assign(abstained=abstained)


def newey_west_t(series: pd.Series, lags: int = 3) -> float:
    """Return the Newey-West t statistic of a series mean."""
    values = pd.Series(series).dropna().to_numpy(dtype=float)
    if len(values) < lags + 2:
        return float("nan")
    demeaned = values - values.mean()
    variance = (demeaned**2).mean()
    for lag in range(1, lags + 1):
        variance += 2 * (1 - lag / (lags + 1)) * (demeaned[lag:] * demeaned[:-lag]).mean()
    return float(values.mean() / np.sqrt(variance / len(values))) if variance > 0 else float("nan")


def block_bootstrap_interval(
    series: pd.Series,
    *,
    block: int = 6,
    draws: int = 4000,
    seed: int = 7,
) -> tuple[float, float]:
    """Return a 95% interval of the annualized mean using moving-block resampling."""
    values = pd.Series(series).dropna().to_numpy(dtype=float)
    if len(values) <= block:
        return float("nan"), float("nan")
    generator = np.random.default_rng(seed)
    count = len(values)
    starts = generator.integers(0, count - block + 1, size=(draws, count // block + 1))
    means = np.empty(draws)
    for index in range(draws):
        sample = np.concatenate([values[start : start + block] for start in starts[index]])[:count]
        means[index] = sample.mean()
    return float(np.quantile(means, 0.025) * 12), float(np.quantile(means, 0.975) * 12)


def summarize(results: pd.DataFrame, *, label: str) -> dict[str, object]:
    """Summarize net performance against both universe benchmarks."""
    versus_equal = results["portfolio_net"] - results["equal_weight"]
    versus_cap = results["portfolio_net"] - results["cap_weight"]
    relative = (1 + versus_cap).cumprod()
    low, high = block_bootstrap_interval(versus_cap)
    return {
        "label": label,
        "months": len(results),
        "avg_universe": results["universe_size"].mean(),
        "avg_holdings": results["holdings"].mean(),
        "min_holdings": int(results["holdings"].min()),
        "net_cagr_tl": (1 + results["portfolio_net"]).prod() ** (12 / len(results)) - 1,
        "excess_vs_cap_ann": versus_cap.mean() * 12,
        "t_vs_cap": newey_west_t(versus_cap),
        "ci95_low_vs_cap": low,
        "ci95_high_vs_cap": high,
        "excess_vs_equal_ann": versus_equal.mean() * 12,
        "t_vs_equal": newey_west_t(versus_equal),
        "information_ratio_vs_cap": versus_cap.mean() / versus_cap.std() * 12**0.5,
        "hit_rate_vs_cap": (versus_cap > 0).mean(),
        "max_relative_drawdown_vs_cap": (relative / relative.cummax() - 1).min(),
        "abstained_months": int(results["abstained"].sum()),
        "turnover_one_way_monthly": results["turnover_one_way"].mean(),
        "cost_ann": results["cost"].mean() * 12,
    }


def signal_ic_table(universe: pd.DataFrame, signals: dict[str, str]) -> pd.DataFrame:
    """Return monthly Spearman IC by signal for the whole sample and three regimes."""
    regimes = {
        "all": (pd.Timestamp("2000-01-01"), pd.Timestamp("2100-01-01")),
        "nominal_to_2023_02": (pd.Timestamp("2000-01-01"), pd.Timestamp("2023-03-01")),
        "transition_2023_03_2024_04": (pd.Timestamp("2023-03-01"), pd.Timestamp("2024-05-01")),
        "ias29_from_2024_05": (pd.Timestamp("2024-05-01"), pd.Timestamp("2100-01-01")),
    }
    rows: list[dict[str, object]] = []
    for name, column in signals.items():
        series = universe.groupby("signal_date").apply(
            lambda group: group[column].corr(group["forward_return"], method="spearman")
            if group[column].notna().sum() >= 20
            else np.nan
        )
        row: dict[str, object] = {"signal": name}
        for regime, (start, end) in regimes.items():
            part = series.loc[(series.index >= start) & (series.index < end)].dropna()
            row[f"ic_{regime}"] = part.mean()
            row[f"t_{regime}"] = newey_west_t(part)
            row[f"months_{regime}"] = len(part)
        rows.append(row)
    return pd.DataFrame(rows)
