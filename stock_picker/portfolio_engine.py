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


ROLE_ORDER = ("Core", "Growth", "Swing", "Speculative", "Cleanup")
DEFAULT_ROLE_TARGETS = {
    "Core": 0.55,
    "Growth": 0.25,
    "Swing": 0.10,
    "Speculative": 0.10,
    "Cleanup": 0.00,
}
DEFAULT_MAX_SPECULATIVE_EXPOSURE = 0.10
DEFAULT_REBALANCE_BAND = 0.025

TICKER_COLUMNS = ("ticker", "symbol", "holding", "security", "stock")
SHARES_COLUMNS = ("shares", "quantity", "qty", "units")
VALUE_COLUMNS = (
    "market_value",
    "current_value",
    "value",
    "position_value",
    "total_value",
)
PRICE_COLUMNS = ("price", "current_price", "last_price", "market_price")
CASH_TICKERS = {"CASH", "USD", "$", "MONEYMARKET", "MONEY_MARKET"}


@dataclass
class Position:
    ticker: str
    currency: str = "USD"
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

    is_negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if is_negative else number


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


def _is_cash_row(row: dict[str, Any], ticker: str) -> bool:
    asset_type = str(row.get("type") or row.get("asset_type") or row.get("asset_class") or "").strip().lower()
    name = str(row.get("name") or row.get("description") or row.get("security") or "").strip().lower()
    return ticker in CASH_TICKERS or asset_type == "cash" or name == "cash"


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
    candidates = [
        config.get("role_targets"),
        config.get("target_role_weights"),
        config.get("target_roles"),
        config.get("allocation", {}).get("role_targets") if isinstance(config.get("allocation"), dict) else None,
        config.get("portfolio", {}).get("role_targets") if isinstance(config.get("portfolio"), dict) else None,
    ]

    role_targets = DEFAULT_ROLE_TARGETS.copy()
    for raw in candidates:
        for role, weight in _coerce_weight_map(raw).items():
            normalized_role = _normalize_role(role)
            if normalized_role in role_targets:
                role_targets[normalized_role] = weight
    return role_targets


def _coerce_ticker_targets(config: dict[str, Any]) -> dict[str, float]:
    candidates = [
        config.get("ticker_targets"),
        config.get("target_weights"),
        config.get("targets"),
        config.get("allocation", {}).get("ticker_targets") if isinstance(config.get("allocation"), dict) else None,
        config.get("portfolio", {}).get("ticker_targets") if isinstance(config.get("portfolio"), dict) else None,
    ]

    targets: dict[str, float] = {}
    for raw in candidates:
        for ticker, weight in _coerce_weight_map(raw).items():
            ticker_symbol = _clean_ticker(ticker)
            if ticker_symbol and ticker_symbol not in ROLE_ORDER:
                targets[ticker_symbol] = weight
    return targets


def _coerce_role_max_weights(config: dict[str, Any]) -> dict[str, float]:
    risk_limits = config.get("risk_limits") if isinstance(config.get("risk_limits"), dict) else {}
    role_definitions = config.get("role_definitions") if isinstance(config.get("role_definitions"), dict) else {}
    role_max = {
        "Core": _normalize_percent(risk_limits.get("max_core_position")) or 0.10,
        "Growth": _normalize_percent(risk_limits.get("max_growth_position")) or 0.06,
        "Swing": _normalize_percent(risk_limits.get("max_swing_position")) or 0.04,
        "Speculative": _normalize_percent(risk_limits.get("max_speculative_position")) or 0.015,
        "Cleanup": 0.0,
    }

    for role, values in role_definitions.items():
        normalized_role = _normalize_role(role)
        if normalized_role in role_max and isinstance(values, dict):
            max_position = _normalize_percent(values.get("max_position"))
            if max_position is not None:
                role_max[normalized_role] = max_position
    return role_max


