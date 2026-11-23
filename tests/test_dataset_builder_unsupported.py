from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.datasets.builder import build_bist30_research_dataset


def _make_company_snapshot(symbol: str) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "period": pd.Timestamp("2024-03-31"),
                "net_income": 10,
                "equity": 20,
                "total_assets": 30,
                "cash": 5,
                "total_debt": 7,
                "net_debt": 2,
                "ebit": 9,
                "depreciation": 1,
                "ebitda": 10,
                "operating_cash_flow": 11,
                "free_cash_flow": 12,
                "symbol": symbol,
            }
        ]
    )


class DatasetBuilderUnsupportedTests(unittest.TestCase):
    @patch("src.datasets.builder.Console", None)
    @patch("src.datasets.builder.Live", None)
    @patch("src.datasets.builder.tqdm", new=lambda iterable, **_: iterable)
    @patch("src.datasets.builder.save_dataframe")
    @patch("src.datasets.builder.load_dataframe", return_value=None)
    @patch("src.datasets.builder.load_financials_metadata")
    @patch("src.datasets.builder.build_financial_snapshot")
    def test_unsupported_symbols_are_skipped_and_reported(
        self,
        mock_build_snapshot: MagicMock,
        mock_load_metadata: MagicMock,
        mock_load_dataframe: MagicMock,
        mock_save_dataframe: MagicMock,
    ) -> None:
        def _load_metadata(symbol: str) -> dict[str, object] | None:
            if symbol == "DSTKF":
                return {"isyatirim_unsupported": True, "isyatirim_unsupported_reason": "No statements"}
            return None

        def _build_snapshot(symbol: str, mode: str = "ytd", verbose: bool = False) -> pd.DataFrame:
            self.assertEqual(symbol, "AAA")
            self.assertEqual(mode, "ytd")
            self.assertFalse(verbose)
            return _make_company_snapshot(symbol)

        mock_load_metadata.side_effect = _load_metadata
        mock_build_snapshot.side_effect = _build_snapshot

        report_dates = pd.DataFrame(
            columns=[
                "publish_date",
                "stock_code",
                "year",
                "period",
                "rule_type",
                "disclosure_index",
                "kap_title",
                "summary",
                "subject",
            ]
        )

        snapshots, summary, failed = build_bist30_research_dataset(
            ["AAA", "DSTKF"],
            snapshot_type="ytd",
            report_dates=report_dates,
        )

        self.assertEqual(failed, [])
        self.assertEqual(list(snapshots["symbol"].unique()), ["AAA"])
        self.assertEqual(list(summary["symbol"]), ["AAA", "DSTKF"])
        self.assertEqual(summary.loc[summary["symbol"] == "AAA", "status"].iat[0], "ok")
        self.assertEqual(summary.loc[summary["symbol"] == "DSTKF", "status"].iat[0], "unsupported")
        self.assertIn("No financial statements were returned", summary.loc[summary["symbol"] == "DSTKF", "message"].iat[0])
        mock_build_snapshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
