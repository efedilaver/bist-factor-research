"""Financial factor helpers built from snapshot data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.isyatirim.profiles import BaseProfile, get_profile, select_profile_from_frame
from src.utils.dates import period_parts, period_to_timestamp
from src.utils.normalization import normalize_numeric_value


COMMON_FACTOR_COLUMNS = [
    "roe",
    "roa",
    "equity_to_assets",
    "cash_to_assets",
    "net_income_growth_yoy",
    "asset_growth_yoy",
    "equity_growth_yoy",
]

PROFILE_FACTOR_COLUMNS = [
    "debt_to_equity",
    "net_debt_to_equity",
    "net_debt_to_ebitda",
    "operating_cf_to_net_income",
    "free_cash_flow_to_net_income",
]

BANK_FACTOR_COLUMNS = [
    "loans_to_assets",
    "deposits_to_assets",
    "loan_to_deposit",
    "net_interest_margin",
    "fee_income_to_operating_income",
    "cost_to_income",
    "provision_expense_to_loans",
    "npl_ratio",
    "npl_coverage_ratio",
]

INSURANCE_FACTOR_COLUMNS = [
    "gross_premium_growth_yoy",
    "retention_ratio",
    "loss_ratio",
    "expense_ratio",
    "combined_ratio",
    "technical_profit_margin",
    "technical_reserves_to_assets",
    "outstanding_claims_reserves_to_equity",
]

HOLDING_FACTOR_COLUMNS = [
    "operating_profit_margin",
    "gross_profit_margin",
    "financial_investments_to_assets",
    "equity_method_investments_to_assets",
    "equity_method_income_to_net_income",
    "financing_expense_to_sales",
    "capex_to_sales",
]

INDUSTRIAL_FACTOR_COLUMNS = [
    "revenue_growth_yoy",
    "ebit_growth_yoy",
    "ebitda_growth_yoy",
    "gross_margin",
    "ebit_margin",
    "ebitda_margin",
    "net_profit_margin",
    "dso",
    "dio",
    "dpo",
    "cash_conversion_cycle",
    "current_ratio",
    "quick_ratio",
    "financial_debt_to_assets",
    "interest_coverage",
    "ebitda_interest_coverage",
    "asset_turnover",
    "fixed_asset_turnover",
    "capex_to_revenue",
    "capex_to_ebitda",
    "capex_to_depreciation",
    "cfo_margin",
    "cfo_to_ebitda",
    "fcf_margin",
    "fcf_to_ebitda",
    "inventory_to_revenue",
    "receivables_to_revenue",
    "payables_to_cost_of_sales",
    "inventory_growth_spread",
    "receivables_growth_spread",
    "rd_to_revenue",
    "selling_expense_ratio",
    "ga_expense_ratio",
    "operating_expense_ratio",
    "depreciation_to_revenue",
    "ppe_to_assets",
    "ppe_to_revenue",
    "cash_to_debt",
    "export_ratio",
]

FACTOR_COLUMNS = (
    COMMON_FACTOR_COLUMNS
    + PROFILE_FACTOR_COLUMNS
    + BANK_FACTOR_COLUMNS
    + INSURANCE_FACTOR_COLUMNS
    + HOLDING_FACTOR_COLUMNS
    + INDUSTRIAL_FACTOR_COLUMNS
)
IDENTIFIER_COLUMNS = ["symbol", "period", "selected_profile", "financial_group", "sector", "sub_sector"]
PROFILE_FACTOR_COLUMN_MAP = {
    "bank": COMMON_FACTOR_COLUMNS + BANK_FACTOR_COLUMNS,
    "katilim_bank": COMMON_FACTOR_COLUMNS + BANK_FACTOR_COLUMNS,
    "industrial": COMMON_FACTOR_COLUMNS + PROFILE_FACTOR_COLUMNS + INDUSTRIAL_FACTOR_COLUMNS,
    "holding": COMMON_FACTOR_COLUMNS + PROFILE_FACTOR_COLUMNS + HOLDING_FACTOR_COLUMNS,
    "reit": COMMON_FACTOR_COLUMNS + PROFILE_FACTOR_COLUMNS,
    "insurance": COMMON_FACTOR_COLUMNS + INSURANCE_FACTOR_COLUMNS,
    "leasing": COMMON_FACTOR_COLUMNS,
}

DEBT_FACTOR_PROFILES = {"industrial", "holding", "reit"}
CASH_FLOW_FACTOR_PROFILES = {"industrial", "holding", "reit"}
BANK_FACTOR_PROFILES = {"bank", "katilim_bank"}

BANK_BALANCE_FIELDS = [
    "loans",
    "non_performing_loans",
    "loan_loss_allowance",
    "deposits",
]

BANK_FLOW_FIELDS = [
    "interest_income",
    "interest_expense",
    "net_interest_income",
    "net_fee_commission_income",
    "total_operating_income",
    "provision_expense",
    "operating_expenses",
]

INSURANCE_BALANCE_FIELDS = [
    "current_technical_reserves",
    "long_technical_reserves",
    "current_outstanding_claims_reserves",
    "long_outstanding_claims_reserves",
]

INSURANCE_FLOW_FIELDS = [
    "non_life_net_earned_premiums",
    "non_life_net_written_premiums",
    "non_life_gross_written_premiums",
    "non_life_net_claims",
    "non_life_operating_expenses",
    "non_life_technical_profit",
    "life_net_earned_premiums",
    "life_net_written_premiums",
    "life_gross_written_premiums",
    "life_net_claims",
    "life_operating_expenses",
    "life_technical_profit",
    "total_technical_profit",
]

HOLDING_BALANCE_FIELDS = [
    "short_term_financial_investments",
    "long_term_financial_investments",
    "equity_method_investments",
]

HOLDING_FLOW_FIELDS = [
    "sales",
    "gross_profit",
    "equity_method_income",
    "financing_expenses",
    "capex",
]

INDUSTRIAL_BALANCE_FIELDS = [
    "current_assets",
    "current_liabilities",
    "trade_receivables",
    "inventory",
    "trade_payables",
    "property_plant_equipment",
]

INDUSTRIAL_FLOW_FIELDS = [
    "sales",
    "cost_of_sales",
    "gross_profit",
    "selling_marketing_expenses",
    "general_admin_expenses",
    "research_development_expenses",
    "financing_expenses",
    "export_revenue",
    "capex",
]

PROFILE_RAW_FIELDS = set(
    BANK_BALANCE_FIELDS
    + BANK_FLOW_FIELDS
    + INSURANCE_BALANCE_FIELDS
    + INSURANCE_FLOW_FIELDS
    + HOLDING_BALANCE_FIELDS
    + HOLDING_FLOW_FIELDS
    + INDUSTRIAL_BALANCE_FIELDS
    + INDUSTRIAL_FLOW_FIELDS
)
PROFILE_FLOW_FIELDS = list(
    dict.fromkeys(BANK_FLOW_FIELDS + INSURANCE_FLOW_FIELDS + HOLDING_FLOW_FIELDS + INDUSTRIAL_FLOW_FIELDS)
)

RAW_ITEM_CODE_COLUMN = "FINANCIAL_ITEM_CODE"
SYMBOL_COLUMN = "SYMBOL"
PERIOD_SEPARATOR = "/"


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def safe_divide(numerator: object, denominator: object) -> pd.Series:
    """Divide numeric series while converting zero and infinite results to NaN."""
    left = pd.to_numeric(numerator, errors="coerce")
    right = pd.to_numeric(denominator, errors="coerce")
    result = left / right.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _profile_mask(frame: pd.DataFrame, profile_column: str, profiles: set[str]) -> pd.Series:
    if profile_column not in frame.columns:
        return pd.Series(False, index=frame.index)
    normalized = frame[profile_column].astype("string").str.lower()
    return normalized.isin(profiles).fillna(False)


def _yoy_growth(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    if "symbol" not in frame.columns:
        return values.pct_change(4).replace([np.inf, -np.inf], np.nan)
    return (
        values.groupby(frame["symbol"].astype("string"), sort=False)
        .pct_change(4)
        .replace([np.inf, -np.inf], np.nan)
    )


def _profile_for_financials(financials: pd.DataFrame) -> BaseProfile:
    # Raw caches can contain stale profile metadata after mapping upgrades.
    # Re-score the actual itemCode structure so V2 factors reflect the data.
    detected_profile = select_profile_from_frame(financials)
    if detected_profile.score_frame(financials) > 0:
        return detected_profile

    profile_name = financials.attrs.get("isyatirim_profile")
    if isinstance(profile_name, str) and profile_name:
        try:
            return get_profile(profile_name)
        except KeyError:
            pass
    return detected_profile


def _period_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(
        [column for column in frame.columns if isinstance(column, str) and column.count(PERIOD_SEPARATOR) == 1],
        key=period_parts,
    )


def _value_for_raw_code(table: pd.DataFrame, raw_code: str | None, period: str) -> object | None:
    if raw_code is None or raw_code not in table.index:
        return None
    row = table.loc[raw_code]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    if period not in row.index:
        return None
    return normalize_numeric_value(row[period])


def _extract_profile_raw_fields(financials: pd.DataFrame) -> pd.DataFrame:
    if financials is None or financials.empty:
        return pd.DataFrame()
    if RAW_ITEM_CODE_COLUMN not in financials.columns:
        return pd.DataFrame()

    profile = _profile_for_financials(financials)
    symbol_column = SYMBOL_COLUMN if SYMBOL_COLUMN in financials.columns else "symbol"
    if symbol_column not in financials.columns:
        return pd.DataFrame()

    symbol = str(financials[symbol_column].dropna().iloc[0]).strip().upper()
    periods = _period_columns(financials)
    if not periods:
        return pd.DataFrame()

    table = (
        financials.drop_duplicates(subset=[RAW_ITEM_CODE_COLUMN], keep="last")
        .set_index(RAW_ITEM_CODE_COLUMN)
    )
    canonical_map = profile.canonical_to_raw_map()
    fields = sorted(
        {
            field.lower()
            for field in canonical_map
            if field.lower() in PROFILE_RAW_FIELDS
        }
    )

    rows: list[dict[str, object | None]] = []
    for period in periods:
        row: dict[str, object | None] = {
            "symbol": symbol,
            "period": period_to_timestamp(period),
            "selected_profile": profile.name,
        }
        for field in fields:
            row[field] = _value_for_raw_code(table, canonical_map.get(field.upper()), period)
        rows.append(row)

    return pd.DataFrame(rows)


def _convert_profile_flows_to_quarterly(raw_fields: pd.DataFrame) -> pd.DataFrame:
    result = raw_fields.copy()
    if result.empty:
        return result
    result = result.sort_values(["symbol", "period"], kind="mergesort").reset_index(drop=True)
    result["_fiscal_year"] = result["period"].dt.year

    groups: list[pd.DataFrame] = []
    for _, group in result.groupby(["symbol", "_fiscal_year"], sort=False):
        group = group.reset_index(drop=True)
        for column in PROFILE_FLOW_FIELDS:
            if column not in group.columns:
                continue
            ytd_values = pd.to_numeric(group[column], errors="coerce")
            quarterly_values = ytd_values.copy()
            if len(ytd_values) >= 2:
                quarterly_values.iloc[1:] = ytd_values.iloc[1:].to_numpy() - ytd_values.iloc[:-1].to_numpy()
            group[column] = quarterly_values
        groups.append(group)

    if not groups:
        return result.drop(columns=["_fiscal_year"], errors="ignore")
    return pd.concat(groups, ignore_index=True).drop(columns=["_fiscal_year"], errors="ignore")


def _convert_profile_flows_to_mode(raw_fields: pd.DataFrame, mode: str | None) -> pd.DataFrame:
    if raw_fields.empty:
        return raw_fields

    normalized_mode = str(mode or "ytd").lower()
    if normalized_mode == "ytd":
        return raw_fields.copy()

    result = _convert_profile_flows_to_quarterly(raw_fields)
    if normalized_mode != "ttm":
        return result

    result = result.sort_values(["symbol", "period"], kind="mergesort").reset_index(drop=True)
    for column in PROFILE_FLOW_FIELDS:
        if column not in result.columns:
            continue
        result[column] = (
            pd.to_numeric(result[column], errors="coerce")
            .groupby(result["symbol"].astype("string"), sort=False)
            .rolling(window=4, min_periods=1)
            .sum()
            .reset_index(level=0, drop=True)
        )
    return result


def _average_balance(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric(frame, column)
    if "symbol" not in frame.columns:
        return values.rolling(window=2, min_periods=1).mean()
    previous = values.groupby(frame["symbol"].astype("string"), sort=False).shift(1)
    return (values + previous.fillna(values)) / 2


def _merge_profile_raw_fields(
    frame: pd.DataFrame,
    financials: pd.DataFrame | None,
    *,
    mode: str | None,
) -> pd.DataFrame:
    if financials is None or financials.empty:
        return frame
    raw_fields = _extract_profile_raw_fields(financials)
    if raw_fields.empty:
        return frame

    raw_fields = _convert_profile_flows_to_mode(raw_fields, mode)
    merge_keys = ["symbol", "period"]
    if not all(column in frame.columns for column in merge_keys):
        return frame

    raw_columns = [
        column
        for column in raw_fields.columns
        if column not in merge_keys and column not in frame.columns
    ]
    if not raw_columns:
        return frame
    return frame.merge(raw_fields[merge_keys + raw_columns], on=merge_keys, how="left", sort=False)


def add_common_financial_factors(frame: pd.DataFrame) -> pd.DataFrame:
    """Add profile-agnostic financial factors to a snapshot dataframe."""
    result = frame.copy()
    result["roe"] = safe_divide(_numeric(result, "net_income"), _numeric(result, "equity"))
    result["roa"] = safe_divide(_numeric(result, "net_income"), _numeric(result, "total_assets"))
    result["equity_to_assets"] = safe_divide(_numeric(result, "equity"), _numeric(result, "total_assets"))
    result["cash_to_assets"] = safe_divide(_numeric(result, "cash"), _numeric(result, "total_assets"))
    result["net_income_growth_yoy"] = _yoy_growth(result, "net_income")
    result["asset_growth_yoy"] = _yoy_growth(result, "total_assets")
    result["equity_growth_yoy"] = _yoy_growth(result, "equity")
    return result


def add_profile_financial_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add factors that should only be interpreted for specific company profiles."""
    result = frame.copy()
    debt_mask = _profile_mask(result, profile_column, DEBT_FACTOR_PROFILES)
    cash_flow_mask = _profile_mask(result, profile_column, CASH_FLOW_FACTOR_PROFILES)

    result["debt_to_equity"] = safe_divide(_numeric(result, "total_debt"), _numeric(result, "equity")).where(debt_mask)
    result["net_debt_to_equity"] = safe_divide(_numeric(result, "net_debt"), _numeric(result, "equity")).where(debt_mask)
    result["net_debt_to_ebitda"] = safe_divide(_numeric(result, "net_debt"), _numeric(result, "ebitda")).where(cash_flow_mask)
    result["operating_cf_to_net_income"] = safe_divide(
        _numeric(result, "operating_cash_flow"),
        _numeric(result, "net_income"),
    ).where(cash_flow_mask)
    result["free_cash_flow_to_net_income"] = safe_divide(
        _numeric(result, "free_cash_flow"),
        _numeric(result, "net_income"),
    ).where(cash_flow_mask)
    return result


