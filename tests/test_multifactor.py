from __future__ import annotations

import unittest

import pandas as pd

from src.factors.multifactor import (
    build_multifactor_frame,
    get_multifactor_profile_view,
    merge_market_prices_asof,
)


class MultiFactorTests(unittest.TestCase):
    def test_market_date_join_uses_first_trading_day_after_publish_date(self) -> None:
        financial = pd.DataFrame(
            [
                {
                    "symbol": "BIMAS",
                    "period": "2024-03-31",
                    "publish_date": "2024-05-10 18:20:52",
                    "selected_profile": "industrial",
                },
                {
                    "symbol": "BIMAS",
                    "period": "2024-06-30",
                    "publish_date": "2024-08-09 08:05:30",
                    "selected_profile": "industrial",
                },
            ]
        )
        market = pd.DataFrame(
            [
                {"symbol": "BIMAS", "date": "2024-05-10", "pd": 900, "close": 9},
                {"symbol": "BIMAS", "date": "2024-05-13", "pd": 1000, "close": 10},
                {"symbol": "BIMAS", "date": "2024-08-12", "pd": 1200, "close": 12},
            ]
        )

        result = merge_market_prices_asof(financial, market)

        self.assertEqual(result["market_anchor_date"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist(), [
            "2024-05-11 00:00:00",
            "2024-08-10 00:00:00",
        ])
        self.assertEqual(result["market_date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-05-13", "2024-08-12"])
        self.assertEqual(result["pd"].tolist(), [1000, 1200])
        self.assertEqual(result["is_point_in_time_safe"].tolist(), [True, True])

    def test_market_date_join_requires_publish_date(self) -> None:
        financial = pd.DataFrame(
            [{"symbol": "BIMAS", "period": "2024-03-31", "selected_profile": "industrial"}]
        )
        market = pd.DataFrame([{"symbol": "BIMAS", "date": "2024-04-01", "pd": 1000, "close": 10}])

        result = merge_market_prices_asof(financial, market)

        self.assertTrue(pd.isna(result.loc[0, "market_date"]))
        self.assertTrue(pd.isna(result.loc[0, "pd"]))
        self.assertFalse(result.loc[0, "is_point_in_time_safe"])

    def test_classic_profile_multifactors_use_market_cap_and_ev(self) -> None:
        financial = pd.DataFrame(
            [
                {
                    "symbol": "EREGL",
                    "period": "2024-03-31",
                    "publish_date": "2024-05-10",
                    "selected_profile": "industrial",
                    "financial_group": "XI_29",
                    "net_income": 100,
                    "equity": 800,
                    "total_assets": 1500,
                    "net_debt": 200,
                    "ebit": 150,
                    "ebitda": 180,
                    "free_cash_flow": 90,
                    "gross_profit": 300,
                    "current_assets": 600,
                    "current_liabilities": 350,
                    "capex": 40,
                    "ebit_margin": 0.15,
                }
            ]
        )
        market = pd.DataFrame([{"symbol": "EREGL", "date": "2024-05-13", "pd": 1000, "hao_pd": 400, "close": 10}])

        result = build_multifactor_frame(financial, market_prices=market)
        row = result.iloc[0]

        self.assertAlmostEqual(row["enterprise_value"], 1200)
        self.assertAlmostEqual(row["ebit_ev"], 150 / 1200)
        self.assertAlmostEqual(row["ebitda_ev"], 180 / 1200)
        self.assertAlmostEqual(row["fcf_yield"], 90 / 1000)
        self.assertAlmostEqual(row["earnings_yield"], 100 / 1000)
        self.assertAlmostEqual(row["book_to_price"], 800 / 1000)
        self.assertAlmostEqual(row["roic"], 150 / 1000)
        self.assertAlmostEqual(row["gross_profitability"], 300 / 1500)
        self.assertAlmostEqual(row["working_capital"], 250)

    def test_zero_or_negative_denominators_become_nan(self) -> None:
        financial = pd.DataFrame(
            [
                {
                    "symbol": "EREGL",
                    "period": "2024-03-31",
                    "publish_date": "2024-05-10",
                    "selected_profile": "industrial",
                    "net_income": 100,
                    "equity": 800,
                    "net_debt": -200,
                    "ebit": 150,
                    "ebitda": 180,
                    "free_cash_flow": 90,
                }
            ]
        )
        market = pd.DataFrame([{"symbol": "EREGL", "date": "2024-05-13", "pd": 0}])

        result = build_multifactor_frame(financial, market_prices=market)

        self.assertTrue(pd.isna(result.loc[0, "enterprise_value"]))
        self.assertTrue(pd.isna(result.loc[0, "ebit_ev"]))
        self.assertTrue(pd.isna(result.loc[0, "earnings_yield"]))

    def test_bank_profile_view_hides_classic_ev_columns(self) -> None:
        financial = pd.DataFrame(
            [
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "publish_date": "2024-05-10",
                    "selected_profile": "bank",
                    "net_income": 100,
                    "equity": 800,
                }
            ]
        )
        market = pd.DataFrame([{"symbol": "AKBNK", "date": "2024-05-13", "pd": 1000}])

        factors = build_multifactor_frame(financial, market_prices=market)
        view = get_multifactor_profile_view(factors)

        self.assertIn("earnings_yield", view.columns)
        self.assertIn("book_to_price", view.columns)
        self.assertNotIn("ebitda_ev", view.columns)
        self.assertNotIn("fcf_yield", view.columns)


if __name__ == "__main__":
    unittest.main()
