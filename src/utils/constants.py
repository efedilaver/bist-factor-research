"""Central project constants."""

from __future__ import annotations

from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
FINANCIALS_DIR: Final[Path] = DATA_DIR / "financials"
MARKET_DATA_DIR: Final[Path] = DATA_DIR / "market"
MARKET_PRICES_DIR: Final[Path] = MARKET_DATA_DIR / "prices"
REPORT_DATE_FILE: Final[Path] = DATA_DIR / "report_dates.parquet"
SINGLE_SNAPSHOT_DIR: Final[Path] = DATA_DIR / "financial_snapshot"
COMBINED_DIR: Final[Path] = DATA_DIR / "combined"
SNAPSHOT_TYPE: Final[str] = "ttm"
BASE_SNAPSHOT_COLUMNS: Final[list[str]] = [
    "symbol",
    "period",
    "net_income",
    "equity",
    "total_assets",
    "cash",
    "total_debt",
    "net_debt",
    "ebit",
    "depreciation",
    "ebitda",
    "operating_cash_flow",
    "free_cash_flow",
]
MERGED_SNAPSHOT_COLUMNS: Final[list[str]] = BASE_SNAPSHOT_COLUMNS + ["publish_date"]