def add_bank_financial_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add bank-specific V2 factors when the required raw fields are available."""
    result = frame.copy()
    bank_mask = _profile_mask(result, profile_column, BANK_FACTOR_PROFILES)
    average_assets = _average_balance(result, "total_assets")

    result["loans_to_assets"] = safe_divide(_numeric(result, "loans"), _numeric(result, "total_assets")).where(bank_mask)
    result["deposits_to_assets"] = safe_divide(_numeric(result, "deposits"), _numeric(result, "total_assets")).where(bank_mask)
    result["loan_to_deposit"] = safe_divide(_numeric(result, "loans"), _numeric(result, "deposits")).where(bank_mask)
    result["net_interest_margin"] = safe_divide(_numeric(result, "net_interest_income"), average_assets).where(bank_mask)
    result["fee_income_to_operating_income"] = safe_divide(
        _numeric(result, "net_fee_commission_income"),
        _numeric(result, "total_operating_income"),
    ).where(bank_mask)
    result["cost_to_income"] = safe_divide(
        _numeric(result, "operating_expenses").abs(),
        _numeric(result, "total_operating_income"),
    ).where(bank_mask)
    result["provision_expense_to_loans"] = safe_divide(
        _numeric(result, "provision_expense").abs(),
        _numeric(result, "loans"),
    ).where(bank_mask)
    result["npl_ratio"] = safe_divide(
        _numeric(result, "non_performing_loans"),
        _numeric(result, "loans"),
    ).where(bank_mask)
    result["npl_coverage_ratio"] = safe_divide(
        _numeric(result, "loan_loss_allowance").abs(),
        _numeric(result, "non_performing_loans"),
    ).where(bank_mask)
    return result


def _sum_columns(frame: pd.DataFrame, columns: list[str], *, absolute: bool = False) -> pd.Series:
    result = pd.Series(0.0, index=frame.index, dtype="float64")
    has_value = pd.Series(False, index=frame.index)
    for column in columns:
        values = _numeric(frame, column)
        if absolute:
            values = values.abs()
        has_value = has_value | values.notna()
        result = result.add(values.fillna(0.0), fill_value=0.0)
    return result.where(has_value)


def add_insurance_financial_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add insurance-specific V2 factors when the required raw fields are available."""
    result = frame.copy()
    insurance_mask = _profile_mask(result, profile_column, {"insurance"})

    gross_premiums = _sum_columns(
        result,
        ["non_life_gross_written_premiums", "life_gross_written_premiums"],
        absolute=True,
    )
    net_written_premiums = _sum_columns(
        result,
        ["non_life_net_written_premiums", "life_net_written_premiums"],
    )
    net_earned_premiums = _sum_columns(
        result,
        ["non_life_net_earned_premiums", "life_net_earned_premiums"],
    )
    net_claims = _sum_columns(
        result,
        ["non_life_net_claims", "life_net_claims"],
        absolute=True,
    )
    operating_expenses = _sum_columns(
        result,
        ["non_life_operating_expenses", "life_operating_expenses"],
        absolute=True,
    )
    technical_profit = _numeric(result, "total_technical_profit")
    technical_profit = technical_profit.where(
        technical_profit.notna(),
        _sum_columns(result, ["non_life_technical_profit", "life_technical_profit"]),
    )
    technical_reserves = _sum_columns(
        result,
        ["current_technical_reserves", "long_technical_reserves"],
        absolute=True,
    )
    outstanding_claims_reserves = _sum_columns(
        result,
        ["current_outstanding_claims_reserves", "long_outstanding_claims_reserves"],
        absolute=True,
    )

    if "symbol" in result.columns:
        gross_premium_growth = (
            gross_premiums.groupby(result["symbol"].astype("string"), sort=False)
            .pct_change(4, fill_method=None)
            .replace([np.inf, -np.inf], np.nan)
        )
    else:
        gross_premium_growth = gross_premiums.pct_change(4, fill_method=None).replace([np.inf, -np.inf], np.nan)

    result["gross_premium_growth_yoy"] = gross_premium_growth.where(insurance_mask)
    result["retention_ratio"] = safe_divide(net_written_premiums, gross_premiums).where(insurance_mask)
    result["loss_ratio"] = safe_divide(net_claims, net_earned_premiums).where(insurance_mask)
    result["expense_ratio"] = safe_divide(operating_expenses, net_earned_premiums).where(insurance_mask)
    result["combined_ratio"] = (result["loss_ratio"] + result["expense_ratio"]).where(insurance_mask)
    result["technical_profit_margin"] = safe_divide(technical_profit, gross_premiums).where(insurance_mask)
    result["technical_reserves_to_assets"] = safe_divide(
        technical_reserves,
        _numeric(result, "total_assets"),
    ).where(insurance_mask)
    result["outstanding_claims_reserves_to_equity"] = safe_divide(
        outstanding_claims_reserves,
        _numeric(result, "equity"),
    ).where(insurance_mask)
    return result


