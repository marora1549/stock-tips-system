"""The canaries, and the one property that makes them worth having.

A test suite proves the code in the repository is correct. It cannot prove anything about the code
in a routine's container, and that gap is exactly where the 92 got through: the scorer was fixed,
190 tests passed, and the next morning's run cloned `main` — which did not have the fix — and
mailed a card scoring Enviro Infra 92. Nothing failed. The email looked completely normal.

So these tests check that the canaries pass here, and, more importantly, that a canary *fails*
when handed a scorer that has regressed. A green canary that cannot go red is decoration.
"""
from __future__ import annotations

from stocktips import selfcheck as sc


def test_every_canary_passes_against_this_working_tree():
    ok, rows = sc.run()
    assert ok, "failing: " + "; ".join(f"{r['name']} (got {r['found']!r})"
                                       for r in rows if not r["ok"])
    assert len(rows) >= 7, "each canary is a specific past failure; do not let them be deleted"


def test_a_canary_survives_a_scorer_too_old_to_have_the_api(monkeypatch):
    """The loudest version of the failure. A container from before `assess` existed must come back
    as a readable FAIL, not a traceback that a routine might read as 'the tool is broken, carry
    on without it'."""
    def gone(*_a, **_k):
        raise AttributeError("module 'stocktips.data.fundamentals' has no attribute 'assess'")
    monkeypatch.setattr(sc.fu, "assess", gone)

    ok, rows = sc.run()
    assert ok is False
    failed = [r for r in rows if not r["ok"]]
    assert failed, "an absent API is a finding, not an exception"
    assert "AttributeError" in str(failed[0]["found"])


def test_a_canary_goes_red_when_the_scorer_regresses(monkeypatch):
    """The property that makes the rest of this file mean anything."""
    monkeypatch.setattr(sc.fu, "assess", lambda f: {"score": 92, "why": [], "flags": [],
                                                    "caps": [], "raw_score": 92})
    ok, rows = sc.run()
    assert ok is False
    names = [r["name"] for r in rows if not r["ok"]]
    assert "a cash-burning company is not excellent" in names
    assert "nothing reaches 90" in names


def test_each_canary_names_the_failure_it_guards():
    """A red canary at 08:00 has to explain itself to whoever reads the email, in one line, with
    no access to this conversation."""
    for r in sc.canaries():
        assert r["was"] and len(r["was"]) > 20, f"{r['name']} does not say what went wrong"
        assert r["want"], f"{r['name']} does not say what it expected"
