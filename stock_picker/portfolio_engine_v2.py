from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
import yfinance as yf

from stock_picker.financials import get_financial_snapshot
from stock_picker.sec_filings import get_sec_companyfacts, get_sec_filing_signals
from stock_picker.technicals import get_technical_snapshot


ROLE_ORDER = ("Core Index", "Core", "Growth", "Swing", "Speculative", "Non-US", "Unknown", "Cleanup")
VALID_ASSET_TYPES = {"US_STOCK", "ETF", "NON_US_STOCK", "CASH", "UNKNOWN"}
DEFAULT_ROLE_TARGETS = {
    "Core Index": 0.00,
    "Core": 0.55,
    "Growth": 0.25,
    "Swing": 0.10,
    "Speculative": 0.10,
    "Non-US": 0.00,
    "Unknown": 0.00,
    "Cleanup": 0.00,
}
DEFAULT_MAX_SPECULATIVE_EXPOSURE = 0.10
DEFAULT_REBALANCE_BAND = 0.025
DEFAULT_TICKER_ALIASES = {"FISV": "FI"}
ETF_TICKERS = {"VWRA"}
NON_US_TICKERS = {"1009", "D05", "Z59"}
US_EXCHANGES = {"", "NYSE", "NASDAQ", "NASDAQ.NMS", "NASDAQ.SCM", "AMEX", "NYSEARCA", "ARCA"}
NON_US_EXCHANGES = {"SGX", "SEHK", "HKEX", "LSE", "LSEETF"}

TICKER_COLUMNS = ("ticker", "symbol", "holding", "security", "stock")
SHARES_COLUMNS = ("shares", "quantity", "qty", "units")
VALUE_COLUMNS = ("market_value", "current_value", "value", "position_value", "total_value")
PRICE_COLUMNS = ("price", "current_price", "last_price", "market_price")
CASH_TICKERS = {"CASH", "USD", "$", "MONEYMARKET", "MONEY_MARKET"}


@dataclass
class Position:
    ticker: str
    original_ticker: str | None = None
    currency: str = "USD"
    asset_type: str = "UNKNOWN"
    manual_role: str | None = None
    shares: float | None = None
    provided_value: float | None = None
    provided_price: float | None = None
    name: str | None = None
    source_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioConfig:
    cash: float = 0.0
    base_currency: str = "USD"
    max_speculative_exposure: float = DEFAULT_MAX_SPECULATIVE_EXPOSURE
    rebalance_band: float = DEFAULT_REBALANCE_BAND
    role_targets: dict[str, float] = field(default_factory=lambda: DEFAULT_ROLE_TARGETS.copy())
    role_max_weights: dict[str, float] = field(default_factory=dict)
    role_overrides: dict[str, str] = field(default_factory=dict)
    ticker_targets: dict[str, float] = field(default_factory=dict)
    ticker_aliases: dict[str, str] = field(default_factory=lambda: DEFAULT_TICKER_ALIASES.copy())
    top_n: int = 5
    sec_enabled: bool = True
    min_market_cap_for_core: float = 50_000_000_000
    avoid_negative_fcf_core: bool = True
    avoid_biotech_binary: bool = True


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def _clean_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a", "na", "--", "data_missing"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _normalize_percent(value: Any) -> float | None:
    number = _parse_number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def _pick(row: dict[str, Any], columns: tuple[str, ...]) -> Any:
    for column in columns:
        if column in row and str(row[column]).strip() != "":
            return row[column]
    return None


def _normalize_role(role: Any) -> str:
    text = str(role or "").strip().lower().replace("_", " ")
    role_map = {
        "core index": "Core Index",
        "core etf": "Core Index",
        "index": "Core Index",
        "etf": "Core Index",
        "core": "Core",
        "growth": "Growth",
        "swing": "Swing",
        "trade": "Swing",
        "trading": "Swing",
        "spec": "Speculative",
        "speculative": "Speculative",
        "cleanup": "Cleanup",
        "clean up": "Cleanup",
        "exit": "Cleanup",
        "non us": "Non-US",
        "non-us": "Non-US",
        "non us stock": "Non-US",
        "unknown": "Unknown",
    }
    return role_map.get(text, str(role or "").strip().title())


def _normalize_asset_type(value: Any, ticker: str, currency: str, exchange: str, name: str) -> str:
    raw = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if raw in VALID_ASSET_TYPES:
        return raw
    exchange = exchange.strip().upper()
    name = name.strip().lower()
    if ticker in CASH_TICKERS:
        return "CASH"
    if ticker in ETF_TICKERS or "etf" in name or exchange == "LSEETF":
        return "ETF"
    if ticker in NON_US_TICKERS or currency.upper() != "USD" or exchange in NON_US_EXCHANGES:
        return "NON_US_STOCK"
    if exchange in US_EXCHANGES:
        return "US_STOCK"
    return "UNKNOWN"