def add_holding_financial_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add holding-specific V2 factors when the required raw fields are available."""
    result = frame.copy()
    holding_mask = _profile_mask(result, profile_column, {"holding"})
    financial_investments = _sum_columns(
        result,
        ["short_term_financial_investments", "long_term_financial_investments"],
    )

    result["operating_profit_margin"] = safe_divide(_numeric(result, "ebit"), _numeric(result, "sales")).where(
        holding_mask
    )
    result["gross_profit_margin"] = safe_divide(
        _numeric(result, "gross_profit"),
        _numeric(result, "sales"),
    ).where(holding_mask)
    result["financial_investments_to_assets"] = safe_divide(
        financial_investments,
        _numeric(result, "total_assets"),
    ).where(holding_mask)
    result["equity_method_investments_to_assets"] = safe_divide(
        _numeric(result, "equity_method_investments"),
        _numeric(result, "total_assets"),
    ).where(holding_mask)
    result["equity_method_income_to_net_income"] = safe_divide(
        _numeric(result, "equity_method_income"),
        _numeric(result, "net_income"),
    ).where(holding_mask)
    result["financing_expense_to_sales"] = safe_divide(
        _numeric(result, "financing_expenses").abs(),
        _numeric(result, "sales"),
    ).where(holding_mask)
    result["capex_to_sales"] = safe_divide(
        _numeric(result, "capex").abs(),
        _numeric(result, "sales"),
    ).where(holding_mask)
    return result


def _growth_spread(frame: pd.DataFrame, balance_column: str, flow_column: str) -> pd.Series:
    balance_growth = _yoy_growth(frame, balance_column)
    flow_growth = _yoy_growth(frame, flow_column)
    return balance_growth - flow_growth


def add_industrial_financial_factors(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Add industrial-company V2 factors when the required raw fields are available."""
    result = frame.copy()
    industrial_mask = _profile_mask(result, profile_column, {"industrial"})
    revenue = _numeric(result, "sales")
    cost_of_sales = _numeric(result, "cost_of_sales").abs()
    gross_profit = _numeric(result, "gross_profit")
    capex = _numeric(result, "capex").abs()
    depreciation = _numeric(result, "depreciation").abs()
    financing_expenses = _numeric(result, "financing_expenses").abs()
    trade_receivables_avg = _average_balance(result, "trade_receivables")
    inventory_avg = _average_balance(result, "inventory")
    trade_payables_avg = _average_balance(result, "trade_payables")
    average_assets = _average_balance(result, "total_assets")
    average_ppe = _average_balance(result, "property_plant_equipment")

    selling_expenses = _numeric(result, "selling_marketing_expenses").abs()
    ga_expenses = _numeric(result, "general_admin_expenses").abs()
    rd_expenses = _numeric(result, "research_development_expenses").abs()
    operating_expenses = _sum_columns(
        result,
        ["selling_marketing_expenses", "general_admin_expenses", "research_development_expenses"],
        absolute=True,
    )

    result["revenue_growth_yoy"] = _yoy_growth(result, "sales").where(industrial_mask)
    result["ebit_growth_yoy"] = _yoy_growth(result, "ebit").where(industrial_mask)
    result["ebitda_growth_yoy"] = _yoy_growth(result, "ebitda").where(industrial_mask)
    result["gross_margin"] = safe_divide(gross_profit, revenue).where(industrial_mask)
    result["ebit_margin"] = safe_divide(_numeric(result, "ebit"), revenue).where(industrial_mask)
    result["ebitda_margin"] = safe_divide(_numeric(result, "ebitda"), revenue).where(industrial_mask)
    result["net_profit_margin"] = safe_divide(_numeric(result, "net_income"), revenue).where(industrial_mask)
    result["dso"] = (safe_divide(trade_receivables_avg, revenue) * 365).where(industrial_mask)
    result["dio"] = (safe_divide(inventory_avg, cost_of_sales) * 365).where(industrial_mask)
    result["dpo"] = (safe_divide(trade_payables_avg, cost_of_sales) * 365).where(industrial_mask)
    result["cash_conversion_cycle"] = (result["dso"] + result["dio"] - result["dpo"]).where(industrial_mask)
    result["current_ratio"] = safe_divide(
        _numeric(result, "current_assets"),
        _numeric(result, "current_liabilities"),
    ).where(industrial_mask)
    result["quick_ratio"] = safe_divide(
        _numeric(result, "current_assets") - _numeric(result, "inventory"),
        _numeric(result, "current_liabilities"),
    ).where(industrial_mask)
    result["financial_debt_to_assets"] = safe_divide(
        _numeric(result, "total_debt"),
        _numeric(result, "total_assets"),
    ).where(industrial_mask)
    result["interest_coverage"] = safe_divide(_numeric(result, "ebit"), financing_expenses).where(industrial_mask)
    result["ebitda_interest_coverage"] = safe_divide(
        _numeric(result, "ebitda"),
        financing_expenses,
    ).where(industrial_mask)
    result["asset_turnover"] = safe_divide(revenue, average_assets).where(industrial_mask)
    result["fixed_asset_turnover"] = safe_divide(revenue, average_ppe).where(industrial_mask)
    result["capex_to_revenue"] = safe_divide(capex, revenue).where(industrial_mask)
    result["capex_to_ebitda"] = safe_divide(capex, _numeric(result, "ebitda")).where(industrial_mask)
    result["capex_to_depreciation"] = safe_divide(capex, depreciation).where(industrial_mask)
    result["cfo_margin"] = safe_divide(_numeric(result, "operating_cash_flow"), revenue).where(industrial_mask)
    result["cfo_to_ebitda"] = safe_divide(
        _numeric(result, "operating_cash_flow"),
        _numeric(result, "ebitda"),
    ).where(industrial_mask)
    result["fcf_margin"] = safe_divide(_numeric(result, "free_cash_flow"), revenue).where(industrial_mask)
    result["fcf_to_ebitda"] = safe_divide(
        _numeric(result, "free_cash_flow"),
        _numeric(result, "ebitda"),
    ).where(industrial_mask)
    result["inventory_to_revenue"] = safe_divide(_numeric(result, "inventory"), revenue).where(industrial_mask)
    result["receivables_to_revenue"] = safe_divide(_numeric(result, "trade_receivables"), revenue).where(industrial_mask)
    result["payables_to_cost_of_sales"] = safe_divide(
        _numeric(result, "trade_payables"),
        cost_of_sales,
    ).where(industrial_mask)
    result["inventory_growth_spread"] = _growth_spread(result, "inventory", "sales").where(industrial_mask)
    result["receivables_growth_spread"] = _growth_spread(result, "trade_receivables", "sales").where(industrial_mask)
    result["rd_to_revenue"] = safe_divide(rd_expenses, revenue).where(industrial_mask)
    result["selling_expense_ratio"] = safe_divide(selling_expenses, revenue).where(industrial_mask)
    result["ga_expense_ratio"] = safe_divide(ga_expenses, revenue).where(industrial_mask)
    result["operating_expense_ratio"] = safe_divide(operating_expenses, revenue).where(industrial_mask)
    result["depreciation_to_revenue"] = safe_divide(depreciation, revenue).where(industrial_mask)
    result["ppe_to_assets"] = safe_divide(
        _numeric(result, "property_plant_equipment"),
        _numeric(result, "total_assets"),
    ).where(industrial_mask)
    result["ppe_to_revenue"] = safe_divide(_numeric(result, "property_plant_equipment"), revenue).where(industrial_mask)
    result["cash_to_debt"] = safe_divide(_numeric(result, "cash"), _numeric(result, "total_debt")).where(industrial_mask)
    result["export_ratio"] = safe_divide(_numeric(result, "export_revenue"), revenue).where(industrial_mask)
    return result


