from __future__ import annotations

from typing import Any


PLACEHOLDER_SCORES = {
    "catalyst_strength": 5,
    "earnings_momentum": 5,
    "insider_institutional_signals": 3,
    "risk_reward": 3,
}


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _add_note(notes: list[str], condition: bool, note: str) -> None:
    if condition:
        notes.append(note)


def score_business_quality(financials: dict[str, Any], notes: list[str]) -> int:
    score = 0
    gross_margin = _num(financials.get("gross_margin"))
    operating_margin = _num(financials.get("operating_margin"))
    profit_margin = _num(financials.get("profit_margin"))

    if gross_margin is not None:
        score += 7 if gross_margin >= 0.60 else 5 if gross_margin >= 0.40 else 3 if gross_margin >= 0.25 else 1
        _add_note(notes, gross_margin >= 0.60, "High gross margin suggests strong business quality.")
        _add_note(notes, gross_margin < 0.25, "Low gross margin weighs on business quality.")

    if operating_margin is not None:
        score += 7 if operating_margin >= 0.25 else 5 if operating_margin >= 0.15 else 3 if operating_margin >= 0.05 else 1
        _add_note(notes, operating_margin >= 0.25, "Strong operating margin supports quality score.")
        _add_note(notes, operating_margin < 0.05, "Thin operating margin reduces quality score.")

    if profit_margin is not None:
        score += 6 if profit_margin >= 0.20 else 4 if profit_margin >= 0.10 else 2 if profit_margin >= 0.03 else 1
        _add_note(notes, profit_margin >= 0.20, "Healthy profit margin shows solid profitability.")
        _add_note(notes, profit_margin < 0.03, "Weak profit margin is a concern.")

    return min(score, 20)


def score_growth(financials: dict[str, Any], notes: list[str]) -> int:
    score = 0
    revenue_growth = _num(financials.get("revenue_growth"))
    earnings_growth = _num(financials.get("earnings_growth"))

    if revenue_growth is not None:
        score += 8 if revenue_growth >= 0.20 else 6 if revenue_growth >= 0.10 else 4 if revenue_growth >= 0.03 else 1
        _add_note(notes, revenue_growth >= 0.10, "Revenue is growing at a useful pace.")
        _add_note(notes, revenue_growth < 0, "Revenue growth is negative.")

    if earnings_growth is not None:
        score += 7 if earnings_growth >= 0.20 else 5 if earnings_growth >= 0.10 else 3 if earnings_growth >= 0.03 else 1
        _add_note(notes, earnings_growth >= 0.10, "Earnings growth adds to the setup.")
        _add_note(notes, earnings_growth < 0, "Negative earnings growth hurts the score.")

    return min(score, 15)


def score_financial_strength(financials: dict[str, Any], notes: list[str]) -> int:
    score = 0
    free_cash_flow = _num(financials.get("free_cash_flow"))
    operating_cash_flow = _num(financials.get("operating_cash_flow"))
    total_cash = _num(financials.get("total_cash"))
    total_debt = _num(financials.get("total_debt"))

    if free_cash_flow is not None:
        score += 5 if free_cash_flow > 0 else 0
        _add_note(notes, free_cash_flow > 0, "Positive free cash flow is a plus.")
        _add_note(notes, free_cash_flow <= 0, "Free cash flow is not positive.")

    if operating_cash_flow is not None:
        score += 4 if operating_cash_flow > 0 else 0
        _add_note(notes, operating_cash_flow > 0, "Operating cash flow is positive.")

    if total_cash is not None and total_debt is not None:
        if total_cash >= total_debt:
            score += 6
            notes.append("Cash covers total debt.")
        elif total_debt > 0 and total_cash / total_debt >= 0.5:
            score += 3
            notes.append("Cash is meaningful, but debt is higher.")
        else:
            score += 1
            notes.append("Debt is high relative to cash.")

    return min(score, 15)


def score_valuation(financials: dict[str, Any], notes: list[str]) -> int:
    score = 0
    forward_pe = _num(financials.get("forward_pe"))
    peg_ratio = _num(financials.get("peg_ratio"))
    price_to_sales = _num(financials.get("price_to_sales"))

    if forward_pe is not None:
        score += 6 if 0 < forward_pe <= 20 else 4 if forward_pe <= 35 else 2 if forward_pe <= 60 else 0
        _add_note(notes, 0 < forward_pe <= 20, "Forward P/E looks reasonable.")
        _add_note(notes, forward_pe > 60, "Forward P/E is expensive.")

    if peg_ratio is not None:
        score += 5 if 0 < peg_ratio <= 1.5 else 3 if peg_ratio <= 2.5 else 1 if peg_ratio <= 4 else 0
        _add_note(notes, 0 < peg_ratio <= 1.5, "PEG ratio is attractive if estimates hold.")
        _add_note(notes, peg_ratio > 4, "PEG ratio looks stretched.")

    if price_to_sales is not None:
        score += 4 if price_to_sales <= 5 else 2 if price_to_sales <= 10 else 1 if price_to_sales <= 20 else 0
        _add_note(notes, price_to_sales > 20, "Price/sales is very high.")

    return min(score, 15)


def score_technical_setup(technicals: dict[str, Any], notes: list[str]) -> int:
    score = 0

    if technicals.get("above_50_ma"):
        score += 2
        notes.append("Price is above the 50-day moving average.")
    else:
        notes.append("Price is below the 50-day moving average.")

    if technicals.get("above_200_ma"):
        score += 2
        notes.append("Price is above the 200-day moving average.")
    else:
        notes.append("Price is below the 200-day moving average.")

    six_month_return = _num(technicals.get("return_6m"))
    if six_month_return is not None and six_month_return > 0:
        score += 1
        notes.append("Six-month price return is positive.")

    return min(score, 5)


def rating_for_score(total_score: int) -> str:
    if total_score >= 85:
        return "Buy"
    if total_score >= 75:
        return "Buy / Watch"
    if total_score >= 65:
        return "Watch"
    if total_score >= 50:
        return "Weak Watch"
    return "Avoid"


def conviction_for_score(total_score: int) -> str:
    if total_score >= 85:
        return "High"
    if total_score >= 75:
        return "Medium-High"
    if total_score >= 65:
        return "Medium"
    if total_score >= 50:
        return "Low"
    return "Very Low"


def score_stock(financials: dict[str, Any], technicals: dict[str, Any]) -> dict[str, Any]:
    notes: list[str] = []

    category_scores = {
        "business_quality": score_business_quality(financials, notes),
        "growth_durability": score_growth(financials, notes),
        "financial_strength_cash_flow": score_financial_strength(financials, notes),
        "valuation_attractiveness": score_valuation(financials, notes),
        "catalyst_strength": PLACEHOLDER_SCORES["catalyst_strength"],
        "earnings_momentum": PLACEHOLDER_SCORES["earnings_momentum"],
        "insider_institutional_signals": PLACEHOLDER_SCORES["insider_institutional_signals"],
        "technical_setup": score_technical_setup(technicals, notes),
        "risk_reward": PLACEHOLDER_SCORES["risk_reward"],
    }

    notes.append("Catalyst, earnings momentum, insider/institutional, and risk/reward scores are placeholders in version 1.")
    total_score = int(sum(category_scores.values()))

    return {
        "ticker": financials["ticker"],
        "company_name": financials.get("company_name") or financials["ticker"],
        "total_score": total_score,
        "rating": rating_for_score(total_score),
        "conviction": conviction_for_score(total_score),
        "category_scores": category_scores,
        "notes": notes[:8],
        "financials": financials,
        "technicals": technicals,
    }
