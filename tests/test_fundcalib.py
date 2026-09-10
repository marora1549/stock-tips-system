"""The fundamentals score's own report card.

Enviro Infra held a 92 for weeks and nothing in the system objected — not a test, not a warning.
It was caught because a person read a paid research note and said so. These tests cover the two
ledgers that make that catchable without a person: the score against what the stock then did, and
the score against somebody else's verdict.

What is deliberately *not* tested, because it deliberately does not exist: any path by which either
ledger changes a score. A number that quietly tuned itself toward Markets Mojo would just be
Markets Mojo with extra steps, and a bucket table feeding back into the weights would chase noise
on a handful of trades. Both ledgers report. Acting on the report is a decision taken in the open.
"""
from __future__ import annotations

import pytest

from stocktips.learning import fundcalib as fc


def test_a_score_is_recorded_when_a_position_opens_and_settled_when_it_closes():
    d = fc.load()
    fc.note_entry(d, "EIEL", score=92, flags=["operating cash flow negative 3 years running"],
                  on="2026-09-01")
    assert fc.table(d)[3]["n_scored"] == 1, "92 belongs to the top band"
    assert fc.table(d)[3]["n_settled"] == 0, "and nothing is settled yet"

    fc.settle(d, "EIEL", outcome="stop_loss", ret_pct=-8.4, on="2026-09-08")
    top = fc.table(d)[3]
    assert top["n_settled"] == 1
    assert top["avg_return_pct"] == pytest.approx(-8.4)
    assert top["hit_rate"] == 0.0


def test_settling_a_name_twice_does_not_overwrite_the_earlier_trade():
    """Re-entering a name later must not rewrite the record of the first trade in it."""
    d = fc.load()
    fc.note_entry(d, "JWL", score=41, on="2026-08-01")
    fc.settle(d, "JWL", outcome="t1", ret_pct=5.0, on="2026-08-10")
    fc.note_entry(d, "JWL", score=41, on="2026-09-01")
    fc.settle(d, "JWL", outcome="stop_loss", ret_pct=-6.0, on="2026-09-05")

    settled = [e for e in d["entries"] if e["symbol"] == "JWL"]
    assert [e["ret_pct"] for e in settled] == [5.0, -6.0], "two trades, two records, in order"
    band = next(r for r in fc.table(d) if r["bucket"] == "40-60")
    assert band["n_settled"] == 2
    assert band["avg_return_pct"] == pytest.approx(-0.5)


def test_settle_returns_none_when_there_is_nothing_open_to_settle():
    d = fc.load()
    assert fc.settle(d, "NOTHERE", outcome="t1", ret_pct=3.0) is None


def test_a_score_that_ranks_backwards_says_so_in_words():
    """The finding that matters: high scores doing worse than low ones. A table of numbers is
    something a person has to remember to read; a sentence is not."""
    d = fc.load()
    for i in range(6):
        fc.note_entry(d, f"GOOD{i}", score=90, on="2026-08-01")
        fc.settle(d, f"GOOD{i}", outcome="stop_loss", ret_pct=-5.0, on="2026-08-20")
        fc.note_entry(d, f"BAD{i}", score=20, on="2026-08-01")
        fc.settle(d, f"BAD{i}", outcome="t2", ret_pct=9.0, on="2026-08-20")

    found = fc.inversions(d)
    assert found, "six trades each way is enough to notice"
    assert "backwards" in found[0]
    assert "75-100" in found[0] and "0-40" in found[0]


def test_a_handful_of_trades_is_not_called_evidence():
    """Four names is not a finding about a scoring band, and must not be reported as one."""
    d = fc.load()
    for i in range(3):
        fc.note_entry(d, f"A{i}", score=85, on="2026-08-01")
        fc.settle(d, f"A{i}", outcome="stop_loss", ret_pct=-4.0, on="2026-08-10")
        fc.note_entry(d, f"B{i}", score=30, on="2026-08-01")
        fc.settle(d, f"B{i}", outcome="t1", ret_pct=6.0, on="2026-08-10")
    assert fc.inversions(d) == [], "an inversion on three trades is noise"
    assert all(r["thin"] for r in fc.table(d) if r["n_settled"])


def test_bucket_boundaries_land_where_they_read():
    assert fc.bucket_of(39) == "0-40"
    assert fc.bucket_of(40) == "40-60"
    assert fc.bucket_of(59.9) == "40-60"
    assert fc.bucket_of(75) == "75-100"
    assert fc.bucket_of(100) == "75-100"


