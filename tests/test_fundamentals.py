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
    assert got["raw_score"] > 60, "the good levels really do add up to a comfortable raw score"
    assert got["score"] <= 45, "and the ceiling has to bring it down anyway"
    assert any("negative 3 years running" in c for c in got["caps"])


def test_a_missing_cash_flow_section_is_not_the_same_as_a_healthy_one():
    """This is the exact shape that produced 92, and it must now say so."""
    nocash = {k: v for k, v in EIEL.items()
              if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity", "promoter_pct",
                       "revenue_ttm_cr", "sales_growth_3_years", "profit_growth_3_years")}
    got = fu.assess(nocash)
    assert got["raw_score"] >= 75, "levels alone still read as a strong company"
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


# ---------------------------------------------------------------------------------------------
# Everything below was written after running the parser against live screener.in pages for the
# first time. Every one of these is a bug the fixtures could not have shown me, and each is here
# so that specific mistake cannot return quietly.
# ---------------------------------------------------------------------------------------------


def test_the_ttm_column_is_not_read_as_a_financial_year():
    """The bug the live pages found.

    Screener's profit-and-loss table ends in a TTM column; its cash-flow table does not. Reading
    the P&L positionally therefore compared TTM-against-FY26 with FY26-against-FY25, and Enviro
    Infra's real deceleration — 46.2% down to 7.5% — came out as a mild 10.3% against 7.5%. The
    -8 stall term never fired. Only the cash-burn ceiling caught that company; a name without a
    burn would have sailed through.
    """
    block = """
    <thead><tr><th class="text"></th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th>
      <th>TTM</th></tr></thead>
    <tbody><tr><td class="text">Sales</td><td>100</td><td>146</td><td>157</td><td>173</td></tr>
    </tbody>"""
    vals, labels = fu._period_values(block, "Sales")
    assert labels == ["Mar 2024", "Mar 2025", "Mar 2026"], "TTM is not a year"
    assert vals == [100.0, 146.0, 157.0]
    got = fu._pair_growth(vals, "sales")
    assert got["sales_growth_1y_pct"] == pytest.approx(7.53, abs=0.1), "FY26 over FY25"
    assert got["sales_growth_prev_1y_pct"] == pytest.approx(46.0, abs=0.5), "FY25 over FY24"


def test_a_blank_cell_does_not_slide_the_series_a_year_earlier():
    """Same class of error, different cause: dropping unreadable cells renumbers every later one."""
    block = """
    <thead><tr><th class="text"></th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th></tr></thead>
    <tbody><tr><td class="text">Borrowings</td><td></td><td>234</td><td>422</td></tr></tbody>"""
    vals, labels = fu._period_values(block, "Borrowings")
    assert (vals, labels) == ([234.0, 422.0], ["Mar 2025", "Mar 2026"]), \
        "the two readable values must keep the two dates they were printed under"


def test_a_sixteen_year_old_sheet_is_not_a_current_one():
    """GE Vernova T&D's *consolidated* page holds one column: Dec 2010. It scored 55 out of 100 off
    that, with no flag, because every check asked whether a figure was present and none asked
    whether it was current."""
    got = fu.assess({"roce": 20.0, "roe": 18.0, "pe": 30.0, "market_cap_cr": 30000.0,
                     "promoter_pct": 75.0, "fy_labels": ["Dec 2010"],
                     "parse_warnings": ["the last annual column is Dec 2010, 16 years old — "
                                        "this is not a current sheet"]})
    assert got["score"] <= 60, "an ancient sheet cannot yield a confident number"
    assert any("did not read cleanly" in c for c in got["caps"])


def test_correlated_strengths_are_counted_once():
    """The 92's mirror image. Infosys came out of the additive scorer at 97 and GE Vernova T&D at
    100, because ROCE, ROE and margin are three readings of one fact and each was paid in full.
    Nothing may reach 90: a public ratio page cannot tell the 90th percentile from the 99th."""
    flawless = {"roce": 60.0, "roe": 45.0, "pe": 20.0, "market_cap_cr": 900000.0,
                "promoter_pct": 60.0, "pledged_pct": 0.0, "fii_pct": 20.0, "dii_pct": 15.0,
                "debt_to_equity": 0.0, "sales_growth_3_years": 40.0, "profit_growth_3_years": 45.0,
                "sales_growth_1y_pct": 38.0, "sales_growth_prev_1y_pct": 36.0,
                "profit_growth_1y_pct": 44.0, "profit_growth_prev_1y_pct": 42.0,
                "np_yoy_growth_pct": 40.0, "revenue_fy_cr": 200000.0, "profit_fy_cr": 40000.0,
                "cfo_cr": 48000.0, "cfo_negative_streak": 0, "borrowings_growth_pct": 0.0,
                "interest_cover": 90.0}
    got = fu.assess(flawless)
    assert got["score"] >= 80, "a company this clean must still read as excellent"
    assert got["raw_score"] <= 90, "and 90 is the ceiling of what this evidence can support"
    assert any("measure the same thing more than once" in w for w in got["why"]), \
        "and the double counting must be shown, not silently absorbed"


