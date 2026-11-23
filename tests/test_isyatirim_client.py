from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from src.data.isyatirim.client import IsYatirimClient, _chunk_periods, _quarter_periods


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class IsYatirimClientTests(unittest.TestCase):
    def test_chunk_periods_uses_four_period_batches(self) -> None:
        periods = _quarter_periods(2016, 2017)

        batches = _chunk_periods(periods)

        self.assertEqual([len(batch) for batch in batches], [4, 4])
        self.assertEqual(batches[0], [(2016, 3), (2016, 6), (2016, 9), (2016, 12)])
        self.assertEqual(batches[1], [(2017, 3), (2017, 6), (2017, 9), (2017, 12)])

    def test_request_batch_builds_expected_query_params(self) -> None:
        client = IsYatirimClient()
        payload = {
            "ok": True,
            "value": [
                {
                    "itemCode": "3Z",
                    "itemDescTr": "Net income",
                    "itemDescEng": "Net income",
                    "value1": "10",
                    "value2": "20",
                    "value3": "30",
                    "value4": "40",
                }
            ],
        }

        try:
            with patch.object(client.session, "get", return_value=_FakeResponse(payload)) as mock_get:
                frame = client._request_batch(
                    "THYAO",
                    [(2016, 3), (2016, 6), (2016, 9), (2016, 12)],
                    exchange="TRY",
                    financial_group="XI_29",
                )
        finally:
            client.close()

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["year1"], 2016)
        self.assertEqual(kwargs["params"]["period1"], 3)
        self.assertEqual(kwargs["params"]["year4"], 2016)
        self.assertEqual(kwargs["params"]["period4"], 12)
        self.assertEqual(list(frame["period"]), ["2016/3", "2016/6", "2016/9", "2016/12"])

    def test_fetch_normalized_financials_batches_in_groups_of_four(self) -> None:
        client = IsYatirimClient()
        captured_batches: list[list[tuple[int, int]]] = []

        def fake_request_batch(
            symbol: str,
            periods: list[tuple[int, int]] | tuple[tuple[int, int], ...],
            *,
            exchange: str,
            financial_group: str,
            progress: object | None = None,
        ) -> pd.DataFrame:
            del symbol, exchange, financial_group, progress
            batch = list(periods)
            captured_batches.append(batch)
            return pd.DataFrame.from_records(
                [
                    {
                        "symbol": "THYAO",
                        "exchange": "TRY",
                        "financial_group": "XI_29",
                        "itemCode": "3Z",
                        "itemDescTr": "Net income",
                        "itemDescEng": "Net income",
                        "period": f"{year}/{quarter}",
                        "year": year,
                        "quarter": quarter,
                        "value": idx,
                    }
                    for idx, (year, quarter) in enumerate(batch, start=1)
                ]
            )

        try:
            with patch.object(client, "_request_batch", side_effect=fake_request_batch):
                frame = client.fetch_normalized_financials(
                    "THYAO",
                    start_year=2016,
                    end_year=2017,
                    exchange="TRY",
                    financial_group="XI_29",
                )
        finally:
            client.close()

        self.assertEqual(captured_batches, [
            [(2016, 3), (2016, 6), (2016, 9), (2016, 12)],
            [(2017, 3), (2017, 6), (2017, 9), (2017, 12)],
        ])
        self.assertEqual(
            list(frame["period"]),
            ["2016/3", "2016/6", "2016/9", "2016/12", "2017/3", "2017/6", "2017/9", "2017/12"],
        )

    def test_fetch_normalized_financials_parallel_matches_sequential(self) -> None:
        client = IsYatirimClient()

        def fake_request_batch(
            symbol: str,
            periods: list[tuple[int, int]] | tuple[tuple[int, int], ...],
            *,
            exchange: str,
            financial_group: str,
            progress: object | None = None,
        ) -> pd.DataFrame:
            del symbol, exchange, financial_group
            batch = list(periods)
            if progress is not None and getattr(progress, "batch_index", 0) == 1:
                time.sleep(0.05)
            else:
                time.sleep(0.01)
            return pd.DataFrame.from_records(
                [
                    {
                        "symbol": "THYAO",
                        "exchange": "TRY",
                        "financial_group": "XI_29",
                        "itemCode": "3Z",
                        "itemDescTr": "Net income",
                        "itemDescEng": "Net income",
                        "period": f"{year}/{quarter}",
                        "year": year,
                        "quarter": quarter,
                        "value": idx,
                    }
                    for idx, (year, quarter) in enumerate(batch, start=1)
                ]
            )

        try:
            with patch.object(IsYatirimClient, "_request_batch", side_effect=fake_request_batch):
                sequential = client.fetch_normalized_financials(
                    "THYAO",
                    start_year=2015,
                    end_year=2016,
                    exchange="TRY",
                    financial_group="XI_29",
                    max_workers=1,
                )
                parallel = client.fetch_normalized_financials(
                    "THYAO",
                    start_year=2015,
                    end_year=2016,
                    exchange="TRY",
                    financial_group="XI_29",
                    max_workers=2,
                )
        finally:
            client.close()

        assert_frame_equal(sequential, parallel, check_dtype=False)
        self.assertEqual(list(sequential["period"]), list(parallel["period"]))
        self.assertFalse(parallel["period"].duplicated().any())

    def test_fetch_normalized_financials_falls_back_to_sequential_on_parallel_error(self) -> None:
        client = IsYatirimClient()
        fallback_frame = pd.DataFrame.from_records(
            [
                {
                    "symbol": "THYAO",
                    "exchange": "TRY",
                    "financial_group": "XI_29",
                    "itemCode": "3Z",
                    "itemDescTr": "Net income",
                    "itemDescEng": "Net income",
                    "period": "2015/3",
                    "year": 2015,
                    "quarter": 3,
                    "value": 1,
                }
            ]
        )

        def fake_request_batch(
            symbol: str,
            periods: list[tuple[int, int]] | tuple[tuple[int, int], ...],
            *,
            exchange: str,
            financial_group: str,
            progress: object | None = None,
        ) -> pd.DataFrame:
            del symbol, periods, exchange, financial_group, progress
            raise RuntimeError("boom")

        try:
            with patch.object(IsYatirimClient, "_request_batch", side_effect=fake_request_batch):
                with patch.object(
                    client,
                    "_fetch_normalized_financials_sequential",
                    return_value=fallback_frame,
                ) as mock_fallback:
                    frame = client.fetch_normalized_financials(
                        "THYAO",
                        start_year=2015,
                        end_year=2016,
                        exchange="TRY",
                        financial_group="XI_29",
                        max_workers=2,
                    )
        finally:
            client.close()

        mock_fallback.assert_called_once()
        assert_frame_equal(frame, fallback_frame, check_dtype=False)


if __name__ == "__main__":
    unittest.main()
