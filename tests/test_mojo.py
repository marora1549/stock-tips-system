"""The Markets Mojo importer, against the exact two pastes that come off that site."""
from __future__ import annotations

from pathlib import Path

import pytest

from stocktips.analysis import contenders
from stocktips.sources import mojo

FIX = Path(__file__).parent / "fixtures"
TABLE = (FIX / "mojo_table.txt").read_text(encoding="utf-8")
DETAIL = (FIX / "mojo_detail.txt").read_text(encoding="utf-8")


class FakeMaster:
    """Just enough of SymbolMaster to resolve names, with no network anywhere near it."""

    def __init__(self, pairs):
        self.rows = [{"symbol": s, "name": n} for s, n in pairs]
        self.by_symbol = {s: r for s, r in zip((s for s, _ in pairs), self.rows)}


MASTER = FakeMaster([
    ("KENNAMET", "Kennametal India Limited"),
    ("RGL", "Renaissance Global Limited"),
    ("FSL", "Firstsource Solutions Limited"),
    ("GNFC", "Gujarat Narmada Valley Fertilizers and Chemicals Limited"),
    ("MOTILALOFS", "Motilal Oswal Financial Services Limited"),
    ("RSYSTEMS", "R Systems International Limited"),
    ("CONCOR", "Container Corporation of India Limited"),
    ("LANCER", "Lancer Container Lines Limited"),
    ("DEEPAKNTR", "Deepak Nitrite Limited"),
    ("ANDHRSUGAR", "The Andhra Sugars Limited"),
    ("APLAPOLLO", "APL Apollo Tubes Limited"),
    ("PRICOLLTD", "Pricol Limited"),
    ("MARKSANS", "Marksans Pharma Limited"),
    ("PAYTM", "One 97 Communications Limited"),
    ("GLAND", "Gland Pharma Limited"),
    ("INDHOTEL", "The Indian Hotels Company Limited"),
    ("JUBLFOOD", "Jubilant Foodworks Limited"),
    ("LALPATHLAB", "Dr. Lal Path Labs Ltd."),
    ("ADANIENT", "Adani Enterprises Limited"),
    ("ADANIPOWER", "Adani Power Limited"),
    ("ADANIGREEN", "Adani Green Energy Limited"),
    ("MARUTI", "Maruti Suzuki India Limited"),
    ("HDFCBANK", "HDFC Bank Limited"),
])


# ------------------------------------------------------------------ the table paste
def test_table_reads_every_row():
    rows = mojo.parse(TABLE)
    assert len(rows) == 19
    assert [r["company_raw"] for r in rows][:3] == ["Kennametal India", "Renaiss. Global", "Firstsour.Solu."]
    assert rows[-1]["company_raw"] == "Maruti Suzuki"


def test_table_header_is_not_mistaken_for_a_row():
    """The paste carries Mojo's own column headers, and "Call" appears in them."""
    assert all(r["company_raw"] not in ("Stock Name", "Call Type", "Days Since") for r in mojo.parse(TABLE))


def test_table_fields_land_in_the_right_columns():
    row = mojo.parse(TABLE)[0]
    assert row == {
        "company_raw": "Kennametal India", "action": "buy", "call_type": "Monthly", "timeframe": "monthly",
        "src_entry": 4700.70, "src_targets": [5168.90], "src_stop": 4385.73,
        "current_price": 4658.40, "entry_date": "2026-09-07", "sector": "Engineering", "mcap": "Small Cap",
        "performance_pct": -0.90, "returns_till_target_pct": 10.96, "days_since": "1 day", "direction": "long",
    }


def test_commas_in_prices_survive():
    maruti = [r for r in mojo.parse(TABLE) if r["company_raw"] == "Maruti Suzuki"][0]
    assert maruti["src_entry"] == 13371.25 and maruti["src_targets"] == [14708.37]


