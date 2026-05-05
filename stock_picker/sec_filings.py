from __future__ import annotations

from functools import lru_cache
from typing import Any

import requests


SEC_USER_AGENT = "Alex Stock Picker evilguang@hotmail.com"
SEC_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
REQUEST_TIMEOUT_SECONDS = 20
TARGET_FORMS = ("10-K", "10-Q", "8-K")


def _empty_result(ticker: str, note: str) -> dict[str, Any]:
    return {
        "ticker": ticker.upper(),
        "cik": None,
        "latest_10k_filing_date": None,
        "latest_10q_filing_date": None,
        "latest_8k_filing_date": None,
        "latest_10k_accession": None,
        "latest_10q_accession": None,
        "latest_8k_accession": None,
        "latest_accession_numbers": {
            "10-K": None,
            "10-Q": None,
            "8-K": None,
        },
        "recent_filing_count": 0,
        "sec_company_name": None,
        "sec_notes": [note],
    }


def _get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=SEC_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"SEC endpoint returned an unexpected payload for {url}")
    return payload


def _format_cik(cik: int | str) -> str:
    return str(cik).zfill(10)


@lru_cache(maxsize=1)
def get_ticker_cik_map() -> dict[str, dict[str, Any]]:
    """Load the official SEC ticker-to-CIK mapping."""
    raw_mapping = _get_json(COMPANY_TICKERS_URL)
    ticker_map: dict[str, dict[str, Any]] = {}

    for company in raw_mapping.values():
        ticker = str(company.get("ticker", "")).upper()
        cik = company.get("cik_str")
        if ticker and cik is not None:
            ticker_map[ticker] = {
                "ticker": ticker,
                "cik": _format_cik(cik),
                "title": company.get("title"),
            }

    return ticker_map


def get_cik_for_ticker(ticker: str) -> dict[str, Any] | None:
    """Map a stock ticker to its SEC CIK."""
    return get_ticker_cik_map().get(ticker.upper())


def get_company_submissions(cik: str) -> dict[str, Any]:
    """Pull recent filing metadata from the official SEC submissions API."""
    return _get_json(SUBMISSIONS_URL.format(cik=cik))


def get_companyfacts(cik: str) -> dict[str, Any]:
    """Pull XBRL company facts from the official SEC Company Facts API."""
    return _get_json(COMPANYFACTS_URL.format(cik=cik))


def _recent_filing_at(recent_filings: dict[str, list[Any]], index: int) -> dict[str, Any]:
    def value_for(key: str) -> Any:
        values = recent_filings.get(key, [])
        return values[index] if index < len(values) else None

    return {
        "form": value_for("form"),
        "filing_date": value_for("filingDate"),
        "accession": value_for("accessionNumber"),
    }


def _latest_filing(recent_filings: dict[str, list[Any]], form_type: str) -> dict[str, Any]:
    forms = recent_filings.get("form", [])
    matches: list[dict[str, Any]] = []

    for index, form in enumerate(forms):
        if str(form).strip().upper() == form_type:
            matches.append(_recent_filing_at(recent_filings, index))

    if not matches:
        return {"filing_date": None, "accession": None}

    latest = max(matches, key=lambda filing: filing.get("filing_date") or "")
    return {
        "filing_date": latest.get("filing_date"),
        "accession": latest.get("accession"),
    }


def get_sec_filing_signals(ticker: str) -> dict[str, Any]:
    """Return recent SEC filing highlights for a ticker."""
    ticker = ticker.upper()

    try:
        cik_record = get_cik_for_ticker(ticker)
    except (ValueError, requests.RequestException) as exc:
        return _empty_result(ticker, f"Could not load SEC ticker mapping: {exc}")

    if not cik_record:
        return _empty_result(ticker, "Ticker was not found in the SEC ticker-to-CIK mapping.")

    cik = cik_record["cik"]
    notes: list[str] = []

    try:
        submissions = get_company_submissions(cik)
    except (ValueError, requests.RequestException) as exc:
        result = _empty_result(ticker, f"Could not load SEC submissions: {exc}")
        result["cik"] = cik
        result["sec_company_name"] = cik_record.get("title")
        return result

    recent_filings = submissions.get("filings", {}).get("recent", {})
    if not isinstance(recent_filings, dict):
        recent_filings = {}
        notes.append("SEC submissions response did not include recent filing metadata.")

    latest_filings = {
        form_type: _latest_filing(recent_filings, form_type)
        for form_type in TARGET_FORMS
    }
    company_name = submissions.get("name") or cik_record.get("title")

    return {
        "ticker": ticker,
        "cik": cik,
        "latest_10k_filing_date": latest_filings["10-K"]["filing_date"],
        "latest_10q_filing_date": latest_filings["10-Q"]["filing_date"],
        "latest_8k_filing_date": latest_filings["8-K"]["filing_date"],
        "latest_10k_accession": latest_filings["10-K"]["accession"],
        "latest_10q_accession": latest_filings["10-Q"]["accession"],
        "latest_8k_accession": latest_filings["8-K"]["accession"],
        "latest_accession_numbers": {
            "10-K": latest_filings["10-K"]["accession"],
            "10-Q": latest_filings["10-Q"]["accession"],
            "8-K": latest_filings["8-K"]["accession"],
        },
        "recent_filing_count": len(recent_filings.get("form", [])),
        "sec_company_name": company_name,
        "sec_notes": notes,
    }


