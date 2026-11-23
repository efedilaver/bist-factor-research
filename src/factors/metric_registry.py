"""Production metric registry and dry-run economic validity audits."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.factors.financial import FACTOR_COLUMNS, PROFILE_FACTOR_COLUMN_MAP
from src.factors.multifactor import MULTIFACTOR_COLUMNS, MULTIFACTOR_PROFILE_COLUMN_MAP
from src.factors.schema import FACTOR_SCHEMA

STATUS_VALID = "VALID"
STATUS_MISSING_INPUT = "MISSING_INPUT"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_INVALID_ECONOMIC = "INVALID_ECONOMIC"
STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"

FLAG_MISSING_INPUT = "MISSING_INPUT"
FLAG_ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
FLAG_SMALL_DENOMINATOR = "SMALL_DENOMINATOR"
FLAG_NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
FLAG_NON_POSITIVE_EBITDA = "NON_POSITIVE_EBITDA"
FLAG_NON_POSITIVE_EBIT = "NON_POSITIVE_EBIT"
FLAG_NON_POSITIVE_NET_INCOME = "NON_POSITIVE_NET_INCOME"
FLAG_NON_POSITIVE_BASE_VALUE = "NON_POSITIVE_BASE_VALUE"
FLAG_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
FLAG_PROFILE_MISMATCH = "PROFILE_MISMATCH"
FLAG_INVALID_MARKET_PRICE = "INVALID_MARKET_PRICE"
FLAG_INVALID_MARKET_CAP = "INVALID_MARKET_CAP"
FLAG_LOW_DATA_COVERAGE = "LOW_DATA_COVERAGE"

DEFAULT_SMALL_DENOMINATOR_ABS = 1e-9
DEFAULT_NET_INCOME_RELATIVE_THRESHOLD = 0.005
DEFAULT_COVERAGE_THRESHOLD = 0.80
DEFAULT_THRESHOLD_SENSITIVITY = (0.0025, 0.005, 0.01, 0.02)
DEFAULT_CORE_REMOVAL_THRESHOLD = 5.0
DEFAULT_OPTIONAL_REMOVAL_THRESHOLD = 30.0
DEFAULT_CORE_VALID_COVERAGE_THRESHOLD = 0.80
DEFAULT_OPTIONAL_VALID_COVERAGE_THRESHOLD = 0.20
DECISION_FINALIZE_NOW = "finalize_now"
DECISION_PROFILE_ROUTING = "finalize_with_profile_routing"
DECISION_NEEDS_DEFINITION = "needs_definition"
TIER_PRODUCTION_CORE = "production_core"
TIER_PRODUCTION_OPTIONAL = "production_optional"
TIER_EXCLUDE_OR_EXPERIMENTAL = "exclude_or_experimental"
TIER_SOURCE_FIELD = "source_field"
ROLE_FACTOR_METRIC = "factor_metric"
ROLE_SOURCE_FIELD = "source_field"
PROFILE_SCOPE_UNIVERSE = "universe"
PROFILE_SCOPE_PROFILE_SPECIFIC = "profile_specific"
PROFILE_SCOPE_PROFILE_ROUTED = "profile_routed"
PROFILE_SCOPE_SOURCE_FIELD = "source_field"
NON_METRIC_COLUMNS = {
    "market_anchor_date",
    "market_date",
    "is_point_in_time_safe",
    "market_lag_days",
}
NEEDS_DEFINITION_METRICS = {
    "close",
    "volume",
    "dolar_bazli_fiyat",
    "dolar_hacim",
    "pd",
    "pd_usd",
    "hao_pd",
    "hao_pd_usd",
}
PROFILE_ROUTING_METRICS = {
    "gross_premium_growth_yoy",
    "inventory_growth_spread",
    "npl_coverage_ratio",
    "operating_profit_margin",
    "gross_profit_margin",
    "financing_expense_to_sales",
}
PROFILE_ROUTE_DECISIONS = {
    "gross_premium_growth_yoy": ("insurance", "Insurance-only premium growth metric."),
    "inventory_growth_spread": ("industrial", "Industrial inventory/revenue mismatch metric; not applicable outside operating inventory businesses."),
    "npl_coverage_ratio": ("bank|katilim_bank", "Bank/credit profile metric; kept experimental because observed source coverage is low."),
    "operating_profit_margin": ("holding", "Holding-only operating profitability metric using sales-style statement fields."),
    "gross_profit_margin": ("holding", "Holding-only gross profitability metric using sales-style statement fields."),
    "financing_expense_to_sales": ("holding", "Holding-only financing expense intensity metric; financial institutions are excluded."),
}


@dataclass(frozen=True)
class MetricRegistryEntry:
    """Production specification for one calculated metric."""

    metric_name: str
    factor_family: str
    metric_role: str
    profile_scope: str
    applicable_profiles: tuple[str, ...]
    formula: str
    required_inputs: tuple[str, ...]
    time_basis: str
    direction: str
    validity_rules: tuple[str, ...]
    missing_policy: str
    outlier_policy: str
    flags: tuple[str, ...]
    status: str = "active"
    production_decision: str = DECISION_FINALIZE_NOW
    route_decision: str = ""
    route_reason: str = ""
    not_applicable_policy: str = "PROFILE_MISMATCH"
    decision_required: bool = False
    notes: str = ""


_FACTOR_BY_METRIC: dict[str, str] = {
    metric.name: factor.name
    for factor in FACTOR_SCHEMA
    for metric in factor.metrics
}
_SCHEMA_METRIC_BY_NAME = {
    metric.name: metric
    for factor in FACTOR_SCHEMA
    for metric in factor.metrics
}


def _normalize_profile(profile: object) -> str:
    value = str(profile or "").strip().lower()
    if value.endswith("profile"):
        value = value[: -len("profile")]
    return value.replace("katılımbank", "katilim_bank").replace("katilimbank", "katilim_bank")


def _profiles_for_metric(metric: str) -> tuple[str, ...]:
    profiles: set[str] = set()
    schema_metric = _SCHEMA_METRIC_BY_NAME.get(metric)
    if schema_metric is not None and schema_metric.status == "active":
        profiles.update(_normalize_profile(profile) for profile in schema_metric.profiles)
    for profile_map in (PROFILE_FACTOR_COLUMN_MAP, MULTIFACTOR_PROFILE_COLUMN_MAP):
        for profile, columns in profile_map.items():
            if metric in columns:
                profiles.add(_normalize_profile(profile))
    return tuple(sorted(profile for profile in profiles if profile))


def _direction_for_metric(metric: str) -> str:
    schema_metric = _SCHEMA_METRIC_BY_NAME.get(metric)
    if schema_metric is None:
        return "higher_better"
    return "higher_better" if schema_metric.direction > 0 else "lower_better"


def _factor_family_for_metric(metric: str) -> str:
    if metric in NEEDS_DEFINITION_METRICS:
        return "market"
    if metric in _FACTOR_BY_METRIC:
        return _FACTOR_BY_METRIC[metric]
    if metric.endswith("_growth_yoy") or metric.endswith("_growth_spread"):
        return "growth"
    if metric in {"roe", "roa", "equity_to_assets", "cash_to_assets"}:
        return "quality"
    if metric.endswith("_margin") or metric.endswith("_ratio"):
        return "profitability"
    if "debt" in metric or "coverage" in metric:
        return "leverage"
    if metric in {"enterprise_value", "pd", "pd_usd", "hao_pd", "hao_pd_usd", "close"}:
        return "market"
    return "financial"


def _metric_role_for_metric(metric: str) -> str:
    return ROLE_SOURCE_FIELD if metric in NEEDS_DEFINITION_METRICS else ROLE_FACTOR_METRIC


def _profile_scope_for_metric(metric: str, applicable_profiles: tuple[str, ...]) -> str:
    if metric in NEEDS_DEFINITION_METRICS:
        return PROFILE_SCOPE_SOURCE_FIELD
    if metric in PROFILE_ROUTING_METRICS:
        return PROFILE_SCOPE_PROFILE_ROUTED
    if len(applicable_profiles) <= 1:
        return PROFILE_SCOPE_PROFILE_SPECIFIC
    return PROFILE_SCOPE_UNIVERSE


def _formula_specs() -> Mapping[str, tuple[str, tuple[str, ...], str]]:
    return {
        "roe": ("net_income / equity", ("net_income", "equity"), "TTM income / period-end equity"),
        "roa": ("net_income / total_assets", ("net_income", "total_assets"), "TTM income / period-end assets"),
        "equity_to_assets": ("equity / total_assets", ("equity", "total_assets"), "period-end balance sheet"),
        "cash_to_assets": ("cash / total_assets", ("cash", "total_assets"), "period-end balance sheet"),
        "net_income_growth_yoy": ("net_income / net_income_lag_4 - 1", ("net_income",), "four-quarter YoY"),
        "asset_growth_yoy": ("total_assets / total_assets_lag_4 - 1", ("total_assets",), "four-quarter YoY"),
        "equity_growth_yoy": ("equity / equity_lag_4 - 1", ("equity",), "four-quarter YoY"),
        "debt_to_equity": ("total_debt / equity", ("total_debt", "equity"), "period-end balance sheet"),
        "net_debt_to_equity": ("net_debt / equity", ("net_debt", "equity"), "period-end balance sheet"),
        "net_debt_to_ebitda": ("net_debt / ebitda", ("net_debt", "ebitda"), "period-end net debt / TTM EBITDA"),
        "operating_cf_to_net_income": ("operating_cash_flow / net_income", ("operating_cash_flow", "net_income"), "TTM cash flow / TTM income"),
        "free_cash_flow_to_net_income": ("free_cash_flow / net_income", ("free_cash_flow", "net_income"), "TTM cash flow / TTM income"),
        "loans_to_assets": ("loans / total_assets", ("loans", "total_assets"), "period-end balance sheet"),
        "deposits_to_assets": ("deposits / total_assets", ("deposits", "total_assets"), "period-end balance sheet"),
        "loan_to_deposit": ("loans / deposits", ("loans", "deposits"), "period-end balance sheet"),
        "net_interest_margin": ("net_interest_income / average_assets", ("net_interest_income", "total_assets"), "TTM income / average assets"),
        "fee_income_to_operating_income": ("net_fee_commission_income / total_operating_income", ("net_fee_commission_income", "total_operating_income"), "TTM bank income"),
        "cost_to_income": ("abs(operating_expenses) / total_operating_income", ("operating_expenses", "total_operating_income"), "TTM bank income"),
        "provision_expense_to_loans": ("abs(provision_expense) / loans", ("provision_expense", "loans"), "TTM provision / period-end loans"),
        "npl_ratio": ("non_performing_loans / loans", ("non_performing_loans", "loans"), "period-end balance sheet"),
        "npl_coverage_ratio": ("abs(loan_loss_allowance) / non_performing_loans", ("loan_loss_allowance", "non_performing_loans"), "period-end balance sheet"),
        "gross_premium_growth_yoy": ("gross_premiums / gross_premiums_lag_4 - 1", ("non_life_gross_written_premiums", "life_gross_written_premiums"), "four-quarter YoY"),
        "retention_ratio": ("net_written_premiums / gross_premiums", ("non_life_net_written_premiums", "life_net_written_premiums", "non_life_gross_written_premiums", "life_gross_written_premiums"), "TTM insurance premiums"),
        "loss_ratio": ("abs(net_claims) / net_earned_premiums", ("non_life_net_claims", "life_net_claims", "non_life_net_earned_premiums", "life_net_earned_premiums"), "TTM insurance technicals"),
        "expense_ratio": ("abs(operating_expenses) / net_earned_premiums", ("non_life_operating_expenses", "life_operating_expenses", "non_life_net_earned_premiums", "life_net_earned_premiums"), "TTM insurance technicals"),
        "combined_ratio": ("loss_ratio + expense_ratio", ("loss_ratio", "expense_ratio"), "TTM insurance technicals"),
        "technical_profit_margin": ("technical_profit / gross_premiums", ("total_technical_profit", "non_life_technical_profit", "life_technical_profit", "non_life_gross_written_premiums", "life_gross_written_premiums"), "TTM insurance technicals"),
        "technical_reserves_to_assets": ("technical_reserves / total_assets", ("current_technical_reserves", "long_technical_reserves", "total_assets"), "period-end balance sheet"),
        "outstanding_claims_reserves_to_equity": ("outstanding_claims_reserves / equity", ("current_outstanding_claims_reserves", "long_outstanding_claims_reserves", "equity"), "period-end balance sheet"),
        "operating_profit_margin": ("ebit / sales", ("ebit", "sales"), "TTM income statement"),
        "gross_profit_margin": ("gross_profit / sales", ("gross_profit", "sales"), "TTM income statement"),
        "financial_investments_to_assets": ("financial_investments / total_assets", ("short_term_financial_investments", "long_term_financial_investments", "total_assets"), "period-end balance sheet"),
        "equity_method_investments_to_assets": ("equity_method_investments / total_assets", ("equity_method_investments", "total_assets"), "period-end balance sheet"),
        "equity_method_income_to_net_income": ("equity_method_income / net_income", ("equity_method_income", "net_income"), "TTM income statement"),
        "financing_expense_to_sales": ("abs(financing_expenses) / sales", ("financing_expenses", "sales"), "TTM income statement"),
        "capex_to_sales": ("abs(capex) / sales", ("capex", "sales"), "TTM capex / TTM sales"),
        "revenue_growth_yoy": ("sales / sales_lag_4 - 1", ("sales",), "four-quarter YoY"),
        "ebit_growth_yoy": ("ebit / ebit_lag_4 - 1", ("ebit",), "four-quarter YoY"),
        "ebitda_growth_yoy": ("ebitda / ebitda_lag_4 - 1", ("ebitda",), "four-quarter YoY"),
        "gross_margin": ("gross_profit / sales", ("gross_profit", "sales"), "TTM income statement"),
        "ebit_margin": ("ebit / sales", ("ebit", "sales"), "TTM income statement"),
        "ebitda_margin": ("ebitda / sales", ("ebitda", "sales"), "TTM income statement"),
        "net_profit_margin": ("net_income / sales", ("net_income", "sales"), "TTM income statement"),
        "dso": ("average_trade_receivables / sales * 365", ("trade_receivables", "sales"), "average balance / TTM sales"),
        "dio": ("average_inventory / abs(cost_of_sales) * 365", ("inventory", "cost_of_sales"), "average balance / TTM cost"),
        "dpo": ("average_trade_payables / abs(cost_of_sales) * 365", ("trade_payables", "cost_of_sales"), "average balance / TTM cost"),
        "cash_conversion_cycle": ("dso + dio - dpo", ("dso", "dio", "dpo"), "derived operating cycle"),
        "current_ratio": ("current_assets / current_liabilities", ("current_assets", "current_liabilities"), "period-end balance sheet"),
        "quick_ratio": ("(current_assets - inventory) / current_liabilities", ("current_assets", "inventory", "current_liabilities"), "period-end balance sheet"),
        "financial_debt_to_assets": ("total_debt / total_assets", ("total_debt", "total_assets"), "period-end balance sheet"),
        "interest_coverage": ("ebit / abs(financing_expenses)", ("ebit", "financing_expenses"), "TTM income statement"),
        "ebitda_interest_coverage": ("ebitda / abs(financing_expenses)", ("ebitda", "financing_expenses"), "TTM income statement"),
        "asset_turnover": ("sales / average_assets", ("sales", "total_assets"), "TTM sales / average assets"),
        "fixed_asset_turnover": ("sales / average_ppe", ("sales", "property_plant_equipment"), "TTM sales / average PPE"),
        "capex_to_revenue": ("abs(capex) / sales", ("capex", "sales"), "TTM capex / TTM sales"),
        "capex_to_ebitda": ("abs(capex) / ebitda", ("capex", "ebitda"), "TTM capex / TTM EBITDA"),
        "capex_to_depreciation": ("abs(capex) / abs(depreciation)", ("capex", "depreciation"), "TTM capex / TTM depreciation"),
        "cfo_margin": ("operating_cash_flow / sales", ("operating_cash_flow", "sales"), "TTM cash flow / TTM sales"),
        "cfo_to_ebitda": ("operating_cash_flow / ebitda", ("operating_cash_flow", "ebitda"), "TTM cash flow / TTM EBITDA"),
        "fcf_margin": ("free_cash_flow / sales", ("free_cash_flow", "sales"), "TTM cash flow / TTM sales"),
        "fcf_to_ebitda": ("free_cash_flow / ebitda", ("free_cash_flow", "ebitda"), "TTM cash flow / TTM EBITDA"),
        "inventory_to_revenue": ("inventory / sales", ("inventory", "sales"), "period-end inventory / TTM sales"),
        "receivables_to_revenue": ("trade_receivables / sales", ("trade_receivables", "sales"), "period-end receivables / TTM sales"),
        "payables_to_cost_of_sales": ("trade_payables / abs(cost_of_sales)", ("trade_payables", "cost_of_sales"), "period-end payables / TTM cost"),
        "inventory_growth_spread": ("inventory_growth_yoy - revenue_growth_yoy", ("inventory", "sales"), "four-quarter YoY spread"),
        "receivables_growth_spread": ("receivables_growth_yoy - revenue_growth_yoy", ("trade_receivables", "sales"), "four-quarter YoY spread"),
        "rd_to_revenue": ("abs(research_development_expenses) / sales", ("research_development_expenses", "sales"), "TTM income statement"),
        "selling_expense_ratio": ("abs(selling_marketing_expenses) / sales", ("selling_marketing_expenses", "sales"), "TTM income statement"),
        "ga_expense_ratio": ("abs(general_admin_expenses) / sales", ("general_admin_expenses", "sales"), "TTM income statement"),
        "operating_expense_ratio": ("abs(selling_marketing_expenses + general_admin_expenses + research_development_expenses) / sales", ("selling_marketing_expenses", "general_admin_expenses", "research_development_expenses", "sales"), "TTM income statement"),
        "depreciation_to_revenue": ("abs(depreciation) / sales", ("depreciation", "sales"), "TTM income statement"),
        "ppe_to_assets": ("property_plant_equipment / total_assets", ("property_plant_equipment", "total_assets"), "period-end balance sheet"),
        "ppe_to_revenue": ("property_plant_equipment / sales", ("property_plant_equipment", "sales"), "period-end PPE / TTM sales"),
        "cash_to_debt": ("cash / total_debt", ("cash", "total_debt"), "period-end balance sheet"),
        "export_ratio": ("export_revenue / sales", ("export_revenue", "sales"), "TTM income statement"),
        "enterprise_value": ("pd + net_debt", ("pd", "net_debt"), "market cap at PIT market date + net debt"),
        "ebit_ev": ("ebit / enterprise_value", ("ebit", "enterprise_value"), "TTM EBIT / PIT EV"),
        "ebitda_ev": ("ebitda / enterprise_value", ("ebitda", "enterprise_value"), "TTM EBITDA / PIT EV"),
        "fcf_yield": ("free_cash_flow / pd", ("free_cash_flow", "pd"), "TTM FCF / PIT market cap"),
        "earnings_yield": ("net_income / pd", ("net_income", "pd"), "TTM net income / PIT market cap"),
        "book_to_price": ("equity / pd", ("equity", "pd"), "period-end equity / PIT market cap"),
        "roic": ("ebit / invested_capital", ("ebit", "equity", "net_debt"), "TTM EBIT / period-end invested capital"),
        "gross_profitability": ("gross_profit / total_assets", ("gross_profit", "total_assets"), "TTM gross profit / period-end assets"),
        "working_capital": ("current_assets - current_liabilities", ("current_assets", "current_liabilities"), "period-end balance sheet"),
        "working_capital_growth_yoy": ("working_capital / working_capital_lag_4 - 1", ("working_capital",), "four-quarter YoY"),
        "capex_growth_yoy": ("abs(capex) / abs(capex_lag_4) - 1", ("capex",), "four-quarter YoY"),
        "margin_stability": ("rolling_8q_std(ebit_margin or operating_profit_margin)", ("ebit_margin|operating_profit_margin",), "rolling 8 quarters, min 4"),
        "earnings_stability": ("rolling_8q_std(net_income)", ("net_income",), "rolling 8 quarters, min 4"),
        "roic_stability": ("rolling_8q_std(roic)", ("roic",), "rolling 8 quarters, min 4"),
        "close": ("market close price; adjustment convention needs definition", ("close",), "market data at PIT market date"),
        "volume": ("raw traded volume; normalization convention needs definition", ("volume",), "market data at PIT market date"),
        "dolar_bazli_fiyat": ("USD-denominated price; FX/adjustment convention needs definition", ("dolar_bazli_fiyat",), "market data at PIT market date"),
        "dolar_hacim": ("USD-denominated volume; calculation convention needs definition", ("dolar_hacim",), "market data at PIT market date"),
        "pd": ("market capitalization; source convention needs definition", ("pd",), "market data at PIT market date"),
        "pd_usd": ("USD market capitalization; FX convention needs definition", ("pd_usd",), "market data at PIT market date"),
        "hao_pd": ("free-float market capitalization; source convention needs definition", ("hao_pd",), "market data at PIT market date"),
        "hao_pd_usd": ("USD free-float market capitalization; FX convention needs definition", ("hao_pd_usd",), "market data at PIT market date"),
    }


def _validity_rules(metric: str, required_inputs: tuple[str, ...], formula: str) -> tuple[str, ...]:
    rules = ["required inputs must be present", "profile must be applicable"]
    if metric in NEEDS_DEFINITION_METRICS:
        rules.append("source field definition must be documented before use as a factor")
    denominator = _denominator_for_metric(metric, formula)
    if denominator is not None:
        rules.append(f"{denominator} must be non-zero")
        rules.append(f"{denominator} must not be near zero")
    if metric in {"roe", "debt_to_equity", "net_debt_to_equity", "outstanding_claims_reserves_to_equity"}:
        rules.append("equity must be positive")
    if metric in {"ebitda_ev", "net_debt_to_ebitda", "ebitda_interest_coverage", "capex_to_ebitda", "cfo_to_ebitda", "fcf_to_ebitda"}:
        rules.append("ebitda must be positive")
    if metric in {"ebit_ev", "interest_coverage"}:
        rules.append("ebit must be positive")
    if metric in {"operating_cf_to_net_income", "free_cash_flow_to_net_income", "equity_method_income_to_net_income"}:
        rules.append("net_income must be positive and economically meaningful")
    if metric in {"ebit_ev", "ebitda_ev", "fcf_yield", "earnings_yield", "book_to_price", "enterprise_value"}:
        rules.append("market cap must be positive")
    if metric.endswith("_growth_yoy") or metric.endswith("_growth_spread"):
        rules.append("four-quarter historical base must exist")
        rules.append("base value should be positive for percentage-growth interpretation")
    if metric.endswith("_stability"):
        rules.append("minimum rolling history must exist")
    return tuple(dict.fromkeys(rules))


def _flags_for_metric(metric: str, formula: str) -> tuple[str, ...]:
    flags = [FLAG_MISSING_INPUT, FLAG_PROFILE_MISMATCH]
    denominator = _denominator_for_metric(metric, formula)
    if denominator is not None:
        flags.extend([FLAG_ZERO_DENOMINATOR, FLAG_SMALL_DENOMINATOR])
    if "equity" in formula and metric in {"roe", "debt_to_equity", "net_debt_to_equity", "outstanding_claims_reserves_to_equity"}:
        flags.append(FLAG_NON_POSITIVE_EQUITY)
    if "ebitda" in formula:
        flags.append(FLAG_NON_POSITIVE_EBITDA)
    if metric in {"ebit_ev", "interest_coverage"}:
        flags.append(FLAG_NON_POSITIVE_EBIT)
    if "net_income" in formula:
        flags.append(FLAG_NON_POSITIVE_NET_INCOME)
    if "pd" in formula or "market cap" in formula:
        flags.append(FLAG_INVALID_MARKET_CAP)
    if metric.endswith("_growth_yoy") or metric.endswith("_growth_spread"):
        flags.extend([FLAG_INSUFFICIENT_HISTORY, FLAG_NON_POSITIVE_BASE_VALUE])
    if metric.endswith("_stability"):
        flags.append(FLAG_INSUFFICIENT_HISTORY)
    flags.append(FLAG_LOW_DATA_COVERAGE)
    return tuple(dict.fromkeys(flags))


def _production_decision_for_metric(metric: str) -> str:
    if metric in NEEDS_DEFINITION_METRICS:
        return DECISION_NEEDS_DEFINITION
    if metric == "npl_coverage_ratio":
        return DECISION_PROFILE_ROUTING
    return DECISION_FINALIZE_NOW


def _route_decision_for_metric(metric: str, applicable_profiles: tuple[str, ...]) -> str:
    if metric in PROFILE_ROUTE_DECISIONS:
        return PROFILE_ROUTE_DECISIONS[metric][0]
    return "|".join(applicable_profiles)


def _route_reason_for_metric(metric: str) -> str:
    if metric in PROFILE_ROUTE_DECISIONS:
        return PROFILE_ROUTE_DECISIONS[metric][1]
    return ""


def _registry_notes(metric: str, production_decision: str) -> str:
    if production_decision == DECISION_NEEDS_DEFINITION:
        return "Source field can be used as an input, but definition is required before using it as a factor metric."
    if production_decision == DECISION_PROFILE_ROUTING:
        return "Profile route is explicit; metric remains decision-required only if status or audit flags require it."
    if metric in {"roe", "roa", "net_interest_margin"}:
        return "Review average-balance convention before changing the formula implementation."
    if "capex" in metric or "financing_expense" in metric:
        return "Sign convention relies on current abs() treatment in the calculation layer."
    return "Dry-run registry; does not mutate factor values."


def _denominator_for_metric(metric: str, formula: str) -> str | None:
    explicit = {
        "roe": "equity",
        "roa": "total_assets",
        "equity_to_assets": "total_assets",
        "cash_to_assets": "total_assets",
        "debt_to_equity": "equity",
        "net_debt_to_equity": "equity",
        "net_debt_to_ebitda": "ebitda",
        "operating_cf_to_net_income": "net_income",
        "free_cash_flow_to_net_income": "net_income",
        "loan_to_deposit": "deposits",
        "net_interest_margin": "average_assets",
        "npl_ratio": "loans",
        "npl_coverage_ratio": "non_performing_loans",
        "ebit_ev": "enterprise_value",
        "ebitda_ev": "enterprise_value",
        "fcf_yield": "pd",
        "earnings_yield": "pd",
        "book_to_price": "pd",
        "roic": "invested_capital",
    }
    if metric in explicit:
        return explicit[metric]
    if "/" not in formula:
        return None
    return formula.split("/", 1)[1].split()[0].strip("()")


def build_metric_registry() -> pd.DataFrame:
    """Return a production metric registry for all currently calculated metrics."""
    formula_specs = _formula_specs()
    metrics = [
        metric
        for metric in dict.fromkeys(list(FACTOR_COLUMNS) + list(MULTIFACTOR_COLUMNS))
        if metric not in NON_METRIC_COLUMNS
    ]
    rows: list[dict[str, object]] = []
    for metric in metrics:
        formula, required_inputs, time_basis = formula_specs.get(
            metric,
            ("current output column; formula pending registry review", (), "unspecified"),
        )
        schema_metric = _SCHEMA_METRIC_BY_NAME.get(metric)
        status = schema_metric.status if schema_metric is not None else "active"
        production_decision = _production_decision_for_metric(metric)
        applicable_profiles = _profiles_for_metric(metric)
        rows.append(
            MetricRegistryEntry(
                metric_name=metric,
                factor_family=_factor_family_for_metric(metric),
                metric_role=_metric_role_for_metric(metric),
                profile_scope=_profile_scope_for_metric(metric, applicable_profiles),
                applicable_profiles=applicable_profiles,
                formula=formula,
                required_inputs=required_inputs,
                time_basis=time_basis,
                direction=_direction_for_metric(metric),
                validity_rules=_validity_rules(metric, required_inputs, formula),
                missing_policy="set metric to NaN; keep observation",
                outlier_policy="audit/winsorize only after economic validity",
                flags=_flags_for_metric(metric, formula),
                status=status,
                production_decision=production_decision,
                route_decision=_route_decision_for_metric(metric, applicable_profiles),
                route_reason=_route_reason_for_metric(metric),
                not_applicable_policy=FLAG_PROFILE_MISMATCH,
                decision_required=(
                    status != "active"
                    or production_decision != DECISION_FINALIZE_NOW
                    or formula == "current output column; formula pending registry review"
                ),
                notes=_registry_notes(metric, production_decision),
            ).__dict__
        )
    return pd.DataFrame.from_records(rows)


def _joined(values: Iterable[object]) -> str:
    return "|".join(str(value) for value in values)


def registry_to_frame(registry: pd.DataFrame) -> pd.DataFrame:
    """Return a CSV-friendly registry frame."""
    result = registry.copy()
    for column in ("applicable_profiles", "required_inputs", "validity_rules", "flags"):
        if column in result.columns:
            result[column] = result[column].map(lambda values: _joined(values) if isinstance(values, tuple) else values)
    return result


def _profile_series(frame: pd.DataFrame, profile_column: str) -> pd.Series:
    if profile_column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="string")
    return frame[profile_column].map(_normalize_profile)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _required_inputs_present(frame: pd.DataFrame, inputs: Sequence[str]) -> pd.Series:
    if not inputs:
        return pd.Series(True, index=frame.index)
    present = pd.Series(True, index=frame.index)
    for column in inputs:
        alternatives = [part.strip() for part in str(column).split("|") if part.strip()]
        if len(alternatives) > 1:
            alternative_present = pd.Series(False, index=frame.index)
            for alternative in alternatives:
                if alternative in frame.columns:
                    alternative_present |= frame[alternative].notna()
            present &= alternative_present
        elif column not in frame.columns:
            present &= False
        else:
            present &= frame[column].notna()
    return present


def _economic_flags(
    frame: pd.DataFrame,
    metric: str,
    *,
    small_denominator_abs: float,
    net_income_relative_threshold: float,
) -> pd.Series:
    flags = pd.Series("", index=frame.index, dtype="object")

    def add(mask: pd.Series, flag: str) -> None:
        nonlocal flags
        clean_mask = mask.fillna(False)
        flags.loc[clean_mask] = flags.loc[clean_mask].map(lambda current: f"{current}|{flag}" if current else flag)

    if metric in {"roe", "debt_to_equity", "net_debt_to_equity", "outstanding_claims_reserves_to_equity"}:
        add(_numeric(frame, "equity").le(0), FLAG_NON_POSITIVE_EQUITY)
    if metric in {"ebitda_ev", "net_debt_to_ebitda", "ebitda_interest_coverage", "capex_to_ebitda", "cfo_to_ebitda", "fcf_to_ebitda"}:
        add(_numeric(frame, "ebitda").le(0), FLAG_NON_POSITIVE_EBITDA)
    if metric in {"ebit_ev", "interest_coverage"}:
        add(_numeric(frame, "ebit").le(0), FLAG_NON_POSITIVE_EBIT)
    if metric in {"operating_cf_to_net_income", "free_cash_flow_to_net_income", "equity_method_income_to_net_income"}:
        net_income = _numeric(frame, "net_income")
        add(net_income.le(0), FLAG_NON_POSITIVE_NET_INCOME)
        assets = _numeric(frame, "total_assets").abs().replace(0, np.nan)
        sales = _numeric(frame, "sales").abs().replace(0, np.nan)
        ni_to_assets = net_income.abs() / assets
        ni_to_sales = net_income.abs() / sales
        small = ni_to_assets.lt(net_income_relative_threshold)
        small = small | (sales.notna() & ni_to_sales.lt(net_income_relative_threshold))
        add(small, FLAG_SMALL_DENOMINATOR)
    if metric in {"ebit_ev", "ebitda_ev", "fcf_yield", "earnings_yield", "book_to_price"}:
        add(_numeric(frame, "pd").le(0), FLAG_INVALID_MARKET_CAP)
    if metric in {"close", "dolar_bazli_fiyat"}:
        add(_numeric(frame, metric).le(0), FLAG_INVALID_MARKET_PRICE)
    if metric in {"pd", "pd_usd", "hao_pd", "hao_pd_usd"}:
        add(_numeric(frame, metric).le(0), FLAG_INVALID_MARKET_CAP)
    if metric == "enterprise_value":
        add(_numeric(frame, "pd").le(0), FLAG_INVALID_MARKET_CAP)
        add(_numeric(frame, "enterprise_value").le(0), FLAG_ZERO_DENOMINATOR)
    denominator = _denominator_for_metric(metric, _formula_specs().get(metric, ("", (), ""))[0])
    if denominator and denominator in frame.columns:
        denominator_values = _numeric(frame, denominator)
        add(denominator_values.eq(0), FLAG_ZERO_DENOMINATOR)
        add(denominator_values.abs().le(small_denominator_abs) & denominator_values.ne(0), FLAG_SMALL_DENOMINATOR)
    if metric.endswith("_growth_yoy") or metric.endswith("_growth_spread"):
        base_column = _growth_base_column(metric)
        if base_column is not None and base_column in frame.columns:
            base = _numeric(frame, base_column).groupby(frame.get("symbol", pd.Series("", index=frame.index)).astype("string"), sort=False).shift(4)
            add(base.isna(), FLAG_INSUFFICIENT_HISTORY)
            add(base.le(0), FLAG_NON_POSITIVE_BASE_VALUE)
    if metric.endswith("_stability"):
        valid_history = _numeric(frame, metric).notna()
        add(~valid_history, FLAG_INSUFFICIENT_HISTORY)
    return flags


def _growth_base_column(metric: str) -> str | None:
    return {
        "net_income_growth_yoy": "net_income",
        "asset_growth_yoy": "total_assets",
        "equity_growth_yoy": "equity",
        "gross_premium_growth_yoy": "non_life_gross_written_premiums",
        "revenue_growth_yoy": "sales",
        "ebit_growth_yoy": "ebit",
        "ebitda_growth_yoy": "ebitda",
        "inventory_growth_spread": "inventory",
        "receivables_growth_spread": "trade_receivables",
        "working_capital_growth_yoy": "working_capital",
        "capex_growth_yoy": "capex",
    }.get(metric)


def build_metric_validity_audit(
    frame: pd.DataFrame,
    *,
    registry: pd.DataFrame | None = None,
    profile_column: str = "selected_profile",
    small_denominator_abs: float = DEFAULT_SMALL_DENOMINATOR_ABS,
    net_income_relative_threshold: float = DEFAULT_NET_INCOME_RELATIVE_THRESHOLD,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> pd.DataFrame:
    """Dry-run economic validity rules and summarize affected observations."""
    registry = build_metric_registry() if registry is None else registry.copy()
    profiles = _profile_series(frame, profile_column)
    rows: list[dict[str, object]] = []
    total = len(frame)
    for entry in registry.itertuples(index=False):
        metric = entry.metric_name
        applicable_profiles = set(entry.applicable_profiles)
        metric_values = _numeric(frame, metric)
        applicable = profiles.isin(applicable_profiles) if applicable_profiles else pd.Series(True, index=frame.index)
        input_present = _required_inputs_present(frame, entry.required_inputs)
        economic_flags = _economic_flags(
            frame,
            metric,
            small_denominator_abs=small_denominator_abs,
            net_income_relative_threshold=net_income_relative_threshold,
        )
        has_economic_flag = economic_flags.ne("")
        valid = applicable & input_present & ~has_economic_flag & metric_values.notna()
        missing = applicable & ~input_present
        not_applicable = ~applicable
        invalid = applicable & input_present & has_economic_flag
        existing_non_null = metric_values.notna()
        removed = existing_non_null & ~valid
        coverage = float(existing_non_null.sum() / total) if total else 0.0
        flags = _flag_breakdown(economic_flags.loc[invalid])
        if coverage < coverage_threshold:
            flags = _append_flag_count(flags, FLAG_LOW_DATA_COVERAGE, int(existing_non_null.sum()))
        rows.append(
            {
                "metric_name": metric,
                "factor_family": entry.factor_family,
                "metric_role": entry.metric_role,
                "profile_scope": entry.profile_scope,
                "status": entry.status,
                "production_decision": entry.production_decision,
                "total_observations": int(total),
                "before_validity_count": int(existing_non_null.sum()),
                "after_validity_count": int(valid.sum()),
                "removed_count": int(removed.sum()),
                "removed_pct": float((removed.sum() / existing_non_null.sum()) * 100) if existing_non_null.sum() else 0.0,
                "valid_count": int(valid.sum()),
                "missing_count": int(missing.sum()),
                "not_applicable_count": int(not_applicable.sum()),
                "invalid_count": int(invalid.sum()),
                "invalid_rate": float(invalid.sum() / max(int(applicable.sum()), 1)),
                "flag_breakdown": flags,
                **_distribution_stats(metric_values, "before"),
                **_distribution_stats(metric_values.where(valid), "after"),
                "decision_required": bool(entry.decision_required or invalid.sum() > 0 or removed.sum() > 0),
            }
        )
    return pd.DataFrame.from_records(rows)


def apply_metric_validity(
    frame: pd.DataFrame,
    *,
    registry: pd.DataFrame | None = None,
    profile_column: str = "selected_profile",
    small_denominator_abs: float = DEFAULT_SMALL_DENOMINATOR_ABS,
    net_income_relative_threshold: float = DEFAULT_NET_INCOME_RELATIVE_THRESHOLD,
    include_experimental: bool = False,
) -> pd.DataFrame:
    """Apply production economic-validity rules and add metric diagnostics.

    Source fields are intentionally skipped. Invalid factor metrics are set to
    NaN, while row-level diagnostics are preserved in `<metric>_valid`,
    `<metric>_flag`, and `<metric>_status` columns.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("apply_metric_validity() expects a DataFrame.")
    if frame.empty:
        return frame.copy()

    registry = build_metric_registry() if registry is None else registry.copy()
    result = frame.copy()
    profiles = _profile_series(result, profile_column)
    diagnostics: dict[str, pd.Series] = {}

    for entry in registry.itertuples(index=False):
        metric = entry.metric_name
        if entry.metric_role != ROLE_FACTOR_METRIC:
            continue
        if entry.status != "active" and not include_experimental:
            continue
        if metric not in result.columns:
            continue

        applicable_profiles = set(entry.applicable_profiles)
        applicable = profiles.isin(applicable_profiles) if applicable_profiles else pd.Series(True, index=result.index)
        input_present = _required_inputs_present(result, entry.required_inputs)
        economic_flags = _economic_flags(
            result,
            metric,
            small_denominator_abs=small_denominator_abs,
            net_income_relative_threshold=net_income_relative_threshold,
        )
        has_economic_flag = economic_flags.ne("")
        metric_values = _numeric(result, metric)
        value_present = metric_values.notna()
        valid = applicable & input_present & ~has_economic_flag & value_present

        flags = pd.Series("", index=result.index, dtype="object")
        statuses = pd.Series(STATUS_VALID, index=result.index, dtype="object")
        not_applicable = ~applicable
        missing_input = applicable & ~input_present
        missing_value = applicable & input_present & ~has_economic_flag & ~value_present
        invalid_economic = applicable & input_present & has_economic_flag

        flags.loc[not_applicable] = FLAG_PROFILE_MISMATCH
        statuses.loc[not_applicable] = STATUS_NOT_APPLICABLE
        flags.loc[missing_input | missing_value] = FLAG_MISSING_INPUT
        statuses.loc[missing_input | missing_value] = STATUS_MISSING_INPUT
        flags.loc[invalid_economic] = economic_flags.loc[invalid_economic]
        statuses.loc[invalid_economic] = STATUS_INVALID_ECONOMIC

        result.loc[:, metric] = metric_values.where(valid)
        diagnostics[f"{metric}_valid"] = valid.astype("boolean")
        diagnostics[f"{metric}_flag"] = flags
        diagnostics[f"{metric}_status"] = statuses

    if diagnostics:
        result = pd.concat([result, pd.DataFrame(diagnostics, index=result.index)], axis=1)
    return result