def _normalize_role(role: Any) -> str:
    text = str(role or "").strip().lower().replace("_", " ")
    role_map = {
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
    }
    return role_map.get(text, str(role or "").strip().title())


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

    cash = (
        _parse_number(portfolio.get("cash"))
        or _parse_number(portfolio.get("cash_available"))
        or _parse_number(budget.get("cash"))
        or _parse_number(raw.get("cash"))
        or 0.0
    )
    max_speculative = (
        _normalize_percent(portfolio.get("max_speculative_exposure"))
        or _normalize_percent(risk_limits.get("max_total_speculative_exposure"))
        or _normalize_percent(raw.get("max_speculative_exposure"))
        or DEFAULT_MAX_SPECULATIVE_EXPOSURE
    )
    rebalance_band = (
        _normalize_percent(portfolio.get("rebalance_band"))
        or _normalize_percent(raw.get("rebalance_band"))
        or DEFAULT_REBALANCE_BAND
    )

    role_overrides: dict[str, str] = {}
    raw_roles = raw.get("roles") or raw.get("role_overrides") or portfolio.get("roles") or {}
    if isinstance(raw_roles, dict):
        for ticker, role in raw_roles.items():
            ticker_symbol = _clean_ticker(ticker)
            normalized_role = _normalize_role(role)
            if ticker_symbol and normalized_role in ROLE_ORDER:
                role_overrides[ticker_symbol] = normalized_role

    top_n = int(_parse_number(raw.get("top_n") or portfolio.get("top_n")) or 5)
    sec_enabled = bool(sec.get("enabled", raw.get("sec_enabled", True)))

    return PortfolioConfig(
        cash=cash,
        base_currency=str(portfolio.get("base_currency") or raw.get("base_currency") or "USD").upper(),
        max_speculative_exposure=max_speculative,
        rebalance_band=rebalance_band,
        role_targets=_coerce_role_targets(raw),
        role_max_weights=_coerce_role_max_weights(raw),
        role_overrides=role_overrides,
        ticker_targets=_coerce_ticker_targets(raw),
        top_n=max(1, top_n),
        sec_enabled=sec_enabled,
        min_market_cap_for_core=_parse_number(risk_limits.get("min_market_cap_for_core")) or 50_000_000_000,
        avoid_negative_fcf_core=bool(risk_limits.get("avoid_negative_fcf_core", True)),
        avoid_biotech_binary=bool(risk_limits.get("avoid_biotech_binary", True)),
    )


def load_positions(portfolio_path: Path) -> tuple[list[Position], float]:
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Missing portfolio file: {portfolio_path}")

    with portfolio_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("data/portfolio.csv must include a header row.")
        rows = [
            {_normalize_key(key): value for key, value in row.items() if key is not None}
            for row in reader
        ]

    positions_by_ticker: dict[str, Position] = {}
    cash = 0.0

    for row in rows:
        ticker = _clean_ticker(_pick(row, TICKER_COLUMNS))
        currency = str(row.get("currency") or "USD").strip().upper()
        value = _parse_number(_pick(row, VALUE_COLUMNS))
        shares = _parse_number(_pick(row, SHARES_COLUMNS))
        price = _parse_number(_pick(row, PRICE_COLUMNS))

        if _is_cash_row(row, ticker):
            cash += value or 0.0
            continue

        if not ticker:
            continue

        position = positions_by_ticker.setdefault(
            ticker,
            Position(
                ticker=ticker,
                currency=currency,
                name=str(row.get("name") or row.get("description") or "").strip() or None,
                source_row=row,
            ),
        )
        position.shares = (position.shares or 0.0) + shares if shares is not None else position.shares
        position.provided_value = (position.provided_value or 0.0) + value if value is not None else position.provided_value
        position.provided_price = price if price is not None else position.provided_price

    return sorted(positions_by_ticker.values(), key=lambda item: item.ticker), cash


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

    symbol = f"{currency}{base_currency}=X"
    try:
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


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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

    # Normalize the available-metric score to a 100-point score, without pretending missing data was good.
    max_observed_points = 93
    normalized_score = int(round(min(score / max_observed_points, 1.0) * 100))
    return normalized_score, missing


def _classify_role(
    ticker: str,
    financials: dict[str, Any],
    technicals: dict[str, Any],
    score: int,
    missing_fields: list[str],
    config: PortfolioConfig,
) -> tuple[str, str]:
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
    if score < 35 or "position_value" in missing_fields:
        return "Cleanup", "low_score_or_missing_price"
    if free_cash_flow is not None and free_cash_flow <= 0:
        return "Speculative", "negative_or_zero_free_cash_flow"
    if profit_margin is not None and profit_margin < 0:
        return "Speculative", "negative_profit_margin"
    if market_cap is not None and market_cap < 5_000_000_000:
        return "Speculative", "small_cap_position"
    if price_to_sales is not None and price_to_sales > 20 and forward_pe is None:
        return "Speculative", "high_sales_multiple_without_earnings_multiple"
    if (
        market_cap is not None
        and market_cap >= config.min_market_cap_for_core
        and score >= 60
        and profit_margin is not None
        and profit_margin > 0
        and (not config.avoid_negative_fcf_core or free_cash_flow is None or free_cash_flow > 0)
    ):
        return "Core", "large_profitable_high_quality"
    if revenue_growth is not None and revenue_growth >= 0.15 and score >= 50:
        return "Growth", "strong_revenue_growth"
    if above_200 is True and score >= 45:
        return "Swing", "constructive_technical_setup"
    if missing_fields:
        return "Speculative", "provisional_due_to_missing_data"
    return "Swing", "default_middle_bucket"


