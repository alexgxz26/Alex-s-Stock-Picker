from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from stock_picker.financials import get_financial_snapshot
from stock_picker.report_writer import write_markdown_report
from stock_picker.scorer import score_stock
from stock_picker.sec_filings import get_sec_filing_signals
from stock_picker.technicals import get_technical_snapshot
from run_portfolio_research import main as run_portfolio_research_main


ROOT_DIR = Path(__file__).parent
CONFIG_PATH = ROOT_DIR / "config.yaml"
REPORT_PATH = ROOT_DIR / "reports" / "weekly_report.md"


def load_tickers(config_path: Path) -> list[str]:
    """Read tickers from config.yaml and normalize them."""
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    tickers = config.get("tickers", [])
    if not isinstance(tickers, list) or not tickers:
        raise ValueError("config.yaml must contain a non-empty 'tickers' list.")

    return [str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()]


def build_results(tickers: list[str], console: Console) -> list[dict]:
    results = []

    for ticker in tickers:
        console.print(f"[cyan]Researching {ticker}...[/cyan]")
        financials = get_financial_snapshot(ticker)
        technicals = get_technical_snapshot(ticker)
        score = score_stock(financials, technicals)
        score["sec_filings"] = get_sec_filing_signals(ticker)
        results.append(score)

    return sorted(results, key=lambda item: item["total_score"], reverse=True)


def print_summary(results: list[dict], console: Console) -> None:
    table = Table(title="Alex Stock Picker Results")
    table.add_column("Rank", justify="right")
    table.add_column("Ticker")
    table.add_column("Company")
    table.add_column("Score", justify="right")
    table.add_column("Rating")
    table.add_column("Conviction")

    for rank, result in enumerate(results, start=1):
        table.add_row(
            str(rank),
            result["ticker"],
            result["company_name"],
            f"{result['total_score']}/100",
            result["rating"],
            result["conviction"],
        )

    console.print(table)


def main() -> None:
    console = Console()
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file) or {}
    if isinstance(raw_config, dict) and isinstance(raw_config.get("portfolio"), dict):
        run_portfolio_research_main()
        return

    tickers = load_tickers(CONFIG_PATH)
    results = build_results(tickers, console)
    write_markdown_report(results, REPORT_PATH)
    print_summary(results, console)
    console.print(f"\n[green]Report saved to {REPORT_PATH}[/green]")


if __name__ == "__main__":
    main()
