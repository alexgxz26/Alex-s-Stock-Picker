from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from stock_picker.portfolio_engine import (
    build_portfolio_research,
    candidate_action,
    maybe_copy_budget_inputs,
    money,
    percent,
    write_portfolio_report,
)


ROOT_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
DEFAULT_PORTFOLIO_PATH = ROOT_DIR / "data" / "portfolio.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Budget portfolio research engine")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config.yaml")
    parser.add_argument("--portfolio", default=None, help="Path to portfolio CSV")
    parser.add_argument("--offline", action="store_true", help="Skip yfinance and SEC API calls")
    parser.add_argument("--copy-inputs", action="store_true", help="Copy budget input files into project paths if present")
    return parser.parse_args()


def _load_raw_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _portfolio_path_from_config(config_path: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    raw = _load_raw_config(config_path)
    portfolio = raw.get("portfolio") if isinstance(raw.get("portfolio"), dict) else {}
    configured = portfolio.get("portfolio_file")
    return (ROOT_DIR / configured).resolve() if configured else DEFAULT_PORTFOLIO_PATH


def _report_paths(config_path: Path) -> list[Path]:
    raw = _load_raw_config(config_path)
    reporting = raw.get("reporting") if isinstance(raw.get("reporting"), dict) else {}
    paths = [
        ROOT_DIR / "reports" / "daily_dashboard.md",
        ROOT_DIR / "reports" / "portfolio_actions.md",
        ROOT_DIR / "reports" / "weekly_report.md",
    ]

    daily = reporting.get("daily_dashboard") if isinstance(reporting.get("daily_dashboard"), dict) else {}
    weekly = reporting.get("weekly_report") if isinstance(reporting.get("weekly_report"), dict) else {}
    configured_paths = [daily.get("output"), weekly.get("output")]
    for configured in configured_paths:
        if configured:
            path = (ROOT_DIR / str(configured)).resolve()
            if path not in paths:
                paths.append(path)
    return paths


def print_first_useful_output(research: dict[str, Any], console: Console) -> None:
    console.print(f"\n[bold]Total portfolio value:[/bold] {money(research['total_portfolio_value'])}")
    console.print(f"[bold]Cash-adjusted investable value:[/bold] {money(research['cash_adjusted_investable_value'])}")
    console.print(
        "[bold]Speculative exposure:[/bold] "
        f"{percent(research['speculative_exposure']['weight'])} "
        f"vs {percent(research['speculative_exposure']['limit_weight'])} limit "
        f"({research['speculative_exposure']['status']})"
    )

    allocation = Table(title="Cash-Adjusted Allocation")
    allocation.add_column("Ticker")
    allocation.add_column("Role")
    allocation.add_column("Value", justify="right")
    allocation.add_column("Weight", justify="right")
    allocation.add_column("Target", justify="right")
    allocation.add_column("Gap", justify="right")
    allocation.add_column("Flag")
    allocation.add_column("Status")

    for row in research["positions"]:
        allocation.add_row(
            row["ticker"],
            row["role"],
            money(row["position_value"]),
            percent(row["cash_adjusted_weight"]),
            percent(row["target_weight"]),
            money(row["allocation_gap_dollars"]),
            row["allocation_flag"],
            row["score_status"],
        )
    console.print(allocation)

    adds = Table(title="Top Add Candidates")
    adds.add_column("Ticker")
    adds.add_column("Role")
    adds.add_column("Score", justify="right")
    adds.add_column("Action")
    adds.add_column("Add Room", justify="right")
    adds.add_column("Status")
    candidates = research["top_add_candidates"] or research["provisional_add_candidates"]
    for row in candidates:
        adds.add_row(
            row["ticker"],
            row["role"],
            str(row["score"]),
            candidate_action(row),
            money(row["allocation_gap_dollars"]),
            row["score_status"],
        )
    if not candidates:
        adds.add_row("n/a", "n/a", "0", "n/a", "$0.00", "no candidates")
    console.print(adds)

    trims = Table(title="Trim / Exit Candidates")
    trims.add_column("Ticker")
    trims.add_column("Role")
    trims.add_column("Score", justify="right")
    trims.add_column("Action")
    trims.add_column("Gap", justify="right")
    trims.add_column("Reason")
    for row in research["trim_exit_candidates"]:
        trims.add_row(
            row["ticker"],
            row["role"],
            str(row["score"]),
            candidate_action(row),
            money(row["allocation_gap_dollars"]),
            row["role_reason"],
        )
    if not research["trim_exit_candidates"]:
        trims.add_row("n/a", "n/a", "0", "n/a", "$0.00", "no candidates")
    console.print(trims)


def main() -> None:
    args = parse_args()
    console = Console()
    config_path = Path(args.config).resolve()

    if args.copy_inputs:
        for action in maybe_copy_budget_inputs(ROOT_DIR):
            console.print(f"[green]{action}[/green]")

    portfolio_path = _portfolio_path_from_config(config_path, args.portfolio)
    research = build_portfolio_research(portfolio_path, config_path, fetch_online=not args.offline)

    for path in _report_paths(config_path):
        write_portfolio_report(research, path)

    print_first_useful_output(research, console)
    console.print("\n[green]Reports saved to reports/daily_dashboard.md, reports/portfolio_actions.md, and reports/weekly_report.md[/green]")


if __name__ == "__main__":
    main()
