# Alex Stock Picker

Alex Stock Picker is a beginner-friendly, local-first Python research engine for US stocks.

It runs from Terminal, reads tickers from `config.yaml`, pulls public market data with `yfinance`, scores each stock, and creates a ranked Markdown report.

This version does not include a web app, backend server, login system, or database.

## Project Structure

```text
alex_stock_picker/
├── run_stock_picker.py
├── config.yaml
├── requirements.txt
├── README.md
├── data/
│   ├── raw/
│   └── processed/
├── reports/
└── stock_picker/
    ├── __init__.py
    ├── financials.py
    ├── technicals.py
    ├── scorer.py
    ├── report_writer.py
    ├── sec_filings.py
    └── insider_activity.py
```

## 1. Create a Virtual Environment

From the project folder, run:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

When the virtual environment is active, your Terminal prompt usually shows `(.venv)`.

## 2. Install Requirements

Run:

```bash
pip install -r requirements.txt
```

This installs:

- `yfinance` for stock market data
- `pandas` and `numpy` for calculations
- `requests` for future data requests
- `pyyaml` for reading `config.yaml`
- `rich` for nicer Terminal output

## 3. Choose Stocks

Edit `config.yaml` to change the tickers you want to research.

Starter tickers:

```yaml
tickers:
  - MSFT
  - GOOGL
  - AMZN
  - META
  - NVDA
  - AMD
  - CRM
  - SHOP
  - UBER
  - ABNB
```

## 4. Run the Stock Picker

Run:

```bash
python run_stock_picker.py
```

With a simple `tickers:` config, the script pulls financial and price data, scores each stock, prints a ranked table, and creates a report.

With the budget-version `portfolio:` config, the script runs the portfolio research engine instead. It reads `data/portfolio.csv`, uses yfinance and SEC EDGAR public APIs where available, marks unavailable fields as `data_missing`, and writes:

- `reports/daily_dashboard.md`
- `reports/portfolio_actions.md`
- `reports/weekly_report.md`

To skip live public-source lookups during a quick smoke test:

```bash
python run_portfolio_research.py --offline
```

## 5. Find the Report

The Markdown report is saved here:

```text
reports/weekly_report.md
```

Open that file to read the ranked stock research report.

## Scoring Model

Each stock receives a score out of 100:

- Business quality: 20 points
- Growth durability: 15 points
- Financial strength and cash flow: 15 points
- Valuation attractiveness: 15 points
- Catalyst strength: 10 points
- Earnings momentum: 10 points
- Insider/institutional signals: 5 points
- Technical setup: 5 points
- Risk/reward: 5 points

Version 1 uses placeholder scores for catalyst strength, earnings momentum, insider/institutional signals, and risk/reward.

## Ratings

- 85-100: Buy
- 75-84: Buy / Watch
- 65-74: Watch
- 50-64: Weak Watch
- Below 50: Avoid
