import unittest

import numpy as np
import pandas as pd

from src.pit.panel import asof_fundamentals, build_monthly_panel, drop_untraded_rows
from src.pit.portfolio import ModelConfig, _select_holdings, add_signals, block_bootstrap_interval, newey_west_t, select_universe, simulate


def ts(text):
    return pd.Timestamp(text)


def _prices(symbols=("A", "B"), periods=320, growth=None):
    dates = pd.bdate_range("2016-01-04", periods=periods)
    frames = []
    for offset, symbol in enumerate(symbols):
        rate = (growth or {}).get(symbol, 0.001 * (offset + 1))
        close = 10.0 * (1 + rate) ** np.arange(periods)
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "date": dates,
                    "close": close,
                    "dolar_hacim": 2e6,
                    "pd": 1e9,
                    "pd_usd": 3e8,
                    "dd_deger": 3.0,
                    "end_deger": 1000.0,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _empty_fundamentals():
    return pd.DataFrame({"symbol": pd.Series(dtype=str), "period": pd.Series(dtype="datetime64[ns]"), "publish_date": pd.Series(dtype="datetime64[ns]")})


def _panel(prices, fundamentals=None):
    return build_monthly_panel(
        prices,
        _empty_fundamentals() if fundamentals is None else fundamentals,
        cpi=pd.Series([100.0], index=[ts("2015-12-31")]),
        company_keys=pd.Series(dtype=str),
        sectors=pd.Series(dtype=str),
    )[0]


class UntradedRowsTest(unittest.TestCase):
    def test_zero_volume_rows_and_rows_after_last_trade_are_removed(self):
        frame = pd.DataFrame(
            {
                "symbol": ["A", "A", "A", "B"],
                "date": [ts("2020-01-01"), ts("2020-01-02"), ts("2020-01-03"), ts("2020-01-03")],
                "close": [1.0, 1.0, 1.0, 0.0],
                "dolar_hacim": [5.0, 0.0, 5.0, 5.0],
            }
        )
        result = drop_untraded_rows(frame, pd.Series({"A": ts("2020-01-02")}))
        self.assertEqual(result["date"].tolist(), [ts("2020-01-01")])


class PanelTimingTest(unittest.TestCase):
    def test_forward_return_runs_from_next_close_to_next_rebalance(self):
        prices = _prices()
        panel = _panel(prices)
        row = panel.loc[panel["ticker"].eq("A")].sort_values("signal_date").iloc[0]
        following = panel.loc[panel["ticker"].eq("A")].sort_values("signal_date").iloc[1]
        close = prices.loc[prices["symbol"].eq("A")].set_index("date")["close"]
        expected = close[following["entry_date"]] / close[row["entry_date"]] - 1
        self.assertAlmostEqual(row["forward_return"], expected)
        self.assertGreater(row["entry_date"], row["signal_date"])

    def test_changing_the_future_does_not_change_signals(self):
        prices = _prices()
        cutoff = ts("2016-11-30")
        base = _panel(prices)
        altered = prices.copy()
        altered.loc[altered["date"] > cutoff + pd.Timedelta(days=5), "close"] *= 3.0
        altered.loc[altered["date"] > cutoff + pd.Timedelta(days=5), "dolar_hacim"] *= 7.0
        changed = _panel(altered)
        date = base.loc[base["signal_date"] <= cutoff, "signal_date"].max()
        columns = ["momentum", "one_month", "volatility", "max_return", "adv_usd"]
        pd.testing.assert_frame_equal(
            base.loc[base["signal_date"].eq(date), columns].reset_index(drop=True),
            changed.loc[changed["signal_date"].eq(date), columns].reset_index(drop=True),
        )

    def test_statement_is_invisible_until_after_publication(self):
        prices = _prices(("A",))
        panel_dates = _panel(prices)["signal_date"].drop_duplicates().sort_values()
        signal = panel_dates.iloc[3]
        fundamentals = pd.DataFrame(
            {
                "symbol": ["A"],
                "period": [signal - pd.DateOffset(months=2)],
                "publish_date": [signal],
                "equity": [50.0],
            }
        )
        panel = _panel(prices, fundamentals).set_index("signal_date")
        self.assertTrue(np.isnan(panel.loc[signal, "equity"]))
        self.assertEqual(panel.loc[panel_dates.iloc[4], "equity"], 50.0)

    def test_stock_that_stops_trading_exits_at_last_price_and_is_flagged(self):
        prices = _prices()
        stop = ts("2016-12-15")
        prices = prices.loc[~(prices["symbol"].eq("A") & (prices["date"] > stop))]
        panel = _panel(prices)
        rows = panel.loc[panel["ticker"].eq("A") & panel["traded_at_entry"]].sort_values("signal_date")
        last = rows.iloc[-1]
        self.assertTrue(last["ended_in_window"])
        close = prices.loc[prices["symbol"].eq("A")].set_index("date")["close"]
        self.assertAlmostEqual(last["forward_return"], close.iloc[-1] / close[last["entry_date"]] - 1)


