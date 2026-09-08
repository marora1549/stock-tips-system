"""The guard in conftest.py, tested — so it fails loudly rather than quietly stopping working."""
from pathlib import Path

import pytest

from stocktips.data import sparks, symbols
from stocktips.learning import confidence, journal
from stocktips.portfolio import ledger

REAL_STATE = Path(__file__).resolve().parents[1] / "state"


def test_no_test_can_reach_the_real_state_files():
    for path in (ledger.PATH, confidence.PATH, journal.PATH, sparks.PATH, symbols.UNIVERSE_PATH):
        assert REAL_STATE not in path.parents, f"{path} is inside the real state directory"


def test_the_ledger_a_test_sees_is_empty_not_the_desks_own():
    led = ledger.load()
    assert led["positions"] == [] and led["closed"] == []


def test_writing_state_in_a_test_lands_in_the_temporary_copy():
    cache = sparks.load()
    cache["closes"]["ZZTEST"] = [1.0, 2.0]
    sparks.save(cache)
    assert sparks.PATH.exists()
    assert not (REAL_STATE / "price_cache.json").read_text(encoding="utf-8").count("ZZTEST")


def test_the_symbol_master_loads_without_a_single_request(monkeypatch):
    """The suite is offline by design, not by luck. If this starts failing, conftest's seed parse
    has drifted from SymbolMaster's own."""
    import stocktips.util as util
    monkeypatch.setattr(util.Http, "get",
                        lambda *a, **k: pytest.fail("the symbol master went to the network"))
    symbols._master = None
    m = symbols.master()
    assert len(m.rows) > 2000, f"only {len(m.rows)} symbols — the seed did not load"
    assert "GVT&D" in m.by_symbol and "M&M" in m.by_symbol


def test_nothing_in_the_suite_reaches_a_third_party_endpoint(monkeypatch):
    """Belt and braces on the fixture above: resolution must not phone anyone."""
    import stocktips.util as util
    monkeypatch.setattr(util.Http, "get", lambda *a, **k: pytest.fail("went to the network"))
    monkeypatch.setattr(util.Http, "post", lambda *a, **k: pytest.fail("went to the network"))
    symbols._master = None
    sym, conf, how = symbols.master().resolve("Some Company Nobody Has Heard Of Limited")
    assert sym is None and how in ("unresolved", "too-short", "skip")
    assert symbols.master().resolve("Tata Steel")[0] == "TATASTEEL"
