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
                            "deployable_cash": 80000.0, "capital_inr": 100000, "min_alloc_inr": 15000.0,
                            "max_alloc_inr": 50000.0, "min_allocation_pct": 15, "max_single_stock_pct": 50}
    assert data["cash_flows"] == []
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


# --------------------------------------------------------------- data-outage detection
def test_mark_to_market_reports_data_availability(monkeypatch, tmp_path):
    """A run that can't price anything is an outage, not a quiet day."""
    import pandas as pd
    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(confidence, "PATH", tmp_path / "conf.json")

    class FakeNow:
        hour, minute = 8, 0
        def date(self):
            return pd.Timestamp("2026-09-08").date()
        def strftime(self, f):
            return "2026-09-08 08:00"
    monkeypatch.setattr(ledger, "now_ist", lambda: FakeNow())

    led = ledger.load()
    ledger.open_position(led, candidate("AAA", entry=100.0), 20000)
    ledger.open_position(led, candidate("BBB", entry=100.0), 20000)
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: None)

    rep: dict = {}
    events = ledger.mark_to_market(led, {}, on="2026-09-08", report=rep)
    assert rep == {"eligible": 2, "no_data": 2, "stale": 0, "marked": 0}
    assert all("no price data" in e for e in events)

    # a pending position dated for a later session isn't due a bar, so it can't be "missing" one
    rep2: dict = {}
    ledger.mark_to_market(led, {}, on="2026-09-04", report=rep2)
    assert rep2["eligible"] == 0 and rep2["no_data"] == 0


def test_mark_to_market_counts_stale_bars_separately(monkeypatch, tmp_path):
    import pandas as pd
    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")

    class FakeNow:
        hour, minute = 8, 0
        def date(self):
            return pd.Timestamp("2026-09-08").date()
        def strftime(self, f):
            return "2026-09-08 08:00"
    monkeypatch.setattr(ledger, "now_ist", lambda: FakeNow())
    led = ledger.load()
    ledger.open_position(led, candidate("AAA", entry=100.0), 20000)

    idx = pd.to_datetime(["2026-09-04"]).tz_localize("Asia/Kolkata")
    stale = pd.DataFrame({"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1e6]}, index=idx)
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: stale)

    rep: dict = {}
    ledger.mark_to_market(led, {}, on="2026-09-08", report=rep)
    assert rep == {"eligible": 1, "no_data": 0, "stale": 1, "marked": 0}   # holiday/lag, not an outage


def test_eod_exits_non_zero_on_total_data_outage(monkeypatch, tmp_path, capsys):
    """The failure mode that made a broken run report SUCCEEDED."""
    import pandas as pd
    from stocktips import pipeline
    from stocktips.learning import journal

    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(confidence, "PATH", tmp_path / "conf.json")
    monkeypatch.setattr(journal, "PATH", tmp_path / "lessons.md")
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()

    class FakeNow:
        hour, minute = 8, 0
        def date(self):
            return pd.Timestamp("2026-09-04").date()
        def strftime(self, f):
            return "2026-09-04 08:00"
    monkeypatch.setattr(ledger, "now_ist", lambda: FakeNow())
    led = ledger.load()
    ledger.open_position(led, candidate("AAA", entry=100.0), 20000)
    ledger.save(led)
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=120: None)

    class EodArgs:
        date = "2026-09-04"
        force = True
    with pytest.raises(SystemExit) as e:
        cli.cmd_eod(EodArgs())
    assert "DATA OUTAGE" in str(e.value) and "1 position(s)" in str(e.value)
    # the report is still written, so the run leaves a record of the outage behind
    assert (tmp_path / "reports" / "2026-09-04" / "eod.md").exists()


# --------------------------------------------------------------- discretionary exits
def test_close_cancels_a_pending_position_and_returns_its_capital(desk):
    cli.cmd_book(Args(capital=20000))
    class CloseArgs:
        symbol, price, note, no_dashboard = "TEST", None, "freeing capital", True
    cli.cmd_close(CloseArgs())
    led = ledger.load()
    assert led["positions"] == []
    assert led["cash_inr"] == 100000.0                     # nothing was ever filled, so nothing was lost
    assert led["closed"] == []                             # a cancellation is not a closed trade
    conf = confidence.load()
    assert conf.get("manual:mohan", {}).get("n_resolved", 0) == 0   # the source is not graded for my call


