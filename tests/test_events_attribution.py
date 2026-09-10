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


# ------------------------------------------------------------------ what day one live actually cost
AGGREGATOR = json.loads((FIX / "news_aggregator_ticker.json").read_text(encoding="utf-8"))


def test_an_aggregator_page_yields_only_what_its_headline_is_about():
    """The first live pre-open run graded two names TRADE and both were wrong.

    The page was an aggregator: a ₹97.66cr wagon-leasing story with a rail of unrelated ticker
    headlines beside it. The scraper read the whole page as article text, so a "Kendrapara
    shipbuilding cluster ... Rs 24,700 crore" headline became the order's size (7.9× revenue instead
    of 3%), and Suzlon — which appears nowhere but in another ticker line — was filed as a named
    beneficiary of the Jupiter Wagons order.
    """
    got = syms(AGGREGATOR, "corp_orders")
    assert set(got) == {"JWL"}, f"expected only the headline's subject, got {sorted(got)}"
    assert got["JWL"]["size_inr_cr"] == 97.66, "the size must be the one in its own sentence"
    assert got["JWL"]["event"] == "order_win"


def test_a_body_scraped_from_every_paragraph_is_not_trusted_for_attribution():
    """`body_how` says how the text was found. `paragraphs` means no article container matched."""
    trusted = dict(AGGREGATOR, body_how="container")
    assert len(syms(trusted, "corp_orders")) > 1, "a trusted body may implicate more names"
    assert set(syms(AGGREGATOR, "corp_orders")) == {"JWL"}


def test_a_named_company_with_no_figure_of_its_own_gets_none_not_the_articles_biggest():
    """"Vishnu Chemicals commissions new plant" acquired ₹404.88cr from a railway bid two lines away."""
    trusted = dict(AGGREGATOR, body_how="container")
    got = syms(trusted, "corp_orders")
    assert got["VISHNU"]["size_inr_cr"] is None
    assert got["JWL"]["size_inr_cr"] == 97.66


def test_a_single_subject_story_still_takes_the_articles_figure():
    """The fix must not cost the ordinary case, where the article's number is about its subject."""
    doc = {"url": "u", "title": "Bharat Electronics bags radar order", "body_how": "container",
           "published": "Tue, 09 Sep 2026 07:00:00 +0530",
           "text": "The order is worth Rs 900 crore.\nThe company said it won the contract from the "
                   "Ministry of Defence and will execute it over two years."}
    assert syms(doc)["BEL"]["size_inr_cr"] == 900.0


def test_a_theme_keyword_does_not_fire_inside_an_unrelated_word():
    """"applicable law" contains the literal substring "cable" — a live US securities-suit wire hit
    the power_cables theme this way and fanned a Beta Bionics lawsuit out to five Indian cable
    stocks as a regulatory-action AVOID. Keyword matching must respect word boundaries."""
    assert events.themes_in("under the applicable law and ethical rules") == []
    assert events.themes_in("KEI supplies EHV cable to the project") != []


def test_page_furniture_is_stripped_before_the_body_is_read():
    from stocktips.sources import fetchers
    page = ('<html><body><article><p>' + 'Jupiter Wagons said it received an order worth Rs 97.66 '
            'crore from GATX India for the supply of freight wagons on lease. ' * 3 + '</p></article>'
            '<aside class="related-news"><p>Kendrapara shipbuilding cluster to draw Rs 24,700 crore</p>'
            '<p>Suzlon bags new order from Ayana Renewable Power for wind turbines</p></aside>'
            '<div class="trending-ticker"><p>RVNL wins Rs 404.88 crore rail electrification bid</p></div>'
            '</body></html>')
    stripped = fetchers.strip_furniture(page)
    assert "Jupiter Wagons" in stripped
    for gone in ("Kendrapara", "Suzlon", "RVNL", "24,700", "404.88"):
        assert gone not in stripped, f"{gone} survived the furniture strip"


def test_a_theme_fan_out_needs_something_tying_the_story_to_this_market():
    """"Babcock LGE secures contract for four new VLGCs" is a UK marine-engineering firm building gas
    carriers for a European operator at a Korean yard. The shipping theme fired on it and produced
    Adani Ports and Cochin Shipyard as candidates on the 9 Sep re-run. A theme play with nobody
    named is already one inference; inferring the country as well is two, and the second was wrong.
    """
    uk = {"url": "u", "title": "Babcock LGE secures contract for four new VLGCs", "body_how": "container",
          "published": "Tue, 09 Sep 2026 06:00:00 +0530",
          "text": "Babcock LGE has secured a contract to supply cargo handling systems for four new "
                  "very large gas carriers. The shipbuilding order was placed by a European operator "
                  "and the vessels will be delivered from a South Korean yard."}
    assert events.scan(uk, "corp_orders") == []

    # the same theme, anchored here, still works
    ind = dict(uk, title="Cochin Shipyard bags shipbuilding order worth Rs 1,200 crore",
               text="Cochin Shipyard said it has secured a shipbuilding order worth Rs 1,200 crore "
                    "from an Indian operator for four vessels.")
    assert "COCHINSHIP" in syms(ind)


def test_only_a_named_company_may_claim_the_order_as_its_own():
    """"HAL · 0.6x revenue" came off Tata's ₹20,000cr tank bid — HAL did not win that order. It reads
    as a fact about HAL and is not one. This holds for a theme play too, not just a sympathy peer:
    when the winner is unlisted, the listed names are the only way to trade it and still did not
    win it."""
    doc = {"url": "u", "body_how": "container",
           "title": "Tata emerges lowest bidder for Rs 20,000-crore Project Zorawar light tank",
           "published": "Tue, 09 Sep 2026 06:30:00 +0530",
           "text": "Tata Advanced Systems has emerged as the lowest bidder for the Rs 20,000 crore "
                   "Project Zorawar light tank programme of the Ministry of Defence."}
    got = syms(doc, "corp_orders")
    assert got, "the listed defence names are still the way to trade an unlisted winner"
    for sym, e in got.items():
        assert e["route"] != "named", f"{sym} is not named in that story"
        assert e["size_is_own_order"] is False
        assert e["size_inr_cr"] == 20000.0, "the deal size is still worth showing"

    # and the scorer must refuse to turn it into a ratio
    from stocktips.analysis import catalyst
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    hal = got["HAL"]
    got_score = catalyst.score(hal, fundamentals={"revenue_ttm_cr": 33800.0, "market_cap_cr": 320000.0},
                               fund_score=89, ta={"avg_turnover_cr": 900.0, "close": 4800.0},
                               now=datetime(2026, 9, 9, 8, 0, tzinfo=ist))
    assert got_score["materiality_ratio"] is None
    assert any("the order the winner took" in r for r in got_score["reasons"])


def test_the_named_winner_keeps_its_materiality():
    """The fix must not cost the case the whole system exists for."""
    from stocktips.analysis import catalyst
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    lead = events.merge(events.scan(SINGLE, "w"))[0]
    assert lead["symbol"] == "GVT&D" and lead["size_is_own_order"] is True
    scored = catalyst.score(lead, fundamentals={"revenue_ttm_cr": 3900.0, "market_cap_cr": 51000.0},
                            fund_score=78, ta={"avg_turnover_cr": 210.0, "close": 2000.0},
                            now=datetime(2026, 9, 8, 8, 0, tzinfo=ist))
    assert scored["materiality_ratio"] > 3.0
