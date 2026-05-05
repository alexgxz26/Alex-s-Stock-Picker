# Alex's Stock Picker

Layer 1 data ingestion system for a US-listed equities research workflow.

This first layer does **data ingestion only**:
- No stock scoring
- No portfolio construction
- No trade execution
- No AI analysis

It pulls data from public/free sources into a local SQLite database.

## Initial universe

- S&P 500
- Nasdaq 100
- Benchmarks and sector ETFs

## Core data sources

1. Universe
2. Market data and fundamentals
3. SEC filings and insider transactions
4. Institutional 13F holdings
5. Short interest
6. Analyst estimates
7. Earnings calendar

## Setup

```bash
cd alex_stock_picker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py --init-db
```

## SEC User-Agent

The SEC requires automated requests to identify themselves with a User-Agent.

This project uses:

```bash
SEC_USER_AGENT="Alex's Stock Picker evilguang@hotmail.com"
```

## Common commands

```bash
python main.py --init-db
python main.py --weekly
python main.py --daily
python main.py --tickers AAPL MSFT NVDA
python main.py --forms AAPL NVDA
python main.py --no-sec
python main.py --no-13f
```

## Database

Default SQLite path:

```text
cache/alex_stock_picker.db
```