def test_close_exits_an_open_position_at_a_named_price(desk):
    cli.cmd_book(Args(capital=20000))
    led = ledger.load()
    pos = led["positions"][0]
    pos.update(status="open", entry=100.0, ltp=104.0, deadline="2026-09-22")
    ledger.save(led)

    conf = confidence.load()
    confidence.ensure(conf, "manual:mohan")
    confidence.save(conf)

    class CloseArgs:
        symbol, price, note, no_dashboard = "test", 104.0, "better idea available", True
    cli.cmd_close(CloseArgs())

    led = ledger.load()
    assert led["positions"] == [] and len(led["closed"]) == 1
    done = led["closed"][0]
    assert done["outcome"] == "manual_exit" and done["pnl_inr"] == 800.0 and done["pnl_pct"] == 4.0
    assert led["cash_inr"] == 100800.0                     # 80,000 left + 20,000 invested + 800 profit
    conf = confidence.load()
    src = conf["manual:mohan"]
    assert src["n_resolved"] == 1 and src["sum_return_pct"] == 4.0
    assert src["score"] == 0.0                             # expectancy counts, score does not move


def test_close_refuses_unknown_symbol_and_needs_a_price_without_data(desk, monkeypatch):
    class CloseArgs:
        symbol, price, note, no_dashboard = "NOSUCH", None, None, True
    with pytest.raises(SystemExit, match="not in the book"):
        cli.cmd_close(CloseArgs())

    cli.cmd_book(Args(capital=20000))
    led = ledger.load()
    led["positions"][0].update(status="open", entry=100.0)
    ledger.save(led)
    monkeypatch.setattr(ledger.prices, "history", lambda s, days=30: None)

    class NoPrice:
        symbol, price, note, no_dashboard = "TEST", None, None, True
    with pytest.raises(SystemExit, match="pass --price"):
        cli.cmd_close(NoPrice())


# --------------------------------------------------------------- capital flows
def test_capital_add_moves_base_and_cash_and_widens_the_caps(desk, capsys):
    class CapArgs:
        add, withdraw, note, no_dashboard = 50000.0, None, "conviction top-up", True
    cli.cmd_capital(CapArgs())
    led = ledger.load()
    assert led["capital_inr"] == 150000.0 and led["cash_inr"] == 150000.0
    assert led["cash_flows"][0]["amount"] == 50000.0 and led["cash_flows"][0]["note"] == "conviction top-up"
    # the 50%/stock cap is a percentage of the live base, so it moved with it
    cli.cmd_book(Args(capital=75000))
    assert ledger.load()["positions"][0]["capital_inr"] == 75000.0


def test_capital_withdraw_cannot_exceed_uncommitted_cash(desk):
    cli.cmd_book(Args(capital=40000))          # 40,000 committed, 60,000 uncommitted
    class TooMuch:
        add, withdraw, note, no_dashboard = None, 80000.0, None, True
    with pytest.raises(SystemExit, match="only ₹60,000.00 is uncommitted"):
        cli.cmd_capital(TooMuch())

    class Fine:
        add, withdraw, note, no_dashboard = None, 60000.0, None, True
    cli.cmd_capital(Fine())
    led = ledger.load()
    assert led["cash_inr"] == 0.0 and led["capital_inr"] == 40000.0
    assert led["cash_flows"][0]["amount"] == -60000.0 and led["cash_flows"][0]["note"] == "withdrawal"


def test_time_weighted_return_ignores_a_mid_period_deposit(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger, "PATH", tmp_path / "ledger.json")
    led = ledger.load()
    # day 1: flat. day 2: +₹50,000 deposited, book ends at 152,000 → the real gain is 2,000 on 150,000
    led["equity_curve"] = [{"date": "2026-09-08", "equity": 100000.0}]
    ledger.cash_flow(led, 50000.0, note="top-up", on="2026-09-09")
    led["equity_curve"].append({"date": "2026-09-09", "equity": 152000.0})
    assert ledger.time_weighted_return_pct(led) == pytest.approx(1.33, abs=0.01)
    st = ledger.stats(led)
    assert st["return_pct"] == pytest.approx(1.33, abs=0.01)
    assert st["simple_return_pct"] == pytest.approx(1.33, abs=0.01)   # same here, because the flow is fully invested
    assert st["initial_capital"] == 100000 and st["net_flows_inr"] == 50000.0
    # the naive reading — equity vs the *old* base — would have called this +52%
    assert round((152000.0 / 100000.0 - 1) * 100, 2) == 52.0
