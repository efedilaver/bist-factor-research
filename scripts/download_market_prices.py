#!/usr/bin/env python3
"""Download raw İş Yatırım HisseTekil market prices for symbols in selected markets."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.market import IsYatirimMarketClient, fetch_market_prices, load_market_price_cache
from src.data.markets import DEFAULT_MARKETS_WORKBOOK, list_markets, load_market_symbols

DEFAULT_MARKET = "PAY PİYASASI-YILDIZ PAZAR"
DEFAULT_START_DATE = "09-08-2015"
DEFAULT_END_DATE = "09-08-2026"


def _chunked(items: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("batch size must be greater than zero")
    for index in range(0, len(items), size):
        yield items[index : index + size]


@dataclass
class DownloadSummary:
    total_symbols: int = 0
    downloaded: int = 0
    cached: int = 0
    empty: int = 0
    failed: int = 0
    total_rows: int = 0
    total_seconds: float = 0.0


def _download_market(
    market: str,
    *,
    workbook_path: Path,
    batch_size: int,
    limit: int | None,
    start_date: str,
    end_date: str,
    overwrite: bool,
) -> DownloadSummary:
    symbols = load_market_symbols(market, workbook_path=workbook_path)
    if limit is not None:
        symbols = symbols[:limit]

    summary = DownloadSummary(total_symbols=len(symbols))
    print(f"Market: {market}")
    print(f"Workbook: {workbook_path}")
    print(f"Symbols: {len(symbols)}")
    print(f"Date range: {start_date} - {end_date}")
    print(f"Batch size: {batch_size}")
    print("-" * 80)

    started = time.perf_counter()
    with IsYatirimMarketClient() as client:
        for batch_number, batch in enumerate(_chunked(symbols, batch_size), start=1):
            batch_started = time.perf_counter()
            print(f"Batch {batch_number}: {len(batch)} symbols")
            for symbol in batch:
                symbol_started = time.perf_counter()
                cached_before = load_market_price_cache(symbol) is not None
                try:
                    frame = fetch_market_prices(
                        symbol,
                        start_date=start_date,
                        end_date=end_date,
                        overwrite=overwrite,
                        client=client,
                    )
                except Exception as exc:
                    summary.failed += 1
                    elapsed = time.perf_counter() - symbol_started
                    print(f"  {symbol:<8} failed ({type(exc).__name__}): {elapsed:.1f}s")
                    continue

                row_count = len(frame)
                summary.total_rows += row_count
                if cached_before and not overwrite:
                    summary.cached += 1
                    status = "cached"
                elif row_count == 0:
                    summary.empty += 1
                    status = "empty"
                else:
                    summary.downloaded += 1
                    status = "downloaded"
                elapsed = time.perf_counter() - symbol_started
                print(f"  {symbol:<8} {status:<10} rows={row_count:<6} {elapsed:.1f}s")

            batch_elapsed = time.perf_counter() - batch_started
            print(f"Batch {batch_number} completed in {batch_elapsed:.1f}s")
            print("-" * 80)

    summary.total_seconds = time.perf_counter() - started
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_MARKETS_WORKBOOK, help="Pazarlar workbook path.")
    parser.add_argument(
        "--market",
        action="append",
        dest="markets",
        default=None,
        help="Exact market name from the workbook. Can be repeated.",
    )
    parser.add_argument("--all-markets", action="store_true", help="Download every market in the workbook.")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of symbols to process per batch.")
    parser.add_argument("--limit", type=int, default=None, help="Optional symbol limit per market.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Start date in dd-mm-yyyy format.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="End date in dd-mm-yyyy format.")
    parser.add_argument("--overwrite", action="store_true", help="Ignore existing cached market price files.")
    args = parser.parse_args()

    markets = list_markets(args.workbook) if args.all_markets else args.markets or [DEFAULT_MARKET]

    print("Selected markets:")
    for market in markets:
        print(f"- {market}")
    print("=" * 80)

    overall = DownloadSummary()
    overall_started = time.perf_counter()
    for market in markets:
        summary = _download_market(
            market,
            workbook_path=args.workbook,
            batch_size=args.batch_size,
            limit=args.limit,
            start_date=args.start_date,
            end_date=args.end_date,
            overwrite=args.overwrite,
        )
        overall.total_symbols += summary.total_symbols
        overall.downloaded += summary.downloaded
        overall.cached += summary.cached
        overall.empty += summary.empty
        overall.failed += summary.failed
        overall.total_rows += summary.total_rows
    overall.total_seconds = time.perf_counter() - overall_started

    print("=" * 80)
    print("Final summary")
    print(f"Total symbols: {overall.total_symbols}")
    print(f"Downloaded: {overall.downloaded}")
    print(f"Cached: {overall.cached}")
    print(f"Empty: {overall.empty}")
    print(f"Failed: {overall.failed}")
    print(f"Total rows: {overall.total_rows}")
    print(f"Total elapsed: {overall.total_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
