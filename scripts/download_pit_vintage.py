#!/usr/bin/env python3
"""Archive a dated copy of İş Yatırım financials and prices.

İş Yatırım overwrites historical columns with restated comparatives, so a dated
copy is the only way to preserve what was visible at download time. Vintages
live under data/vintages/<vintage>/ and never touch data/financials.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.isyatirim.client import IsYatirimClient
from src.data.isyatirim.fetch import _wide_from_normalized
from src.data.market import IsYatirimMarketClient
from src.data.markets import DEFAULT_MARKETS_WORKBOOK, list_markets, load_market_symbols

EQUITY_MARKET_PREFIX = "PAY PİYASASI"
EXCLUDED_MARKET_WORDS = ("FON", "EMTİA")
START_YEAR = 2015
END_YEAR = 2026
PRICE_START = "01-08-2015"
OLD_CACHE_DIR = ROOT / "data" / "financials"
# Columns before the first IAS 29 comparatives are not rewritten, so they can come from the older cache.
REWRITTEN_FROM_YEAR = 2022
LIQUID_ADV_USD = 1e6
LIQUID_WINDOW = 63


def equity_symbols() -> dict[str, str]:
    """Return every listed equity symbol mapped to its current market."""
    symbols: dict[str, str] = {}
    for market in list_markets(DEFAULT_MARKETS_WORKBOOK):
        if not market.startswith(EQUITY_MARKET_PREFIX):
            continue
        if any(word in market for word in EXCLUDED_MARKET_WORDS):
            continue
        for symbol in load_market_symbols(market, workbook_path=DEFAULT_MARKETS_WORKBOOK):
            symbols.setdefault(symbol, market)
    return symbols


def _old_cache(symbol: str) -> tuple[pd.DataFrame, str] | None:
    path = OLD_CACHE_DIR / f"{symbol}.parquet"
    meta_path = path.with_suffix(".json")
    if not path.exists() or not meta_path.exists():
        return None
    group = str(json.loads(meta_path.read_text()).get("isyatirim_selected_financial_group") or "")
    return (pd.read_parquet(path), group) if group else None


def _merge_old_columns(fresh: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """Add unchanged early-period columns from the older cache to a recent download."""
    key = "FINANCIAL_ITEM_CODE"
    old_periods = [
        column
        for column in old.columns
        if column.count("/") == 1 and int(column.split("/")[0]) < REWRITTEN_FROM_YEAR
    ]
    early = old.drop_duplicates(key).set_index(key)[old_periods]
    return fresh.join(early, on=key)


def _write_financials(symbol: str, target: Path, client: IsYatirimClient, workers: int) -> str:
    path = target / f"{symbol}.parquet"
    meta_path = target / f"{symbol}.json"
    if meta_path.exists():
        return "cached"
    old = _old_cache(symbol)
    start_year = REWRITTEN_FROM_YEAR if old is not None else START_YEAR
    normalized = client.fetch_normalized_financials(
        symbol,
        start_year=start_year,
        end_year=END_YEAR,
        exchange="TRY",
        financial_group=old[1] if old is not None else "XI_29",
        max_workers=workers,
    )
    group = normalized.attrs.get("isyatirim_selected_financial_group", "")
    meta = {
        "symbol": symbol,
        "fetched_at": pd.Timestamp.now().isoformat(),
        "selected_financial_group": group,
        "rows": len(normalized),
        "merged_with_old_cache": bool(old is not None and old[1] == group),
    }
    if not normalized.empty:
        wide = _wide_from_normalized(normalized, symbol)
        if old is not None and old[1] == group:
            wide = _merge_old_columns(wide, old[0])
        wide.to_parquet(path)
    meta_path.write_text(json.dumps(meta))
    return "downloaded" if not normalized.empty else "empty"


def _ever_liquid(symbol: str, price_dir: Path) -> bool:
    path = price_dir / f"{symbol}.parquet"
    if not path.exists():
        return False
    volume = pd.read_parquet(path, columns=["dolar_hacim"])["dolar_hacim"]
    return bool(volume.rolling(LIQUID_WINDOW, min_periods=45).median().max() >= LIQUID_ADV_USD)


def _write_prices(symbol: str, target: Path, client: IsYatirimMarketClient, end_date: str) -> str:
    path = target / f"{symbol}.parquet"
    meta_path = target / f"{symbol}.json"
    if meta_path.exists():
        return "cached"
    frame = client.fetch_prices(symbol, start_date=PRICE_START, end_date=end_date)
    if not frame.empty:
        frame.to_parquet(path)
    meta_path.write_text(json.dumps({"symbol": symbol, "fetched_at": pd.Timestamp.now().isoformat(), "rows": len(frame)}))
    return "downloaded" if not frame.empty else "empty"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", default=date.today().isoformat())
    parser.add_argument("--workers", type=int, default=1, help="Parallel batches per company")
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--symbols", nargs="*", help="Use these symbols instead of the equity market lists")
    parser.add_argument("--skip-financials", action="store_true")
    parser.add_argument("--liquid-only", action="store_true", help="Fetch financials only for symbols with enough trading volume at some point")
    args = parser.parse_args()

    root = ROOT / "data" / "vintages" / args.vintage
    financial_dir = root / "financials"
    price_dir = root / "prices"
    financial_dir.mkdir(parents=True, exist_ok=True)
    price_dir.mkdir(parents=True, exist_ok=True)

    markets = equity_symbols()
    symbols = args.symbols if args.symbols else sorted(markets)
    if args.limit:
        symbols = symbols[: args.limit]

    counts: dict[str, int] = {}
    failures: list[dict[str, str]] = []
    started = time.monotonic()
    end_date = pd.Timestamp(args.vintage).strftime("%d-%m-%Y")
    with IsYatirimClient() as financial_client, IsYatirimMarketClient() as price_client:
        for index, symbol in enumerate(symbols, start=1):
            try:
                price_status = _write_prices(symbol, price_dir, price_client, end_date)
                counts[f"prices_{price_status}"] = counts.get(f"prices_{price_status}", 0) + 1
                if not args.skip_financials and (not args.liquid_only or _ever_liquid(symbol, price_dir)):
                    status = _write_financials(symbol, financial_dir, financial_client, args.workers)
                    counts[f"financials_{status}"] = counts.get(f"financials_{status}", 0) + 1
            except Exception as exc:
                failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            if index % 25 == 0:
                minutes = (time.monotonic() - started) / 60
                print(f"{index}/{len(symbols)} {minutes:.1f} min {counts} failures={len(failures)}", flush=True)
            time.sleep(args.pause)

    suffix = "_custom" if args.symbols else ""
    pd.DataFrame(
        [{"symbol": symbol, "market_at_vintage": markets.get(symbol, "")} for symbol in symbols]
    ).to_csv(root / f"symbols{suffix}.csv", index=False)
    pd.DataFrame(failures, columns=["symbol", "error"]).to_csv(root / f"failures{suffix}.csv", index=False)
    print(f"Done {counts} failures={len(failures)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
