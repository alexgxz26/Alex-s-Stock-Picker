from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _money(value: Any) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def _number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _percent(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _text(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value)


def _category_label(key: str) -> str:
    labels = {
        "business_quality": "Business quality",
        "growth_durability": "Growth durability",
        "financial_strength_cash_flow": "Financial strength and cash flow",
        "valuation_attractiveness": "Valuation attractiveness",
        "catalyst_strength": "Catalyst strength",
        "earnings_momentum": "Earnings momentum",
        "insider_institutional_signals": "Insider/institutional signals",
        "technical_setup": "Technical setup",
        "risk_reward": "Risk/reward",
    }
    return labels.get(key, key.replace("_", " ").title())


def write_markdown_report(results: list[dict[str, Any]], output_path: Path) -> None:
    """Write a ranked Markdown report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Alex Stock Picker Weekly Report",
        "",
        f"Generated: {generated_at}",
        "",
        "Version 1 note: catalyst strength, earnings momentum, insider/institutional signals, and risk/reward use placeholder scores.",
        "",
        "## Rankings",
        "",
        "| Rank | Ticker | Company | Score | Rating | Conviction |",
        "|---:|---|---|---:|---|---|",
    ]

    for rank, result in enumerate(results, start=1):
        lines.append(
            f"| {rank} | {result['ticker']} | {result['company_name']} | "
            f"{result['total_score']} | {result['rating']} | {result['conviction']} |"
        )

    lines.extend(["", "## Stock Details", ""])

    for result in results:
        financials = result["financials"]
        technicals = result["technicals"]
        sec_filings = result.get("sec_filings", {})
        lines.extend(
            [
                f"### {result['ticker']} - {result['company_name']}",
                "",
                f"**Score:** {result['total_score']}/100  ",
                f"**Rating:** {result['rating']}  ",
                f"**Conviction:** {result['conviction']}",
                "",
                "#### Category Scores",
                "",
            ]
        )

        for key, score in result["category_scores"].items():
            lines.append(f"- {_category_label(key)}: {score}")

        lines.extend(
            [
                "",
                "#### Fundamentals",
                "",
                f"- Sector: {financials.get('sector', 'n/a')}",
                f"- Industry: {financials.get('industry', 'n/a')}",
                f"- Market cap: {_money(financials.get('market_cap'))}",
                f"- Current price: {_money(financials.get('current_price'))}",
                f"- Forward P/E: {_number(financials.get('forward_pe'))}",
                f"- Trailing P/E: {_number(financials.get('trailing_pe'))}",
                f"- PEG ratio: {_number(financials.get('peg_ratio'))}",
                f"- Price/sales: {_number(financials.get('price_to_sales'))}",
                f"- Revenue growth: {_percent(financials.get('revenue_growth'))}",
                f"- Earnings growth: {_percent(financials.get('earnings_growth'))}",
                f"- Gross margin: {_percent(financials.get('gross_margin'))}",
                f"- Operating margin: {_percent(financials.get('operating_margin'))}",
                f"- Profit margin: {_percent(financials.get('profit_margin'))}",
                f"- Free cash flow: {_money(financials.get('free_cash_flow'))}",
                f"- Operating cash flow: {_money(financials.get('operating_cash_flow'))}",
                f"- Total cash: {_money(financials.get('total_cash'))}",
                f"- Total debt: {_money(financials.get('total_debt'))}",
                f"- Analyst recommendation: {financials.get('analyst_recommendation', 'n/a')}",
                "",
                "#### Technicals",
                "",
                f"- Latest close: {_money(technicals.get('latest_close'))}",
                f"- 50-day moving average: {_money(technicals.get('ma_50'))}",
                f"- 200-day moving average: {_money(technicals.get('ma_200'))}",
                f"- Above 50-day moving average: {_yes_no(technicals.get('above_50_ma', False))}",
                f"- Above 200-day moving average: {_yes_no(technicals.get('above_200_ma', False))}",
                f"- 1-month return: {_percent(technicals.get('return_1m'))}",
                f"- 3-month return: {_percent(technicals.get('return_3m'))}",
                f"- 6-month return: {_percent(technicals.get('return_6m'))}",
                f"- 1-year return: {_percent(technicals.get('return_1y'))}",
                "",
                "#### SEC Filing Highlights",
                "",
                f"- SEC company name: {_text(sec_filings.get('sec_company_name'))}",
                f"- CIK: {_text(sec_filings.get('cik'))}",
                f"- Recent filing count: {_text(sec_filings.get('recent_filing_count'))}",
                f"- Latest 10-K filing date: {_text(sec_filings.get('latest_10k_filing_date'))}",
                f"- Latest 10-K accession: {_text(sec_filings.get('latest_10k_accession'))}",
                f"- Latest 10-Q filing date: {_text(sec_filings.get('latest_10q_filing_date'))}",
                f"- Latest 10-Q accession: {_text(sec_filings.get('latest_10q_accession'))}",
                f"- Latest 8-K filing date: {_text(sec_filings.get('latest_8k_filing_date'))}",
                f"- Latest 8-K accession: {_text(sec_filings.get('latest_8k_accession'))}",
                "",
                "#### Notes",
                "",
            ]
        )

        for note in sec_filings.get("sec_notes", []):
            lines.append(f"- SEC: {note}")

        for note in result["notes"]:
            lines.append(f"- {note}")

        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