def test_a_debt_free_company_is_not_charged_for_a_missing_ratio():
    """Interest cover only means something when there is interest to cover. Skipping it for
    Infosys, TCS and HAL then billed all three the 75 partial-view ceiling for being debt-free."""
    clean = {"roce": 40.0, "roe": 30.0, "pe": 25.0, "market_cap_cr": 600000.0,
             "promoter_pct": 55.0, "fii_pct": 18.0, "dii_pct": 12.0, "debt_to_equity": 0.0,
             "sales_growth_3_years": 12.0, "profit_growth_3_years": 11.0,
             "sales_growth_1y_pct": 9.0, "sales_growth_prev_1y_pct": 10.0,
             "profit_growth_1y_pct": 8.0, "revenue_fy_cr": 160000.0, "profit_fy_cr": 27000.0,
             "cfo_cr": 30000.0, "cfo_negative_streak": 0, "borrowings_growth_pct": 0.0,
             "interest_immaterial": True}
    got = fu.assess(clean)
    assert not any("interest cover" in c for c in got["caps"]), \
        "having no debt is knowledge, not a blind spot"
    assert got["score"] >= 70


def test_a_lender_is_not_graded_by_an_industrial_model():
    """Bajaj Finance was capped at 45 for 'operating cash flow negative 12 years running' — which
    for an NBFC is not a finding: disbursing a loan is an operating outflow, so a growing lender's
    operating cash flow is negative by construction. Capping the number was not enough, because
    the sentence printed under it was false."""
    got = fu.assess({"roce": 12.0, "roe": 20.0, "pe": 30.0, "market_cap_cr": 500000.0,
                     "promoter_pct": 54.0, "debt_to_equity": 3.8, "cfo_cr": -40000.0,
                     "cfo_negative_streak": 12, "sector": "Financial Services",
                     "industry": "Finance",
                     "model_misfit": "Finance — borrowings are this company's raw material"})
    assert got["unrated"] is True
    assert got["score"] == 50, "neutral, and declared unrated"
    assert not got["caps"], "no ceiling, because no scoring happened"
    assert "not rated" in got["why"][0]
    assert not any("negative" in w and "cash flow" in w for w in got["why"]), \
        "and above all it must not print a false reason"


def test_a_sheet_that_contradicts_itself_caps_lower_than_a_sheet_with_gaps():
    """A number I cannot reconcile is worse than a number I do not have."""
    contradictory = fu.assess({"roce": 25.0, "roe": 20.0, "pe": 18.0, "market_cap_cr": 20000.0,
                               "promoter_pct": 60.0, "revenue_ttm_cr": 8000.0,
                               "revenue_fy_cr": 400.0,
                               "parse_warnings": ["trailing revenue ₹8,000cr against last year's "
                                                  "₹400cr — one of the two is misread"]})
    assert contradictory["score"] <= 60
    assert any("did not read cleanly" in c for c in contradictory["caps"])


def test_the_self_check_stays_quiet_on_a_sound_sheet():
    """A guard that cries wolf gets ignored, and then it is worth nothing."""
    d = {"fy_labels": ["Mar 2024", "Mar 2025", "Mar 2026"], "cfo_labels": ["Mar 2025", "Mar 2026"],
         "revenue_ttm_cr": 1263.0, "revenue_fy_cr": 1146.0, "sales_growth_1y_pct": 7.5,
         "sales_growth_prev_1y_pct": 46.23, "profit_growth_1y_pct": 6.21,
         "promoter_pct": 70.19, "institutional_pct": 1.37, "opm_pct": 24.0, "pe": 19.8}
    assert fu._self_check(d) == []
