"""Recent closes per symbol — state/price_cache.json.

The dashboard wants a price line behind every idea and position. The prices are already fetched by
`analyze` and by the evening mark-to-market, so they are cached here rather than re-fetched, and they
live in their own file rather than in the ledger: this is market data, not a trading record, and
nothing here is an input to any decision.
"""
from __future__ import annotations

import pandas as pd

from ..util import STATE_DIR, read_json, today_str, write_json

PATH = STATE_DIR / "price_cache.json"
BARS = 60
KEEP_SYMBOLS = 400


def load() -> dict:
    d = read_json(PATH, {"updated": today_str(), "bars": BARS, "closes": {}})
    d.setdefault("closes", {})
    return d


def save(cache: dict) -> None:
    closes = cache.get("closes") or {}
    if len(closes) > KEEP_SYMBOLS:                    # keep the most recently written
        cache["closes"] = dict(list(closes.items())[-KEEP_SYMBOLS:])
    cache["updated"] = today_str()
    cache["bars"] = BARS
    write_json(PATH, cache)


def remember(cache: dict, symbol: str, df: pd.DataFrame) -> None:
    """Store the tail of a price history that was fetched for another purpose."""
    if df is None or df.empty:
        return
    tail = df["close"].tail(BARS)
    cache.setdefault("closes", {})[symbol] = {
        "from": str(df.index[max(0, len(df) - BARS)].date()),
        "to": str(df.index[-1].date()),
        "c": [round(float(x), 2) for x in tail],
    }


def series(cache: dict, symbol: str) -> list[float]:
    return ((cache.get("closes") or {}).get(symbol) or {}).get("c") or []
