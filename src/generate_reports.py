from __future__ import annotations

from pathlib import Path

from stock_picker.portfolio_engine import write_portfolio_report
from src.analyze_portfolio import run as analyze_portfolio


def run(
    portfolio_path: str | Path = "data/portfolio.csv",
    config_path: str | Path = "config.yaml",
    output_path: str | Path = "reports/portfolio_actions.md",
    *,
    fetch_online: bool = True,
) -> Path:
    research = analyze_portfolio(portfolio_path, config_path, fetch_online=fetch_online)
    output = Path(output_path)
    write_portfolio_report(research, output)
    return output