def _universe(count=20, *, date="2020-01-31"):
    return pd.DataFrame(
        {
            "signal_date": ts(date),
            "ticker": [f"T{i:02d}" for i in range(count)],
            "company_key": [f"c{i}" for i in range(count)],
            "sector": ["s1"] * count,
            "score": np.arange(count, 0, -1, dtype=float),
            "risk_excluded": False,
            "quality_excluded": False,
            "entry_limit_up": False,
            "traded_at_entry": True,
            "trades_later": True,
            "forward_return": 0.0,
            "ended_in_window": False,
            "market_cap_usd": 1e9,
        }
    )


class StatementSelectionTest(unittest.TestCase):
    def test_late_filing_of_an_old_period_does_not_replace_a_newer_statement(self):
        frame = pd.DataFrame(
            {
                "symbol": ["A", "A"],
                "period": [ts("2016-03-31"), ts("2017-12-31")],
                "publish_date": [ts("2018-04-20"), ts("2018-03-01")],
                "equity": [1.0, 2.0],
            }
        )
        result = asof_fundamentals(frame, ts("2018-04-30"), cpi=pd.Series([100.0], index=[ts("2015-12-31")]))
        self.assertEqual(result.loc["A", "equity"], 2.0)


class HoldingsTest(unittest.TestCase):
    def test_sector_cap_limits_a_single_sector(self):
        group = _universe(50)
        group.loc[group.index[25:], "sector"] = [f"x{i}" for i in range(25)]
        config = ModelConfig(score="score")
        selected = _select_holdings(group, "score", {}, config)
        self.assertEqual(len(selected), 10)
        self.assertLessEqual(sum(ticker < "T25" for ticker in selected), 3)

    def test_excluded_names_are_not_bought(self):
        group = _universe(50)
        group.loc[group.index[0], "risk_excluded"] = True
        group.loc[group.index[1], "quality_excluded"] = True
        group["sector"] = [f"x{i}" for i in range(50)]
        selected = _select_holdings(group, "score", {}, ModelConfig(score="score"))
        self.assertNotIn("T00", selected)
        self.assertNotIn("T01", selected)

    def test_hold_buffer_keeps_a_name_that_slipped_into_the_zone(self):
        group = _universe(50)
        group["sector"] = [f"x{i}" for i in range(50)]
        selected = _select_holdings(group, "score", {"T15": 0.1}, ModelConfig(score="score"))
        self.assertIn("T15", selected)
        dropped = _select_holdings(group, "score", {"T30": 0.1}, ModelConfig(score="score"))
        self.assertNotIn("T30", dropped)


class SimulationTest(unittest.TestCase):
    def test_first_month_pays_full_one_way_cost_on_entry(self):
        universe = _universe(50)
        universe["sector"] = [f"x{i}" for i in range(50)]
        result = simulate(universe, ModelConfig(score="score", one_way_cost=0.01)).iloc[0]
        self.assertAlmostEqual(result["cost"], 0.01)
        self.assertAlmostEqual(result["portfolio_net"], -0.01)

    def test_delisting_penalty_applies_only_to_flagged_names(self):
        universe = _universe(50)
        universe["sector"] = [f"x{i}" for i in range(50)]
        universe.loc[universe["ticker"].eq("T00"), "ended_in_window"] = True
        result = simulate(universe, ModelConfig(score="score", one_way_cost=0.0, delisting_penalty=1.0)).iloc[0]
        self.assertAlmostEqual(result["portfolio_gross"], -1.0 / 10)
        self.assertAlmostEqual(result["equal_weight"], -1.0 / 50)


