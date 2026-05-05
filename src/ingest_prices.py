from __future__ import annotations

from stock_picker.financials import get_financial_snapshot
from stock_picker.technicals import get_technical_snapshot


def run(ticker: str) -> dict:
    return {
        "financials": get_financial_snapshot(ticker),
        "technicals": get_technical_snapshot(ticker),
    }
