from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = '''
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS universe (
    ticker TEXT PRIMARY KEY,
    company_name TEXT,
    gics_sector TEXT,
    gics_sub_industry TEXT,
    source TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT NOT NULL,
    period_type TEXT NOT NULL,
    fiscal_period TEXT,
    fiscal_year INTEGER,
    report_date TEXT,
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    net_income REAL,
    ebit REAL,
    total_assets REAL,
    total_liabilities REAL,
    shareholders_equity REAL,
    cash_and_equivalents REAL,
    total_debt REAL,
    operating_cash_flow REAL,
    capital_expenditures REAL,
    free_cash_flow REAL,
    shares_outstanding REAL,
    dividends_paid REAL,
    buybacks REAL,
    r_and_d_expense REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, period_type, fiscal_period, fiscal_year)
);

CREATE TABLE IF NOT EXISTS derived_ratios (
    ticker TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    roe REAL,
    roa REAL,
    gross_margin REAL,
    operating_margin REAL,
    net_margin REAL,
    revenue_growth_yoy REAL,
    revenue_growth_qoq REAL,
    earnings_growth_yoy REAL,
    earnings_growth_qoq REAL,
    debt_to_equity REAL,
    fcf_yield REAL,
    current_ratio REAL,
    ar_to_revenue REAL,
    cfo_to_net_income REAL,
    accruals_ratio REAL,
    retained_earnings REAL,
    working_capital REAL,
    asset_turnover REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, as_of_date)
);

CREATE TABLE IF NOT EXISTS sec_filings (
    accession_number TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    cik TEXT,
    form_type TEXT NOT NULL,
    filing_date TEXT,
    report_date TEXT,
    filing_url TEXT,
    local_path TEXT,
    source TEXT DEFAULT 'SEC EDGAR',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    accession_number TEXT,
    insider_name TEXT,
    insider_title TEXT,
    transaction_type TEXT,
    transaction_code TEXT,
    shares REAL,
    price REAL,
    transaction_date TEXT,
    ownership_type TEXT,
    is_open_market_purchase INTEGER DEFAULT 0,
    is_ceo_cfo INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS institutional_holdings (
    fund_name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    shares_held REAL,
    market_value REAL,
    report_date TEXT NOT NULL,
    source TEXT DEFAULT 'SEC 13F',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fund_name, ticker, report_date)
);

CREATE TABLE IF NOT EXISTS short_interest (
    ticker TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    shares_short REAL,
    short_ratio REAL,
    short_percent_of_float REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, as_of_date)
);

CREATE TABLE IF NOT EXISTS analyst_estimates (
    ticker TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    forward_eps_estimate REAL,
    price_target_consensus REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, as_of_date)
);

CREATE TABLE IF NOT EXISTS earnings_calendar (
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    company_name TEXT,
    eps_estimate REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, earnings_date)
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    rows_inserted INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    source TEXT,
    issue_type TEXT,
    severity TEXT,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
'''


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
