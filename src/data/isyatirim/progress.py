"""Internal progress hooks for the İş Yatırım extraction pipeline."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass(frozen=True)
class FetchProgressEvent:
    """Lightweight event emitted while fetching financial data."""

    kind: str
    symbol: str
    profile: str | None = None
    financial_group: str | None = None
    selected_group: str | None = None
    batch_index: int | None = None
    batch_total: int | None = None
    period_start: tuple[int, int] | None = None
    period_end: tuple[int, int] | None = None
    status: str | None = None
    request_count: int = 0
    retries: int = 0
    failure: str | None = None
    cached: bool = False


ProgressCallback = Callable[[FetchProgressEvent], None]

_PROGRESS_CALLBACK: ProgressCallback | None = None


@contextmanager
def progress_callback(callback: ProgressCallback | None) -> Iterator[None]:
    """Temporarily register a callback for fetch progress events."""
    global _PROGRESS_CALLBACK
    previous = _PROGRESS_CALLBACK
    _PROGRESS_CALLBACK = callback
    try:
        yield
    finally:
        _PROGRESS_CALLBACK = previous


def emit_progress(event: FetchProgressEvent) -> None:
    """Emit a progress event if a callback is registered."""
    callback = _PROGRESS_CALLBACK
    if callback is not None:
        callback(event)
