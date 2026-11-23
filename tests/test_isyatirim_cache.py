from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from pandas.testing import assert_frame_equal

from src.data.isyatirim.cache import clear_financials_cache, load_financials_cache, save_financials_cache
from src.data.isyatirim.fetch import fetch_financials


def _make_cached_frame() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "FINANCIAL_ITEM_CODE": "3Z",
                "SYMBOL": "THYAO",
                "itemCode": "3Z",
                "itemDescTr": "Net income",
                "itemDescEng": "Net income",
                "2015/3": 10,
                "2015/6": 20,
            }
        ]
    )


class IsYatirimCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_financials_cache()

    def tearDown(self) -> None:
        clear_financials_cache()

    def test_memory_cache_avoids_re_reading_parquet(self) -> None:
        frame = _make_cached_frame()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "THYAO.parquet"
            with patch("src.data.isyatirim.cache.financials_cache_path", return_value=cache_path):
                save_financials_cache("THYAO", frame)
                clear_financials_cache("THYAO")

                real_read_parquet = pd.read_parquet
                with patch("pandas.read_parquet", wraps=real_read_parquet) as mock_read_parquet:
                    first = load_financials_cache("THYAO")
                    second = load_financials_cache("THYAO")

            assert first is not None
            assert second is not None
            assert_frame_equal(first, frame)
            assert_frame_equal(second, frame)
            self.assertEqual(mock_read_parquet.call_count, 1)

    @patch("src.data.isyatirim.fetch.save_financials_cache")
    @patch("src.data.isyatirim.fetch.IsYatirimClient")
    def test_fetch_financials_uses_cached_dataframe_when_present(
        self,
        mock_client: MagicMock,
        mock_save_cache: MagicMock,
    ) -> None:
        cached = _make_cached_frame()

        with patch("src.data.isyatirim.fetch.load_financials_cache", return_value=cached):
            result = fetch_financials("THYAO", 2015, 2026)

        assert_frame_equal(result, cached)
        mock_client.assert_not_called()
        mock_save_cache.assert_not_called()

    @patch("src.data.isyatirim.fetch.save_financials_cache")
    @patch("src.data.isyatirim.fetch.load_financials_cache")
    @patch("src.data.isyatirim.fetch.IsYatirimClient")
    def test_fetch_financials_overwrite_refreshes_cache(
        self,
        mock_client: MagicMock,
        mock_load_cache: MagicMock,
        mock_save_cache: MagicMock,
    ) -> None:
        mock_load_cache.return_value = _make_cached_frame()

        normalized = pd.DataFrame.from_records(
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
                    "value": 10,
                }
            ]
        )

        fake_client = MagicMock()
        fake_client.fetch_normalized_financials.return_value = normalized
        mock_client.return_value.__enter__.return_value = fake_client

        result = fetch_financials("THYAO", 2015, 2026, overwrite=True)

        expected = pd.DataFrame.from_records(
            [
                {
                    "FINANCIAL_ITEM_CODE": "3Z",
                    "SYMBOL": "THYAO",
                    "itemCode": "3Z",
                    "itemDescTr": "Net income",
                    "itemDescEng": "Net income",
                    "2015/3": 10,
                }
            ]
        )

        assert_frame_equal(result, expected)
        mock_load_cache.assert_not_called()
        fake_client.fetch_normalized_financials.assert_called_once()
        mock_save_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
