import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("STOCKTIPS_ROOT", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stocktips.sources import extract  # noqa: E402
from stocktips.analysis import ta, plan  # noqa: E402


def test_anchor_mint_style():
    txt = "Stocks to buy today: Tata Steel : Buy at ₹ 188, target price of ₹ 198, stop loss of ₹ 182. Also UCO Bank: Buy at ₹ 24.50 | Target ₹ 26 | Stop Loss ₹ 22."
    tips = extract.extract(txt, source_id="x", url="u", title="")
    by = {t["symbol"]: t for t in tips}
    assert by["TATASTEEL"]["src_entry"] == 188 and by["TATASTEEL"]["src_targets"] == [198] and by["TATASTEEL"]["src_stop"] == 182
    assert by["UCOBANK"]["src_targets"] == [26] and by["UCOBANK"]["src_stop"] == 22
    assert not by["TATASTEEL"]["needs_review"]


def test_anchor_brokerage_headline_and_subsource():
    txt = "Buy Brigade Enterprises; target of Rs 900: Motilal Oswal. Nuvama recommends buy on Devyani International, target price Rs 210."
    tips = extract.extract(txt, source_id="mc", url="u")
    by = {t["symbol"]: t for t in tips}
    assert by["BRIGADE"]["src_targets"] == [900] and by["BRIGADE"]["brokerage"] == "motilal"
    assert by["DEVYANI"]["brokerage"] == "nuvama" and by["DEVYANI"]["src_targets"] == [210]


def test_boilerplate_and_junk_names_dropped():
    txt = "Add as a Reliable and Trusted News Source Add Now! Buy the stock. Top Trending Stocks: SBI Share Price, HDFC Bank Share Price. The Indian stock market should buy dips."
    tips = extract.extract(txt, source_id="x", url="u")
    assert all(t["symbol"] not in ("IEX", "SBIN", "HDFCBANK") or t["needs_review"] for t in tips)


def synthetic_uptrend(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.15, 1.0, n))
    high = close + rng.uniform(0.2, 1.5, n)
    low = close - rng.uniform(0.2, 1.5, n)
    open_ = close + rng.normal(0, 0.5, n)
    idx = pd.bdate_range("2025-06-01", periods=n, tz="Asia/Kolkata")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(1e6, 3e6, n)}, index=idx)


def test_plan_geometry():
    df = synthetic_uptrend()
    snap = ta.analyze(df)
    for tf in ("weekly", "monthly"):
        p = plan.build_plan(snap, tf)
        assert p["stop_loss"] < p["entry"] < p["targets"][0] < p["targets"][1] < p["targets"][2]
        assert 0 <= p["ta_confidence"] <= 95
        assert p["time_stop_days"] == (10 if tf == "weekly" else 30)
    assert plan.classify_timeframe("target in two to three months", None) == "monthly"
    assert plan.classify_timeframe("for today's intraday trade", None) == "intraday"
    assert plan.classify_timeframe("", 25) == "long"
