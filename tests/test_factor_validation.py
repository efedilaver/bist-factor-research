from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.factors import (
    add_quality_component_scores,
    apply_quality_economic_validity_rules,
    build_direction_audit,
    build_hygiene_report,
    build_validation_reports,
    calculate_value_ic_by_quality_bucket,
    calculate_quantile_portfolios,
    evaluate_quality_components,
    summarize_value_ic_by_quality_bucket,
    summarize_quantile_portfolios,
    winsorize_metrics,
)


class FactorValidationTests(unittest.TestCase):
    def _base_frame(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        periods = (
            "2023-03-31",
            "2023-06-30",
            "2023-09-30",
            "2023-12-31",
            "2024-03-31",
            "2024-06-30",
        )
        for period_index, period in enumerate(periods):
            for idx in range(12):
                net_income = 100.0 + idx + period_index * 10.0
                equity = 500.0 + idx * 10.0 + period_index * 20.0
                total_assets = 1000.0 + idx * 25.0 + period_index * 50.0
                market_cap = 2000.0 + idx * 100.0 + period_index * 150.0
                total_debt = 120.0 + idx * 5.0
                rows.append(
                    {
                        "symbol": f"AAA{idx}",
                        "period": period,
                        "publish_date": pd.Timestamp("2024-05-10"),
                        "market_date": pd.Timestamp("2024-05-13"),
                        "close": 10 + idx,
                        "selected_profile": "industrial",
                        "sector": "SANAYI",
                        "sub_sector": "PERAKENDE" if idx < 10 else "DIGER",
                        "net_income": net_income,
                        "equity": equity,
                        "total_assets": total_assets,
                        "pd": market_cap,
                        "total_debt": total_debt,
                        "earnings_yield": idx / 100,
                        "book_to_price": idx / 10,
                        "debt_to_equity": 12 - idx,
                        "asset_growth_yoy": idx / 20,
                        "net_income_growth_yoy": idx / 30,
                        "margin_stability": idx / 40,
                        "forward_return_1m": idx / 100,
                        "forward_return_3m": idx / 50,
                        "forward_return_6m": idx / 25,
                    }
                )
        return pd.DataFrame(rows)

    def test_winsorize_metrics_removes_inf_and_preserves_rows(self) -> None:
        frame = self._base_frame()
        frame.loc[0, "earnings_yield"] = np.inf

        result = winsorize_metrics(frame, metric_columns=("earnings_yield",), group_columns=("period", "sector"))

        self.assertEqual(len(result), len(frame))
        self.assertEqual(np.isinf(pd.to_numeric(result["earnings_yield"], errors="coerce").dropna()).sum(), 0)

    def test_direction_audit_uses_schema_direction(self) -> None:
        audit = build_direction_audit(self._base_frame())

        debt = audit.loc[audit["metric"].eq("debt_to_equity")].iloc[0]
        self.assertEqual(debt["direction"], -1)
        self.assertTrue(debt["lower_is_better"])

    def test_hygiene_report_counts_inf_outliers_and_coverage(self) -> None:
        frame = self._base_frame()
        frame.loc[0, "book_to_price"] = np.inf

        report = build_hygiene_report(frame, metric_columns=("book_to_price",), outlier_z=3.0)

        row = report.iloc[0]
        self.assertEqual(row["inf"], 1)
        self.assertGreater(row["coverage_pct"], 90)

    def test_quality_validity_rules_remove_unstable_cash_ratios(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "selected_profile": "industrial",
                    "net_income": 1.0,
                    "total_assets": 1000.0,
                    "sales": 1000.0,
                    "operating_cf_to_net_income": 100.0,
                    "free_cash_flow_to_net_income": 50.0,
                },
                {
                    "selected_profile": "industrial",
                    "net_income": 100.0,
                    "total_assets": 1000.0,
                    "sales": 1000.0,
                    "operating_cf_to_net_income": 1.2,
                    "free_cash_flow_to_net_income": 0.8,
                },
            ]
        )

        result = apply_quality_economic_validity_rules(frame, min_net_income_to_assets=0.005, min_net_income_to_sales=0.005)

        self.assertTrue(pd.isna(result.loc[0, "operating_cf_to_net_income"]))
        self.assertTrue(pd.isna(result.loc[0, "free_cash_flow_to_net_income"]))
        self.assertAlmostEqual(result.loc[1, "operating_cf_to_net_income"], 1.2)
        self.assertAlmostEqual(result.loc[1, "free_cash_flow_to_net_income"], 0.8)

    def test_quality_component_scores_split_core_cash_and_profile_specific(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "selected_profile": "industrial",
                    "quality_score": 0.5,
                    "roa_z": 0.8,
                    "roic_z": 0.6,
                    "gross_profitability_z": 0.4,
                    "operating_cf_to_net_income_z": 0.2,
                    "free_cash_flow_to_net_income_z": 0.0,
                    "roe_z": 0.9,
                },
                {
                    "selected_profile": "BankProfile",
                    "quality_score": 0.3,
                    "roa_z": 0.4,
                    "roe_z": 0.6,
                    "cost_to_income_z": 0.8,
                },
                {
                    "selected_profile": "holding",
                    "quality_score": 0.7,
                    "roa_z": 1.0,
                    "roe_z": 1.0,
                },
            ]
        )

        result = add_quality_component_scores(frame)

        self.assertAlmostEqual(result.loc[0, "quality_score_legacy"], 0.5)
        self.assertAlmostEqual(result.loc[0, "quality_core_score"], 0.6)
        self.assertAlmostEqual(result.loc[0, "quality_cash_score"], 0.1)
        self.assertAlmostEqual(result.loc[0, "quality_core_plus_cash_score"], 0.45)
        self.assertAlmostEqual(result.loc[0, "quality_profile_specific_score"], 0.6)
        self.assertAlmostEqual(result.loc[0, "quality_roe_standalone_score"], 0.9)
        self.assertEqual(result.loc[0, "quality_reliability_flag"], "high")
        self.assertAlmostEqual(result.loc[1, "quality_bank_core_score"], 0.6)
        self.assertAlmostEqual(result.loc[1, "quality_profile_specific_score"], 0.6)
        self.assertTrue(pd.isna(result.loc[2, "quality_profile_specific_score"]))
        self.assertEqual(result.loc[2, "quality_reliability_flag"], "unsupported")

    def test_quantile_portfolios_calculate_long_short(self) -> None:
        frame = self._base_frame()

        quantiles = calculate_quantile_portfolios(
            frame,
            score_columns=("earnings_yield",),
            forward_return_columns=("forward_return_3m",),
            quantiles=3,
            min_observations=6,
        )
        summary = summarize_quantile_portfolios(quantiles)

        self.assertFalse(quantiles.empty)
        self.assertGreater(summary.loc[0, "long_short_return"], 0)
        self.assertTrue(summary.loc[0, "monotonic_increasing"])

    def test_build_validation_reports_returns_expected_tables(self) -> None:
        reports = build_validation_reports(
            self._base_frame(),
            horizons=("1M", "3M", "6M"),
            sub_sector_min_size=10,
            sector_min_size=15,
        )

        self.assertIn("factor_ic_summary", reports)
        self.assertIn("metric_ic_summary", reports)
        self.assertIn("quantile_summary", reports)
        self.assertIn("quality_validity_report", reports)
        self.assertIn("metric_validity_audit", reports)
        self.assertIn("metric_production_tiers", reports)
        self.assertIn("quality_component_ic_summary", reports)
        self.assertIn("value_by_quality_bucket_summary", reports)
        self.assertEqual(len(reports["raw_scored"]), len(self._base_frame()))
        self.assertEqual(len(reports["sector_neutral_scored"]), len(self._base_frame()))

    def test_evaluate_quality_components_returns_reports(self) -> None:
        rows: list[dict[str, object]] = []
        for period in ("2024-03-31", "2024-06-30"):
            for idx in range(40):
                value = idx / 40
                rows.append(
                    {
                        "symbol": f"AAA{idx}",
                        "period": period,
                        "selected_profile": "industrial",
                        "roa_z": value,
                        "roic_z": value,
                        "gross_profitability_z": value,
                        "operating_cf_to_net_income_z": value / 2,
                        "free_cash_flow_to_net_income_z": value / 3,
                        "quality_score": value,
                        "forward_return_3m": value,
                    }
                )
        reports = evaluate_quality_components(
            pd.DataFrame(rows),
            forward_return_columns=("forward_return_3m",),
            quantiles=5,
            min_observations=30,
        )

        summary = reports["quality_component_ic_summary"]
        self.assertFalse(summary.empty)
        self.assertIn("quality_core_score", set(summary["factor"]))
        self.assertFalse(reports["quality_component_quantile_summary"].empty)

    def test_value_ic_by_quality_bucket_detects_filter_effect(self) -> None:
        rows: list[dict[str, object]] = []
        for period in ("2024-03-31", "2024-06-30"):
            for idx in range(40):
                value = idx % 20
                high_quality = idx >= 20
                rows.append(
                    {
                        "symbol": f"AAA{idx}",
                        "period": period,
                        "value_score": value,
                        "quality_profile_specific_score": 1.0 if high_quality else 0.0,
                        "forward_return_3m": value if high_quality else -value,
                    }
                )

        ic = calculate_value_ic_by_quality_bucket(
            pd.DataFrame(rows),
            forward_return_columns=("forward_return_3m",),
            min_observations=10,
        )
        summary = summarize_value_ic_by_quality_bucket(ic)

        high = summary.loc[summary["quality_bucket_label"].eq("high_quality")].iloc[0]
        low = summary.loc[summary["quality_bucket_label"].eq("low_quality")].iloc[0]
        self.assertGreater(high["mean_ic"], 0)
        self.assertLess(low["mean_ic"], 0)

if __name__ == "__main__":
    unittest.main()
