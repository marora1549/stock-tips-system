"""Price data.

Daily OHLCV history  — Yahoo Finance chart API (query1/query2), `.NS` suffix, with `.BO` fallback.
Live quote           — Moneycontrol pricefeed (needs sc_id from autosuggest), Yahoo meta as fallback.

Yahoo rate-limits (429) without warning; Http() does exponential backoff and
caches responses for cache_ttl_minutes so a run never fetches a symbol twice.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from urllib.parse import quote

import pandas as pd

from ..util import http, settings
from .symbols import mc_suggest

log = logging.getLogger(__name__)

YF_CHART = "https://query{n}.finance.yahoo.com/v8/finance/chart/{sym}"
MC_PRICE = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{scid}"


# Yahoo's edge returns 429 for full browser UAs and for python-requests/curl UAs
# without cookies, but accepts a bare "Mozilla/5.0". Verified 2026-09-07.
YF_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _yahoo_chart(symbol: str, rng: str, interval: str) -> dict | None:
    # NSE tickers can contain "&" (GVT&D, M&M). Unencoded it ends the path segment at the ampersand,
    # so the request asks for a different symbol — or none — and the desk silently has no history.
    sym = quote(symbol, safe="")
    for n in (1, 2):
        r = http().get(YF_CHART.format(n=n, sym=sym), params={"range": rng, "interval": interval, "includePrePost": "false"},
                       headers=YF_HEADERS, ttl=timedelta(hours=6) if interval == "1d" else None)
        if r is not None and r.status_code == 200:
            try:
                res = r.json()["chart"]["result"]
                if res:
                    return res[0]
            except Exception as e:
                log.warning("yahoo parse error %s: %s", symbol, e)
        time.sleep(1.0)
    return None


def history(symbol: str, days: int | None = None, interval: str = "1d") -> pd.DataFrame | None:
    """Daily (or intraday) OHLCV as a DataFrame indexed by IST timestamp. Tries NSE then BSE listing."""
    days = days or settings()["data"]["history_days"]
    rng = "2y" if days > 365 else ("1y" if days > 180 else "6mo")
    if interval != "1d":
        rng = "1mo" if interval in ("60m", "1h") else "5d"
    for suffix in (".NS", ".BO"):
        res = _yahoo_chart(symbol + suffix, rng, interval)
        if not res:
            continue
        try:
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]},
                              index=pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata"))
            df = df.dropna(subset=["close"])
            df.index.name = "date"
            df.attrs["meta"] = {k: res["meta"].get(k) for k in ("regularMarketPrice", "previousClose", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "regularMarketTime", "symbol", "longName", "shortName")}
            if len(df) >= 30:
                return df
        except Exception as e:
            log.warning("history build error %s: %s", symbol, e)
    return None


def live_quote(symbol: str, company_hint: str | None = None) -> dict | None:
    """Best-effort live LTP. Moneycontrol first (true intraday), Yahoo meta as fallback."""
    sug = mc_suggest(company_hint or symbol)
    if sug and sug[0] == symbol:
        r = http().get(MC_PRICE.format(scid=sug[1]), use_cache=False)
        if r is not None and r.status_code == 200:
            try:
                d = r.json().get("data") or {}
                if d.get("pricecurrent"):
                    return {"ltp": float(d["pricecurrent"]), "prev_close": float(d.get("priceprevclose") or 0) or None,
                            "day_high": float(d.get("HP") or 0) or None, "day_low": float(d.get("LP") or 0) or None,
                            "volume": float(d.get("VOL") or 0) or None, "source": "moneycontrol", "ts": d.get("lastupd")}
            except Exception:
                pass
    res = _yahoo_chart(symbol + ".NS", "5d", "1d")
    if res:
        m = res["meta"]
        return {"ltp": m.get("regularMarketPrice"), "prev_close": m.get("previousClose") or m.get("chartPreviousClose"),
                "source": "yahoo", "ts": m.get("regularMarketTime")}
    return None