def _coerce_weight_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    weights: dict[str, float] = {}
    for key, value in raw.items():
        percent = _normalize_percent(value)
        if percent is not None:
            weights[str(key).strip()] = percent
    return weights


def _coerce_role_targets(config: dict[str, Any]) -> dict[str, float]:
    role_targets = DEFAULT_ROLE_TARGETS.copy()
    candidates = [
        config.get("role_targets"),
        config.get("target_role_weights"),
        config.get("target_roles"),
        config.get("allocation", {}).get("role_targets") if isinstance(config.get("allocation"), dict) else None,
        config.get("portfolio", {}).get("role_targets") if isinstance(config.get("portfolio"), dict) else None,
    ]
    for raw in candidates:
        for role, weight in _coerce_weight_map(raw).items():
            normalized = _normalize_role(role)
            if normalized in role_targets:
                role_targets[normalized] = weight
    return role_targets


def _coerce_ticker_targets(config: dict[str, Any]) -> dict[str, float]:
    targets: dict[str, float] = {}
    candidates = [
        config.get("ticker_targets"),
        config.get("target_weights"),
        config.get("targets"),
        config.get("allocation", {}).get("ticker_targets") if isinstance(config.get("allocation"), dict) else None,
        config.get("portfolio", {}).get("ticker_targets") if isinstance(config.get("portfolio"), dict) else None,
    ]
    for raw in candidates:
        for ticker, weight in _coerce_weight_map(raw).items():
            ticker_symbol = _clean_ticker(ticker)
            if ticker_symbol and ticker_symbol not in ROLE_ORDER:
                targets[ticker_symbol] = weight
    return targets


def _coerce_ticker_aliases(config: dict[str, Any]) -> dict[str, str]:
    aliases = DEFAULT_TICKER_ALIASES.copy()
    raw_aliases = config.get("ticker_aliases")
    if isinstance(raw_aliases, dict):
        for source, target in raw_aliases.items():
            source_ticker = _clean_ticker(source)
            target_ticker = _clean_ticker(target)
            if source_ticker and target_ticker:
                aliases[source_ticker] = target_ticker
    return aliases


def _coerce_role_max_weights(config: dict[str, Any]) -> dict[str, float]:
    risk_limits = config.get("risk_limits") if isinstance(config.get("risk_limits"), dict) else {}
    role_definitions = config.get("role_definitions") if isinstance(config.get("role_definitions"), dict) else {}
    role_max = {
        "Core Index": 1.00,
        "Core": _normalize_percent(risk_limits.get("max_core_position")) or 0.10,
        "Growth": _normalize_percent(risk_limits.get("max_growth_position")) or 0.06,
        "Swing": _normalize_percent(risk_limits.get("max_swing_position")) or 0.04,
        "Speculative": _normalize_percent(risk_limits.get("max_speculative_position")) or 0.015,
        "Non-US": 0.00,
        "Unknown": 0.00,
        "Cleanup": 0.00,
    }
    for role, values in role_definitions.items():
        normalized = _normalize_role(role)
        if normalized in role_max and isinstance(values, dict):
            max_position = _normalize_percent(values.get("max_position"))
            if max_position is not None:
                role_max[normalized] = max_position
    return role_max


def load_portfolio_config(config_path: Path) -> PortfolioConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config file: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must contain a YAML mapping.")
    portfolio = raw.get("portfolio") if isinstance(raw.get("portfolio"), dict) else {}
    budget = raw.get("budget") if isinstance(raw.get("budget"), dict) else {}
    risk_limits = raw.get("risk_limits") if isinstance(raw.get("risk_limits"), dict) else {}
    sec = raw.get("sec") if isinstance(raw.get("sec"), dict) else {}

    role_overrides: dict[str, str] = {}
    raw_roles = raw.get("roles") or raw.get("role_overrides") or portfolio.get("roles") or {}
    if isinstance(raw_roles, dict):
        for ticker, role in raw_roles.items():
            normalized = _normalize_role(role)
            if normalized in ROLE_ORDER:
                role_overrides[_clean_ticker(ticker)] = normalized

    return PortfolioConfig(
        cash=(
            _parse_number(portfolio.get("cash"))
            or _parse_number(portfolio.get("cash_available"))
            or _parse_number(budget.get("cash"))
            or _parse_number(raw.get("cash"))
            or 0.0
        ),
        base_currency=str(portfolio.get("base_currency") or raw.get("base_currency") or "USD").upper(),
        max_speculative_exposure=(
            _normalize_percent(portfolio.get("max_speculative_exposure"))
            or _normalize_percent(risk_limits.get("max_total_speculative_exposure"))
            or _normalize_percent(raw.get("max_speculative_exposure"))
            or DEFAULT_MAX_SPECULATIVE_EXPOSURE
        ),
        rebalance_band=(
            _normalize_percent(portfolio.get("rebalance_band"))
            or _normalize_percent(raw.get("rebalance_band"))
            or DEFAULT_REBALANCE_BAND
        ),
        role_targets=_coerce_role_targets(raw),
        role_max_weights=_coerce_role_max_weights(raw),
        role_overrides=role_overrides,
        ticker_targets=_coerce_ticker_targets(raw),
        ticker_aliases=_coerce_ticker_aliases(raw),
        top_n=max(1, int(_parse_number(raw.get("top_n") or portfolio.get("top_n")) or 5)),
        sec_enabled=bool(sec.get("enabled", raw.get("sec_enabled", True))),
        min_market_cap_for_core=_parse_number(risk_limits.get("min_market_cap_for_core")) or 50_000_000_000,
        avoid_negative_fcf_core=bool(risk_limits.get("avoid_negative_fcf_core", True)),
        avoid_biotech_binary=bool(risk_limits.get("avoid_biotech_binary", True)),
    )