def _distribution_stats(values: pd.Series, prefix: str) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    finite = numeric.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return {f"{prefix}_{name}": np.nan for name in ("min", "p1", "median", "p99", "max")}
    return {
        f"{prefix}_min": float(finite.min()),
        f"{prefix}_p1": float(finite.quantile(0.01)),
        f"{prefix}_median": float(finite.median()),
        f"{prefix}_p99": float(finite.quantile(0.99)),
        f"{prefix}_max": float(finite.max()),
    }


def _flag_breakdown(flags: pd.Series) -> str:
    counts: dict[str, int] = {}
    for value in flags.dropna().astype(str):
        for flag in [part for part in value.split("|") if part]:
            counts[flag] = counts.get(flag, 0) + 1
    return "|".join(f"{flag}:{count}" for flag, count in sorted(counts.items()))


def _append_flag_count(existing: str, flag: str, count: int) -> str:
    return f"{existing}|{flag}:{count}" if existing else f"{flag}:{count}"


def build_net_income_denominator_sensitivity(
    frame: pd.DataFrame,
    *,
    thresholds: Sequence[float] = DEFAULT_THRESHOLD_SENSITIVITY,
    metrics: Sequence[str] = ("operating_cf_to_net_income", "free_cash_flow_to_net_income"),
) -> pd.DataFrame:
    """Report how many cash-quality observations fail relative denominator thresholds."""
    rows: list[dict[str, object]] = []
    net_income = _numeric(frame, "net_income")
    assets = _numeric(frame, "total_assets").abs().replace(0, np.nan)
    sales = _numeric(frame, "sales").abs().replace(0, np.nan)
    for metric in metrics:
        values = _numeric(frame, metric)
        existing = values.notna()
        for threshold in thresholds:
            ni_to_assets = net_income.abs() / assets
            ni_to_sales = net_income.abs() / sales
            small = ni_to_assets.lt(threshold)
            small = small | (sales.notna() & ni_to_sales.lt(threshold))
            affected = existing & small.fillna(False)
            rows.append(
                {
                    "metric_name": metric,
                    "threshold": threshold,
                    "before_validity_count": int(existing.sum()),
                    "affected_count": int(affected.sum()),
                    "affected_pct": float((affected.sum() / existing.sum()) * 100) if existing.sum() else 0.0,
                }
            )
    return pd.DataFrame.from_records(rows)


