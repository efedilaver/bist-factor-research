import unittest

import numpy as np
import pandas as pd

from src.pit.financials import (
    BASIS_IAS29,
    BASIS_NOMINAL,
    BASIS_TRANSITION,
    BASIS_UNRECOVERABLE,
    _trailing_twelve_months,
    column_price_base,
    period_basis,
)
from src.pit.panel import asof_fundamentals
from src.pit.report_dates import attach_publish_dates, expand_report_dates, normalize_company_name, off_calendar_symbols


def ts(text):
    return pd.Timestamp(text)


class ColumnPriceBaseTest(unittest.TestCase):
    published = {ts(item) for item in ["2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]}

    def test_december_moves_to_latest_report_of_next_year(self):
        self.assertEqual(column_price_base(ts("2024-12-31"), is_flow=False, published_periods=self.published), ts("2025-12-31"))
        self.assertEqual(column_price_base(ts("2025-12-31"), is_flow=True, published_periods=self.published), ts("2026-03-31"))

    def test_interim_balance_sheet_is_never_restated(self):
        self.assertEqual(column_price_base(ts("2025-03-31"), is_flow=False, published_periods=self.published), ts("2025-03-31"))

    def test_interim_flow_moves_only_after_next_year_report(self):
        self.assertEqual(column_price_base(ts("2025-03-31"), is_flow=True, published_periods=self.published), ts("2026-03-31"))
        self.assertEqual(column_price_base(ts("2025-06-30"), is_flow=True, published_periods=self.published), ts("2025-06-30"))

    def test_periods_before_inflation_accounting_are_untouched(self):
        self.assertEqual(column_price_base(ts("2022-09-30"), is_flow=True, published_periods=self.published), ts("2022-09-30"))


class PeriodBasisTest(unittest.TestCase):
    def test_basis_classification(self):
        self.assertEqual(period_basis(ts("2022-09-30"), is_ias29=True), BASIS_NOMINAL)
        self.assertEqual(period_basis(ts("2022-12-31"), is_ias29=True), BASIS_UNRECOVERABLE)
        self.assertEqual(period_basis(ts("2023-06-30"), is_ias29=True), BASIS_TRANSITION)
        self.assertEqual(period_basis(ts("2023-12-31"), is_ias29=True), BASIS_IAS29)
        self.assertEqual(period_basis(ts("2025-12-31"), is_ias29=False), BASIS_NOMINAL)


class TrailingTwelveMonthsTest(unittest.TestCase):
    def test_uses_year_end_and_prior_ytd(self):
        values = pd.Series(
            [10.0, 40.0, 15.0],
            index=[ts("2023-03-31"), ts("2023-12-31"), ts("2024-03-31")],
        )
        result = _trailing_twelve_months(values)
        self.assertEqual(result[ts("2024-03-31")], 45.0)
        self.assertEqual(result[ts("2023-12-31")], 40.0)
        self.assertTrue(np.isnan(result[ts("2023-03-31")]))

    def test_partial_history_stays_missing(self):
        values = pd.Series([15.0], index=[ts("2024-03-31")])
        self.assertTrue(_trailing_twelve_months(values).isna().all())


class ReportDateTest(unittest.TestCase):
    def test_company_name_spelling_is_normalized(self):
        self.assertEqual(normalize_company_name("Türkiye Şişe A.Ş."), normalize_company_name("TÜRKİYE ŞİŞE A.Ş"))

    def test_kap_code_maps_to_all_tickers_of_a_company(self):
        tickers = pd.DataFrame(
            {"ticker": ["KRDMA", "KRDMD"], "company_key": [normalize_company_name("Kardemir A.Ş.")] * 2}
        )
        dates = pd.DataFrame(
            {
                "stock_code": ["KRDMA"],
                "kap_title": ["KARDEMİR A.Ş."],
                "year": [2024],
                "period": [1],
                "publish_date": [ts("2024-05-10")],
            }
        )
        expanded = expand_report_dates(dates, tickers)
        self.assertEqual(sorted(expanded["ticker"]), ["KRDMA", "KRDMD"])

    def test_missing_publish_date_uses_conservative_estimate(self):
        pit = pd.DataFrame({"symbol": ["A", "B", "C"], "period": [ts("2024-03-31")] * 3})
        expanded = pd.DataFrame(
            {
                "ticker": ["A", "B"],
                "period_end": [ts("2024-03-31")] * 2,
                "publish_date": [ts("2024-05-01"), ts("2024-06-10")],
            }
        )
        result = attach_publish_dates(pit, expanded).set_index("symbol")
        self.assertEqual(result.loc["C", "publish_date_source"], "estimated_p95")
        self.assertGreater(result.loc["C", "publish_date"], ts("2024-06-01"))


class EstimateLagTest(unittest.TestCase):
    def test_period_with_few_late_filers_uses_the_same_quarter_of_other_years(self):
        tickers = [f"T{i}" for i in range(40)]
        frames = [
            pd.DataFrame({"symbol": tickers, "period": ts("2017-03-31")}),
            pd.DataFrame({"symbol": ["X", "Y", "Z"], "period": ts("2016-03-31")}),
        ]
        expanded = pd.concat(
            [
                pd.DataFrame({"ticker": tickers, "period_end": ts("2017-03-31"), "publish_date": ts("2017-05-10")}),
                pd.DataFrame({"ticker": ["X", "Y"], "period_end": ts("2016-03-31"), "publish_date": ts("2018-04-24")}),
            ]
        )
        result = attach_publish_dates(pd.concat(frames, ignore_index=True), expanded)
        estimate = result.loc[result["symbol"].eq("Z"), "publish_date"].iloc[0]
        self.assertEqual(estimate, ts("2016-03-31") + pd.Timedelta(days=40))

    def test_long_median_lag_marks_off_calendar_fiscal_year(self):
        expanded = pd.DataFrame(
            {
                "ticker": ["A", "A", "B", "B"],
                "period_end": [ts("2024-03-31"), ts("2024-06-30")] * 2,
                "publish_date": [ts("2024-05-01"), ts("2024-08-01"), ts("2024-10-20"), ts("2025-01-20")],
            }
        )
        self.assertEqual(off_calendar_symbols(expanded), {"B"})


class AsofTest(unittest.TestCase):
    def setUp(self):
        self.cpi = pd.Series(
            [100.0, 110.0, 120.0],
            index=[ts("2024-03-31"), ts("2024-04-30"), ts("2024-05-31")],
        )
        self.frame = pd.DataFrame(
            {
                "symbol": ["A", "A"],
                "period": [ts("2023-12-31"), ts("2024-03-31")],
                "publish_date": [ts("2024-03-01"), ts("2024-05-31 18:00")],
                "pit_basis": [BASIS_IAS29, BASIS_IAS29],
                "equity": [100.0, 200.0],
            }
        )

    def test_statement_published_on_signal_date_is_not_visible(self):
        result = asof_fundamentals(self.frame.iloc[[1]], ts("2024-05-31"), cpi=self.cpi)
        self.assertTrue(result.empty)

    def test_values_are_indexed_with_last_known_cpi(self):
        result = asof_fundamentals(self.frame, ts("2024-06-03"), cpi=self.cpi)
        self.assertAlmostEqual(result.loc["A", "equity"], 200.0 * 120.0 / 100.0)

    def test_stale_statement_is_dropped(self):
        result = asof_fundamentals(self.frame.iloc[[0]], ts("2025-01-31"), cpi=self.cpi)
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