def test_a_sell_call_is_read_as_a_short():
    fsl = [r for r in mojo.parse(TABLE) if r["company_raw"] == "Firstsour.Solu."][0]
    assert fsl["action"] == "sell" and fsl["direction"] == "short"
    assert fsl["src_targets"][0] < fsl["src_entry"] < fsl["src_stop"]


def test_a_buy_label_with_a_target_below_entry_is_still_a_short():
    """Trust the arithmetic over the label — a mislabelled row must not reach the book as a long."""
    rows = mojo.parse("Some Co\n\nBuy\n\nMonthly\n\nMid Cap\n\nChemicals\n\n100\n\n0.1%\n\n100\n\n"
                      "01-Sep-2026\n\n90\n\n110\n\n0.5%\n\n2 days\n\n9%\n\nFollow\n")
    assert rows[0]["action"] == "sell" and rows[0]["direction"] == "short"


# ------------------------------------------------------------------ the detail paste
def test_detail_panel_reads_its_labels():
    row = mojo.parse(DETAIL)[0]
    assert row["action"] == "buy" and row["timeframe"] == "monthly"
    assert (row["src_entry"], row["src_targets"], row["src_stop"]) == (4700.70, [5168.90], 4385.73)
    assert row["entry_date"] == "2026-09-07" and row["returns_till_target_pct"] == 10.96


def test_detail_panel_without_a_name_says_so_rather_than_inventing_one():
    """The panel often omits the stock; "BUY" is a value, not a company."""
    assert mojo.parse(DETAIL)[0]["company_raw"] == ""


def test_detail_panel_keeps_a_name_when_the_paste_has_one():
    assert mojo.parse("Kennametal India\n" + DETAIL)[0]["company_raw"] == "Kennametal India"


def test_nonsense_paste_yields_nothing():
    assert mojo.parse("") == [] and mojo.parse("hello\nthere\n") == []


# ------------------------------------------------------------------ names → symbols
@pytest.mark.parametrize("name,symbol", [
    ("Kennametal India", "KENNAMET"),
    ("Renaiss. Global", "RGL"),
    ("Firstsour.Solu.", "FSL"),
    ("Motil.Oswal.Fin.", "MOTILALOFS"),
    ("R Systems Intl.", "RSYSTEMS"),
    ("Container Corpn.", "CONCOR"),
    ("Deepak Nitrite", "DEEPAKNTR"),
    ("Andhra Sugars", "ANDHRSUGAR"),
    ("APL Apollo Tubes", "APLAPOLLO"),
    ("Pricol Ltd", "PRICOLLTD"),
    ("Marksans Pharma", "MARKSANS"),
    ("One 97", "PAYTM"),
    ("Gland Pharma", "GLAND"),
    ("Indian Hotels Co", "INDHOTEL"),
    ("Jubilant Food", "JUBLFOOD"),
    ("Dr Lal Pathlabs", "LALPATHLAB"),
    ("Adani Enterp.", "ADANIENT"),
    ("Maruti Suzuki", "MARUTI"),
])
def test_every_truncated_name_in_the_paste_resolves(name, symbol):
    assert mojo.resolve_name(name, MASTER)["symbol"] == symbol


def test_a_pasted_ticker_resolves_as_itself():
    hit = mojo.resolve_name("GNFC", MASTER)
    assert (hit["symbol"], hit["method"]) == ("GNFC", "symbol")


def test_a_name_nobody_has_is_left_alone():
    assert mojo.resolve_name("Zzz Holdings Universal", MASTER)["symbol"] is None
    assert mojo.resolve_name("", MASTER)["symbol"] is None


def test_a_genuinely_ambiguous_name_comes_back_with_its_candidates_not_a_guess():
    hit = mojo.resolve_name("Adani", MASTER)
    assert hit["symbol"] is None
    assert hit["method"] == "ambiguous"
    assert {c["symbol"] for c in hit["candidates"]} >= {"ADANIENT", "ADANIPOWER"}


