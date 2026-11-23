#!/usr/bin/env python3
"""Run the fixed Value + Momentum model and measure how much each data bias contributes."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.kap import load_report_dates
from src.data.markets import load_market_symbols
from src.data.sector import load_sector_mapping
from src.pit.financials import load_cpi
from src.pit.panel import build_monthly_panel, load_fundamentals, load_prices
from src.pit.portfolio import (
    ModelConfig,
    add_signals,
    latest_selection,
    select_universe,
    signal_ic_table,
    simulate,
    summarize,
)
from src.pit.report_dates import (
    attach_publish_dates,
    expand_report_dates,
    load_ticker_companies,
    normalize_company_name,
    off_calendar_symbols,
)
from src.utils.symbols import canonical_symbol

STAR_MARKET = "PAY PİYASASI-YILDIZ PAZAR"
DELISTED_PATH = ROOT / "data" / "universe" / "delisted_candidates.csv"
PRIMARY = "PRIMARY: PIT data, current + delisted equities"
# Set by hand for the delisted names that were ever liquid enough to enter the universe.
DELISTED_SECTORS = {
    "ADNAC": "İMALAT",
    "ASLAN": "İMALAT",
    "BOLUC": "İMALAT",
    "ANACM": "İMALAT",
    "SODA": "İMALAT",
    "TRKCM": "İMALAT",
    "AKPAZ": "TOPTAN VE PERAKENDE TİCARET",
    "BMEKS": "TOPTAN VE PERAKENDE TİCARET",
    "KIPA": "TOPTAN VE PERAKENDE TİCARET",
    "DGZTE": "BİLGİ VE İLETİŞİM",
    "NTTUR": "OTELLER VE LOKANTALAR",
    "USAS": "ULAŞTIRMA VE DEPOLAMA",
    "YGYO": "MALİ KURULUŞLAR",
}
PERIODS = {
    "2016-2019": ("2016-01-01", "2020-01-01"),
    "2020-2022": ("2020-01-01", "2023-01-01"),
    "2023-2026": ("2023-01-01", "2027-01-01"),
    "ias29_from_2024_05": ("2024-05-01", "2027-01-01"),
}
IC_SIGNALS = {
    "value": "value_score",
    "ebit_ev": "ebit_ev",
    "cfo_yield": "cfo_yield",
    "earnings_yield": "earnings_yield",
    "book_to_price": "book_to_price",
    "momentum_12_1": "momentum_score",
    "value_momentum": "value_momentum",
    "low_volatility": "low_volatility_score",
    "roa": "quality_score",
    "last_month_return": "last_month_score",
}


def legacy_publish_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach dates the old way: exact code match, dropping everything unmatched."""
    dates = load_report_dates()
    dates = dates.dropna(subset=["year", "period", "publish_date"])
    dates = dates.loc[dates["period"].isin([1, 2, 3, 4])].copy()
    month = dates["period"].astype(int).map({1: 3, 2: 6, 3: 9, 4: 12})
    dates["period_end"] = pd.to_datetime(dict(year=dates["year"].astype(int), month=month, day=1)) + pd.offsets.MonthEnd(0)
    dates["ticker"] = dates["stock_code"].map(canonical_symbol)
    dates = dates.sort_values("publish_date").drop_duplicates(["ticker", "period_end"], keep="first")
    merged = frame.merge(dates[["ticker", "period_end", "publish_date"]], left_on=["symbol", "period"], right_on=["ticker", "period_end"], how="inner")
    return merged.drop(columns=["ticker", "period_end"])


