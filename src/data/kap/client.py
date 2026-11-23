"""HTTP client for KAP disclosure queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

KAP_DISCLOSURE_URL: Final[str] = "https://kap.org.tr/tr/api/disclosure/members/byCriteria"
DEFAULT_TIMEOUT: Final[tuple[float, float]] = (10.0, 30.0)


@dataclass(frozen=True)
class KAPRequestConfig:
    """Configuration applied to all KAP HTTP requests."""

    timeout: tuple[float, float] = DEFAULT_TIMEOUT
    max_retries: int = 5
    backoff_factor: float = 1.0
    min_request_interval: float = 1.0


class KapClient:
    """Reusable HTTP client with retry/backoff for KAP requests."""

    def __init__(self, config: KAPRequestConfig | None = None) -> None:
        self.config = config or KAPRequestConfig()
        self._min_request_interval = self.config.min_request_interval
        self._last_request_at = 0.0
        self.session = requests.Session()
        retry = Retry(
            total=self.config.max_retries,
            connect=self.config.max_retries,
            read=self.config.max_retries,
            status=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://kap.org.tr",
                "Referer": "https://kap.org.tr/tr/",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            }
        )

    def close(self) -> None:
        """Close the underlying session."""
        self.session.close()

    def __enter__(self) -> "KapClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_disclosures(self, payload: dict[str, object]) -> object:
        """Fetch raw disclosure rows for a given query payload."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            response = self.session.post(
                KAP_DISCLOSURE_URL,
                json=payload,
                timeout=self.config.timeout,
            )
            self._last_request_at = time.monotonic()
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        sleep_for = float(retry_after)
                    except ValueError:
                        sleep_for = self.config.backoff_factor * (2**attempt)
                else:
                    sleep_for = self.config.backoff_factor * (2**attempt)
                time.sleep(max(sleep_for, 0.0))
                last_error = requests.HTTPError(
                    f"429 Client Error: Request Limit Exceeded for url: {response.url}",
                    response=response,
                )
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_error = exc
                time.sleep(self.config.backoff_factor * (2**attempt))
                continue

            return response.json()

        if last_error is not None:
            raise last_error
        raise RuntimeError("KAP request failed without a response")