def _production_tier_reason(row: pd.Series) -> tuple[str, str]:
    if row["metric_role"] == ROLE_SOURCE_FIELD:
        return TIER_SOURCE_FIELD, "Source field; usable as an input, not as a standalone factor metric."
    if row["status"] != "active":
        return TIER_EXCLUDE_OR_EXPERIMENTAL, "Metric is not active in the factor schema."
    if row["production_decision"] != DECISION_FINALIZE_NOW:
        return TIER_EXCLUDE_OR_EXPERIMENTAL, "Metric still requires a production decision."

    before_count = int(row.get("before_validity_count", 0) or 0)
    after_count = int(row.get("after_validity_count", 0) or 0)
    removed_pct = float(row.get("removed_pct", 0.0) or 0.0)
    total = int(row.get("total_observations", 0) or 0)
    valid_coverage = after_count / total if total else 0.0

    if before_count == 0 or after_count == 0:
        return TIER_EXCLUDE_OR_EXPERIMENTAL, "No valid observations after economic validity filtering."
    if removed_pct >= DEFAULT_OPTIONAL_REMOVAL_THRESHOLD:
        return TIER_EXCLUDE_OR_EXPERIMENTAL, "Too many existing observations are removed by validity rules."
    if valid_coverage < DEFAULT_OPTIONAL_VALID_COVERAGE_THRESHOLD:
        return TIER_EXCLUDE_OR_EXPERIMENTAL, "Valid observation coverage is too low for production scoring."
    if removed_pct > DEFAULT_CORE_REMOVAL_THRESHOLD:
        return TIER_PRODUCTION_OPTIONAL, "Some observations are removed by validity rules; keep as monitored optional metric."
    if valid_coverage < DEFAULT_CORE_VALID_COVERAGE_THRESHOLD:
        return TIER_PRODUCTION_OPTIONAL, "Coverage is below core threshold; keep as optional metric."
    return TIER_PRODUCTION_CORE, "Active metric with sufficient coverage and low validity-rule removal."


