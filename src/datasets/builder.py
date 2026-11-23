"""Dataset orchestration for point-in-time research snapshots."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from src.data.isyatirim.progress import FetchProgressEvent, progress_callback
from src.data.isyatirim.cache import load_financials_metadata
from src.financials.merge import merge_report_dates
from src.financials.snapshot import build_financial_snapshot
from src.utils.constants import (
    COMBINED_DIR,
    MERGED_SNAPSHOT_COLUMNS,
    SINGLE_SNAPSHOT_DIR,
    SNAPSHOT_TYPE,
)
from src.utils.logger import get_logger

from src.data.kap import load_report_dates as load_kap_report_dates

from .loader import finalize_snapshot_frame, load_dataframe, prepare_report_dates, save_dataframe

try:
    from tqdm.auto import tqdm
except ImportError:  # pragma: no cover

    def tqdm(iterable, **kwargs):
        return iterable

try:  # pragma: no cover - rich is optional at runtime, but preferred
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None  # type: ignore[assignment]
    Group = None  # type: ignore[assignment]
    Live = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]


logger = get_logger("bist30_dataset")


@dataclass
class _DatasetProgressState:
    total_companies: int
    started_at: float = field(default_factory=time.perf_counter)
    completed_companies: int = 0
    downloaded_companies: int = 0
    cached_companies: int = 0
    unsupported_companies: int = 0
    failed_companies: int = 0
    retries: int = 0
    total_http_requests: int = 0
    current_symbol: str = ""
    current_profile: str = ""
    current_group: str = ""
    current_batch: str = ""
    current_period_range: str = ""
    current_status: str = "waiting"
    _company_start_times: dict[str, float] = field(default_factory=dict)
    company_durations: list[float] = field(default_factory=list)

    def handle_event(self, event: FetchProgressEvent) -> None:
        symbol = str(event.symbol).strip().upper()
        if event.kind == "company_start":
            self.current_symbol = symbol
            self.current_status = "starting"
            self.current_profile = ""
            self.current_group = str(event.financial_group or "").upper()
            self.current_batch = ""
            self.current_period_range = ""
            self._company_start_times[symbol] = time.perf_counter()
            return

        if event.kind == "batch_start":
            self.current_symbol = symbol
            self.current_group = str(event.financial_group or "").upper()
            self.current_batch = f"{event.batch_index}/{event.batch_total}" if event.batch_index and event.batch_total else ""
            if event.period_start and event.period_end:
                start_year, start_quarter = event.period_start
                end_year, end_quarter = event.period_end
                self.current_period_range = f"{start_year}Q{start_quarter}-{end_year}Q{end_quarter}"
            self.current_status = "fetching batch"
            return

        if event.kind == "batch_done":
            self.total_http_requests += int(event.request_count)
            self.retries += int(event.retries)
            self.current_status = event.status or "batch complete"
            if event.failure:
                self.current_status = f"batch failed: {event.failure}"
            return

        if event.kind == "company_done":
            self.current_symbol = symbol
            self.current_profile = str(event.profile or "").strip()
            self.current_group = str(event.selected_group or event.financial_group or "").upper()
            self.current_status = str(event.status or "done")
            if self.current_status == "unsupported":
                self.unsupported_companies += 1
            elif event.cached:
                self.cached_companies += 1
            else:
                self.downloaded_companies += 1
            self.completed_companies += 1
            started_at = self._company_start_times.pop(symbol, None)
            if started_at is not None:
                self.company_durations.append(time.perf_counter() - started_at)

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.started_at

    @property
    def average_company_seconds(self) -> float:
        if not self.company_durations:
            return 0.0
        return sum(self.company_durations) / len(self.company_durations)

    @property
    def eta_seconds(self) -> float:
        remaining = max(self.total_companies - self.completed_companies, 0)
        if not self.company_durations:
            return 0.0
        return remaining * self.average_company_seconds

    @property
    def throughput_per_minute(self) -> float:
        elapsed_minutes = self.elapsed_seconds / 60.0
        if elapsed_minutes <= 0:
            return 0.0
        return self.completed_companies / elapsed_minutes


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0.0s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:04.1f}s"


def _render_progress_panel(state: _DatasetProgressState):
    if Console is None or Group is None or Panel is None or Table is None:
        return None

    overall = Table.grid(expand=True)
    overall.add_column(ratio=1)
    overall.add_column(justify="right")
    percentage = (state.completed_companies / state.total_companies * 100.0) if state.total_companies else 100.0
    overall.add_row("completed companies", f"{state.completed_companies} / {state.total_companies}")
    overall.add_row("percentage", f"{percentage:.1f}%")
    overall.add_row("elapsed time", _format_duration(state.elapsed_seconds))
    overall.add_row("ETA", _format_duration(state.eta_seconds))
    overall.add_row("average time/company", _format_duration(state.average_company_seconds))

    current = Table.grid(expand=True)
    current.add_column(ratio=1)
    current.add_column(justify="right")
    current.add_row("symbol", state.current_symbol or "-")
    current.add_row("detected profile", state.current_profile or "-")
    current.add_row("selected financial group", state.current_group or "-")
    current.add_row("current batch", state.current_batch or "-")
    current.add_row("current period range", state.current_period_range or "-")
    current.add_row("current status", state.current_status or "-")

    stats = Table.grid(expand=True)
    stats.add_column(ratio=1)
    stats.add_column(justify="right")
    stats.add_row("downloaded companies", str(state.downloaded_companies))
    stats.add_row("cached companies", str(state.cached_companies))
    stats.add_row("unsupported companies", str(state.unsupported_companies))
    stats.add_row("failed companies", str(state.failed_companies))
    stats.add_row("retries", str(state.retries))
    stats.add_row("total HTTP requests", str(state.total_http_requests))

    return Group(
        Panel(overall, title="Overall Progress", border_style="cyan"),
        Panel(current, title="Current Company", border_style="green"),
        Panel(stats, title="Statistics", border_style="magenta"),
    )


def _ensure_directories() -> None:
    """Create output directories if they do not exist."""
    SINGLE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    COMBINED_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_symbol(symbol: str) -> str:
    """Normalize a ticker symbol for file paths and joins."""
    return str(symbol).strip().upper()


def _load_report_dates() -> pd.DataFrame:
    """Load and normalize the cached report-date table."""
    return prepare_report_dates(load_kap_report_dates())


class UnsupportedFinancialDataError(RuntimeError):
    """Raised when the source endpoint returns no financial statements."""

    def __init__(self, message: str, *, progress_counted: bool = False) -> None:
        super().__init__(message)
        self.progress_counted = progress_counted


def _unsupported_financial_reason(symbol: str) -> str:
    return f"No financial statements were returned by the İş Yatırım endpoint for {symbol}."


def _raw_financials_unsupported(symbol: str) -> bool:
    metadata = load_financials_metadata(symbol)
    return bool(metadata and metadata.get("isyatirim_unsupported"))


def _build_company_snapshot(
    symbol: str,
    report_dates: pd.DataFrame,
    snapshot_type: str = SNAPSHOT_TYPE,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Build or load a cached point-in-time snapshot for a single company."""
    symbol_value = _normalize_symbol(symbol)
    cache_path = SINGLE_SNAPSHOT_DIR / f"{symbol_value}.parquet"
    csv_cache_path = cache_path.with_suffix(".csv")

    if _raw_financials_unsupported(symbol_value):
        raise UnsupportedFinancialDataError(_unsupported_financial_reason(symbol_value), progress_counted=False)

    if not overwrite:
        cached = load_dataframe(cache_path)
        if cached is None:
            cached = load_dataframe(csv_cache_path)
        if cached is not None and not cached.empty and {"publish_date", "period"}.issubset(cached.columns):
            return finalize_snapshot_frame(cached)

    try:
        snapshot = build_financial_snapshot(symbol_value, snapshot_type)
    except ValueError as exc:
        if _raw_financials_unsupported(symbol_value):
            raise UnsupportedFinancialDataError(
                _unsupported_financial_reason(symbol_value),
                progress_counted=True,
            ) from exc
        raise

    merged = merge_report_dates(snapshot, report_dates)
    merged = merged[[column for column in MERGED_SNAPSHOT_COLUMNS if column in merged.columns]]
    merged = finalize_snapshot_frame(merged)

    save_dataframe(merged, cache_path)
    return merged