def _is_cash_row(row: dict[str, Any], ticker: str) -> bool:
    asset_type = str(row.get("type") or row.get("asset_type") or row.get("asset_class") or "").strip().lower()
    name = str(row.get("name") or row.get("description") or row.get("security") or "").strip().lower()
    return ticker in CASH_TICKERS or asset_type == "cash" or name == "cash"


def load_positions(portfolio_path: Path, ticker_aliases: dict[str, str] | None = None) -> tuple[list[Position], float]:
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Missing portfolio file: {portfolio_path}")
    aliases = ticker_aliases or DEFAULT_TICKER_ALIASES
    with portfolio_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("data/portfolio.csv must include a header row.")
        rows = [{_normalize_key(key): value for key, value in row.items() if key is not None} for row in reader]

    positions_by_ticker: dict[str, Position] = {}
    cash = 0.0
    for row in rows:
        original_ticker = _clean_ticker(_pick(row, TICKER_COLUMNS))
        if not original_ticker:
            continue
        ticker = aliases.get(original_ticker, original_ticker)
        currency = str(row.get("currency") or "USD").strip().upper()
        name = str(row.get("name") or row.get("description") or "").strip()
        exchange = str(row.get("exchange") or "").strip().upper()
        asset_type = _normalize_asset_type(row.get("asset_type"), original_ticker, currency, exchange, name)
        manual_role = _normalize_role(row.get("manual_role")) if row.get("manual_role") else None
        manual_role = manual_role if manual_role in ROLE_ORDER else None
        value = _parse_number(_pick(row, VALUE_COLUMNS))
        shares = _parse_number(_pick(row, SHARES_COLUMNS))
        price = _parse_number(_pick(row, PRICE_COLUMNS))

        if _is_cash_row(row, original_ticker) or asset_type == "CASH":
            cash += value or 0.0
            continue

        position = positions_by_ticker.setdefault(
            ticker,
            Position(
                ticker=ticker,
                original_ticker=original_ticker if original_ticker != ticker else None,
                currency=currency,
                asset_type=asset_type,
                manual_role=manual_role,
                name=name or None,
                source_row=row,
            ),
        )
        if position.asset_type == "UNKNOWN" and asset_type != "UNKNOWN":
            position.asset_type = asset_type
        if position.manual_role is None and manual_role is not None:
            position.manual_role = manual_role
        if position.original_ticker is None and original_ticker != ticker:
            position.original_ticker = original_ticker
        position.shares = (position.shares or 0.0) + shares if shares is not None else position.shares
        position.provided_value = (position.provided_value or 0.0) + value if value is not None else position.provided_value
        position.provided_price = price if price is not None else position.provided_price
    return sorted(positions_by_ticker.values(), key=lambda item: item.ticker), cash


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_from_position(position: Position, market_price: float | None) -> tuple[float | None, str]:
    if position.shares is not None and market_price is not None:
        return position.shares * market_price, "shares_x_yfinance_price"
    if position.provided_value is not None:
        return position.provided_value, "portfolio_csv_value"
    if position.shares is not None and position.provided_price is not None:
        return position.shares * position.provided_price, "shares_x_csv_price"
    return None, "data_missing"


def _fx_rate_to_base(currency: str, base_currency: str, fetch_online: bool) -> tuple[float | None, str | None]:
    currency = currency.upper()
    base_currency = base_currency.upper()
    if currency == base_currency:
        return 1.0, None
    if not fetch_online:
        return None, f"fx_rate_{currency}_{base_currency}"
    try:
        symbol = f"{currency}{base_currency}=X"
        ticker = yf.Ticker(symbol)
        fast_info = getattr(ticker, "fast_info", {}) or {}
        rate = _num(fast_info.get("last_price") if hasattr(fast_info, "get") else None)
        if rate is None:
            history = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
            if not history.empty and "Close" in history:
                close_data = history["Close"]
                if isinstance(close_data, pd.DataFrame):
                    close_data = close_data.iloc[:, 0]
                rate = _num(close_data.dropna().iloc[-1])
        if rate is not None and rate > 0:
            return rate, None
    except Exception:
        pass
    return None, f"fx_rate_{currency}_{base_currency}"