def _target_weights(research_rows: list[dict[str, Any]], config: PortfolioConfig) -> dict[str, float]:
    explicit_targets = {
        ticker: weight
        for ticker, weight in config.ticker_targets.items()
        if any(row["ticker"] == ticker for row in research_rows)
    }

    targets = explicit_targets.copy()
    for row in research_rows:
        if row["ticker"] in targets:
            continue
        role = row["role"]
        targets[row["ticker"]] = config.role_max_weights.get(role, config.role_targets.get(role, 0.0))

    return targets


def _flag_for_gap(gap: float, band: float) -> str:
    if gap > band:
        return "underweight"
    if gap < -band:
        return "overweight"
    return "in_band"


def _safe_sec_signals(ticker: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"ticker": ticker, "sec_notes": ["SEC lookup disabled in config."]}
    try:
        return get_sec_filing_signals(ticker)
    except Exception as exc:
        return {
            "ticker": ticker,
            "cik": None,
            "sec_company_name": None,
            "latest_10k_filing_date": None,
            "latest_10q_filing_date": None,
            "latest_8k_filing_date": None,
            "recent_filing_count": 0,
            "sec_notes": [f"data_missing: SEC lookup failed: {exc}"],
        }


def _merge_companyfacts(financials: dict[str, Any], companyfacts: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    merged = financials.copy()
    filled: list[str] = []
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
            filled.append(financials_key)

    revenue = _num(merged.get("revenue"))
    gross_profit = _num(merged.get("gross_profit"))
    operating_income = _num(merged.get("operating_income"))
    free_cash_flow = _num(merged.get("free_cash_flow"))
    if merged.get("gross_margin") is None and revenue and gross_profit is not None:
        merged["gross_margin"] = gross_profit / revenue
        filled.append("gross_margin")
    if merged.get("operating_margin") is None and revenue and operating_income is not None:
        merged["operating_margin"] = operating_income / revenue
        filled.append("operating_margin")
    if merged.get("fcf_margin") is None and revenue and free_cash_flow is not None:
        merged["fcf_margin"] = free_cash_flow / revenue
        filled.append("fcf_margin")
    return merged, filled


def build_portfolio_research(
    portfolio_path: Path,
    config_path: Path,
    *,
    fetch_online: bool = True,
) -> dict[str, Any]:
    config = load_portfolio_config(config_path)
    positions, csv_cash = load_positions(portfolio_path)
    cash = config.cash + csv_cash

    rows: list[dict[str, Any]] = []
    for position in positions:
        companyfacts: dict[str, Any] = {}
        if fetch_online:
            financials = get_financial_snapshot(position.ticker)
            if config.sec_enabled:
                companyfacts = get_sec_companyfacts(position.ticker)
                financials, _ = _merge_companyfacts(financials, companyfacts)
            technicals = get_technical_snapshot(position.ticker)
            sec_filings = _safe_sec_signals(position.ticker, config.sec_enabled)
        else:
            financials = {"ticker": position.ticker, "company_name": position.name or position.ticker}
            technicals = {"ticker": position.ticker}
            sec_filings = {"ticker": position.ticker, "sec_notes": ["Online fetch skipped."]}

        current_price = _num(financials.get("current_price")) or _num(technicals.get("latest_close"))
        local_value, value_source = _value_from_position(position, current_price)
        fx_rate, missing_fx = _fx_rate_to_base(position.currency, config.base_currency, fetch_online)
        value = local_value * fx_rate if local_value is not None and fx_rate is not None else None
        missing_fields = []
        if current_price is None:
            missing_fields.append("current_price")
        if local_value is None:
            missing_fields.append("position_value")
        if missing_fx is not None:
            missing_fields.append(missing_fx)

        score, score_missing = _score_available_metrics(financials, technicals)
        missing_fields.extend(field_name for field_name in score_missing if field_name not in missing_fields)

        role, role_reason = _classify_role(
            position.ticker,
            financials,
            technicals,
            score,
            missing_fields,
            config,
        )
        rows.append(
            {
                "ticker": position.ticker,
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
                "score_status": "provisional" if missing_fields else "complete",
                "missing_fields": sorted(set(missing_fields)),
                "financials": financials,
                "technicals": technicals,
                "sec_filings": sec_filings,
                "companyfacts": companyfacts,
            }
        )

    positions_value = sum(row["position_value"] or 0.0 for row in rows)
    total_value = positions_value + cash
    investable_value = max(total_value - cash, 0.0)
    targets = _target_weights(rows, config)

    for row in rows:
        current_weight = (row["position_value"] or 0.0) / total_value if total_value > 0 else None
        invested_weight = (row["position_value"] or 0.0) / investable_value if investable_value > 0 else None
        target_weight = targets.get(row["ticker"], 0.0)
        target_dollars = target_weight * investable_value
        gap_dollars = target_dollars - (row["position_value"] or 0.0)
        row.update(
            {
                "portfolio_weight": current_weight,
                "cash_adjusted_weight": invested_weight,
                "target_weight": target_weight,
                "cash_adjusted_target_dollars": target_dollars,
                "allocation_gap": target_weight - (invested_weight or 0.0),
                "allocation_gap_dollars": gap_dollars,
                "allocation_flag": _flag_for_gap(target_weight - (invested_weight or 0.0), config.rebalance_band),
            }
        )

    role_exposures = {
        role: sum(row["position_value"] or 0.0 for row in rows if row["role"] == role)
        for role in ROLE_ORDER
    }
    speculative_value = role_exposures["Speculative"]
    speculative_weight = speculative_value / total_value if total_value > 0 else 0.0
    speculative_limit_dollars = config.max_speculative_exposure * total_value

    add_candidates = sorted(
        [
            row
            for row in rows
            if row["allocation_flag"] == "underweight"
            and row["role"] != "Cleanup"
            and row["score_status"] != "provisional"
            and not (
                row["role"] == "Speculative"
                and speculative_weight > config.max_speculative_exposure
            )
        ],
        key=lambda row: (row["score"], row["allocation_gap_dollars"]),
        reverse=True,
    )
    provisional_add_candidates = sorted(
        [
            row
            for row in rows
            if row["allocation_flag"] == "underweight"
            and row["role"] != "Cleanup"
            and row["score_status"] == "provisional"
            and not (
                row["role"] == "Speculative"
                and speculative_weight > config.max_speculative_exposure
            )
        ],
        key=lambda row: (row["score"], row["allocation_gap_dollars"]),
        reverse=True,
    )
    trim_exit_candidates = sorted(
        [
            row
            for row in rows
            if row["allocation_flag"] == "overweight" or row["role"] == "Cleanup" or row["score"] < 40
        ],
        key=lambda row: (row["role"] == "Cleanup", row["allocation_gap_dollars"]),
    )

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
        "role_exposures": role_exposures,
        "speculative_exposure": {
            "value": speculative_value,
            "weight": speculative_weight,
            "limit_weight": config.max_speculative_exposure,
            "limit_dollars": speculative_limit_dollars,
            "excess_dollars": max(0.0, speculative_value - speculative_limit_dollars),
            "status": "over_limit" if speculative_weight > config.max_speculative_exposure else "within_limit",
        },
        "top_add_candidates": add_candidates[: config.top_n],
        "provisional_add_candidates": provisional_add_candidates[: config.top_n],
        "trim_exit_candidates": trim_exit_candidates[: config.top_n],
    }


