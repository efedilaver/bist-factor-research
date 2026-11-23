from __future__ import annotations

import unittest

import pandas as pd

from src.factors import (
    apply_metric_validity,
    build_metric_registry,
    build_metric_registry_reports,
    build_metric_production_tiers,
    build_metric_validity_audit,
    build_net_income_denominator_sensitivity,
)


class MetricRegistryTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "roe": 0.10,
                    "net_income": 10.0,
                    "equity": 100.0,
                    "total_assets": 500.0,
                    "sales": 200.0,
                    "operating_cf_to_net_income": 1.2,
                    "free_cash_flow_to_net_income": 0.9,
                    "operating_cash_flow": 12.0,
                    "free_cash_flow": 9.0,
                    "pd": 1000.0,
                    "earnings_yield": 0.01,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "roe": 0.20,
                    "net_income": 10.0,
                    "equity": -50.0,
                    "total_assets": 400.0,
                    "sales": 200.0,
                    "operating_cf_to_net_income": 1.1,
                    "free_cash_flow_to_net_income": 0.8,
                    "operating_cash_flow": 11.0,
                    "free_cash_flow": 8.0,
                    "pd": 900.0,
                    "earnings_yield": 0.01,
                },
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "roe": 0.15,
                    "net_income": 15.0,
                    "equity": 100.0,
                    "total_assets": 1000.0,
                    "pd": 1200.0,
                    "earnings_yield": 0.0125,
                },
            ]
        )

    def test_registry_contains_core_metric_spec(self) -> None:
        registry = build_metric_registry()
        roe = registry.loc[registry["metric_name"].eq("roe")].iloc[0]

        self.assertEqual(roe["formula"], "net_income / equity")
        self.assertEqual(roe["metric_role"], "factor_metric")
        self.assertIn("equity", roe["required_inputs"])
        self.assertIn("industrial", roe["applicable_profiles"])
        self.assertEqual(roe["production_decision"], "finalize_now")

    def test_registry_marks_market_fields_as_needs_definition(self) -> None:
        registry = build_metric_registry()
        close = registry.loc[registry["metric_name"].eq("close")].iloc[0]

        self.assertEqual(close["metric_role"], "source_field")
        self.assertEqual(close["profile_scope"], "source_field")
        self.assertEqual(close["production_decision"], "needs_definition")
        self.assertTrue(close["decision_required"])

    def test_registry_marks_profile_routed_metrics(self) -> None:
        registry = build_metric_registry()
        gross_premium = registry.loc[registry["metric_name"].eq("gross_premium_growth_yoy")].iloc[0]
        npl_coverage = registry.loc[registry["metric_name"].eq("npl_coverage_ratio")].iloc[0]

        self.assertEqual(gross_premium["profile_scope"], "profile_routed")
        self.assertEqual(gross_premium["route_decision"], "insurance")
        self.assertEqual(gross_premium["production_decision"], "finalize_now")
        self.assertFalse(gross_premium["decision_required"])
        self.assertEqual(npl_coverage["profile_scope"], "profile_routed")
        self.assertEqual(npl_coverage["route_decision"], "bank|katilim_bank")
        self.assertEqual(npl_coverage["production_decision"], "finalize_with_profile_routing")
        self.assertEqual(npl_coverage["status"], "experimental")

    def test_validity_audit_flags_negative_equity_without_mutating_frame(self) -> None:
        frame = self._frame()
        before = frame["roe"].copy()

        audit = build_metric_validity_audit(frame)

        pd.testing.assert_series_equal(frame["roe"], before)
        roe = audit.loc[audit["metric_name"].eq("roe")].iloc[0]
        self.assertGreaterEqual(roe["invalid_count"], 1)
        self.assertIn("NON_POSITIVE_EQUITY", roe["flag_breakdown"])

    def test_apply_metric_validity_nulls_invalid_metrics_and_adds_diagnostics(self) -> None:
        frame = self._frame()

        result = apply_metric_validity(frame)

        self.assertTrue(pd.isna(result.loc[1, "roe"]))
        self.assertFalse(bool(result.loc[1, "roe_valid"]))
        self.assertEqual(result.loc[1, "roe_flag"], "NON_POSITIVE_EQUITY")
        self.assertEqual(result.loc[1, "roe_status"], "INVALID_ECONOMIC")
        self.assertAlmostEqual(result.loc[0, "roe"], 0.10)
        self.assertTrue(bool(result.loc[0, "roe_valid"]))

    def test_apply_metric_validity_keeps_source_fields_unchanged(self) -> None:
        frame = self._frame()
        frame["close"] = [10.0, 20.0, 30.0]

        result = apply_metric_validity(frame)

        self.assertEqual(result["close"].tolist(), [10.0, 20.0, 30.0])
        self.assertNotIn("close_valid", result.columns)

    def test_apply_metric_validity_marks_profile_mismatch_without_dropping_rows(self) -> None:
        frame = self._frame()
        frame["debt_to_equity"] = [0.5, 0.7, 0.9]
        frame["total_debt"] = [50.0, 60.0, 70.0]

        result = apply_metric_validity(frame)

        self.assertEqual(len(result), len(frame))
        self.assertTrue(pd.isna(result.loc[2, "debt_to_equity"]))
        self.assertEqual(result.loc[2, "debt_to_equity_flag"], "PROFILE_MISMATCH")
        self.assertEqual(result.loc[2, "debt_to_equity_status"], "NOT_APPLICABLE")

    def test_profile_mismatch_is_not_counted_as_missing_input(self) -> None:
        audit = build_metric_validity_audit(self._frame())

        debt = audit.loc[audit["metric_name"].eq("debt_to_equity")].iloc[0]
        self.assertGreater(debt["not_applicable_count"], 0)

    def test_denominator_sensitivity_reports_thresholds(self) -> None:
        sensitivity = build_net_income_denominator_sensitivity(self._frame(), thresholds=(0.005, 0.01))

        self.assertEqual(set(sensitivity["threshold"]), {0.005, 0.01})
        self.assertIn("operating_cf_to_net_income", set(sensitivity["metric_name"]))

    def test_report_package_contains_expected_tables(self) -> None:
        reports = build_metric_registry_reports(self._frame())

        self.assertIn("metric_registry", reports)
        self.assertIn("metric_validity_audit", reports)
        self.assertIn("metric_production_tiers", reports)
        self.assertIn("metric_decision_required", reports)
        self.assertIn("metric_source_fields", reports)
        self.assertIn("metric_profile_routing", reports)
        self.assertIn("metric_denominator_sensitivity", reports)

    def test_production_tiers_classify_core_source_and_experimental_metrics(self) -> None:
        registry = build_metric_registry()
        audit = build_metric_validity_audit(self._frame(), registry=registry)

        tiers = build_metric_production_tiers(audit, registry=registry)

        earnings_yield = tiers.loc[tiers["metric_name"].eq("earnings_yield")].iloc[0]
        close = tiers.loc[tiers["metric_name"].eq("close")].iloc[0]
        npl_coverage = tiers.loc[tiers["metric_name"].eq("npl_coverage_ratio")].iloc[0]
        self.assertEqual(earnings_yield["production_tier"], "production_core")
        self.assertEqual(close["production_tier"], "source_field")
        self.assertEqual(npl_coverage["production_tier"], "exclude_or_experimental")


if __name__ == "__main__":
    unittest.main()
