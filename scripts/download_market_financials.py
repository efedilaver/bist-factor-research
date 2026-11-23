#!/usr/bin/env python3
"""Download raw İş Yatırım financial tables for symbols in a selected market."""

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

from src.data.markets import DEFAULT_MARKETS_WORKBOOK, list_markets, load_market_symbols
from src.data.isyatirim.cache import load_financials_cache
from src.data.isyatirim.fetch import fetch_financials

DEFAULT_MARKET = "PAY PİYASASI-YILDIZ PAZAR"


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
    unsupported: int = 0
    failed: int = 0
    total_seconds: float = 0.0


def _status_for_frame(frame) -> str:
    if bool(frame.attrs.get("isyatirim_unsupported")):
        return "unsupported"
    return "downloaded"


def _download_market(
    market: str,
    *,
    workbook_path: Path,
    batch_size: int,
    start_year: int,
    end_year: int,
    financial_group: str,
    overwrite: bool,
    verbose: bool,
) -> DownloadSummary:
    symbols = load_market_symbols(market, workbook_path=workbook_path)
    summary = DownloadSummary(total_symbols=len(symbols))

    print(f"Market: {market}")
    print(f"Workbook: {workbook_path}")
    print(f"Symbols: {len(symbols)}")
    print(f"Batch size: {batch_size}")
    print("-" * 80)

    started = time.perf_counter()
    for batch_number, batch in enumerate(_chunked(symbols, batch_size), start=1):
        batch_started = time.perf_counter()
        print(f"Batch {batch_number}: {len(batch)} symbols")
        for symbol in batch:
            symbol_started = time.perf_counter()
            cached_before = load_financials_cache(symbol) is not None
            try:
                frame = fetch_financials(
                    symbol,
                    start_year,
                    end_year,
                    financial_group=financial_group,
                    overwrite=overwrite,
                    verbose=verbose,
                )
            except Exception as exc:
                summary.failed += 1
                elapsed = time.perf_counter() - symbol_started
                print(f"  {symbol:<8} failed ({type(exc).__name__}): {elapsed:.1f}s")
                continue

            status = "cached" if cached_before and not overwrite else _status_for_frame(frame)
            if status == "downloaded":
                summary.downloaded += 1
            elif status == "unsupported":
                summary.unsupported += 1
            else:
                summary.cached += 1
            elapsed = time.perf_counter() - symbol_started
            print(f"  {symbol:<8} {status:<11} {elapsed:.1f}s")

        batch_elapsed = time.perf_counter() - batch_started
        print(f"Batch {batch_number} completed in {batch_elapsed:.1f}s")
        print("-" * 80)

    summary.total_seconds = time.perf_counter() - started
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_MARKETS_WORKBOOK,
        help="Pazarlar workbook path.",
    )
    parser.add_argument(
        "--market",
        action="append",
        dest="markets",
        default=None,
        help="Exact market name from the workbook. Can be repeated.",
    )
    parser.add_argument(
        "--all-markets",
        action="store_true",
        help="Download every market in the workbook instead of the selected markets.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of symbols to process per batch.",
    )
    parser.add_argument("--start-year", type=int, default=2015, help="Start year for financial fetches.")
    parser.add_argument("--end-year", type=int, default=2026, help="End year for financial fetches.")
    parser.add_argument(
        "--financial-group",
        default="XI_29",
        help="Financial group to request from İş Yatırım.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Ignore existing cached raw financial files.")
    parser.add_argument("--verbose", action="store_true", help="Print per-company diagnostics.")
    args = parser.parse_args()

    if args.all_markets:
        markets = list_markets(args.workbook)
    else:
        markets = args.markets or [DEFAULT_MARKET]

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
            start_year=args.start_year,
            end_year=args.end_year,
            financial_group=args.financial_group,
            overwrite=args.overwrite,
            verbose=args.verbose,
        )
        overall.total_symbols += summary.total_symbols
        overall.downloaded += summary.downloaded
        overall.cached += summary.cached
        overall.unsupported += summary.unsupported
        overall.failed += summary.failed
    overall.total_seconds = time.perf_counter() - overall_started

    print("=" * 80)
    print("Final summary")
    print(f"Total symbols: {overall.total_symbols}")
    print(f"Downloaded: {overall.downloaded}")
    print(f"Cached: {overall.cached}")
    print(f"Unsupported: {overall.unsupported}")
    print(f"Failed: {overall.failed}")
    print(f"Total elapsed: {overall.total_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
