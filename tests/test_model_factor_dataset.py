from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.factors import build_model_factor_dataset


def _raw_financials(symbol: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {"symbol": symbol, "itemCode": "1BL", "FINANCIAL_ITEM_CODE": "1BL", "2024/3": 220},
            {"symbol": symbol, "itemCode": "3DF", "FINANCIAL_ITEM_CODE": "3DF", "2024/3": 8},
            {"symbol": symbol, "itemCode": "4CAB", "FINANCIAL_ITEM_CODE": "4CAB", "2024/3": 2},
            {"symbol": symbol, "itemCode": "4C", "FINANCIAL_ITEM_CODE": "4C", "2024/3": 5},
            {"symbol": symbol, "itemCode": "4CB", "FINANCIAL_ITEM_CODE": "4CB", "2024/3": 3},
        ]
    )
    frame.attrs["isyatirim_selected_financial_group"] = "XI_29"
    return frame


def _snapshot(symbol: str) -> pd.DataFrame:
    debt_offset = 20 if symbol == "EREGL" else 0
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "period": pd.Timestamp("2024-03-31"),
                "sector": "SANAYI",
                "sub_sector": "PERAKENDE" if symbol == "BIMAS" else "CELIK",
                "net_income": 10,
                "equity": 100,
                "total_assets": 220,
                "cash": 40,
                "total_debt": 30 + debt_offset,
                "net_debt": 10 + debt_offset,
                "ebit": 8,
                "depreciation": 2,
                "ebitda": 10,
                "operating_cash_flow": 5,
                "free_cash_flow": 3,
            }
        ]
    )


class ModelFactorDatasetTests(unittest.TestCase):
    @patch("src.factors.model.load_report_dates")
    @patch("src.factors.model.build_financial_snapshot")
    @patch("src.factors.model.fetch_financials")
    def test_build_model_factor_dataset_returns_point_in_time_scores(
        self,
        mock_fetch: object,
        mock_snapshot: object,
        mock_report_dates: object,
    ) -> None:
        mock_fetch.side_effect = lambda symbol, **_: _raw_financials(symbol)
        mock_snapshot.side_effect = lambda symbol, **_: _snapshot(symbol)
        mock_report_dates.return_value = pd.DataFrame(
            [
                {"stock_code": "BIMAS", "year": 2024, "period": 1, "publish_date": pd.Timestamp("2024-05-10")},
                {"stock_code": "EREGL", "year": 2024, "period": 1, "publish_date": pd.Timestamp("2024-05-10")},
            ]
        )
        market = pd.DataFrame(
            [
                {"symbol": "BIMAS", "date": "2024-05-13", "pd": 1000},
                {"symbol": "EREGL", "date": "2024-05-13", "pd": 2000},
            ]
        )

        result = build_model_factor_dataset(["BIMAS", "EREGL"], market_prices=market)

        self.assertEqual(len(result), 2)
        self.assertTrue(result["is_point_in_time_safe"].all())
        self.assertEqual(result["selected_profile"].tolist(), ["industrial", "industrial"])
        self.assertEqual(result["financial_group"].tolist(), ["XI_29", "XI_29"])
        self.assertEqual(result["market_date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-05-13", "2024-05-13"])
        self.assertFalse(result["value_score"].isna().any())
        self.assertFalse(result["leverage_score"].isna().any())

    @patch("src.factors.model.load_report_dates")
    @patch("src.factors.model.build_financial_snapshot")
    @patch("src.factors.model.fetch_financials")
    def test_build_model_factor_dataset_filters_unsafe_rows_by_default(
        self,
        mock_fetch: object,
        mock_snapshot: object,
        mock_report_dates: object,
    ) -> None:
        mock_fetch.return_value = _raw_financials("BIMAS")
        mock_snapshot.return_value = _snapshot("BIMAS")
        mock_report_dates.return_value = pd.DataFrame()
        market = pd.DataFrame([{"symbol": "BIMAS", "date": "2024-05-13", "pd": 1000}])

        filtered = build_model_factor_dataset(["BIMAS"], market_prices=market)
        debug = build_model_factor_dataset(["BIMAS"], market_prices=market, include_unsafe=True)

        self.assertTrue(filtered.empty)
        self.assertEqual(len(debug), 1)
        self.assertFalse(debug.loc[0, "is_point_in_time_safe"])

    @patch("src.factors.model.load_report_dates")
    @patch("src.factors.model.build_financial_snapshot")
    @patch("src.factors.model.fetch_financials")
    def test_build_model_factor_dataset_supports_adaptive_sector_scoring(
        self,
        mock_fetch: object,
        mock_snapshot: object,
        mock_report_dates: object,
    ) -> None:
        mock_fetch.side_effect = lambda symbol, **_: _raw_financials(symbol)
        mock_snapshot.side_effect = lambda symbol, **_: _snapshot(symbol)
        mock_report_dates.return_value = pd.DataFrame(
            [
                {"stock_code": "BIMAS", "year": 2024, "period": 1, "publish_date": pd.Timestamp("2024-05-10")},
                {"stock_code": "EREGL", "year": 2024, "period": 1, "publish_date": pd.Timestamp("2024-05-10")},
            ]
        )
        market = pd.DataFrame(
            [
                {"symbol": "BIMAS", "date": "2024-05-13", "pd": 1000},
                {"symbol": "EREGL", "date": "2024-05-13", "pd": 2000},
            ]
        )

        result = build_model_factor_dataset(
            ["BIMAS", "EREGL"],
            market_prices=market,
            scoring="adaptive_sector",
            min_sector_group_size=2,
        )

        self.assertEqual(len(result), 2)
        self.assertFalse(result["value_score"].isna().any())


if __name__ == "__main__":
    unittest.main()