def _latest_usd_fact(companyfacts: dict[str, Any], taxonomy: str, fact_name: str) -> Any:
    facts = companyfacts.get("facts", {}).get(taxonomy, {})
    fact = facts.get(fact_name, {})
    units = fact.get("units", {})
    values = units.get("USD") or units.get("shares") or []
    if not isinstance(values, list) or not values:
        return None

    annual_or_quarterly = [
        value for value in values if value.get("form") in {"10-K", "10-Q"} and value.get("val") is not None
    ]
    if not annual_or_quarterly:
        annual_or_quarterly = [value for value in values if value.get("val") is not None]
    if not annual_or_quarterly:
        return None

    latest = max(annual_or_quarterly, key=lambda value: value.get("end") or value.get("filed") or "")
    return latest.get("val")


def get_sec_companyfacts(ticker: str) -> dict[str, Any]:
    """Return a compact fundamental snapshot from SEC Company Facts XBRL."""
    ticker = ticker.upper()
    try:
        cik_record = get_cik_for_ticker(ticker)
    except (ValueError, requests.RequestException) as exc:
        return {"ticker": ticker, "companyfacts_notes": [f"data_missing: could not load SEC ticker mapping: {exc}"]}

    if not cik_record:
        return {"ticker": ticker, "companyfacts_notes": ["data_missing: ticker not found in SEC ticker mapping."]}

    try:
        companyfacts = get_companyfacts(cik_record["cik"])
    except (ValueError, requests.RequestException) as exc:
        return {
            "ticker": ticker,
            "cik": cik_record["cik"],
            "companyfacts_notes": [f"data_missing: could not load SEC Company Facts: {exc}"],
        }

    revenue = (
        _latest_usd_fact(companyfacts, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax")
        or _latest_usd_fact(companyfacts, "us-gaap", "Revenues")
        or _latest_usd_fact(companyfacts, "us-gaap", "SalesRevenueNet")
    )
    operating_cash_flow = _latest_usd_fact(companyfacts, "us-gaap", "NetCashProvidedByUsedInOperatingActivities")
    capex = (
        _latest_usd_fact(companyfacts, "us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment")
        or _latest_usd_fact(companyfacts, "us-gaap", "CapitalExpenditures")
    )
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - abs(capex)

    return {
        "ticker": ticker,
        "cik": cik_record["cik"],
        "company_name": companyfacts.get("entityName") or cik_record.get("title"),
        "revenue": revenue,
        "gross_profit": _latest_usd_fact(companyfacts, "us-gaap", "GrossProfit"),
        "operating_income": _latest_usd_fact(companyfacts, "us-gaap", "OperatingIncomeLoss"),
        "net_income": _latest_usd_fact(companyfacts, "us-gaap", "NetIncomeLoss"),
        "operating_cash_flow": operating_cash_flow,
        "capex": capex,
        "free_cash_flow": free_cash_flow,
        "cash_and_equivalents": (
            _latest_usd_fact(companyfacts, "us-gaap", "CashAndCashEquivalentsAtCarryingValue")
            or _latest_usd_fact(companyfacts, "us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
        ),
        "total_debt": (
            _latest_usd_fact(companyfacts, "us-gaap", "DebtCurrent")
            or _latest_usd_fact(companyfacts, "us-gaap", "LongTermDebtAndFinanceLeaseObligations")
            or _latest_usd_fact(companyfacts, "us-gaap", "LongTermDebt")
        ),
        "shares_outstanding": _latest_usd_fact(companyfacts, "dei", "EntityCommonStockSharesOutstanding"),
        "companyfacts_notes": [],
    }