def build_bist30_research_dataset(
    symbols: Iterable[str],
    snapshot_type: str = SNAPSHOT_TYPE,
    overwrite: bool = False,
    report_dates: pd.DataFrame | None = None,
    company_limit: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Build cached point-in-time snapshots for a list of BIST symbols."""
    _ensure_directories()

    if report_dates is None:
        report_dates = _load_report_dates()
    else:
        report_dates = prepare_report_dates(report_dates)

    snapshots: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    failed_symbols: list[str] = []
    unsupported_symbols: list[str] = []

    normalized_symbols = [_normalize_symbol(symbol) for symbol in symbols]
    if company_limit is not None and company_limit < 0:
        raise ValueError("company_limit must be greater than or equal to 0")

    limited_symbols = normalized_symbols if company_limit is None else normalized_symbols[:company_limit]
    if company_limit is not None and len(normalized_symbols) > len(limited_symbols):
        logger.warning(
            "Limiting dataset build to %d companies out of %d",
            len(limited_symbols),
            len(normalized_symbols),
        )

    progress_state = _DatasetProgressState(total_companies=len(limited_symbols))
    progress_lock = threading.Lock()

    def _handle_progress(event: FetchProgressEvent) -> None:
        with progress_lock:
            progress_state.handle_event(event)
            if live is not None:
                live.update(_render_progress_panel(progress_state), refresh=True)

    live = None
    if Console is not None and Live is not None:
        console = Console()
        live = Live(_render_progress_panel(progress_state), console=console, refresh_per_second=4, transient=False)

    iterable = limited_symbols if live is None else limited_symbols
    with progress_callback(_handle_progress):
        if live is None:
            iterator = tqdm(iterable, desc="Building BIST30 snapshots", unit="company")
            for symbol in iterator:
                progress_state.current_symbol = symbol
                progress_state.current_status = "starting"
                try:
                    company_snapshot = _build_company_snapshot(
                        symbol=symbol,
                        report_dates=report_dates,
                        snapshot_type=snapshot_type,
                        overwrite=overwrite,
                    )
                    snapshots.append(company_snapshot)

                    financial_columns = [
                        column
                        for column in company_snapshot.columns
                        if column not in {"symbol", "period", "publish_date"}
                    ]
                    summary_rows.append(
                        {
                            "symbol": symbol,
                            "rows": len(company_snapshot),
                            "first_period": company_snapshot["period"].min(),
                            "last_period": company_snapshot["period"].max(),
                            "missing_publish_dates": int(company_snapshot["publish_date"].isna().sum()),
                            "missing_financial_values": int(company_snapshot[financial_columns].isna().sum().sum()),
                            "status": "ok",
                            "message": "",
                        }
                    )
                except UnsupportedFinancialDataError as exc:
                    if not exc.progress_counted:
                        progress_state.completed_companies += 1
                        progress_state.unsupported_companies += 1
                        progress_state.company_durations.append(0.0)
                    progress_state.current_status = "unsupported"
                    logger.warning("%s", exc)
                    unsupported_symbols.append(symbol)
                    summary_rows.append(
                        {
                            "symbol": symbol,
                            "rows": 0,
                            "first_period": pd.NaT,
                            "last_period": pd.NaT,
                            "missing_publish_dates": pd.NA,
                            "missing_financial_values": pd.NA,
                            "status": "unsupported",
                            "message": str(exc),
                        }
                    )
                except Exception:  # pragma: no cover
                    progress_state.failed_companies += 1
                    progress_state.completed_companies += 1
                    progress_state.current_status = "failed"
                    logger.exception("Failed to process %s", symbol)
                    failed_symbols.append(symbol)
                    summary_rows.append(
                        {
                            "symbol": symbol,
                            "rows": 0,
                            "first_period": pd.NaT,
                            "last_period": pd.NaT,
                            "missing_publish_dates": pd.NA,
                            "missing_financial_values": pd.NA,
                            "status": "failed",
                            "message": "Failed to build snapshot",
                        }
                    )
        else:
            with live:
                for symbol in limited_symbols:
                    progress_state.current_symbol = symbol
                    progress_state.current_status = "starting"
                    live.update(_render_progress_panel(progress_state), refresh=True)
                    try:
                        company_snapshot = _build_company_snapshot(
                            symbol=symbol,
                            report_dates=report_dates,
                            snapshot_type=snapshot_type,
                            overwrite=overwrite,
                        )
                        snapshots.append(company_snapshot)

                        financial_columns = [
                            column
                            for column in company_snapshot.columns
                            if column not in {"symbol", "period", "publish_date"}
                        ]
                        summary_rows.append(
                            {
                                "symbol": symbol,
                                "rows": len(company_snapshot),
                                "first_period": company_snapshot["period"].min(),
                                "last_period": company_snapshot["period"].max(),
                                "missing_publish_dates": int(company_snapshot["publish_date"].isna().sum()),
                                "missing_financial_values": int(company_snapshot[financial_columns].isna().sum().sum()),
                                "status": "ok",
                                "message": "",
                            }
                        )
                    except UnsupportedFinancialDataError as exc:
                        if not exc.progress_counted:
                            progress_state.completed_companies += 1
                            progress_state.unsupported_companies += 1
                            progress_state.company_durations.append(0.0)
                        progress_state.current_status = "unsupported"
                        logger.warning("%s", exc)
                        unsupported_symbols.append(symbol)
                        summary_rows.append(
                            {
                                "symbol": symbol,
                                "rows": 0,
                                "first_period": pd.NaT,
                                "last_period": pd.NaT,
                                "missing_publish_dates": pd.NA,
                                "missing_financial_values": pd.NA,
                                "status": "unsupported",
                                "message": str(exc),
                            }
                        )
                    except Exception:  # pragma: no cover
                        progress_state.failed_companies += 1
                        progress_state.completed_companies += 1
                        progress_state.current_status = "failed"
                        logger.exception("Failed to process %s", symbol)
                        failed_symbols.append(symbol)
                        summary_rows.append(
                            {
                                "symbol": symbol,
                                "rows": 0,
                                "first_period": pd.NaT,
                                "last_period": pd.NaT,
                                "missing_publish_dates": pd.NA,
                                "missing_financial_values": pd.NA,
                                "status": "failed",
                                "message": "Failed to build snapshot",
                            }
                        )
                    finally:
                        live.update(_render_progress_panel(progress_state), refresh=True)
                        if symbol not in failed_symbols and symbol not in progress_state._company_start_times:
                            # A successful company fetch increments completion via company_done event.
                            pass

    if snapshots:
        all_snapshots = pd.concat(snapshots, ignore_index=True)
        all_snapshots = finalize_snapshot_frame(all_snapshots)
        all_snapshots = all_snapshots.sort_values(["symbol", "period"], kind="mergesort").reset_index(drop=True)
    else:
        all_snapshots = pd.DataFrame(columns=MERGED_SNAPSHOT_COLUMNS)

    financial_snapshot_summary = pd.DataFrame(summary_rows)
    financial_snapshot_summary = financial_snapshot_summary[
        [
            "symbol",
            "rows",
            "first_period",
            "last_period",
            "missing_publish_dates",
            "missing_financial_values",
            "status",
            "message",
        ]
    ]

    elapsed = progress_state.elapsed_seconds
    if Console is not None and Panel is not None:
        console = Console()
        summary = Table.grid(expand=True)
        summary.add_column(ratio=1)
        summary.add_column(justify="right")
        summary.add_row("total elapsed time", _format_duration(elapsed))
        summary.add_row("average company time", _format_duration(progress_state.average_company_seconds))
        summary.add_row("total HTTP requests", str(progress_state.total_http_requests))
        summary.add_row("cache hits", str(progress_state.cached_companies))
        summary.add_row("unsupported companies", str(progress_state.unsupported_companies))
        summary.add_row("retries", str(progress_state.retries))
        summary.add_row("failures", str(progress_state.failed_companies))
        summary.add_row("unsupported symbols", ", ".join(unsupported_symbols) if unsupported_symbols else "none")
        summary.add_row("throughput", f"{progress_state.throughput_per_minute:.2f} companies/min")
        console.print(Panel(summary, title="BIST30 First Rollout Summary", border_style="blue"))
    else:  # pragma: no cover
        print(f"total elapsed time: {_format_duration(elapsed)}")
        print(f"average company time: {_format_duration(progress_state.average_company_seconds)}")
        print(f"total HTTP requests: {progress_state.total_http_requests}")
        print(f"cache hits: {progress_state.cached_companies}")
        print(f"unsupported companies: {progress_state.unsupported_companies}")
        print(f"retries: {progress_state.retries}")
        print(f"failures: {progress_state.failed_companies}")
        print(f"unsupported symbols: {', '.join(unsupported_symbols) if unsupported_symbols else 'none'}")
        print(f"throughput: {progress_state.throughput_per_minute:.2f} companies/min")

    return all_snapshots, financial_snapshot_summary, failed_symbols