def test_resolution_never_touches_the_network(monkeypatch):
    import stocktips.util as util
    monkeypatch.setattr(util, "http", lambda *a, **k: pytest.fail("resolve_name went online"))
    for row in mojo.parse(TABLE):
        mojo.resolve_name(row["company_raw"], MASTER)


# ------------------------------------------------------------------ the head-to-head
def _idea(symbol, composite, eta, momentum=50, corroborating=(), src_target=None, targets=(110, 120, 130)):
    return {
        "symbol": symbol, "company": symbol, "source_id": "mojo", "corroborating_sources": list(corroborating),
        "n_mentions": 1 + len(corroborating), "composite": composite, "verdict": "BUY", "bucket": "b",
        "ta_confidence": 70, "fund_score": 60, "source_confidence": 50, "ltp": 100.0,
        "src_targets": [src_target] if src_target else [], "src_stop": 92.0, "src_entry": 99.0,
        "ta": {"momentum_score": momentum},
        "plan": {"timeframe": "monthly", "time_stop_days": 30, "entry": 100.0, "stop_loss": 95.0,
                 "stop_loss_pct": 5.0, "targets": list(targets), "reward_risk_t2": 2.5,
                 "eta_days": eta, "tradeable": True},
    }


def test_the_faster_clock_wins_a_tie_on_composite():
    top = contenders.rank([_idea("SLOW", 70, 28), _idea("FAST", 70, 6)], n=2)
    assert [c["symbol"] for c in top] == ["FAST", "SLOW"]
    assert "clock" in top[0]["why"][1]


def test_a_target_the_drift_cannot_reach_is_penalised():
    top = contenders.rank([_idea("NODRIFT", 80, None), _idea("MOVING", 74, 8)], n=2)
    assert top[0]["symbol"] == "MOVING"


def test_corroboration_counts_but_is_capped():
    top = contenders.rank([_idea("SOLO", 70, 10), _idea("BOTH", 68, 10, corroborating=["a", "b", "c"])], n=2)
    assert top[0]["symbol"] == "BOTH"
    assert top[0]["contender_score"] - 8.0 == pytest.approx(  # only two extra sources are counted
        contenders.rank([_idea("BOTH", 68, 10)], n=1)[0]["contender_score"])


def test_a_tipster_asking_for_more_than_the_chart_offers_loses_points():
    modest = contenders.rank([_idea("A", 70, 10, src_target=125)], n=1)[0]["contender_score"]
    greedy = contenders.rank([_idea("A", 70, 10, src_target=180)], n=1)[0]["contender_score"]
    assert greedy == modest - 4


def test_only_three_come_back_and_each_symbol_once():
    ideas = [_idea(s, 70 + i, 10) for i, s in enumerate("ABCDE")] + [_idea("A", 99, 5)]
    top = contenders.rank(ideas, n=3)
    assert len(top) == 3 and len({c["symbol"] for c in top}) == 3
    assert [c["rank"] for c in top] == [1, 2, 3]


def test_untradeable_ideas_never_contend():
    dead = _idea("DEAD", 95, 4)
    dead["plan"]["tradeable"] = False
    assert [c["symbol"] for c in contenders.rank([dead, _idea("LIVE", 50, 20)], n=3)] == ["LIVE"]


def test_the_comparison_states_both_sides():
    c = contenders.rank([_idea("A", 70, 10, src_target=125)], n=1)[0]["vs_source"]
    assert c["src_target"] == 125 and c["our_targets"] == [110, 120, 130]
    assert c["our_upside_pct"] == 30.0 and c["src_upside_pct"] == 25.0
    assert any("inside our ladder" in n for n in c["notes"])


def test_a_held_name_is_flagged_as_held():
    top = contenders.rank([_idea("MINE", 70, 10)], n=1, held={"MINE"})
    assert top[0]["held"] is True
