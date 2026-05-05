from __future__ import annotations

from pathlib import Path

from stock_picker.portfolio_engine import load_portfolio_config


def run(config_path: str | Path = "config.yaml"):
    return load_portfolio_config(Path(config_path))