def _score_available_metrics(financials: dict[str, Any], technicals: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    available = 0
    metrics = [
        ("gross_margin", financials.get("gross_margin"), [(0.60, 14), (0.40, 10), (0.25, 6)]),
        ("operating_margin", financials.get("operating_margin"), [(0.25, 14), (0.15, 10), (0.05, 6)]),
        ("profit_margin", financials.get("profit_margin"), [(0.20, 12), (0.10, 8), (0.03, 4)]),
        ("revenue_growth", financials.get("revenue_growth"), [(0.20, 12), (0.10, 9), (0.03, 5)]),
        ("free_cash_flow", financials.get("free_cash_flow"), [(0, 10)]),
        ("total_debt", financials.get("total_debt"), [(0, 0)]),
        ("forward_pe", financials.get("forward_pe"), [(20, 10), (35, 7), (60, 4)]),
        ("price_to_sales", financials.get("price_to_sales"), [(5, 7), (10, 4), (20, 2)]),
        ("return_6m", technicals.get("return_6m"), [(0.10, 7), (0.00, 4)]),
    ]
    missing: list[str] = []
    for metric_name, raw_value, thresholds in metrics:
        value = _num(raw_value)
        if value is None:
            missing.append(metric_name)
            continue
        available += 1
        if metric_name in {"forward_pe", "price_to_sales"}:
            score += next((points for threshold, points in thresholds if 0 < value <= threshold), 0)
        else:
            score += next((points for threshold, points in thresholds if value >= threshold), 0)
    if technicals.get("above_200_ma") is True:
        score += 7
        available += 1
    elif technicals.get("ma_200") is None:
        missing.append("ma_200")
    else:
        available += 1
    if available == 0:
        return 0, missing
    return int(round(min(score / 93, 1.0) * 100)), missing


def _safe_sec_signals(ticker: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"ticker": ticker, "sec_notes": ["SEC lookup disabled in config."]}
    try:
        return get_sec_filing_signals(ticker)
    except Exception as exc:
        return {"ticker": ticker, "sec_notes": [f"data_missing: SEC lookup failed: {exc}"]}


def _merge_companyfacts(financials: dict[str, Any], companyfacts: dict[str, Any]) -> dict[str, Any]:
    merged = financials.copy()
    sec_fields = {
        "revenue": "revenue",
        "gross_profit": "gross_profit",
        "operating_income": "operating_income",
        "net_income": "net_income",
        "operating_cash_flow": "operating_cash_flow",
        "capex": "capex",
        "free_cash_flow": "free_cash_flow",
        "cash_and_equivalents": "total_cash",
        "total_debt": "total_debt",
        "shares_outstanding": "shares_outstanding",
    }
    for sec_key, financials_key in sec_fields.items():
        if merged.get(financials_key) is None and companyfacts.get(sec_key) is not None:
            merged[financials_key] = companyfacts[sec_key]
    revenue = _num(merged.get("revenue"))
    gross_profit = _num(merged.get("gross_profit"))
    operating_income = _num(merged.get("operating_income"))
    free_cash_flow = _num(merged.get("free_cash_flow"))
    if merged.get("gross_margin") is None and revenue and gross_profit is not None:
        merged["gross_margin"] = gross_profit / revenue
    if merged.get("operating_margin") is None and revenue and operating_income is not None:
        merged["operating_margin"] = operating_income / revenue
    if merged.get("fcf_margin") is None and revenue and free_cash_flow is not None:
        merged["fcf_margin"] = free_cash_flow / revenue
    return merged


def _classify_role(ticker: str, asset_type: str, manual_role: str | None, financials: dict[str, Any], technicals: dict[str, Any], score: int, missing_fields: list[str], config: PortfolioConfig) -> tuple[str, str]:
    if manual_role is not None:
        return manual_role, "manual_role"
    if asset_type == "ETF":
        return "Core Index", "etf_core_index_allocation"
    if asset_type == "NON_US_STOCK":
        return "Non-US", "non_us_stock_not_scored_with_us_model"
    if asset_type == "UNKNOWN":
        return "Unknown", "asset_type_unknown_requires_mapping"
    if ticker in config.role_overrides:
        return config.role_overrides[ticker], "config_override"

    market_cap = _num(financials.get("market_cap"))
    revenue_growth = _num(financials.get("revenue_growth"))
    free_cash_flow = _num(financials.get("free_cash_flow"))
    profit_margin = _num(financials.get("profit_margin"))
    forward_pe = _num(financials.get("forward_pe"))
    price_to_sales = _num(financials.get("price_to_sales"))
    above_200 = technicals.get("above_200_ma")
    industry = str(financials.get("industry") or "").lower()

    if config.avoid_biotech_binary and ("biotech" in industry or "biotechnology" in industry):
        return "Speculative", "biotech_binary_risk_screen"
    if "position_value" in missing_fields:
        return "Cleanup", "missing_position_value"
    if score < 35 and not missing_fields:
        return "Cleanup", "low_complete_score"
    if free_cash_flow is not None and free_cash_flow <= 0:
        return "Speculative", "negative_or_zero_free_cash_flow"
    if profit_margin is not None and profit_margin < 0:
        return "Speculative", "negative_profit_margin"
    if market_cap is not None and market_cap < 5_000_000_000:
        return "Speculative", "small_cap_position"
    if price_to_sales is not None and price_to_sales > 20 and forward_pe is None:
        return "Speculative", "high_sales_multiple_without_earnings_multiple"
    if market_cap is not None and market_cap >= config.min_market_cap_for_core and score >= 60 and profit_margin is not None and profit_margin > 0:
        return "Core", "large_profitable_high_quality"
    if revenue_growth is not None and revenue_growth >= 0.15 and score >= 50:
        return "Growth", "strong_revenue_growth"
    if above_200 is True and score >= 45:
        return "Swing", "constructive_technical_setup"
    if missing_fields:
        return "Unknown", "data_quality_issue_not_a_fundamental_cleanup"
    return "Swing", "default_middle_bucket"


def _score_status_for_us_stock(missing_fields: list[str]) -> str:
    blocking = {"position_value", "current_price", "company_name"}
    if not missing_fields:
        return "complete"
    if blocking.isdisjoint(missing_fields) and len(missing_fields) <= 3:
        return "mostly_complete"
    return "provisional"


def _non_scored_status(asset_type: str) -> str:
    if asset_type == "ETF":
        return "not_scored_etf"
    if asset_type == "NON_US_STOCK":
        return "not_scored_non_us"
    if asset_type == "UNKNOWN":
        return "data_quality_issue"
    return "not_scored"


def _target_weights(rows: list[dict[str, Any]], config: PortfolioConfig) -> dict[str, float]:
    targets = {ticker: weight for ticker, weight in config.ticker_targets.items() if any(row["ticker"] == ticker for row in rows)}
    for row in rows:
        if row["ticker"] not in targets:
            targets[row["ticker"]] = config.role_max_weights.get(row["role"], config.role_targets.get(row["role"], 0.0))
    return targets


def _flag_for_gap(gap: float, band: float) -> str:
    if gap > band:
        return "underweight"
    if gap < -band:
        return "overweight"
    return "in_band"


def _has_reportable_company_name(row: dict[str, Any]) -> bool:
    company_name = str(row.get("company_name") or "").strip()
    return bool(company_name) and company_name.lower() != "data_missing" and company_name.upper() != row["ticker"]


def _is_data_quality_issue(row: dict[str, Any]) -> bool:
    if row["asset_type"] == "UNKNOWN":
        return True
    if row["asset_type"] == "NON_US_STOCK":
        return bool(row["missing_fields"])
    return row["score_status"] in {"data_quality_issue", "provisional"} or "company_name" in row["missing_fields"]


def _trim_bucket(row: dict[str, Any]) -> str | None:
    if _is_data_quality_issue(row):
        return "data_quality_issues"
    if row["role"] == "Cleanup" or (row.get("score") is not None and row["score"] < 40):
        return "true_fundamental_cleanup"
    if row["allocation_flag"] == "overweight" and row["role"] not in {"Cleanup", "Unknown"}:
        return "overweight_quality_holdings"
    return None


def build_portfolio_research(portfolio_path: Path, config_path: Path, *, fetch_online: bool = True) -> dict[str, Any]:
    config = load_portfolio_config(config_path)
    positions, csv_cash = load_positions(portfolio_path, config.ticker_aliases)
    cash = config.cash + csv_cash
    rows: list[dict[str, Any]] = []

    for position in positions:
        companyfacts: dict[str, Any] = {}
        should_score_us_stock = position.asset_type == "US_STOCK"
        if fetch_online and should_score_us_stock:
            financials = get_financial_snapshot(position.ticker)
            if config.sec_enabled:
                companyfacts = get_sec_companyfacts(position.ticker)
                financials = _merge_companyfacts(financials, companyfacts)
            technicals = get_technical_snapshot(position.ticker)
            sec_filings = _safe_sec_signals(position.ticker, config.sec_enabled)
        elif position.asset_type == "ETF":
            financials = {"ticker": position.ticker, "company_name": position.name or position.ticker}
            technicals = {"ticker": position.ticker}
            sec_filings = {"ticker": position.ticker, "sec_notes": ["ETF: US stock scoring and SEC lookup not applicable."]}
        elif position.asset_type == "NON_US_STOCK":
            financials = {"ticker": position.ticker, "company_name": position.name or position.ticker}
            technicals = {"ticker": position.ticker}
            sec_filings = {"ticker": position.ticker, "sec_notes": ["NON_US_STOCK: SEC lookup skipped."]}
        elif position.asset_type == "UNKNOWN":
            financials = {"ticker": position.ticker, "company_name": position.name or "data_missing"}
            technicals = {"ticker": position.ticker}
            sec_filings = {"ticker": position.ticker, "sec_notes": ["UNKNOWN asset_type: map before using for decisions."]}
        else:
            financials = {"ticker": position.ticker, "company_name": position.name or position.ticker}
            technicals = {"ticker": position.ticker}
            sec_filings = {"ticker": position.ticker, "sec_notes": ["Online fetch skipped."]}

        current_price = _num(financials.get("current_price")) or _num(technicals.get("latest_close"))
        local_value, value_source = _value_from_position(position, current_price)
        fx_rate, missing_fx = _fx_rate_to_base(position.currency, config.base_currency, fetch_online)
        value = local_value * fx_rate if local_value is not None and fx_rate is not None else None
        missing_fields: list[str] = []
        if current_price is None:
            missing_fields.append("current_price")
        if local_value is None:
            missing_fields.append("position_value")
        if missing_fx is not None:
            missing_fields.append(missing_fx)
        if not financials.get("company_name") or financials.get("company_name") == "data_missing":
            missing_fields.append("company_name")

        if should_score_us_stock:
            score, score_missing = _score_available_metrics(financials, technicals)
            missing_fields.extend(field for field in score_missing if field not in missing_fields)
            score_status = _score_status_for_us_stock(sorted(set(missing_fields)))
        else:
            score = None
            score_status = _non_scored_status(position.asset_type)

        role, role_reason = _classify_role(position.ticker, position.asset_type, position.manual_role, financials, technicals, score or 0, missing_fields, config)
        rows.append({
            "ticker": position.ticker,
            "original_ticker": position.original_ticker,
            "asset_type": position.asset_type,
            "company_name": financials.get("company_name") or position.name or position.ticker,
            "shares": position.shares,
            "currency": position.currency,
            "current_price": current_price,
            "local_position_value": local_value,
            "position_value": value,
            "fx_rate_to_base": fx_rate,
            "value_source": value_source,
            "role": role,
            "role_reason": role_reason,
            "score": score,
            "score_status": score_status,
            "missing_fields": sorted(set(missing_fields)),
            "financials": financials,
            "technicals": technicals,
            "sec_filings": sec_filings,
            "companyfacts": companyfacts,
        })

    positions_value = sum(row["position_value"] or 0.0 for row in rows)
    total_value = positions_value + cash
    investable_value = max(total_value - cash, 0.0)
    targets = _target_weights(rows, config)
    for row in rows:
        current_weight = (row["position_value"] or 0.0) / total_value if total_value > 0 else None
        invested_weight = (row["position_value"] or 0.0) / investable_value if investable_value > 0 else None
        target_weight = targets.get(row["ticker"], 0.0)
        gap_dollars = target_weight * investable_value - (row["position_value"] or 0.0)
        row.update({
            "portfolio_weight": current_weight,
            "cash_adjusted_weight": invested_weight,
            "target_weight": target_weight,
            "cash_adjusted_target_dollars": target_weight * investable_value,
            "allocation_gap": target_weight - (invested_weight or 0.0),
            "allocation_gap_dollars": gap_dollars,
            "allocation_flag": _flag_for_gap(target_weight - (invested_weight or 0.0), config.rebalance_band),
        })

    role_exposures = {role: sum(row["position_value"] or 0.0 for row in rows if row["role"] == role) for role in ROLE_ORDER}
    speculative_value = role_exposures["Speculative"]
    speculative_weight = speculative_value / total_value if total_value > 0 else 0.0
    trim_exit_candidates = sorted([row for row in rows if _trim_bucket(row) is not None], key=lambda row: (_trim_bucket(row) or "", row["allocation_gap_dollars"]))
    trim_exit_buckets = {
        "true_fundamental_cleanup": [row for row in trim_exit_candidates if _trim_bucket(row) == "true_fundamental_cleanup"],
        "data_quality_issues": [row for row in trim_exit_candidates if _trim_bucket(row) == "data_quality_issues"],
        "overweight_quality_holdings": [row for row in trim_exit_candidates if _trim_bucket(row) == "overweight_quality_holdings"],
    }
    add_candidates = sorted([
        row for row in rows
        if row["asset_type"] == "US_STOCK"
        and row["allocation_flag"] == "underweight"
        and row["role"] != "Cleanup"
        and row["score_status"] in {"complete", "mostly_complete"}
        and _has_reportable_company_name(row)
        and not (row["role"] == "Speculative" and speculative_weight > config.max_speculative_exposure)
    ], key=lambda row: (row["score"] or 0, row["allocation_gap_dollars"]), reverse=True)
    provisional_add_candidates = sorted([
        row for row in rows
        if row["asset_type"] == "US_STOCK"
        and row["allocation_flag"] == "underweight"
        and row["role"] != "Cleanup"
        and row["score_status"] == "provisional"
        and _has_reportable_company_name(row)
    ], key=lambda row: (row["score"] or 0, row["allocation_gap_dollars"]), reverse=True)
    data_issues = [row for row in rows if row["asset_type"] in {"UNKNOWN", "NON_US_STOCK"} or row["missing_fields"] or row["original_ticker"] or row["score_status"] in {"provisional", "data_quality_issue"}]

    return {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "portfolio_path": str(portfolio_path),
        "config_path": str(config_path),
        "total_portfolio_value": total_value,
        "base_currency": config.base_currency,
        "cash": cash,
        "positions_value": positions_value,
        "cash_adjusted_investable_value": investable_value,
        "positions": sorted(rows, key=lambda row: row["position_value"] or 0.0, reverse=True),
        "core_etf_allocation": sorted([row for row in rows if row["asset_type"] == "ETF" or row["role"] == "Core Index"], key=lambda row: row["position_value"] or 0.0, reverse=True),
        "us_stock_holdings": sorted([row for row in rows if row["asset_type"] == "US_STOCK"], key=lambda row: row["position_value"] or 0.0, reverse=True),
        "role_exposures": role_exposures,
        "speculative_exposure": {
            "value": speculative_value,
            "weight": speculative_weight,
            "limit_weight": config.max_speculative_exposure,
            "limit_dollars": config.max_speculative_exposure * total_value,
            "excess_dollars": max(0.0, speculative_value - config.max_speculative_exposure * total_value),
            "status": "over_limit" if speculative_weight > config.max_speculative_exposure else "within_limit",
        },
        "top_add_candidates": add_candidates[: config.top_n],
        "provisional_add_candidates": provisional_add_candidates[: config.top_n],
        "trim_exit_candidates": trim_exit_candidates[: config.top_n],
        "trim_exit_buckets": {key: value[: config.top_n] for key, value in trim_exit_buckets.items()},
        "data_issues": sorted(data_issues, key=lambda row: row["position_value"] or 0.0, reverse=True),
    }


def money(value: Any) -> str:
    if value is None:
        return "data_missing"
    return f"${float(value):,.2f}"


def percent(value: Any) -> str:
    if value is None:
        return "data_missing"
    return f"{float(value) * 100:.1f}%"


def score_text(row: dict[str, Any]) -> str:
    return "n/a" if row.get("score") is None else str(row["score"])


def ticker_text(row: dict[str, Any]) -> str:
    if row.get("original_ticker"):
        return f"{row['ticker']} (alias for {row['original_ticker']})"
    return row["ticker"]


def missing_text(row: dict[str, Any]) -> str:
    return ", ".join(row["missing_fields"]) if row["missing_fields"] else ""


def candidate_action(row: dict[str, Any]) -> str:
    score = row.get("score")
    if row["asset_type"] != "US_STOCK":
        return "not_applicable"
    if row["role"] == "Cleanup" or (score is not None and score < 50):
        return "trim" if row["allocation_flag"] == "overweight" else "exit_or_watchlist"
    if row["allocation_flag"] == "underweight" and score is not None and score >= 75 and row["score_status"] == "complete":
        return "add_on_pullback"
    if row["allocation_flag"] == "overweight":
        return "trim"
    return "hold"


def sizing_view(row: dict[str, Any]) -> str:
    if row["role"] == "Cleanup":
        return "target 0%; trim/exit candidate"
    room = max(0.0, row.get("allocation_gap_dollars") or 0.0)
    return f"up to {percent(row.get('target_weight'))} cash-adjusted role cap; add room {money(room)}"


def invalidation_condition(row: dict[str, Any]) -> str:
    if row["asset_type"] != "US_STOCK":
        return "not_applicable"
    ma_200 = row.get("technicals", {}).get("ma_200")
    free_cash_flow = row.get("financials", {}).get("free_cash_flow")
    if ma_200 is not None:
        return f"close below 200-day moving average ({money(ma_200)}) or thesis/data deterioration"
    if free_cash_flow is not None and float(free_cash_flow) <= 0:
        return "no clear path to positive free cash flow"
    return "data_missing: invalidation needs technical or thesis data"


def append_position_table(lines: list[str], rows: list[dict[str, Any]], *, include_target: bool = False) -> None:
    if include_target:
        lines.extend(["| Ticker | Asset Type | Company | Value | Weight | Role | Target | Gap | Status | Notes |", "|---|---|---|---:|---:|---|---:|---:|---|---|"])
    else:
        lines.extend(["| Ticker | Asset Type | Company | Value | Weight | Role | Score | Status | Notes |", "|---|---|---|---:|---:|---|---:|---|---|"])
    if not rows:
        lines.append("| " + " | ".join(["n/a"] * (10 if include_target else 9)) + " |")
        return
    for row in rows:
        company = str(row["company_name"]).replace("|", "/")
        notes = missing_text(row) or row["role_reason"]
        if include_target:
            lines.append(f"| {ticker_text(row)} | {row['asset_type']} | {company} | {money(row['position_value'])} | {percent(row['portfolio_weight'])} | {row['role']} | {percent(row['target_weight'])} | {money(row['allocation_gap_dollars'])} | {row['score_status']} | {notes} |")
        else:
            lines.append(f"| {ticker_text(row)} | {row['asset_type']} | {company} | {money(row['position_value'])} | {percent(row['portfolio_weight'])} | {row['role']} | {score_text(row)} | {row['score_status']} | {notes} |")


def write_portfolio_report(research: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exposure = research["speculative_exposure"]
    lines = [
        "# Budget Portfolio Research",
        "",
        f"Generated: {research['generated_at']}",
        "",
        "Data policy: missing public-source fields are marked `data_missing`; affected scores are provisional.",
        "",
        "## Portfolio Summary",
        "",
        f"1. Total portfolio value: **{money(research['total_portfolio_value'])}**",
        f"2. Cash-adjusted investable value: **{money(research['cash_adjusted_investable_value'])}**",
        f"3. Cash: **{money(research['cash'])}**",
        f"4. Speculative exposure: **{percent(exposure['weight'])}**",
        "",
        "## Core / ETF Allocation",
        "",
    ]
    append_position_table(lines, research["core_etf_allocation"], include_target=True)
    lines.extend(["", "## US Stock Holdings", ""])
    append_position_table(lines, research["us_stock_holdings"], include_target=False)
    lines.extend(["", "### Top Add Candidates", "", "| Ticker | Role | Score | Action | Add Gap | Sizing View | Invalidation |", "|---|---|---:|---|---:|---|---|"])
    if research["top_add_candidates"]:
        for row in research["top_add_candidates"]:
            lines.append(f"| {ticker_text(row)} | {row['role']} | {score_text(row)} | {candidate_action(row)} | {money(row['allocation_gap_dollars'])} | {sizing_view(row)} | {invalidation_condition(row)} |")
    else:
        lines.append("| n/a | n/a | 0 | n/a | $0.00 | no complete or mostly complete US_STOCK candidates | n/a |")
    lines.extend([
        "",
        "## Speculative Exposure",
        "",
        f"- Current speculative exposure: **{percent(exposure['weight'])}** ({money(exposure['value'])})",
        f"- Limit: **{percent(exposure['limit_weight'])}** ({money(exposure['limit_dollars'])})",
        f"- Status: **{exposure['status']}**",
        f"- Excess above limit: **{money(exposure['excess_dollars'])}**",
        "",
        "## Cleanup Candidates",
        "",
        "### True Fundamental Cleanup Candidates",
        "",
    ])
    append_position_table(lines, research["trim_exit_buckets"]["true_fundamental_cleanup"], include_target=True)
    lines.extend(["", "### Data-Quality Issues", ""])
    append_position_table(lines, research["trim_exit_buckets"]["data_quality_issues"], include_target=True)
    lines.extend(["", "### Overweight But Quality Holdings", ""])
    append_position_table(lines, research["trim_exit_buckets"]["overweight_quality_holdings"], include_target=True)
    lines.extend(["", "## Data Issues To Fix", "", "| Ticker | Asset Type | Issue | Notes |", "|---|---|---|---|"])
    if research["data_issues"]:
        for row in research["data_issues"]:
            issues = []
            if row.get("original_ticker"):
                issues.append(f"ticker_alias:{row['original_ticker']}->{row['ticker']}")
            if row["asset_type"] in {"UNKNOWN", "NON_US_STOCK"}:
                issues.append(row["asset_type"])
            issues.extend(row["missing_fields"])
            sec_notes = row.get("sec_filings", {}).get("sec_notes") or []
            notes = "; ".join(sec_notes) if sec_notes else row["role_reason"]
            lines.append(f"| {ticker_text(row)} | {row['asset_type']} | {', '.join(issues) or row['score_status']} | {notes} |")
    else:
        lines.append("| n/a | n/a | n/a | no data issues found |")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def maybe_copy_budget_inputs(root_dir: Path) -> list[str]:
    actions: list[str] = []
    source_portfolio = root_dir / "portfolio_first_cut.csv"
    target_portfolio = root_dir / "data" / "portfolio.csv"
    source_config = root_dir / "config_budget.yaml"
    target_config = root_dir / "config.yaml"
    if source_portfolio.exists():
        target_portfolio.parent.mkdir(parents=True, exist_ok=True)
        target_portfolio.write_text(source_portfolio.read_text(encoding="utf-8-sig"), encoding="utf-8")
        actions.append(f"Copied {source_portfolio.name} to {target_portfolio}")
    if source_config.exists():
        target_config.write_text(source_config.read_text(encoding="utf-8"), encoding="utf-8")
        actions.append(f"Copied {source_config.name} to {target_config}")
    return actions


def sec_user_agent_from_config(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return None
    sec = raw.get("sec") if isinstance(raw.get("sec"), dict) else {}
    env_key = sec.get("user_agent_env")
    if env_key:
        return os.getenv(str(env_key))
    return sec.get("user_agent")
