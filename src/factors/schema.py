"""Declarative factor schema for profile-aware scoring."""

from __future__ import annotations

from dataclasses import dataclass

ALL_PROFILES = ("industrial", "holding", "reit", "bank", "katilim_bank", "insurance")
CLASSIC_PROFILES = ("industrial", "holding", "reit")
BANK_PROFILES = ("bank", "katilim_bank")

DIRECTION_HIGH_IS_GOOD = 1
DIRECTION_LOW_IS_GOOD = -1


@dataclass(frozen=True)
class MetricSpec:
    """Describe one metric used to build a factor score."""

    name: str
    direction: int
    profiles: tuple[str, ...]
    source: str
    formula: str
    description: str = ""
    status: str = "active"


@dataclass(frozen=True)
class FactorSpec:
    """Describe one economic factor family and its metric inputs."""

    name: str
    metrics: tuple[MetricSpec, ...]
    description: str = ""


FACTOR_SCHEMA: tuple[FactorSpec, ...] = (
    FactorSpec(
        name="value",
        description="Ucuz/pahalı değerleme sinyalleri.",
        metrics=(
            MetricSpec("ebit_ev", 1, CLASSIC_PROFILES, "financial+market", "ebit / enterprise_value"),
            MetricSpec("ebitda_ev", 1, CLASSIC_PROFILES, "financial+market", "ebitda / enterprise_value"),
            MetricSpec("fcf_yield", 1, CLASSIC_PROFILES, "financial+market", "free_cash_flow / market_cap"),
            MetricSpec("earnings_yield", 1, ALL_PROFILES, "financial+market", "net_income / market_cap"),
            MetricSpec("book_to_price", 1, ALL_PROFILES, "financial+market", "equity / market_cap"),
        ),
    ),
    FactorSpec(
        name="quality",
        description="Sermaye verimliliği, nakit kalitesi ve bilanço kalitesi.",
        metrics=(
            MetricSpec("roic", 1, CLASSIC_PROFILES, "financial+market", "ebit / invested_capital"),
            MetricSpec("roe", 1, ALL_PROFILES, "financial", "net_income / equity"),
            MetricSpec("roa", 1, ALL_PROFILES, "financial", "net_income / total_assets"),
            MetricSpec("gross_profitability", 1, ("industrial", "holding"), "financial", "gross_profit / total_assets"),
            MetricSpec("operating_cf_to_net_income", 1, CLASSIC_PROFILES, "financial", "operating_cash_flow / net_income"),
            MetricSpec("free_cash_flow_to_net_income", 1, CLASSIC_PROFILES, "financial", "free_cash_flow / net_income"),
            MetricSpec("cost_to_income", -1, BANK_PROFILES, "financial", "operating_expenses / operating_income"),
            MetricSpec("npl_ratio", -1, BANK_PROFILES, "financial", "non_performing_loans / loans"),
            MetricSpec(
                "npl_coverage_ratio",
                1,
                BANK_PROFILES,
                "financial",
                "loan_loss_allowance / non_performing_loans",
                status="experimental",
            ),
            MetricSpec("combined_ratio", -1, ("insurance",), "financial", "loss_ratio + expense_ratio"),
        ),
    ),
    FactorSpec(
        name="profitability",
        description="Marj ve faaliyet karlılığı sinyalleri.",
        metrics=(
            MetricSpec("gross_margin", 1, ("industrial",), "financial", "gross_profit / sales"),
            MetricSpec("ebit_margin", 1, ("industrial",), "financial", "ebit / sales"),
            MetricSpec("ebitda_margin", 1, ("industrial",), "financial", "ebitda / sales"),
            MetricSpec("net_profit_margin", 1, ("industrial",), "financial", "net_income / sales"),
            MetricSpec("operating_profit_margin", 1, ("holding",), "financial", "ebit / sales"),
            MetricSpec("gross_profit_margin", 1, ("holding",), "financial", "gross_profit / sales"),
            MetricSpec("technical_profit_margin", 1, ("insurance",), "financial", "technical_profit / gross_premiums"),
            MetricSpec("net_interest_margin", 1, BANK_PROFILES, "financial", "net_interest_income / average_assets"),
        ),
    ),
    FactorSpec(
        name="growth",
        description="Operasyonel ve karlılık büyümesi.",
        metrics=(
            MetricSpec("revenue_growth_yoy", 1, ("industrial",), "financial", "sales yoy growth"),
            MetricSpec("ebit_growth_yoy", 1, ("industrial",), "financial", "ebit yoy growth"),
            MetricSpec("ebitda_growth_yoy", 1, ("industrial",), "financial", "ebitda yoy growth"),
            MetricSpec("net_income_growth_yoy", 1, ALL_PROFILES, "financial", "net_income yoy growth"),
            MetricSpec("gross_premium_growth_yoy", 1, ("insurance",), "financial", "gross_premiums yoy growth"),
        ),
    ),
    FactorSpec(
        name="investment",
        description="Agresif yatırım ve bilanço genişlemesi sinyalleri.",
        metrics=(
            MetricSpec("asset_growth_yoy", -1, ALL_PROFILES, "financial", "total_assets yoy growth"),
            MetricSpec("working_capital_growth_yoy", -1, ("industrial",), "financial", "working_capital yoy growth"),
            MetricSpec("capex_growth_yoy", -1, ("industrial", "holding"), "financial", "capex yoy growth"),
            MetricSpec("inventory_growth_spread", -1, ("industrial",), "financial", "inventory growth - sales growth"),
            MetricSpec("receivables_growth_spread", -1, ("industrial",), "financial", "receivables growth - sales growth"),
        ),
    ),
    FactorSpec(
        name="leverage",
        description="Borçluluk ve finansal risk sinyalleri.",
        metrics=(
            MetricSpec("net_debt_to_ebitda", -1, CLASSIC_PROFILES, "financial", "net_debt / ebitda"),
            MetricSpec("debt_to_equity", -1, CLASSIC_PROFILES, "financial", "total_debt / equity"),
            MetricSpec("net_debt_to_equity", -1, CLASSIC_PROFILES, "financial", "net_debt / equity"),
            MetricSpec("interest_coverage", 1, ("industrial",), "financial", "ebit / financing_expenses"),
            MetricSpec("ebitda_interest_coverage", 1, ("industrial",), "financial", "ebitda / financing_expenses"),
            MetricSpec("loan_to_deposit", -1, BANK_PROFILES, "financial", "loans / deposits"),
            MetricSpec("technical_reserves_to_assets", -1, ("insurance",), "financial", "technical_reserves / assets"),
        ),
    ),
    FactorSpec(
        name="stability",
        description="Düşük oynaklık/stabil finansal performans sinyalleri.",
        metrics=(
            MetricSpec("margin_stability", -1, ("industrial", "holding"), "financial", "rolling std of margin"),
            MetricSpec("earnings_stability", -1, CLASSIC_PROFILES, "financial", "rolling std of net_income"),
            MetricSpec("roic_stability", -1, CLASSIC_PROFILES, "financial", "rolling std of roic"),
        ),
    ),
    FactorSpec(
        name="capital_allocation",
        description="Temettü, geri alım ve pay ihracı sinyalleri. Veri kaynağı henüz eklenmedi.",
        metrics=(),
    ),
)