# ------------------------------------------------------------------ against a second opinion

def test_the_eiel_disagreement_is_on_the_record():
    """55 points apart from a paid research desk, on a company they called SELL. This is the case
    the whole rework came out of, and it stays visible rather than being remembered."""
    d = fc.load_verdicts()
    fc.note_verdict(d, "EIEL", source="markets_mojo", their_score=37, their_stance="sell",
                    my_score=92, note="three years of negative operating cash flow, unread",
                    on="2026-09-09")
    dis = fc.disagreements(d)
    assert len(dis) == 1
    assert dis[0]["symbol"] == "EIEL" and dis[0]["gap"] == 55.0


def test_bias_is_signed_because_generous_and_erratic_are_different_problems():
    """A scorer twenty points high on every name is a different, more fixable thing than one that
    is twenty points off in both directions. An absolute mean would hide which it is."""
    d = fc.load_verdicts()
    for i, gap in enumerate((14, 18, 11, 16)):
        fc.note_verdict(d, f"SYM{i}", source="markets_mojo", their_score=50,
                        my_score=50 + gap, on="2026-09-01")
    row = next(r for r in fc.bias(d) if r["source"] == "markets_mojo")
    assert row["mean_gap"] == pytest.approx(14.8), "reported to one decimal"
    assert "generous" in row["reading"], "consistently high, and named as such"

    e = fc.load_verdicts()
    for i, gap in enumerate((30, -28, 26, -30)):
        fc.note_verdict(e, f"SYM{i}", source="markets_mojo", their_score=50,
                        my_score=50 + gap, on="2026-09-01")
    erratic = next(r for r in fc.bias(e) if r["source"] == "markets_mojo")
    assert abs(erratic["mean_gap"]) < 3, "the signed mean nets out"
    assert erratic["mean_abs_gap"] > 25, "but the error is large, and the pair of numbers shows it"
    assert "in line" in erratic["reading"]


def test_a_verdict_without_a_number_still_records():
    """Screener publishes Pros and Cons, not a score. A stance with no number is still an opinion
    worth keeping; it just cannot contribute to a gap."""
    d = fc.load_verdicts()
    row = fc.note_verdict(d, "EIEL", source="screener", their_score=None,
                          their_stance="cons: capitalizing interest cost", my_score=32)
    assert "gap" not in row
    assert fc.bias(d) == [], "no number, no bias claim"
    assert d["EIEL"][0]["their_stance"].startswith("cons:")


def test_neither_ledger_can_reach_the_scorer():
    """The guard on the whole design: these modules record, and nothing else."""
    import inspect
    src = inspect.getsource(fc)
    assert "fundamentals" not in src.replace("fundamentals_calibration", "").replace(
        "fundamentals_verdicts", "").replace("fundamentals score", "").replace(
        "fundamentals number", ""), "the ledgers must not import or call the scorer"


def test_a_corrected_score_supersedes_the_one_it_replaced():
    """Fixing the scorer and re-comparing the same company writes a second row. Both belong in the
    history — the +55 on Enviro Infra is the record of what went wrong and is not being quietly
    deleted — but counting both would let a corrected mistake keep reporting itself forever."""
    d = fc.load_verdicts()
    fc.note_verdict(d, "EIEL", source="markets_mojo", their_score=37, their_stance="sell",
                    my_score=92, note="before the rebuild", on="2026-09-09")
    fc.note_verdict(d, "EIEL", source="markets_mojo", their_score=37, their_stance="sell",
                    my_score=32, note="after the rebuild", on="2026-09-09")
    row = next(r for r in fc.bias(d) if r["source"] == "markets_mojo")
    assert row["n"] == 1, "one company, one current comparison"
    assert row["mean_gap"] == pytest.approx(-5.0), "the corrected score is the one that counts"

    kept = fc.disagreements(d)
    assert len(kept) == 1 and kept[0]["gap"] == 55.0
    assert kept[0]["superseded"] is True, "still on the record, and labelled"


def test_a_second_look_on_a_later_day_is_not_a_supersede():
    """Re-comparing the same name months later is new evidence, not a correction."""
    d = fc.load_verdicts()
    fc.note_verdict(d, "EIEL", source="markets_mojo", their_score=37, my_score=50, on="2026-09-09")
    fc.note_verdict(d, "EIEL", source="markets_mojo", their_score=40, my_score=44, on="2026-11-09")
    row = next(r for r in fc.bias(d) if r["source"] == "markets_mojo")
    assert row["n"] == 2, "two dates, two observations"
