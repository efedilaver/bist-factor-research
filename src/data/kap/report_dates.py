"""Build and load KAP report publication dates."""

from __future__ import annotations

from typing import Final
import time

import pandas as pd
import requests

from .cache import load_report_dates_from_cache
from .cache import save_report_dates
from .client import KapClient, KAPRequestConfig
from .parser import REPORT_DATE_COLUMNS, parse_kap_disclosures
from src.utils.symbols import canonical_symbol

KAP_MAX_ATTEMPTS: Final[int] = 3
KAP_BACKOFF_SECONDS: Final[float] = 1.0
KAP_REQUEST_PAUSE_SECONDS: Final[float] = 0.5
KAP_SUBJECT_OID_LIST: Final[list[str]] = ["4028328c594bfdca01594c0af9aa0057"]
KAP_MEMBER_TYPE: Final[str] = "IGS"
KAP_DISCLOSURE_CLASS: Final[str] = "FR"
HALF_YEAR_RANGES: Final[tuple[tuple[str, str], ...]] = (("01-01", "06-30"), ("07-01", "12-31"))
FINANCIAL_SUBJECTS: Final[set[str]] = {"Finansal Rapor", "Finansal Rapor Bildirimi"}


def _build_payload(
    start_date: str,
    end_date: str,
    *,
    market_oid: str = "",
    member_oids: list[str] | None = None,
) -> dict[str, object]:
    """Serialize the KAP request payload for a date window."""
    return {
        "fromDate": start_date,
        "toDate": end_date,
        "memberType": KAP_MEMBER_TYPE,
        "mkkMemberOidList": member_oids or [],
        "inactiveMkkMemberOidList": [],
        "disclosureClass": KAP_DISCLOSURE_CLASS,
        "subjectList": KAP_SUBJECT_OID_LIST,
        "isLate": "",
        "mainSector": "",
        "sector": "",
        "subSector": "",
        "marketOid": market_oid,
        "index": "",
        "bdkReview": "",
        "bdkMemberOidList": [],
        "year": "",
        "term": "",
        "ruleType": "",
        "period": "",
        "fromSrc": False,
        "srcCategory": "",
        "disclosureIndexList": [],
    }


def _fetch_window(
    client: KapClient,
    *,
    start_date: str,
    end_date: str,
    market_oid: str = "",
    member_oids: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch one date window and normalize it."""
    last_error: Exception | None = None
    for attempt in range(KAP_MAX_ATTEMPTS):
        try:
            payload = _build_payload(
                start_date=start_date,
                end_date=end_date,
                market_oid=market_oid,
                member_oids=member_oids,
            )
            rows = client.fetch_disclosures(payload)
            frame = parse_kap_disclosures(rows)
            return frame
        except (requests.RequestException, ValueError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt < KAP_MAX_ATTEMPTS - 1:
                time.sleep(KAP_BACKOFF_SECONDS * (2**attempt))
            continue
    if last_error is not None:
        raise RuntimeError(f"Failed to fetch KAP report dates for {start_date} to {end_date}: {last_error}")
    return pd.DataFrame(columns=REPORT_DATE_COLUMNS)


def _finalize_report_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize the final report-date table for downstream joins."""
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=REPORT_DATE_COLUMNS)

    result = result.loc[result["subject"].isin(FINANCIAL_SUBJECTS)].copy()

    result["publish_date"] = pd.to_datetime(result["publish_date"], errors="coerce")
    result["stock_code"] = result["stock_code"].map(canonical_symbol)
    result["year"] = pd.array(pd.to_numeric(result["year"], errors="coerce"), dtype="Int64")
    result["period"] = pd.array(pd.to_numeric(result["period"], errors="coerce"), dtype="Int64")
    result["disclosure_index"] = pd.array(pd.to_numeric(result["disclosure_index"], errors="coerce"), dtype="Int64")
    result = result.dropna(subset=["disclosure_index", "stock_code", "publish_date"])
    result = result.sort_values("publish_date", kind="mergesort").drop_duplicates(
        subset=["disclosure_index"],
        keep="last",
    )
    result = result.sort_values("publish_date", kind="mergesort").reset_index(drop=True)
    return result[REPORT_DATE_COLUMNS]


def build_report_dates(
    start_year: int,
    end_year: int,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Build and cache the report-date table from KAP disclosures."""
    if not overwrite:
        try:
            return load_report_dates()
        except FileNotFoundError:
            pass

    if end_year < start_year:
        raise ValueError("end_year must be greater than or equal to start_year")

    frames: list[pd.DataFrame] = []
    client_config = KAPRequestConfig(min_request_interval=1.0)
    with KapClient(client_config) as client:
        for year in range(start_year, end_year + 1):
            for start_suffix, end_suffix in HALF_YEAR_RANGES:
                start_date = f"{year}-{start_suffix}"
                end_date = f"{year}-{end_suffix}"
                frame = _fetch_window(
                    client,
                    start_date=start_date,
                    end_date=end_date,
                )
                if not frame.empty:
                    frames.append(frame)
                time.sleep(KAP_REQUEST_PAUSE_SECONDS)

    if not frames:
        result = pd.DataFrame(columns=REPORT_DATE_COLUMNS)
    else:
        result = pd.concat(frames, ignore_index=True)
    result = _finalize_report_dates(result)
    save_report_dates(result)
    return result


def load_report_dates() -> pd.DataFrame:
    """Load cached report dates."""
    frame = load_report_dates_from_cache()
    if frame.empty:
        return pd.DataFrame(columns=REPORT_DATE_COLUMNS)

    result = frame.copy()
    result["publish_date"] = pd.to_datetime(result["publish_date"], errors="coerce")
    result["stock_code"] = result["stock_code"].map(canonical_symbol)
    result["year"] = pd.array(pd.to_numeric(result["year"], errors="coerce"), dtype="Int64")
    result["period"] = pd.array(pd.to_numeric(result["period"], errors="coerce"), dtype="Int64")
    result["disclosure_index"] = pd.array(pd.to_numeric(result["disclosure_index"], errors="coerce"), dtype="Int64")
    return result[REPORT_DATE_COLUMNS]