def factor_names() -> list[str]:
    """Return factor names in scoring order."""
    return [factor.name for factor in FACTOR_SCHEMA]


def get_factor_spec(name: str) -> FactorSpec:
    """Return the schema entry for one factor family."""
    normalized = str(name).strip().lower()
    for factor in FACTOR_SCHEMA:
        if factor.name == normalized:
            return factor
    raise KeyError(f"Unknown factor family: {name}")


def metric_specs_for_factor(name: str, *, profile: str | None = None) -> list[MetricSpec]:
    """Return metric specs for a factor, optionally filtered by profile."""
    factor = get_factor_spec(name)
    if profile is None:
        return list(factor.metrics)
    normalized_profile = str(profile).strip().lower()
    return [metric for metric in factor.metrics if normalized_profile in metric.profiles]


def supported_metrics_for_profile(profile: str) -> list[MetricSpec]:
    """Return every active metric supported by a profile."""
    normalized_profile = str(profile).strip().lower()
    metrics: list[MetricSpec] = []
    for factor in FACTOR_SCHEMA:
        metrics.extend(
            metric
            for metric in factor.metrics
            if metric.status == "active" and normalized_profile in metric.profiles
        )
    return metrics


def factor_for_metric(metric_name: str) -> str | None:
    """Return the factor family name for a metric column."""
    normalized = str(metric_name).strip()
    for factor in FACTOR_SCHEMA:
        if any(metric.name == normalized for metric in factor.metrics):
            return factor.name
    return None


def metric_direction(metric_name: str) -> int | None:
    """Return whether high values are good (`1`) or low values are good (`-1`)."""
    normalized = str(metric_name).strip()
    for factor in FACTOR_SCHEMA:
        for metric in factor.metrics:
            if metric.name == normalized:
                return metric.direction
    return None