def run(universe_panel: pd.DataFrame, config: ModelConfig, label: str, returns_out: dict[str, pd.DataFrame]) -> dict[str, object]:
    universe = add_signals(select_universe(universe_panel, config), config.value_metrics)
    results = simulate(universe, config, panel=universe_panel)
    returns_out[label] = results
    return summarize(results, label=label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", default="2026-11-01")
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "reports" / "pit_model"))
    args = parser.parse_args()

    vintage_dir = ROOT / "data" / "vintages" / args.vintage
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cpi = load_cpi()

    delisted = pd.read_csv(DELISTED_PATH, parse_dates=["last_trade_date"])
    delisted_symbols = set(delisted["symbol"])
    merged_symbols = set(delisted.loc[delisted["reason"].eq("merger"), "symbol"])
    delisted_tickers = pd.DataFrame(
        {"ticker": delisted["symbol"], "company_key": delisted["company_name"].map(normalize_company_name)}
    )
    tickers = pd.concat([load_ticker_companies(), delisted_tickers], ignore_index=True).drop_duplicates("ticker")
    company_keys = tickers.set_index("ticker")["company_key"]
    mapping = load_sector_mapping()
    sectors = mapping.drop_duplicates("ticker").set_index("ticker")["sector"]
    sectors = pd.concat([sectors, pd.Series(DELISTED_SECTORS)])
    sectors = sectors[~sectors.index.duplicated()]
    star_symbols = set(load_market_symbols(STAR_MARKET))

    prices = load_prices(vintage_dir, delisted.dropna(subset=["last_trade_date"]).set_index("symbol")["last_trade_date"])
    expanded = expand_report_dates(load_report_dates(), tickers)

    fundamentals, failures = load_fundamentals(vintage_dir, cpi=cpi)
    failures.to_csv(output_dir / "fundamental_build_failures.csv", index=False)
    fundamentals = attach_publish_dates(fundamentals, expanded)
    off_calendar = off_calendar_symbols(expanded)
    fundamentals = fundamentals.loc[~fundamentals["symbol"].isin(off_calendar)]
    print(f"off-calendar fiscal years, no fundamentals used: {sorted(off_calendar)}", flush=True)
    legacy, _ = load_fundamentals(vintage_dir, cpi=cpi, legacy=True)
    legacy = legacy_publish_dates(legacy)
    print(f"prices {prices['symbol'].nunique()} symbols, fundamentals {fundamentals['symbol'].nunique()}, failures {len(failures)}", flush=True)

    panel, benchmarks = build_monthly_panel(prices, fundamentals, cpi=cpi, company_keys=company_keys, sectors=sectors)
    legacy_panel, _ = build_monthly_panel(prices, legacy, cpi=cpi, company_keys=company_keys, sectors=sectors)
    # A merger pays out in successor shares near the last price, so only other exits take the delisting penalty.
    panel.loc[panel["ticker"].isin(merged_symbols), "ended_in_window"] = False
    current_panel = panel.loc[~panel["ticker"].isin(delisted_symbols)]
    benchmarks.to_csv(output_dir / "benchmarks.csv")
    star_panel = panel.loc[panel["ticker"].isin(star_symbols)]
    star_legacy = legacy_panel.loc[legacy_panel["ticker"].isin(star_symbols)]
    print(f"panel rows {len(panel)}, months {panel['signal_date'].nunique()}", flush=True)

    base = ModelConfig()
    returns: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, object]] = []
    rows.append(run(star_legacy, base, "bias_A: uncorrected data, today's Star market", returns))
    rows.append(run(star_panel, dataclasses.replace(base, min_scored_share=0.0, abstain_below_holdings=0), "bias_B0: PIT data, today's Star market, thin book allowed", returns))
    rows.append(run(star_panel, base, "bias_B: PIT data, today's Star market", returns))
    rows.append(run(current_panel, base, "bias_C: PIT data, all current listed equities", returns))
    rows.append(run(panel, base, PRIMARY, returns))

    sensitivities = {
        "no_abstain_thin_book": {"min_scored_share": 0.0, "abstain_below_holdings": 0},
        "momentum_when_value_missing": {"fallback_score": "momentum_score"},
        "value_without_cash_flow": {"value_metrics": ("ebit_ev", "earnings_yield", "book_to_price")},
        "value_only": {"score": "value_score"},
        "momentum_only": {"score": "momentum_score"},
        "exploratory_value_low_volatility": {"score": "value_low_volatility"},
        "no_guardrails": {"apply_guardrails": False},
        "universe_top50": {"top_n_liquidity": 50},
        "universe_top150": {"top_n_liquidity": 150},
        "cost_60bp": {"one_way_cost": 0.006},
        "no_hold_buffer": {"hold_fraction": 0.20},
        "skip_limit_up_entries": {"skip_limit_up": True},
        "delisting_minus_30pct": {"delisting_penalty": 0.30},
        "delisting_minus_100pct": {"delisting_penalty": 1.00},
    }
    for label, changes in sensitivities.items():
        rows.append(run(panel, dataclasses.replace(base, **changes), f"sensitivity: {label}", returns))
    summary = pd.DataFrame(rows)
    summary.to_csv(output_dir / "model_summary.csv", index=False)

    primary = returns[PRIMARY]
    primary.join(benchmarks).to_csv(output_dir / "primary_monthly_returns.csv")
    period_rows = []
    for name, (start, end) in PERIODS.items():
        part = primary.loc[(primary.index >= start) & (primary.index < end)]
        if len(part) >= 6:
            period_rows.append(summarize(part, label=name))
    pd.DataFrame(period_rows).to_csv(output_dir / "primary_by_period.csv", index=False)

    joined = primary.join(benchmarks)
    years = len(joined) / 12
    usd = (1 + joined["portfolio_net"]) / (1 + joined["usdtry_return"]) - 1
    absolute = {
        "years": years,
        "portfolio_cagr_tl": (1 + joined["portfolio_net"]).prod() ** (1 / years) - 1,
        "cap_weight_cagr_tl": (1 + joined["cap_weight"]).prod() ** (1 / years) - 1,
        "equal_weight_cagr_tl": (1 + joined["equal_weight"]).prod() ** (1 / years) - 1,
        "xu100_price_cagr_tl": (1 + joined["xu100_price_return"]).prod() ** (1 / years) - 1,
        "usdtry_cagr": (1 + joined["usdtry_return"]).prod() ** (1 / years) - 1,
        "portfolio_cagr_usd": (1 + usd).prod() ** (1 / years) - 1,
        "portfolio_vol_ann": joined["portfolio_net"].std() * 12**0.5,
        "cap_weight_vol_ann": joined["cap_weight"].std() * 12**0.5,
    }
    pd.DataFrame([absolute]).to_csv(output_dir / "primary_absolute.csv", index=False)

    universe = add_signals(select_universe(panel, base))
    print(f"held or eligible rows flagged as ended: {int(universe['ended_in_window'].astype(bool).sum())}", flush=True)
    print("unknown sector share of universe rows:", round(universe["sector"].eq("unknown").mean(), 4), flush=True)
    delisted_held = {
        ticker: int(sum(ticker in names.split(",") for names in primary["tickers"]))
        for ticker in sorted(delisted_symbols)
    }
    print("months held, delisted names:", {key: value for key, value in delisted_held.items() if value}, flush=True)
    exits = []
    entry_returns = panel.set_index(["signal_date", "ticker"])["entry_return"]
    for before, after in zip(primary.index[:-1], primary.index[1:]):
        for ticker in set(primary.at[before, "tickers"].split(",")) - set(primary.at[after, "tickers"].split(",")):
            exits.append({"signal_date": after, "ticker": ticker, "entry_return": entry_returns.get((after, ticker))})
    exits = pd.DataFrame(exits)
    locked = exits.loc[exits["entry_return"].le(-0.095)]
    locked.to_csv(output_dir / "primary_exits_on_limit_down.csv", index=False)
    print(f"exits {len(exits)}, on a limit-down day {len(locked)}", flush=True)
    previous = primary["tickers"].iloc[-1].split(",")
    paper = latest_selection(panel, base, previous)
    paper[["signal_date", "ticker", "sector", "value_score", "momentum_score", "value_momentum", "market_cap_usd", "adv_usd", "abstained"]].to_csv(
        output_dir / "paper_portfolio_latest.csv", index=False
    )
    signal_ic_table(universe, IC_SIGNALS).to_csv(output_dir / "signal_ic.csv", index=False)
    latest_date = universe["signal_date"].max()
    pd.DataFrame(
        {
            "universe_by_year": universe.groupby(universe["signal_date"].dt.year).size()
            / universe.groupby(universe["signal_date"].dt.year)["signal_date"].nunique()
        }
    ).to_csv(output_dir / "universe_by_year.csv")
    print(f"latest signal date with returns {latest_date.date()}", flush=True)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 40)
    print(summary.set_index("label").round(3).T.to_string())
    print(pd.DataFrame(period_rows).set_index("label").round(3).T.to_string())
    print({key: round(value, 3) for key, value in absolute.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
