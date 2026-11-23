from __future__ import annotations

import unittest

import pandas as pd

from src.factors import add_forward_returns, forward_return_columns


class ForwardReturnTests(unittest.TestCase):
    def test_add_forward_returns_uses_first_trading_day_on_or_after_target(self) -> None:
        factors = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "market_date": "2024-05-10",
                    "close": 10.0,
                }
            ]
        )
        prices = pd.DataFrame(
            [
                {"symbol": "AAA", "date": "2024-05-10", "close": 10.0},
                {"symbol": "AAA", "date": "2024-06-11", "close": 11.0},
                {"symbol": "AAA", "date": "2024-06-12", "close": 12.0},
            ]
        )

        result = add_forward_returns(factors, horizons=("1M",), market_prices=prices)

        self.assertEqual(result.loc[0, "forward_return_1m_exit_date"], pd.Timestamp("2024-06-11"))
        self.assertAlmostEqual(result.loc[0, "forward_return_1m"], 0.10)

    def test_add_forward_returns_supports_day_horizons(self) -> None:
        factors = pd.DataFrame(
            [{"symbol": "AAA", "period": "2024-03-31", "market_date": "2024-05-10", "close": 10.0}]
        )
        prices = pd.DataFrame(
            [
                {"symbol": "AAA", "date": "2024-05-10", "close": 10.0},
                {"symbol": "AAA", "date": "2024-05-15", "close": 15.0},
            ]
        )

        result = add_forward_returns(factors, horizons=("5D",), market_prices=prices)

        self.assertEqual(result.loc[0, "forward_return_5d_exit_date"], pd.Timestamp("2024-05-15"))
        self.assertAlmostEqual(result.loc[0, "forward_return_5d"], 0.50)

    def test_add_forward_returns_leaves_missing_exit_as_nan(self) -> None:
        factors = pd.DataFrame(
            [{"symbol": "AAA", "period": "2024-03-31", "market_date": "2024-05-10", "close": 10.0}]
        )
        prices = pd.DataFrame([{"symbol": "AAA", "date": "2024-05-10", "close": 10.0}])

        result = add_forward_returns(factors, horizons=("1M",), market_prices=prices)

        self.assertTrue(pd.isna(result.loc[0, "forward_return_1m_exit_date"]))
        self.assertTrue(pd.isna(result.loc[0, "forward_return_1m"]))

    def test_forward_return_columns_normalizes_horizons(self) -> None:
        self.assertEqual(forward_return_columns(("1M", "20D")), ["forward_return_1m", "forward_return_20d"])


if __name__ == "__main__":
    unittest.main()