class AbstainTest(unittest.TestCase):
    def _thin(self):
        universe = _universe(50)
        universe["sector"] = [f"x{i}" for i in range(50)]
        universe.loc[universe.index[5:], "score"] = np.nan
        universe["momentum_score"] = np.arange(50, 0, -1, dtype=float)
        return universe

    def test_thin_coverage_holds_the_equal_weight_universe(self):
        result = simulate(self._thin(), ModelConfig(score="score", one_way_cost=0.0)).iloc[0]
        self.assertTrue(result["abstained"])
        self.assertEqual(result["holdings"], 50)

    def test_thin_coverage_can_fall_back_to_another_score(self):
        config = ModelConfig(score="score", one_way_cost=0.0, fallback_score="momentum_score")
        result = simulate(self._thin(), config).iloc[0]
        self.assertFalse(result["abstained"])
        self.assertEqual(result["holdings"], 10)

    def test_book_below_the_minimum_is_not_held(self):
        universe = _universe(50)
        result = simulate(universe, ModelConfig(score="score", one_way_cost=0.0)).iloc[0]
        self.assertTrue(result["abstained"])


class HaltTest(unittest.TestCase):
    def test_halted_position_cannot_be_sold_and_keeps_its_return(self):
        first = _universe(50, date="2020-01-31")
        first["sector"] = [f"x{i}" for i in range(50)]
        second = first.assign(signal_date=ts("2020-02-28"))
        second["score"] = np.arange(1, 51, dtype=float)
        second = second.loc[~second["ticker"].eq("T00")]
        panel = pd.DataFrame(
            {
                "signal_date": [ts("2020-02-28")],
                "ticker": ["T00"],
                "traded_at_entry": [False],
                "trades_later": [True],
                "forward_return": [-0.5],
            }
        )
        result = simulate(pd.concat([first, second]), ModelConfig(score="score", one_way_cost=0.0), panel=panel).iloc[1]
        self.assertIn("T00", result["tickers"].split(","))
        self.assertAlmostEqual(result["portfolio_gross"], 0.1 * -0.5)

    def test_name_not_trading_on_entry_is_not_bought(self):
        group = _universe(50)
        group["sector"] = [f"x{i}" for i in range(50)]
        group.loc[group["ticker"].eq("T00"), "traded_at_entry"] = False
        self.assertNotIn("T00", _select_holdings(group, "score", {}, ModelConfig(score="score")))


class UniverseTest(unittest.TestCase):
    def test_keeps_most_liquid_share_class_and_applies_limits(self):
        panel = pd.DataFrame(
            {
                "signal_date": ts("2020-01-31"),
                "ticker": ["A1", "A2", "B", "C"],
                "company_key": ["a", "a", "b", "c"],
                "adv_usd": [5e6, 9e6, 2e6, 5e5],
                "market_cap_usd": [1e9, 1e9, 1e9, 1e9],
                "recent_trades": 5,
                "momentum": 0.1,
                "volatility": 0.02,
                "forward_return": 0.0,
            }
        )
        result = select_universe(panel, ModelConfig(top_n_liquidity=10))
        self.assertEqual(result["ticker"].tolist(), ["A2", "B"])


class SignalTest(unittest.TestCase):
    def test_negative_enterprise_value_gives_no_ebit_yield(self):
        frame = pd.DataFrame(
            {
                "signal_date": ts("2020-01-31"),
                "sector": ["s"] * 6,
                "net_income": [1.0] * 6,
                "market_cap": [10.0] * 6,
                "equity": [5.0] * 6,
                "net_debt": [-20.0, 1, 2, 3, 4, 5],
                "ebit": [2.0] * 6,
                "operating_cash_flow": [1.0] * 6,
                "total_assets": [20.0] * 6,
                "momentum": [0.1] * 6,
                "volatility": [0.02] * 6,
                "max_return": [0.03] * 6,
                "one_month": [0.0] * 6,
            }
        )
        self.assertTrue(np.isnan(add_signals(frame).loc[0, "ebit_ev"]))


class StatisticsTest(unittest.TestCase):
    def test_newey_west_matches_plain_t_without_lags(self):
        series = pd.Series([0.01, 0.03, -0.02, 0.04, 0.0, 0.02, 0.01, -0.01])
        expected = series.mean() / (series.std(ddof=0) / len(series) ** 0.5)
        self.assertAlmostEqual(newey_west_t(series, lags=0), expected)

    def test_bootstrap_interval_contains_the_annualized_mean(self):
        series = pd.Series(np.random.default_rng(1).normal(0.01, 0.02, 200))
        low, high = block_bootstrap_interval(series, draws=500)
        self.assertLess(low, series.mean() * 12)
        self.assertGreater(high, series.mean() * 12)


if __name__ == "__main__":
    unittest.main()
