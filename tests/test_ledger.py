"""Ledger lifecycle tests with synthetic bars (no network)."""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("STOCKTIPS_ROOT", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stocktips.portfolio import ledger  # noqa: E402
from stocktips.learning import confidence  # noqa: E402


def bars(rows):
    """rows: list of (date, o, h, l, c)"""
    idx = pd.to_datetime([r[0] for r in rows]).tz_localize("Asia/Kolkata")
    return pd.DataFrame({"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": 1e6}, index=idx)


def make_pick(symbol="TEST", entry=100.0):
    return {"symbol": symbol, "company": "Test Ltd", "tip_id": "t1", "source_id": "src_a", "corroborating_sources": ["src_b"],
            "ta_confidence": 70, "fund_score": 80, "composite": 72, "ta": {"patterns": ["breakout_60d_high_volume"]},
            "plan": {"entry": entry, "stop_loss": 95.0, "targets": [105.0, 110.0, 115.0], "timeframe": "weekly", "time_stop_days": 10}}


@pytest.fixture
def led(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(confidence, "PATH", tmp_path / "conf.json")
    l = ledger.load()
    # force "booked before open" so opened == today for deterministic tests
    class FakeNow:
        hour, minute = 8, 0
        def date(self):
            return pd.Timestamp("2026-09-08").date()
        def strftime(self, f):
            return "2026-09-08 08:00"
    monkeypatch.setattr(ledger, "now_ist", lambda: FakeNow())
    return l


def test_fill_then_stepped_targets(led, monkeypatch):
    pos = ledger.open_position(led, make_pick(), 40000)
    assert pos["qty"] == 400 and led["cash_inr"] == 60000
    conf = {}
    series = {
        "2026-09-08": bars([("2026-09-08", 100.5, 103, 99, 102)]),          # fill at 100.5
        "2026-09-09": bars([("2026-09-08", 100.5, 103, 99, 102), ("2026-09-09", 102, 106, 101, 105.5)]),   # T1
        "2026-09-10": bars([("2026-09-09", 102, 106, 101, 105.5), ("2026-09-10", 106, 116, 105, 114)]),   # T2 + T3 same bar
    }
    for day, df in series.items():
        monkeypatch.setattr(ledger.prices, "history", lambda s, days=120, _df=df: _df)
        ev = ledger.mark_to_market(led, conf, on=day)
    assert not led["positions"] and len(led["closed"]) == 1
    p = led["closed"][0]
    assert p["entry"] == 100.5 and p["targets_hit"] == [1, 2, 3]
    qtys = [e["qty"] for e in p["exits"]]
    assert qtys == [160, 120, 120]                     # 40/30/30 of 400
    assert p["outcome"] == "t3" and p["pnl_inr"] > 0
    assert abs(led["cash_inr"] - (100000 + p["pnl_inr"])) < 0.01
    # primary source got full credit, corroborating half
    assert conf["src_a"]["score"] > conf["src_b"]["score"] > 0
    assert conf["src_a"]["n_t1"] == 1 and conf["src_a"]["n_resolved"] == 1


def test_stop_loss_gap_through(led, monkeypatch):
    ledger.open_position(led, make_pick(), 40000)
    conf = {}
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: bars([("2026-09-08", 100, 101, 99, 100)]))
    ledger.mark_to_market(led, conf, on="2026-09-08")
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: bars([("2026-09-08", 100, 101, 99, 100), ("2026-09-09", 92, 94, 90, 93)]))
    ev = ledger.mark_to_market(led, conf, on="2026-09-09")
    p = led["closed"][0]
    assert p["outcome"] == "stop_loss" and p["exits"][0]["price"] == 92   # gapped through 95 → filled at open 92
    assert conf["src_a"]["score"] < 0 and conf["src_a"]["n_sl"] == 1
    assert "STOP-LOSS" in " ".join(ev)


def test_time_stop_hot_potato_exits_but_quality_holds(led, monkeypatch):
    hot = make_pick("HOT"); hot["fund_score"] = 40
    good = make_pick("GOOD"); good["fund_score"] = 80
    ledger.open_position(led, hot, 30000)
    ledger.open_position(led, good, 30000)
    conf = {}
    flat = [("2026-09-08", 100, 101, 99, 100)]
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: bars(flat))
    ledger.mark_to_market(led, conf, on="2026-09-08")
    deadline = [p for p in led["positions"] if p["symbol"] == "HOT"][0]["deadline"]
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: bars(flat + [(deadline, 100, 101, 99, 99.5)]))
    ev = ledger.mark_to_market(led, conf, on=deadline)
    assert [p["symbol"] for p in led["closed"]] == ["HOT"]
    assert led["closed"][0]["outcome"] == "time_stop_loss"
    held = [p for p in led["positions"] if p["symbol"] == "GOOD"][0]
    assert held["status"] == "hold"
    assert any("HOLD" in e for e in ev) and any("TIME STOP" in e for e in ev)


def test_gap_up_cancels(led, monkeypatch):
    ledger.open_position(led, make_pick(), 40000)
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: bars([("2026-09-08", 104, 105, 103, 104)]))
    ev = ledger.mark_to_market(led, {}, on="2026-09-08")
    assert not led["positions"] and led["cash_inr"] == 100000 and "CANCELLED" in ev[0]


def test_confidence_weight_neutral_prior():
    assert confidence.weight(0.0) == 0.5
    assert confidence.weight(50) > 0.9 and confidence.weight(-50) < 0.1
    assert confidence.display(0) == 50