def build_metric_production_tiers(
    audit: pd.DataFrame,
    *,
    registry: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Classify metrics into production core, optional, or excluded tiers."""
    if not isinstance(audit, pd.DataFrame):
        raise TypeError("build_metric_production_tiers() expects an audit DataFrame.")
    if audit.empty:
        return pd.DataFrame(
            columns=[
                "metric_name",
                "factor_family",
                "metric_role",
                "profile_scope",
                "status",
                "production_decision",
                "production_tier",
                "tier_reason",
                "before_validity_count",
                "after_validity_count",
                "removed_pct",
                "valid_coverage_pct",
                "flag_breakdown",
            ]
        )

    registry_frame = registry_to_frame(build_metric_registry() if registry is None else registry)
    metadata_columns = [
        "metric_name",
        "applicable_profiles",
        "required_inputs",
        "formula",
        "route_decision",
        "route_reason",
        "notes",
    ]
    merged = audit.merge(
        registry_frame[metadata_columns],
        on="metric_name",
        how="left",
    )
    tiers = merged.apply(_production_tier_reason, axis=1, result_type="expand")
    merged["production_tier"] = tiers[0]
    merged["tier_reason"] = tiers[1]
    total = pd.to_numeric(merged["total_observations"], errors="coerce").replace(0, np.nan)
    merged["valid_coverage_pct"] = pd.to_numeric(merged["after_validity_count"], errors="coerce") / total * 100
    columns = [
        "metric_name",
        "factor_family",
        "metric_role",
        "profile_scope",
        "applicable_profiles",
        "status",
        "production_decision",
        "production_tier",
        "tier_reason",
        "before_validity_count",
        "after_validity_count",
        "removed_count",
        "removed_pct",
        "valid_coverage_pct",
        "invalid_count",
        "flag_breakdown",
        "required_inputs",
        "formula",
        "route_decision",
        "route_reason",
        "notes",
    ]
    return merged[columns].sort_values(
        ["production_tier", "factor_family", "metric_name"],
        kind="mergesort",
    ).reset_index(drop=True)


def build_metric_registry_reports(frame: pd.DataFrame) -> Mapping[str, pd.DataFrame]:
    """Build dry-run reports without mutating metric values."""
    registry = build_metric_registry()
    audit = build_metric_validity_audit(frame, registry=registry)
    registry_csv = registry_to_frame(registry)
    production_tiers = build_metric_production_tiers(audit, registry=registry)
    decision_required = audit.loc[audit["decision_required"].eq(True)].merge(
        registry_csv[
            [
                "metric_name",
                "applicable_profiles",
                "formula",
                "required_inputs",
                "validity_rules",
                "missing_policy",
                "outlier_policy",
                "flags",
                "notes",
            ]
        ],
        on="metric_name",
        how="left",
    )
    return {
        "metric_registry": registry_csv,
        "metric_validity_audit": audit,
        "metric_production_tiers": production_tiers,
        "metric_decision_required": decision_required,
        "metric_source_fields": registry_csv.loc[registry_csv["metric_role"].eq(ROLE_SOURCE_FIELD)].reset_index(drop=True),
        "metric_profile_routing": registry_csv.loc[
            registry_csv["profile_scope"].eq(PROFILE_SCOPE_PROFILE_ROUTED)
        ].reset_index(drop=True),
        "metric_denominator_sensitivity": build_net_income_denominator_sensitivity(frame),
    }
