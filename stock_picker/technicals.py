from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf


def _as_float(value: Any) -> float | None:
    if isinstance(value, pd.Series):
        if value.empty:
            return None
        value = value.iloc[0]
    if value is None or pd.isna(value):
        return None
    return float(value)


def _close_series(history: pd.DataFrame) -> pd.Series:
    close_data = history["Close"]
    if isinstance(close_data, pd.DataFrame):
        close_data = close_data.iloc[:, 0]
    return close_data.dropna()


def _period_return(closes: pd.Series, trading_days: int) -> float | None:
    if len(closes) <= trading_days:
        return None

    old_price = closes.iloc[-trading_days - 1]
    latest_price = closes.iloc[-1]
    if old_price == 0:
        return None

    return float((latest_price / old_price) - 1)


def get_technical_snapshot(ticker_symbol: str) -> dict[str, Any]:
    """Pull one year of price history and calculate simple trend metrics."""
    empty_snapshot = {
        "ticker": ticker_symbol.upper(),
        "latest_close": None,
        "ma_50": None,
        "ma_200": None,
        "above_50_ma": False,
        "above_200_ma": False,
        "return_1m": None,
        "return_3m": None,
        "return_6m": None,
        "return_1y": None,
    }

    try:
        history = yf.download(
            ticker_symbol,
            period="1y",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        return empty_snapshot

    if history.empty or "Close" not in history:
        return {
            **empty_snapshot,
        }

    closes = _close_series(history)
    latest_close = _as_float(closes.iloc[-1])
    ma_50 = _as_float(closes.tail(50).mean()) if len(closes) >= 50 else None
    ma_200 = _as_float(closes.tail(200).mean()) if len(closes) >= 200 else None

    return {
        "ticker": ticker_symbol.upper(),
        "latest_close": latest_close,
        "ma_50": ma_50,
        "ma_200": ma_200,
        "above_50_ma": bool(latest_close and ma_50 and latest_close > ma_50),
        "above_200_ma": bool(latest_close and ma_200 and latest_close > ma_200),
        "return_1m": _period_return(closes, 21),
        "return_3m": _period_return(closes, 63),
        "return_6m": _period_return(closes, 126),
        "return_1y": _period_return(closes, min(252, len(closes) - 1)),
    }
