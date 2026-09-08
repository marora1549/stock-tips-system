"""The trade that got away, replayed end to end.

On 7 September 2026 Power Grid named GE Vernova T&D India L1 bidder for a 6,000 MW HVDC terminal
station. The announcement carried a capacity and no rupee value. On the 8th the stock opened higher,
ran to about +12% and closed near +9%; the desk owner read the story mid-morning, after the move.

Everything below asserts the two things that had to be true for that morning to have gone
differently: **GVT&D on the page before the open**, and **a plan that would not have bought the top**.
No network anywhere — the wires, the prices and the fundamentals are all fixtures.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from stocktips import pipeline, report
from stocktips.analysis import catalyst, intraday
from stocktips.learning import eventscore
from stocktips.portfolio import daybook
from stocktips.sources import events

IST = timezone(timedelta(hours=5, minutes=30))
FIX = Path(__file__).parent / "fixtures"
STORY = json.loads((FIX / "news_gvtd_l1.json").read_text(encoding="utf-8"))

PREV_CLOSE = 2000.0
PREOPEN_NOW = datetime(2026, 9, 8, 8, 0, tzinfo=IST)

# GE Vernova T&D India, roughly: a debt-free, high-return business on about ₹3,900cr of revenue.
# The whole point of the case is the ratio — ₹13,000cr of order against that revenue.
FUNDAMENTALS = {
    "market_cap_cr": 51000.0, "pe": 62.0, "roce": 38.0, "roe": 29.0, "debt_to_equity": 0.02,
    "promoter_pct": 75.0, "revenue_ttm_cr": 3900.0, "revenue_basis": "trailing 4 quarters",
    "sales_growth_3_years": 24.0, "profit_growth_3_years": 71.0, "np_yoy_growth_pct": 42.0,
}


def daily_bars(last_close=PREV_CLOSE, n=260, atr_pct=3.2, turnover_cr=210.0):
    """A rising chart with a realistic daily range, ending at `last_close`."""
    idx = pd.date_range(end="2026-09-07", periods=n, freq="B", tz=IST)
    closes = [last_close * (1 - 0.0022 * (n - 1 - i)) for i in range(n)]
    rng = [c * atr_pct / 100 for c in closes]
    vol = turnover_cr * 1e7 / last_close
    return pd.DataFrame({
        "open": [c - r * 0.2 for c, r in zip(closes, rng)],
        "high": [c + r * 0.5 for c, r in zip(closes, rng)],
        "low": [c - r * 0.5 for c, r in zip(closes, rng)],
        "close": closes,
        "volume": [vol] * n,
    }, index=idx)


def five_min(shape, start=(9, 15)):
    idx = pd.to_datetime([datetime(2026, 9, 8, start[0], start[1], tzinfo=IST) + timedelta(minutes=5 * i)
                          for i in range(len(shape))])
    return pd.DataFrame({"open": [s[0] for s in shape], "high": [s[1] for s in shape],
                         "low": [s[2] for s in shape], "close": [s[3] for s in shape],
                         "volume": [s[4] for s in shape]}, index=idx)


# the real 8 September: gap to +5.6%, run to +12%, close near +9%
RUNAWAY_DAY = five_min([
    (2112, 2140, 2105, 2135, 900_000),
    (2135, 2165, 2130, 2160, 700_000),
    (2160, 2180, 2155, 2175, 600_000),
    (2175, 2240, 2170, 2235, 800_000),
    (2235, 2245, 2150, 2160, 700_000),
    (2160, 2200, 2155, 2185, 500_000),
])
# the same news on a calm open, which is the case the plan is built to take
MODEST_DAY = five_min([
    (2028, 2040, 2020, 2036, 500_000),
    (2036, 2044, 2030, 2033, 300_000),
    (2033, 2042, 2028, 2040, 280_000),
    (2040, 2075, 2038, 2070, 620_000),
    (2070, 2092, 2065, 2090, 480_000),
])


@pytest.fixture
def desk(monkeypatch, tmp_path):
    """The whole pipeline with the wires, the prices and the fundamentals replaced by fixtures."""
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(pipeline, "news_sources",
                        lambda: [{"id": "corp_bs_capitalmarket", "kind": "gnews", "enabled": True}])
    monkeypatch.setattr(pipeline.fetchers, "fetch_source", lambda src, **kw: [dict(STORY)])
    monkeypatch.setattr(pipeline.fundamentals, "fetch", lambda sym: dict(FUNDAMENTALS))

    state = {"intraday": MODEST_DAY}

    def history(symbol, days=None, interval="1d"):
        if interval == "1d":
            return daily_bars()
        return state["intraday"]

    monkeypatch.setattr(pipeline.prices, "history", history)
    return state


# ------------------------------------------------------------------ the reading
def test_the_story_names_the_supplier_not_the_utility():
    """POWERGRID is in the headline. It is also the party spending the money."""
    evs = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))
    syms = [e["symbol"] for e in evs]
    assert "GVT&D" == syms[0], f"the supplier should lead, got {syms[:3]}"
    assert "POWERGRID" not in syms, "the awarding party is not the beneficiary of its own capex"


def test_it_is_read_as_an_l1_call_and_not_a_signed_order():
    """The article says Power Grid *secured the contract* and GE Vernova *emerged L1*, forty words
    apart. Filing the second as the first overstates both the class and the certainty."""
    top = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    assert top["event"] == "l1_bidder"
    assert top["certainty"] == 0.8
    assert "order_win" in top["also_matched"]


def test_the_size_is_estimated_from_the_capacity_because_the_filing_gave_none():
    """No rupee figure in the announcement. 6,000 MW × ₹2.1cr/MW lands within 3% of Nomura's
    ₹12,980cr — which is the difference between a computable materiality and a shrug."""
    top = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    assert top["size_estimated"] is True
    assert 12_000 <= top["size_inr_cr"] <= 13_500
    assert abs(top["size_inr_cr"] - 12_980) / 12_980 < 0.05
    assert "6000 MW" in top["size_basis"].replace(",", "")


def test_theme_peers_are_demoted_because_the_story_has_a_winner():
    """Hitachi Energy makes HVDC terminals too. It did not win this one."""
    evs = {e["symbol"]: e for e in events.merge(events.scan(STORY, "corp_bs_capitalmarket"))}
    assert evs["GVT&D"]["route"] == "named" and evs["GVT&D"]["directness"] == 1.0
    peers = [e for s, e in evs.items() if s != "GVT&D"]
    assert peers, "the theme map should still surface peers"
    assert all(p["route"] == "sympathy" and p["directness"] < 0.5 for p in peers)


# ------------------------------------------------------------------ the scoring
def test_the_catalyst_clears_the_trade_bar_before_the_open():
    top = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    import stocktips.analysis.ta as ta
    snap = ta.analyze(daily_bars())
    got = catalyst.score(top, fundamentals=FUNDAMENTALS, fund_score=78, ta=snap, now=PREOPEN_NOW)
    assert got["verdict"] == "TRADE", got["reasons"]
    assert got["catalyst"] >= catalyst.TRADE_AT
    assert got["materiality_ratio"] > 3.0
    assert got["freshness"]["window"] == "overnight"
    joined = " ".join(got["reasons"])
    assert "a year's sales" in joined and "still ahead of the open" in joined


def test_the_same_story_read_at_eleven_is_worth_much_less():
    """This is the whole product: the news is identical, the tradability is not."""
    top = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    import stocktips.analysis.ta as ta
    snap = ta.analyze(daily_bars())
    early = catalyst.score(top, fundamentals=FUNDAMENTALS, fund_score=78, ta=snap, now=PREOPEN_NOW)
    late = catalyst.score({**top, "published_utc": "2026-09-08T05:30:00+00:00"},
                          fundamentals=FUNDAMENTALS, fund_score=78, ta=snap,
                          now=datetime(2026, 9, 8, 11, 30, tzinfo=IST))
    assert late["catalyst"] < early["catalyst"] - 15
    assert late["freshness"]["window"] == "in-session"


def test_an_illiquid_name_is_vetoed_whatever_the_news():
    top = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    import stocktips.analysis.ta as ta
    snap = ta.analyze(daily_bars(turnover_cr=1.2))
    got = catalyst.score(top, fundamentals=FUNDAMENTALS, fund_score=78, ta=snap, now=PREOPEN_NOW)
    assert got["verdict"] == "SKIP" and "too thin to exit" in got["veto"]


# ------------------------------------------------------------------ the plan
def test_the_real_open_is_refused_because_the_gap_ran_away():
    """A market order at 09:15 on the 8th bought most of the way into a +12% top. The rule says no."""
    plan = intraday.session_plan(PREV_CLOSE, RUNAWAY_DAY.iloc[:4], {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 9, 35, tzinfo=IST))
    assert plan["band"] == "runaway"
    assert plan["acts"] is False and plan["state"] == "voided"
    assert plan.get("trigger") is None, "a voided plan must not hand over an entry price"
    assert plan["watch"]["kind"] == "vwap_reclaim"
    assert plan["watch"]["reclaimed_now"] is False


def test_the_runaway_reopens_only_on_a_genuine_vwap_reclaim():
    plan = intraday.session_plan(PREV_CLOSE, RUNAWAY_DAY, {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 9, 55, tzinfo=IST))
    assert plan["watch"]["has_traded_below_vwap"] is True
    assert plan["watch"]["reclaimed_now"] is True


def test_a_calm_open_gets_a_real_plan_with_a_capped_stop():
    plan = intraday.session_plan(PREV_CLOSE, MODEST_DAY, {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 9, 35, tzinfo=IST))
    assert plan["band"] == "modest" and plan["acts"] is True
    assert plan["trigger"] > plan["opening_range"]["high"], "a break, not a touch"
    assert plan["stop_pct"] <= 1.5 and plan["stop_pct"] >= 0.5
    assert plan["targets"] == sorted(plan["targets"])
    assert plan["reward_risk_t2"] >= 1.0


def test_the_stop_is_not_tested_against_bars_from_before_the_trigger():
    """The opening-range low sits below the stop, but it happened before the break. Reading the
    whole day at once reports a winning trade as a stop-out."""
    plan = intraday.session_plan(PREV_CLOSE, MODEST_DAY, {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 10, 0, tzinfo=IST))
    assert MODEST_DAY["low"].min() <= plan["stop"], "the fixture must contain the trap"
    assert plan["state"] == "triggered" and plan["stopped"] is False


def test_the_size_comes_from_the_risk_budget_not_the_cash():
    plan = intraday.session_plan(PREV_CLOSE, MODEST_DAY, {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 9, 35, tzinfo=IST))
    size = intraday.size_for(plan)
    assert size["qty"] > 0
    assert size["risk_inr"] <= size["risk_budget_inr"] + plan["risk_inr"]
    assert size["capital_inr"] <= 100_000 * 0.40 + plan["trigger"]


def test_a_target_further_than_the_stock_travels_in_a_day_is_capped():
    """A 2.5× measured move off a wide opening range can imply +15% on a stock that moves 3% a day."""
    wide = five_min([(2100, 2200, 2090, 2195, 900_000), (2195, 2205, 2150, 2200, 500_000),
                     (2200, 2210, 2180, 2205, 400_000)])
    plan = intraday.session_plan(2090.0, wide, {"atr_pct": 3.2}, daily_bars(),
                                 now=datetime(2026, 9, 8, 9, 35, tzinfo=IST))
    if plan.get("targets"):
        cap = plan["open"] * (1 + 1.5 * 3.2 / 100)
        assert max(plan["targets"]) <= cap + 0.01
        assert any("daily ATR" in b for b in plan["target_basis"])


# ------------------------------------------------------------------ end to end
def test_the_preopen_run_puts_it_on_the_page_before_the_open(desk):
    raw = pipeline.gather_news()
    assert raw["events"], "the wire produced no events"
    card = pipeline.preopen(raw, now=PREOPEN_NOW, date="2026-09-08")
    traded = [c["symbol"] for c in card["trade"]]
    assert "GVT&D" in traded, f"TRADE list was {traded}"
    lead = card["trade"][0]
    assert lead["symbol"] == "GVT&D"
    assert lead["event"] == "l1_bidder"
    assert lead["plan"]["gap_ladder"][-1]["acts"] is False, "the runaway branch must refuse"


def test_the_email_says_the_useful_thing_in_its_first_line(desk):
    card = pipeline.preopen(pipeline.gather_news(), now=PREOPEN_NOW, date="2026-09-08")
    md = report.preopen(card)
    first = md.splitlines()[0]
    assert "GVT&D" in first and "Pre-open" in first
    assert "paper trading only" in md
    assert "gap up to +2%" in md or "gap up to +2" in md
    assert "3.3× a year's sales" in md or "a year's sales" in md


def test_the_session_run_opens_a_paper_trade_only_when_the_tape_triggered_it(desk):
    pipeline.preopen(pipeline.gather_news(), now=PREOPEN_NOW, date="2026-09-08")
    desk["intraday"] = MODEST_DAY
    out = pipeline.intraday_watch(now=datetime(2026, 9, 8, 10, 0, tzinfo=IST), date="2026-09-08")
    gv = next(c for c in out["candidates"] if c["symbol"] == "GVT&D")
    assert gv["state"] == "triggered"
    assert out["trades"] and out["trades"][0]["symbol"] == "GVT&D"
    assert out["trades"][0]["entry"] == gv["trigger"]


def test_the_runaway_day_never_becomes_a_trade(desk):
    pipeline.preopen(pipeline.gather_news(), now=PREOPEN_NOW, date="2026-09-08")
    desk["intraday"] = RUNAWAY_DAY.iloc[:4]
    out = pipeline.intraday_watch(now=datetime(2026, 9, 8, 9, 35, tzinfo=IST), date="2026-09-08")
    assert out["trades"] == [], "the +5.6% gap must not produce a paper entry"
    gv = next(c for c in out["candidates"] if c["symbol"] == "GVT&D")
    assert gv["state"] == "voided" and "VWAP" in gv["why_not"]


def test_the_close_settles_the_trade_and_grades_the_news(desk):
    pipeline.preopen(pipeline.gather_news(), now=PREOPEN_NOW, date="2026-09-08")
    desk["intraday"] = MODEST_DAY
    pipeline.intraday_watch(now=datetime(2026, 9, 8, 10, 0, tzinfo=IST), date="2026-09-08")
    out = pipeline.intraday_close(now=datetime(2026, 9, 8, 15, 20, tzinfo=IST), date="2026-09-08")

    assert out["exits"] and out["exits"][0]["symbol"] == "GVT&D"
    assert out["exits"][0]["pnl_inr"] > 0, out["exits"]
    graded = {g["event"]: g for g in out["graded"]}
    assert "l1_bidder" in graded
    assert graded["l1_bidder"]["open_to_high_pct"] > 0

    # the class now carries evidence, and the seed has moved
    classes = eventscore.load()
    assert classes["l1_bidder"]["n"] == 1
    assert eventscore.prior(classes, "l1_bidder", 24) != 24
    assert daybook.stats()["n_trades"] == 1


def test_a_news_class_that_keeps_fading_loses_weight_and_one_that_travels_gains_it():
    """What "training the system" means here: no model, just an honest ledger of what each kind of
    news was worth."""
    d = {}
    for _ in range(8):
        eventscore.note_outcome(d, "order_win", open_to_high_pct=3.4, open_to_close_pct=2.1, seed_prior=30)
        eventscore.note_outcome(d, "analyst_upgrade", open_to_high_pct=0.2, open_to_close_pct=-0.4, seed_prior=10)
        eventscore.note_outcome(d, "jv_partnership", open_to_high_pct=2.5, open_to_close_pct=-1.8, seed_prior=12)
    assert eventscore.prior(d, "order_win", 30) > 30
    assert eventscore.prior(d, "analyst_upgrade", 10) < 10
    # opens up and closes down must not accumulate weight the way a real move does
    assert (eventscore.prior(d, "jv_partnership", 12) - 12) < (eventscore.prior(d, "order_win", 30) - 30) / 3
    ranked = [r["event"] for r in eventscore.summary(d)]
    assert ranked.index("order_win") < ranked.index("analyst_upgrade")


# ------------------------------------------------------------------ what the run costs
def test_one_symbol_is_priced_once_however_many_events_name_it(monkeypatch, tmp_path):
    """A wire can hand over the same company under two event classes, and a busy morning can hand
    over fifty names. Each extra fetch is a Yahoo request and a Screener request, and those are what
    rate-limit and take a whole run down."""
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    charts, books = [], []

    def history(symbol, days=None, interval="1d"):
        if interval == "1d":
            charts.append(symbol)
            return daily_bars()
        return MODEST_DAY

    monkeypatch.setattr(pipeline.prices, "history", history)
    monkeypatch.setattr(pipeline.fundamentals, "fetch",
                        lambda sym: books.append(sym) or dict(FUNDAMENTALS))

    base = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    # the same symbol under three different classes, plus one other name
    raw = {"events": [base,
                      {**base, "event": "order_win", "event_prior": 30},
                      {**base, "event": "analyst_upgrade", "event_prior": 10},
                      {**base, "symbol": "POWERINDIA", "route": "theme", "directness": 1.0}],
           "sources": {}}
    pipeline.preopen(raw, now=PREOPEN_NOW, date="2026-09-08")
    assert charts.count("GVT&D") == 1, f"priced GVT&D {charts.count('GVT&D')} times"
    assert books.count("GVT&D") == 1
    assert sorted(set(charts)) == ["GVT&D", "POWERINDIA"]


def test_the_queue_is_capped_and_the_best_events_are_priced_first(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(pipeline, "MAX_SYMBOLS_PRICED", 2)
    seen = []
    monkeypatch.setattr(pipeline.prices, "history",
                        lambda s, days=None, interval="1d": (seen.append(s) or daily_bars())
                        if interval == "1d" else MODEST_DAY)
    monkeypatch.setattr(pipeline.fundamentals, "fetch", lambda sym: dict(FUNDAMENTALS))

    base = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    raw = {"events": [
        {**base, "symbol": "WEAK", "event": "corporate_action", "event_prior": 8, "directness": 0.4},
        {**base, "symbol": "STRONG", "event": "order_win", "event_prior": 30, "directness": 1.0},
        {**base, "symbol": "MIDDLE", "event": "regulatory_approval", "event_prior": 26, "directness": 1.0},
    ], "sources": {}}
    card = pipeline.preopen(raw, now=PREOPEN_NOW, date="2026-09-08")
    assert set(seen) == {"STRONG", "MIDDLE"}, f"priced {seen}"
    assert any("queue was full" in s["why"] for s in card["skipped"])


def test_a_stale_story_costs_no_requests_at_all(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(pipeline.prices, "history",
                        lambda *a, **k: pytest.fail("a stale story should never be priced"))
    base = events.merge(events.scan(STORY, "corp_bs_capitalmarket"))[0]
    raw = {"events": [{**base, "published_utc": "2026-09-01T10:00:00+00:00"}], "sources": {}}
    card = pipeline.preopen(raw, now=PREOPEN_NOW, date="2026-09-08")
    assert card["trade"] == [] and card["skipped"]
    assert "days old" in card["skipped"][0]["why"]
