from __future__ import annotations

from typing import Any

import yfinance as yf


FIELDS = {
    "longName": "company_name",
    "sector": "sector",
    "industry": "industry",
    "marketCap": "market_cap",
    "currentPrice": "current_price",
    "forwardPE": "forward_pe",
    "trailingPE": "trailing_pe",
    "pegRatio": "peg_ratio",
    "priceToSalesTrailing12Months": "price_to_sales",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "grossMargins": "gross_margin",
    "operatingMargins": "operating_margin",
    "profitMargins": "profit_margin",
    "freeCashflow": "free_cash_flow",
    "operatingCashflow": "operating_cash_flow",
    "totalCash": "total_cash",
    "totalDebt": "total_debt",
    "recommendationKey": "analyst_recommendation",
}


def _safe_info(ticker: yf.Ticker) -> dict[str, Any]:
    try:
        return ticker.get_info()
    except Exception:
        try:
            return ticker.info
        except Exception:
            return {}


def get_financial_snapshot(ticker_symbol: str) -> dict[str, Any]:
    """Pull a beginner-friendly fundamental snapshot from yfinance."""
    ticker = yf.Ticker(ticker_symbol)
    info = _safe_info(ticker)

    snapshot = {"ticker": ticker_symbol.upper()}
    for source_key, output_key in FIELDS.items():
        snapshot[output_key] = info.get(source_key)

    snapshot["company_name"] = snapshot.get("company_name") or ticker_symbol.upper()
    snapshot["sector"] = snapshot.get("sector") or "Unknown"
    snapshot["industry"] = snapshot.get("industry") or "Unknown"
    snapshot["analyst_recommendation"] = snapshot.get("analyst_recommendation") or "n/a"
    return snapshot
