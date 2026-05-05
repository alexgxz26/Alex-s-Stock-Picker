from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_picker.portfolio_engine import build_portfolio_research, load_portfolio_config, load_positions


class PortfolioEngineTest(unittest.TestCase):
    def test_load_budget_config_understands_risk_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                """
portfolio:
  cash_available: 1000
  base_currency: USD
risk_limits:
  max_total_speculative_exposure: 0.10
  max_core_position: 0.10
  max_growth_position: 0.06
  max_swing_position: 0.04
  max_speculative_position: 0.015
  min_market_cap_for_core: 50000000000
""",
                encoding="utf-8",
            )

            config = load_portfolio_config(config_path)

            self.assertEqual(config.cash, 1000)
            self.assertEqual(config.max_speculative_exposure, 0.10)
            self.assertEqual(config.role_max_weights["Core"], 0.10)
            self.assertEqual(config.role_max_weights["Speculative"], 0.015)


    def test_load_positions_aggregates_duplicate_tickers_and_cash(self):
        with tempfile.TemporaryDirectory() as tmp:
            portfolio_path = Path(tmp) / "portfolio.csv"
            portfolio_path.write_text(
                "ticker,currency,shares,last_price,market_value\n"
                "MSFT,USD,1,400,400\n"
                "MSFT,USD,2,410,820\n"
                "CASH,USD,,1,50\n",
                encoding="utf-8",
            )

            positions, cash = load_positions(portfolio_path)

            self.assertEqual(cash, 50)
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0].ticker, "MSFT")
            self.assertEqual(positions[0].shares, 3)
            self.assertEqual(positions[0].provided_value, 1220)


    def test_offline_research_marks_non_base_fx_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            portfolio_path = Path(tmp) / "portfolio.csv"
            config_path.write_text(
                """
portfolio:
  cash_available: 100
  base_currency: USD
risk_limits:
  max_total_speculative_exposure: 0.10
""",
                encoding="utf-8",
            )
            portfolio_path.write_text(
                "ticker,currency,shares,last_price,market_value\n"
                "MSFT,USD,1,400,400\n"
                "D05,SGD,10,50,500\n",
                encoding="utf-8",
            )

            research = build_portfolio_research(portfolio_path, config_path, fetch_online=False)
            by_ticker = {row["ticker"]: row for row in research["positions"]}

            self.assertEqual(research["total_portfolio_value"], 500)
            self.assertEqual(by_ticker["MSFT"]["position_value"], 400)
            self.assertIsNone(by_ticker["D05"]["position_value"])
            self.assertIn("fx_rate_SGD_USD", by_ticker["D05"]["missing_fields"])


if __name__ == "__main__":
    unittest.main()