def money(value: Any) -> str:
    if value is None:
        return "data_missing"
    return f"${float(value):,.2f}"


def percent(value: Any) -> str:
    if value is None:
        return "data_missing"
    return f"{float(value) * 100:.1f}%"


def candidate_action(row: dict[str, Any]) -> str:
    if row["role"] == "Cleanup" or row["score"] < 50:
        return "trim" if row["allocation_flag"] == "overweight" else "exit_or_watchlist"
    if row["allocation_flag"] == "underweight" and row["score"] >= 75 and row["score_status"] == "complete":
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
    ma_200 = row.get("technicals", {}).get("ma_200")
    free_cash_flow = row.get("financials", {}).get("free_cash_flow")
    if ma_200 is not None:
        return f"close below 200-day moving average ({money(ma_200)}) or thesis/data deterioration"
    if free_cash_flow is not None and float(free_cash_flow) <= 0:
        return "no clear path to positive free cash flow"
    return "data_missing: invalidation needs technical or thesis data"


def write_portfolio_report(research: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Budget Portfolio Research",
        "",
        f"Generated: {research['generated_at']}",
        "",
        "Data policy: missing public-source fields are marked `data_missing`; affected scores are provisional.",
        "",
        "## First Useful Output",
        "",
        f"1. Total portfolio value: **{money(research['total_portfolio_value'])}**",
        f"2. Cash-adjusted investable value: **{money(research['cash_adjusted_investable_value'])}**",
        f"3. Cash: **{money(research['cash'])}**",
        "",
        "### Cash-Adjusted Target Allocation",
        "",
        "| Ticker | Role | Current Weight | Cash-Adjusted Weight | Target Weight | Target Dollars | Gap | Flag |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for row in research["positions"]:
        lines.append(
            "| {ticker} | {role} | {current} | {cash_adjusted} | {target} | {target_dollars} | {gap} | {flag} |".format(
                ticker=row["ticker"],
                role=row["role"],
                current=percent(row["portfolio_weight"]),
                cash_adjusted=percent(row["cash_adjusted_weight"]),
                target=percent(row["target_weight"]),
                target_dollars=money(row["cash_adjusted_target_dollars"]),
                gap=money(row["allocation_gap_dollars"]),
                flag=row["allocation_flag"],
            )
        )

    lines.extend(
        [
            "",
            "### Position Weights And Role Classification",
            "",
            "| Ticker | Company | Value | Weight | Role | Score | Status | Missing Data | Role Reason |",
            "|---|---|---:|---:|---|---:|---|---|---|",
        ]
    )

    for row in research["positions"]:
        missing = ", ".join(row["missing_fields"]) if row["missing_fields"] else ""
        lines.append(
            "| {ticker} | {company} | {value} | {weight} | {role} | {score} | {status} | {missing} | {reason} |".format(
                ticker=row["ticker"],
                company=str(row["company_name"]).replace("|", "/"),
                value=money(row["position_value"]),
                weight=percent(row["portfolio_weight"]),
                role=row["role"],
                score=row["score"],
                status=row["score_status"],
                missing=missing or "",
                reason=row["role_reason"],
            )
        )

    lines.extend(
        [
            "",
            "### Top Add Candidates",
            "",
            "| Ticker | Role | Score | Action | Add Gap | Sizing View | Invalidation |",
            "|---|---|---:|---|---:|---|---|",
        ]
    )
    candidates = research["top_add_candidates"] or research["provisional_add_candidates"]
    if candidates:
        for row in candidates:
            lines.append(
                f"| {row['ticker']} | {row['role']} | {row['score']} | {candidate_action(row)} | "
                f"{money(row['allocation_gap_dollars'])} | {sizing_view(row)} | {invalidation_condition(row)} |"
            )
    else:
        lines.append("| n/a | n/a | 0 | n/a | $0.00 | no underweight candidates | n/a |")

    lines.extend(
        [
            "",
            "### Trim / Exit Candidates",
            "",
            "| Ticker | Role | Score | Action | Gap | Flag | Reason |",
            "|---|---|---:|---|---:|---|---|",
        ]
    )
    if research["trim_exit_candidates"]:
        for row in research["trim_exit_candidates"]:
            lines.append(
                f"| {row['ticker']} | {row['role']} | {row['score']} | {candidate_action(row)} | "
                f"{money(row['allocation_gap_dollars'])} | {row['allocation_flag']} | {row['role_reason']} |"
            )
    else:
        lines.append("| n/a | n/a | 0 | n/a | $0.00 | in_band | no trim/exit candidates |")

    exposure = research["speculative_exposure"]
    lines.extend(
        [
            "",
            "### Speculative Exposure",
            "",
            f"- Current speculative exposure: **{percent(exposure['weight'])}** ({money(exposure['value'])})",
            f"- Limit: **{percent(exposure['limit_weight'])}** ({money(exposure['limit_dollars'])})",
            f"- Status: **{exposure['status']}**",
            f"- Excess above limit: **{money(exposure['excess_dollars'])}**",
            "",
            "### Public Source Notes",
            "",
        ]
    )

    for row in research["positions"]:
        sec_notes = row.get("sec_filings", {}).get("sec_notes") or []
        if sec_notes:
            lines.append(f"- {row['ticker']}: {'; '.join(sec_notes)}")
        elif row.get("sec_filings", {}).get("cik"):
            lines.append(f"- {row['ticker']}: SEC CIK {row['sec_filings']['cik']} found.")

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