def select_factor_columns_for_profile(
    profile: str | None,
    *,
    include_identifiers: bool = True,
) -> list[str]:
    """Return the factor columns that are economically meaningful for a profile."""
    normalized_profile = str(profile or "").strip().lower()
    factor_columns = PROFILE_FACTOR_COLUMN_MAP.get(normalized_profile, COMMON_FACTOR_COLUMNS)
    if not include_identifiers:
        return list(factor_columns)
    return IDENTIFIER_COLUMNS + list(factor_columns)


def get_profile_factor_view(
    factors: pd.DataFrame,
    profile: str | None = None,
    *,
    profile_column: str = "selected_profile",
    include_identifiers: bool = True,
) -> pd.DataFrame:
    """Return a profile-specific view that hides unsupported factor columns."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("get_profile_factor_view() expects a factors DataFrame.")

    selected_profile = profile
    if selected_profile is None and profile_column in factors.columns:
        profiles = factors[profile_column].dropna().astype("string").str.lower().unique().tolist()
        if len(profiles) == 1:
            selected_profile = profiles[0]

    selected_columns = select_factor_columns_for_profile(
        selected_profile,
        include_identifiers=include_identifiers,
    )
    available_columns = [column for column in selected_columns if column in factors.columns]
    return factors.loc[:, available_columns].copy()


def build_financial_factors(
    snapshot: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
    financials: pd.DataFrame | None = None,
    mode: str | None = None,
) -> pd.DataFrame:
    """Return a snapshot dataframe enriched with financial factors.

    Passing raw İş Yatırım `financials` enables profile-specific V2 factors
    without changing the snapshot schema.
    """
    if not isinstance(snapshot, pd.DataFrame):
        raise TypeError(
            "build_financial_factors() expects a snapshot DataFrame. "
            "Use build_financial_snapshot(symbol, mode=...) first, then pass that dataframe."
        )

    if snapshot.empty:
        result = snapshot.copy()
        for column in FACTOR_COLUMNS:
            if column not in result.columns:
                result[column] = pd.Series(dtype="float64")
        return result

    result = snapshot.copy()
    if "period" in result.columns:
        result["period"] = pd.to_datetime(result["period"], errors="coerce")
        sort_columns = ["period"]
        if "symbol" in result.columns:
            sort_columns = ["symbol", "period"]
        result = result.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    result = _merge_profile_raw_fields(result, financials, mode=mode)
    result = add_common_financial_factors(result)
    result = add_profile_financial_factors(result, profile_column=profile_column)
    result = add_bank_financial_factors(result, profile_column=profile_column)
    result = add_insurance_financial_factors(result, profile_column=profile_column)
    result = add_holding_financial_factors(result, profile_column=profile_column)
    result = add_industrial_financial_factors(result, profile_column=profile_column)
    return result
