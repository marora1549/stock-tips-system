"""The fundamentals score, tested against a stock it got badly wrong.

On 9 September 2026 this desk scored **Enviro Infra Engineers 92 out of 100**. Markets Mojo's paid
verdict on the same company, the same morning, was **37 — SELL**, and the report's case was not a
matter of opinion:

* operating cash flow of −₹78.49cr, **negative three years running** and worsening 68%;
* operating cash flow at −26.4% of net profit — the profit was not becoming cash;
* interest cover the lowest of five quarters at 5.23×, down from 9.11×;
* borrowings up 80% (₹234cr → ₹422cr);
* net sales growth 7.46% against 46.25% the year before, profit 3.77% against 62.59%;
* mutual funds holding 0.09% and the number of FIIs falling from 16 to 13.

The 92 was not a rounding error. Every one of the nine terms in the old score was a *level* or a
*long average*, the two largest were three-year CAGRs describing a boom that had just ended, and
there was no cash-flow term at all. A flaw could only ever be one vote among nine.

These tests pin the specific failure and the structural fix: findings that put a **ceiling** on the
score rather than being averaged into it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stocktips.data import fundamentals as fu

FIX = Path(__file__).parent / "fixtures"
EIEL = json.loads((FIX / "fundamentals_eiel.json").read_text(encoding="utf-8"))
MOJO_VERDICT = 37


def test_the_stock_that_scored_92_now_scores_like_a_sell():
    got = fu.assess(EIEL)
    assert got["score"] < 45, f"scored {got['score']}; Mojo said {MOJO_VERDICT} SELL"
    assert abs(got["score"] - MOJO_VERDICT) <= 12, (
        f"scored {got['score']} against an independent {MOJO_VERDICT} — not required to agree, but a "
        f"large gap means one of us is reading different numbers")


def test_the_cash_flow_is_actually_read_and_it_dominates():
    got = fu.assess(EIEL)
    joined = " ".join(got["why"])
    assert "operating cash flow" in joined, "the most important line in the filing must appear"
    assert "consumed cash" in joined
    assert any("negative 3 years running" in fl for fl in got["flags"])


def test_a_long_cagr_the_latest_year_contradicts_is_discounted():
    """A 50% three-year CAGR beside 7.5% last year is describing a boom that has ended."""
    joined = " ".join(fu.assess(EIEL)["why"])
    assert "is history" in joined
    assert "has stalled" in joined


def test_the_deterioration_terms_all_fire():
    joined = " ".join(fu.assess(EIEL)["why"])
    for expected in ("interest cover", "interest cost up", "borrowings up",
                     "institutions hold", "PEG"):
        assert expected in joined, f"missing the {expected!r} term"


def test_good_levels_cannot_outvote_a_cash_burn():
    """The structural fix. Strip the trend data — which is how the 92 happened — and the score must
    still refuse to call a cash-burning company excellent."""
    blind = {k: v for k, v in EIEL.items()
             if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity", "promoter_pct",
                      "pledged_pct", "revenue_ttm_cr", "revenue_fy_cr", "profit_fy_cr",
                      "sales_growth_3_years", "profit_growth_3_years", "np_yoy_growth_pct",
                      "cfo_cr", "cfo_negative_streak")}
    got = fu.assess(blind)
    assert got["raw_score"] > 70, "the good levels really do add up to a high raw score"
    assert got["score"] <= 45, "and the ceiling has to bring it down anyway"
    assert any("negative 3 years running" in c for c in got["caps"])


def test_a_missing_cash_flow_section_is_not_the_same_as_a_healthy_one():
    """This is the exact shape that produced 92, and it must now say so."""
    nocash = {k: v for k, v in EIEL.items()
              if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity", "promoter_pct",
                       "revenue_ttm_cr", "sales_growth_3_years", "profit_growth_3_years")}
    got = fu.assess(nocash)
    assert got["raw_score"] >= 85, "the old arithmetic still reaches the low 90s"
    assert got["score"] <= 75, "but it may not be presented as one"
    assert any("partial view" in c for c in got["caps"])
    assert "cash flow" in " ".join(got["caps"])


def test_a_genuinely_sound_company_still_scores_well():
    """The fix must not simply mark everything down. Cash converting, growth intact, low debt."""
    sound = {
        "market_cap_cr": 51000.0, "pe": 34.0, "roce": 38.0, "roe": 29.0, "debt_to_equity": 0.02,
        "promoter_pct": 75.0, "pledged_pct": 0.0, "fii_pct": 12.0, "dii_pct": 9.0,
        "institutional_pct": 21.0, "revenue_ttm_cr": 3900.0, "revenue_fy_cr": 3900.0,
        "profit_fy_cr": 420.0, "sales_growth_3_years": 24.0, "profit_growth_3_years": 30.0,
        "sales_growth_1y_pct": 22.0, "sales_growth_prev_1y_pct": 26.0,
        "profit_growth_1y_pct": 28.0, "profit_growth_prev_1y_pct": 31.0,
        "cfo_cr": 390.0, "cfo_negative_streak": 0, "borrowings_growth_pct": 4.0,
        "interest_cover": 18.0, "interest_cover_falling": False, "interest_growth_yoy_pct": 3.0,
        "np_yoy_growth_pct": 26.0,
    }
    got = fu.assess(sound)
    assert got["score"] >= 75, f"a sound company scored {got['score']}: {got['why']}"
    assert not got["caps"], got["caps"]
    assert "profit is turning into cash" in " ".join(got["why"])


def test_the_two_value_wrapper_still_works_for_existing_callers():
    n, why = fu.score(EIEL)
    assert isinstance(n, int) and isinstance(why, list) and why
    assert n == fu.assess(EIEL)["score"]


def test_screeners_own_pros_and_cons_are_kept_verbatim():
    """A number with a dissenting voice beside it beats a more confident number on its own."""
    h = ('<div class="pros"><h2>Pros</h2><ul><li>Company is almost debt free.</li>'
         '<li>Company has delivered good profit growth of 50.2% CAGR over last 5 years</li></ul></div>'
         '<div class="cons"><h2>Cons</h2><ul>'
         '<li>Company has a low return on equity of 15.4% over last 3 years.</li>'
         '<li>Working capital days have increased from 210 to 305 days</li></ul></div>')
    d = fu._parse(h)
    assert d["screener_pros"][0].startswith("Company is almost debt free")
    assert any("Working capital days" in c for c in d["screener_cons"])


def test_no_data_at_all_is_neutral_low_and_says_so():
    got = fu.assess(None)
    assert got["score"] == 40 and "no fundamentals data" in got["why"][0]
