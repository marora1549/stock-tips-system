"""`stocktips book` — the dashboard's "Formalise" button, and the dashboard payload it feeds."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("STOCKTIPS_ROOT", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stocktips import cli, report  # noqa: E402
from stocktips.learning import confidence  # noqa: E402
from stocktips.portfolio import ledger  # noqa: E402


def candidate(symbol="TEST", entry=100.0, verdict="BUY", composite=70, tradeable=True):
    return {
        "symbol": symbol, "company": f"{symbol} Ltd", "tip_id": "t1", "source_id": "manual:mohan",
        "corroborating_sources": [], "n_mentions": 1, "src_entry": None, "src_targets": [130.0], "src_stop": 90.0,
        "brokerages": [], "ltp": entry, "verdict": verdict, "composite": composite,
        "ta_confidence": 70, "fund_score": 80, "source_confidence": 50, "bucket": "hold-capable",
        "ta": {"patterns": ["breakout_60d_high_volume"]},
        "plan": {"entry": entry, "entry_zone": [entry * 0.995, entry * 1.005], "stop_loss": 95.0, "stop_loss_pct": -5.0,
                 "targets": [105.0, 110.0, 115.0], "target_pct": [5.0, 10.0, 15.0], "reward_risk_t2": 2.0,
                 "timeframe": "weekly", "time_stop_days": 10, "tradeable": tradeable},
    }


class Args:
    def __init__(self, **kw):
        self.symbol = kw.get("symbol", "TEST")
        self.capital = kw.get("capital")
        self.date = kw.get("date", "2026-09-07")
        self.force = kw.get("force", False)
        self.no_dashboard = kw.get("no_dashboard", True)


@pytest.fixture
def desk(monkeypatch, tmp_path):
    """Isolated reports/ + ledger with one analysed BUY candidate."""
    day = tmp_path / "reports" / "2026-09-07"
    day.mkdir(parents=True)
    (day / "analysis.json").write_text(json.dumps([candidate(), candidate("SKIPME", verdict="AVOID", composite=40),
                                                   candidate("UNTRADEABLE", tradeable=False)]), encoding="utf-8")
    monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(confidence, "PATH", tmp_path / "conf.json")

    class FakeNow:
        hour, minute = 8, 0
        def date(self):
            return pd.Timestamp("2026-09-08").date()
        def strftime(self, f):
            return "2026-09-08 08:00"
    monkeypatch.setattr(ledger, "now_ist", lambda: FakeNow())
    return tmp_path


def test_book_creates_pending_position_and_spreads_over_free_slots(desk, capsys):
    cli.cmd_book(Args())
    out = capsys.readouterr().out
    led = ledger.load()
    assert len(led["positions"]) == 1
    pos = led["positions"][0]
    # default allocation = deployable cash / free slots (100000 / 4), not the whole book
    assert pos["symbol"] == "TEST" and pos["status"] == "pending"
    assert pos["qty"] == 250 and pos["capital_inr"] == 25000.0
    assert led["cash_inr"] == 75000.0
    assert pos["stop_loss"] == 95.0 and pos["targets"] == [105.0, 110.0, 115.0]
    assert pos["bucket"] == "hold-capable"
    assert "BUY 250 TEST NSE CNC limit ₹100.00 · SL-M ₹95.00 · GTT ₹105.00 / 110.00 / 115.00" in out


def test_book_default_uses_per_stock_cap_when_only_one_slot_is_left(desk):
    led = ledger.load()
    for i in range(3):
        ledger.open_position(led, candidate(f"HELD{i}", entry=100.0), 15000)
    ledger.save(led)                      # 3 live, 1 slot, 55,000 cash
    cli.cmd_book(Args())
    pos = next(p for p in ledger.load()["positions"] if p["symbol"] == "TEST")
    assert pos["capital_inr"] == 50000.0  # clipped by the 50%/stock cap, not the 55,000 cash


def test_book_explicit_capital_and_duplicate_refused(desk):
    cli.cmd_book(Args(capital=20000))
    assert ledger.load()["positions"][0]["qty"] == 200
    with pytest.raises(SystemExit, match="already in the book"):
        cli.cmd_book(Args())


def test_book_refuses_non_buy_untradeable_unknown_and_overcap(desk):
    with pytest.raises(SystemExit, match="not a BUY"):
        cli.cmd_book(Args(symbol="SKIPME"))
    with pytest.raises(SystemExit, match="not tradeable"):
        cli.cmd_book(Args(symbol="UNTRADEABLE"))
    with pytest.raises(SystemExit, match="not in reports"):
        cli.cmd_book(Args(symbol="NOSUCH"))
    with pytest.raises(SystemExit, match="exceeds the 50%/stock cap"):
        cli.cmd_book(Args(capital=60000))
    with pytest.raises(SystemExit, match="below the 15% minimum"):
        cli.cmd_book(Args(capital=1000))
    assert ledger.load()["positions"] == []


def test_book_refuses_when_no_slots_or_no_cash(desk, monkeypatch):
    led = ledger.load()
    for i in range(4):
        ledger.open_position(led, candidate(f"HELD{i}", entry=100.0), 15000)
    ledger.save(led)
    with pytest.raises(SystemExit, match="no room"):
        cli.cmd_book(Args())
    # free a slot but leave the cash thin
    led = ledger.load()
    led["positions"] = led["positions"][:3]
    led["cash_inr"] = 500.0
    ledger.save(led)
    with pytest.raises(SystemExit, match="below the 15% minimum"):
        cli.cmd_book(Args())


def test_book_force_overrides_verdict(desk):
    cli.cmd_book(Args(symbol="SKIPME", capital=20000, force=True))
    assert ledger.load()["positions"][0]["symbol"] == "SKIPME"


def test_order_line_format():
    assert report.order_line("TATASTEEL", 12, 1234.5, 1180.25, [1300.0, 1400.5, 1512.75]) == \
        "BUY 12 TATASTEEL NSE CNC limit ₹1,234.50 · SL-M ₹1,180.25 · GTT ₹1,300.00 / 1,400.50 / 1,512.75"


def test_dashboard_payload_carries_levels_and_book_room(desk, monkeypatch, tmp_path):
    cli.cmd_book(Args(capital=20000))
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    cli.cmd_dashboard_data(Args())
    data = json.loads((tmp_path / "docs" / "data.json").read_text(encoding="utf-8"))
    assert data["analysis_day"] == "2026-09-07"
    assert data["book"] == {"max_open_positions": 4, "open_or_pending": 1, "slots_left": 3,
                            "deployable_cash": 80000.0, "min_alloc_inr": 15000.0, "max_alloc_inr": 50000.0}
    pos = data["positions"][0]
    assert pos["stop_loss_pct"] == -5.0 and pos["target_pct"] == [5.0, 10.0, 15.0]
    assert pos["order_line"].startswith("BUY 200 TEST NSE CNC")
    # suggestions carry everything the levels table + "source said" column needs
    sug = next(p for p in data["latest_analysis"] if p["symbol"] == "TEST")
    assert sug["plan"]["targets"] == [105.0, 110.0, 115.0]
    assert sug["src_targets"] == [130.0] and sug["src_stop"] == 90.0
    assert sug["tip_id"] == "t1" and sug["n_mentions"] == 1
    # the ledger file itself never gains the derived fields
    assert "order_line" not in ledger.load()["positions"][0]
