from __future__ import annotations

import unittest

from src.factors.schema import (
    factor_for_metric,
    factor_names,
    get_factor_spec,
    metric_direction,
    metric_specs_for_factor,
    supported_metrics_for_profile,
)


class FactorSchemaTests(unittest.TestCase):
    def test_factor_schema_contains_expected_families(self) -> None:
        self.assertEqual(
            factor_names(),
            [
                "value",
                "quality",
                "profitability",
                "growth",
                "investment",
                "leverage",
                "stability",
                "capital_allocation",
            ],
        )

    def test_metric_specs_can_be_filtered_by_profile(self) -> None:
        industrial_value = {metric.name for metric in metric_specs_for_factor("value", profile="industrial")}
        bank_value = {metric.name for metric in metric_specs_for_factor("value", profile="bank")}

        self.assertIn("ebitda_ev", industrial_value)
        self.assertIn("earnings_yield", bank_value)
        self.assertNotIn("ebitda_ev", bank_value)

    def test_direction_tracks_whether_high_or_low_is_good(self) -> None:
        self.assertEqual(metric_direction("book_to_price"), 1)
        self.assertEqual(metric_direction("debt_to_equity"), -1)
        self.assertEqual(metric_direction("combined_ratio"), -1)

    def test_supported_metrics_for_profile_excludes_unsupported_metrics(self) -> None:
        bank_metrics = {metric.name for metric in supported_metrics_for_profile("bank")}

        self.assertIn("loan_to_deposit", bank_metrics)
        self.assertIn("book_to_price", bank_metrics)
        self.assertNotIn("npl_coverage_ratio", bank_metrics)
        self.assertNotIn("ebitda_ev", bank_metrics)
        self.assertNotIn("combined_ratio", bank_metrics)

    def test_reit_excludes_metrics_that_have_no_source_coverage(self) -> None:
        reit_metrics = {metric.name for metric in supported_metrics_for_profile("reit")}

        self.assertIn("book_to_price", reit_metrics)
        self.assertIn("asset_growth_yoy", reit_metrics)
        self.assertNotIn("working_capital_growth_yoy", reit_metrics)
        self.assertNotIn("capex_growth_yoy", reit_metrics)
        self.assertNotIn("gross_profitability", reit_metrics)
        self.assertNotIn("margin_stability", reit_metrics)

    def test_holding_excludes_working_capital_growth_but_keeps_capex(self) -> None:
        holding_metrics = {metric.name for metric in supported_metrics_for_profile("holding")}

        self.assertNotIn("working_capital_growth_yoy", holding_metrics)
        self.assertIn("capex_growth_yoy", holding_metrics)

    def test_factor_lookup_for_metric(self) -> None:
        self.assertEqual(factor_for_metric("roic"), "quality")
        self.assertEqual(factor_for_metric("gross_margin"), "profitability")
        self.assertIsNone(factor_for_metric("not_a_metric"))

    def test_capital_allocation_is_placeholder_until_source_exists(self) -> None:
        self.assertEqual(get_factor_spec("capital_allocation").metrics, ())


if __name__ == "__main__":
    unittest.main()
