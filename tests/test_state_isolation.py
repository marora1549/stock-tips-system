"""The guard in conftest.py, tested — so it fails loudly rather than quietly stopping working."""
from pathlib import Path

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
