from __future__ import annotations

from pathlib import Path

from stock_picker.portfolio_engine import load_positions


def run(portfolio_path: str | Path = "data/portfolio.csv"):
    return load_positions(Path(portfolio_path))
