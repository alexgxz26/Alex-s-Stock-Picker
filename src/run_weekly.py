from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from run_portfolio_research import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    _portfolio_path_from_config,
    print_first_useful_output,
)
from stock_picker.portfolio_engine import build_portfolio_research, write_portfolio_report  # noqa: E402


WEEKLY_REPORT_PATHS = [
    ROOT_DIR / "reports" / "weekly_report.md",
    ROOT_DIR / "reports" / "portfolio_actions.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weekly stock picker reports")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to config.yaml")
    parser.add_argument("--portfolio", default=None, help="Path to portfolio CSV")
    parser.add_argument("--offline", action="store_true", help="Skip yfinance and SEC API calls")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    portfolio_path = _portfolio_path_from_config(config_path, args.portfolio)

    research = build_portfolio_research(portfolio_path, config_path, fetch_online=not args.offline)
    for report_path in WEEKLY_REPORT_PATHS:
        write_portfolio_report(research, report_path)
    print_first_useful_output(research, Console())
    print("Weekly reports saved to " + ", ".join(str(path) for path in WEEKLY_REPORT_PATHS))


if __name__ == "__main__":
    main()
