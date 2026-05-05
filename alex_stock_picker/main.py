from __future__ import annotations

import argparse
from pathlib import Path

from data.config import load_config
from data.db import init_db
from data.logging_utils import get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alex's Stock Picker - Layer 1 data ingestion")
    parser.add_argument("--init-db", action="store_true", help="Initialize SQLite database schema")
    parser.add_argument("--daily", action="store_true", help="Run daily ingestion jobs")
    parser.add_argument("--weekly", action="store_true", help="Run weekly ingestion jobs")
    parser.add_argument("--tickers", nargs="*", help="Run selective ingestion for specific tickers")
    parser.add_argument("--forms", nargs="*", help="Run SEC Form 4 selective pull for specific tickers")
    parser.add_argument("--no-sec", action="store_true", help="Skip SEC ingestion")
    parser.add_argument("--no-13f", action="store_true", help="Skip institutional 13F ingestion")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    logger = get_logger(config)

    if args.init_db:
        db_path = Path(config["app"]["database_path"])
        init_db(db_path)
        logger.info("Initialized database at %s", db_path)

    if args.daily:
        logger.info("Daily ingestion selected. Module implementation comes next.")

    if args.weekly:
        logger.info("Weekly ingestion selected. Module implementation comes next.")

    if args.tickers:
        logger.info("Selective ticker ingestion selected: %s", args.tickers)

    if args.forms:
        logger.info("Selective SEC Form 4 pull selected: %s", args.forms)

    if not any([args.init_db, args.daily, args.weekly, args.tickers, args.forms]):
        logger.info("No action selected. Try: python main.py --init-db")


if __name__ == "__main__":
    main()
