from __future__ import annotations

from stock_picker.sec_filings import get_sec_companyfacts


def run(ticker: str) -> dict:
    return get_sec_companyfacts(ticker)
