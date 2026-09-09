"""Which company a story's event actually belongs to.

This is the failure mode that would have quietly ruined the pre-open email. A "stocks to watch"
column — one of the wires this desk reads every morning — names a dozen companies and reports
something eventful about one of them. Handing the eventful bit to all twelve produces eleven
confident, wrong candidates, each with the right rupee figure attached to the wrong stock.
"""
from __future__ import annotations

import json
from pathlib import Path

from stocktips.sources import events

FIX = Path(__file__).parent / "fixtures"
ROUNDUP = json.loads((FIX / "news_stocks_to_watch.json").read_text(encoding="utf-8"))
SINGLE = json.loads((FIX / "news_gvtd_l1.json").read_text(encoding="utf-8"))


def syms(doc, source="w"):
    return {e["symbol"]: e for e in events.merge(events.scan(doc, source))}


def test_a_roundup_gives_the_event_only_to_the_company_it_is_about():
    got = syms(ROUNDUP)
    assert "BEL" in got, "the company that actually won the order must survive"
    for other in ("CIPLA", "RELIANCE", "TITAN", "TMCV", "TMPV"):
        assert other not in got, f"{other} was only mentioned; it did not win a defence order"


def test_the_roundups_peers_come_through_the_theme_map_and_stay_demoted():
    got = syms(ROUNDUP)
    peers = {s: e for s, e in got.items() if s != "BEL"}
    assert peers, "a defence order should still surface defence peers"
    assert all(e["route"] == "sympathy" and e["directness"] < 0.5 for e in peers.values())


def test_the_size_lands_on_the_company_whose_sentence_carried_it():
    assert syms(ROUNDUP)["BEL"]["size_inr_cr"] == 2100.0


def test_a_single_subject_story_is_unaffected_by_the_roundup_rule():
    """The rule must not cost the case the whole system exists for."""
    got = syms(SINGLE)
    assert got["GVT&D"]["route"] == "named"
    assert got["GVT&D"]["directness"] == 1.0
    assert got["GVT&D"]["event"] == "l1_bidder"


def test_a_headline_naming_one_company_still_carries_the_story_to_it():
    """Where the eventful sentence says "the company" rather than the name."""
    doc = {"url": "u", "title": "Bharat Electronics bags radar order", "published": "Mon, 07 Sep 2026 20:00:00 +0530",
           "text": "The order is worth Rs 900 crore. The company said it won the contract from the "
                   "Ministry of Defence and will execute it over two years."}
    got = syms(doc)
    assert "BEL" in got and got["BEL"]["route"] == "named"
    assert got["BEL"]["size_inr_cr"] == 900.0


def test_an_article_with_no_event_at_all_yields_nothing():
    doc = {"url": "u", "title": "Nifty ends flat as banks drag", "published": "Mon, 07 Sep 2026 20:00:00 +0530",
           "text": "The Nifty ended marginally lower on Monday. Reliance Industries and Titan Company "
                   "closed in the red while Cipla gained. Analysts said volumes were thin."}
    assert events.scan(doc, "w") == []


def test_a_negative_event_beats_a_positive_one_in_the_same_story():
    doc = {"url": "u", "title": "Suzlon Energy wins 300 MW order, board approves Rs 3,000 crore QIP",
           "published": "Mon, 07 Sep 2026 20:00:00 +0530",
           "text": "Suzlon Energy said it won a 300 MW order. Separately its board approved a "
                   "qualified institutional placement to raise up to Rs 3,000 crore."}
    got = syms(doc)
    assert "SUZLON" in got
    assert got["SUZLON"]["sign"] == -1, "a dilution alongside an order win is not a story to buy"
    assert got["SUZLON"]["event"] == "dilution"
