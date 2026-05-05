from __future__ import annotations

from pathlib import Path

from stock_picker.portfolio_engine import build_portfolio_research


def run(
    portfolio_path: str | Path = "data/portfolio.csv",
    config_path: str | Path = "config.yaml",
    *,
    fetch_online: bool = True,
) -> list[dict]:
    positions = build_portfolio_research(Path(portfolio_path), Path(config_path), fetch_online=fetch_online)["positions"]
    return [{"ticker": row["ticker"], "score": row["score"], "status": row["score_status"]} for row in positions]
