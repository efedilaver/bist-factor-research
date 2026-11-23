"""Reusable HTTP client for the İş Yatırım MaliTablo endpoint."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Final

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .mapper import FINANCIAL_GROUP_ALIASES, FINANCIAL_GROUP_ORDER
from .parser import parse_mali_tablo_payload
from .progress import FetchProgressEvent, emit_progress

BASE_URL: Final[str] = (
    "https://www.isyatirim.com.tr/_Layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo"
)
DEFAULT_TIMEOUT: Final[tuple[float, float]] = (10.0, 30.0)
MAX_PERIODS_PER_REQUEST: Final[int] = 4


def _quarter_periods(start_year: int, end_year: int) -> list[tuple[int, int]]:
    """Generate quarter-end periods in ascending order."""
    if end_year < start_year:
        raise ValueError("end_year must be greater than or equal to start_year")

    periods: list[tuple[int, int]] = []
    for year in range(start_year, end_year + 1):
        for quarter in (3, 6, 9, 12):
            periods.append((year, quarter))
    return periods


def _chunk_periods(
    periods: Sequence[tuple[int, int]],
    size: int = MAX_PERIODS_PER_REQUEST,
) -> list[list[tuple[int, int]]]:
    """Split periods into endpoint-sized batches."""
    return [list(periods[index : index + size]) for index in range(0, len(periods), size)]


def _period_sort_key(period: str) -> tuple[int, int]:
    year_text, quarter_text = period.split("/", 1)
    return int(year_text), int(quarter_text)


def _normalize_group_name(financial_group: str) -> str:
    """Map legacy aliases to canonical financial-group names."""
    normalized = str(financial_group).strip().upper()
    return FINANCIAL_GROUP_ALIASES.get(normalized, normalized)


class RequestConfig:
    """Configuration applied to every endpoint request."""

    def __init__(
        self,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        backoff_factor: float = 0.4,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor


@dataclass(frozen=True)
class _BatchProgress:
    symbol: str
    batch_index: int
    batch_total: int
    financial_group: str
    periods: Sequence[tuple[int, int]]


class _ParallelBatchFetchError(RuntimeError):
    """Signal that parallel batch fetching should fall back to sequential mode."""


class _ThreadLocalClientPool:
    """Reuse one `IsYatirimClient` per worker thread."""

    def __init__(self, config: RequestConfig) -> None:
        self._config = config
        self._local = threading.local()
        self._clients: list[IsYatirimClient] = []
        self._lock = threading.Lock()

    def get(self) -> "IsYatirimClient":
        client = getattr(self._local, "client", None)
        if client is None:
            client = IsYatirimClient(config=self._config)
            self._local.client = client
            with self._lock:
                self._clients.append(client)
        return client

    def close(self) -> None:
        for client in self._clients:
            try:
                client.close()
            except Exception:
                pass


class IsYatirimClient:
    """HTTP client with retry support and batching for MaliTablo requests."""

    def __init__(self, config: RequestConfig | None = None) -> None:
        self.config = config or RequestConfig()
        self.session = requests.Session()
        retry = Retry(
            total=self.config.max_retries,
            connect=self.config.max_retries,
            read=self.config.max_retries,
            status=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.isyatirim.com.tr/",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> "IsYatirimClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request_batch(
        self,
        symbol: str,
        periods: Sequence[tuple[int, int]],
        *,
        exchange: str,
        financial_group: str,
        progress: _BatchProgress | None = None,
    ) -> pd.DataFrame:
        """Fetch and parse one endpoint batch."""
        symbol_value = symbol.upper()
        progress_event = None
        if progress is not None:
            period_start = progress.periods[0] if progress.periods else None
            period_end = progress.periods[-1] if progress.periods else None
            progress_event = FetchProgressEvent(
                kind="batch_start",
                symbol=symbol_value,
                financial_group=financial_group,
                batch_index=progress.batch_index,
                batch_total=progress.batch_total,
                period_start=period_start,
                period_end=period_end,
                status="started",
            )
            emit_progress(progress_event)

        params: dict[str, object] = {
            "companyCode": symbol_value,
            "exchange": exchange,
            "financialGroup": financial_group,
        }
        for index, (year, quarter) in enumerate(periods, start=1):
            params[f"year{index}"] = int(year)
            params[f"period{index}"] = int(quarter)

        response = None
        failure: Exception | None = None
        try:
            response = self.session.get(
                BASE_URL,
                params=params,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            return parse_mali_tablo_payload(
                payload,
                periods,
                symbol=symbol,
                exchange=exchange,
                financial_group=financial_group,
            )
        except Exception as exc:
            failure = exc
            raise
        finally:
            if progress_event is not None:
                retry_state = getattr(getattr(response, "raw", None), "retries", None)
                retry_history = list(getattr(retry_state, "history", []) or [])
                emit_progress(
                    FetchProgressEvent(
                        kind="batch_done",
                        symbol=symbol_value,
                        financial_group=financial_group,
                        batch_index=progress.batch_index,
                        batch_total=progress.batch_total,
                        period_start=progress_event.period_start,
                        period_end=progress_event.period_end,
                        status="success" if failure is None else "failed",
                        request_count=1,
                        retries=len(retry_history),
                        failure=type(failure).__name__ if failure is not None else None,
                    )
                )

    def _combine_group_frames(
        self,
        symbol: str,
        group: str,
        group_frames: list[tuple[int, pd.DataFrame]],
    ) -> pd.DataFrame:
        combined = pd.concat([frame for _, frame in sorted(group_frames, key=lambda item: item[0])], ignore_index=True)
        combined = combined.sort_values(
            ["itemCode", "year", "quarter"],
            kind="mergesort",
        ).reset_index(drop=True)
        combined.attrs["isyatirim_groups_attempted"] = []
        combined.attrs["isyatirim_selected_financial_group"] = group
        combined.attrs["isyatirim_raw_rows"] = len(combined)
        return combined

    def _fetch_normalized_financials_sequential(
        self,
        symbol: str,
        *,
        start_year: int,
        end_year: int,
        exchange: str = "TRY",
        financial_group: str = "XI_29",
    ) -> pd.DataFrame:
        periods = _quarter_periods(start_year, end_year)
        batches = _chunk_periods(periods, MAX_PERIODS_PER_REQUEST)
        group_candidates = self._group_candidates(financial_group)

        attempts: list[dict[str, object]] = []
        last_error: Exception | None = None
        for group in group_candidates:
            group_frames: list[pd.DataFrame] = []
            try:
                for batch_index, batch in enumerate(batches, start=1):
                    frame = self._request_batch(
                        symbol,
                        batch,
                        exchange=exchange,
                        financial_group=group,
                        progress=_BatchProgress(
                            symbol=symbol,
                            batch_index=batch_index,
                            batch_total=len(batches),
                            financial_group=group,
                            periods=batch,
                        ),
                    )
                    if not frame.empty:
                        group_frames.append(frame)
            except (requests.RequestException, ValueError, TypeError, KeyError, RuntimeError) as exc:
                last_error = exc
                attempts.append({"financial_group": group, "rows": 0})
                continue

            if group_frames:
                combined = pd.concat(group_frames, ignore_index=True)
                combined = combined.sort_values(
                    ["itemCode", "year", "quarter"],
                    kind="mergesort",
                ).reset_index(drop=True)
                attempts.append({"financial_group": group, "rows": len(combined)})
                combined.attrs["isyatirim_groups_attempted"] = attempts
                combined.attrs["isyatirim_selected_financial_group"] = group
                combined.attrs["isyatirim_raw_rows"] = len(combined)
                return combined
            attempts.append({"financial_group": group, "rows": 0})

        if last_error is not None:
            raise last_error
        empty = pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "financial_group",
                "itemCode",
                "itemDescTr",
                "itemDescEng",
                "period",
                "year",
                "quarter",
                "value",
            ]
        )
        empty.attrs["isyatirim_groups_attempted"] = attempts
        empty.attrs["isyatirim_selected_financial_group"] = ""
        empty.attrs["isyatirim_raw_rows"] = 0
        return empty

    def _fetch_group_batches_parallel(
        self,
        symbol: str,
        *,
        batches: Sequence[Sequence[tuple[int, int]]],
        exchange: str,
        financial_group: str,
        max_workers: int,
    ) -> pd.DataFrame | None:
        pool = _ThreadLocalClientPool(self.config)
        try:
            results: list[tuple[int, pd.DataFrame]] = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(
                        self._parallel_batch_request,
                        pool,
                        symbol,
                        batch,
                        exchange,
                        financial_group,
                        index,
                        len(batches),
                    ): index
                    for index, batch in enumerate(batches, start=1)
                }
                try:
                    for future in as_completed(future_map):
                        index = future_map[future]
                        try:
                            frame = future.result()
                        except Exception as exc:
                            for pending in future_map:
                                pending.cancel()
                            raise _ParallelBatchFetchError(
                                f"Parallel batch {index} failed for {symbol}"
                            ) from exc
                        if not frame.empty:
                            results.append((index, frame))
                except _ParallelBatchFetchError:
                    raise
            if not results:
                return None
            return self._combine_group_frames(symbol, financial_group, results)
        finally:
            pool.close()

    def _parallel_batch_request(
        self,
        pool: _ThreadLocalClientPool,
        symbol: str,
        batch: Sequence[tuple[int, int]],
        exchange: str,
        financial_group: str,
        batch_index: int,
        batch_total: int,
    ) -> pd.DataFrame:
        client = pool.get()
        return client._request_batch(
            symbol,
            batch,
            exchange=exchange,
            financial_group=financial_group,
            progress=_BatchProgress(
                symbol=symbol,
                batch_index=batch_index,
                batch_total=batch_total,
                financial_group=financial_group,
                periods=batch,
            ),
        )

    def fetch_normalized_financials(
        self,
        symbol: str,
        *,
        start_year: int,
        end_year: int,
        exchange: str = "TRY",
        financial_group: str = "XI_29",
        max_workers: int = 1,
    ) -> pd.DataFrame:
        """Fetch a long-form normalized financial table for a symbol."""
        if max_workers < 1:
            raise ValueError("max_workers must be greater than or equal to 1")

        periods = _quarter_periods(start_year, end_year)
        batches = _chunk_periods(periods, MAX_PERIODS_PER_REQUEST)
        group_candidates = self._group_candidates(financial_group)

        if max_workers == 1 or len(batches) <= 1:
            return self._fetch_normalized_financials_sequential(
                symbol,
                start_year=start_year,
                end_year=end_year,
                exchange=exchange,
                financial_group=financial_group,
            )

        attempts: list[dict[str, object]] = []
        last_error: Exception | None = None
        for group in group_candidates:
            try:
                combined = self._fetch_group_batches_parallel(
                    symbol,
                    batches=batches,
                    exchange=exchange,
                    financial_group=group,
                    max_workers=max_workers,
                )
            except _ParallelBatchFetchError as exc:
                last_error = exc
                break

            if combined is None:
                attempts.append({"financial_group": group, "rows": 0})
                continue

            combined.attrs["isyatirim_groups_attempted"] = attempts + [
                {"financial_group": group, "rows": len(combined)}
            ]
            combined.attrs["isyatirim_selected_financial_group"] = group
            combined.attrs["isyatirim_raw_rows"] = len(combined)
            return combined

        if last_error is not None:
            return self._fetch_normalized_financials_sequential(
                symbol,
                start_year=start_year,
                end_year=end_year,
                exchange=exchange,
                financial_group=financial_group,
            )

        empty = pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "financial_group",
                "itemCode",
                "itemDescTr",
                "itemDescEng",
                "period",
                "year",
                "quarter",
                "value",
            ]
        )
        empty.attrs["isyatirim_groups_attempted"] = attempts
        empty.attrs["isyatirim_selected_financial_group"] = ""
        empty.attrs["isyatirim_raw_rows"] = 0
        return empty

    def _group_candidates(self, financial_group: str) -> list[str]:
        """Return the requested financial group followed by supported fallbacks."""
        requested = _normalize_group_name(financial_group)
        candidates = [requested, *FINANCIAL_GROUP_ORDER]
        unique: list[str] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique
