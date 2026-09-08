"""Nothing in the suite may touch the real `state/` — the ledger and the source scores are records.

Every module that writes into `state/` binds its path once, at import, so each is redirected here to
a per-test temporary directory. A test that reaches for live state gets an empty file instead of the
desk's own history, and a test that writes cannot corrupt it. Individual fixtures still point
`ledger.PATH` and friends wherever they like; this only guarantees the floor.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("STOCKTIPS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# module attribute -> the file it would otherwise write in state/
REDIRECT = [
    ("stocktips.portfolio.ledger", "PATH", "ledger.json"),
    ("stocktips.learning.confidence", "PATH", "sources_confidence.json"),
    ("stocktips.learning.journal", "PATH", "lessons.md"),
    ("stocktips.data.sparks", "PATH", "price_cache.json"),
    ("stocktips.data.symbols", "UNIVERSE_PATH", "universe_cache.json"),
    ("stocktips.portfolio.daybook", "PATH", "daybook.json"),
    ("stocktips.learning.eventscore", "PATH", "event_classes.json"),
]


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch, tmp_path):
    import importlib
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    for module, attr, name in REDIRECT:
        try:
            mod = importlib.import_module(module)
        except Exception:                     # a module this test never imports cannot leak either
            continue
        assert hasattr(mod, attr), f"{module}.{attr} has moved — this guard is now blind"
        monkeypatch.setattr(mod, attr, state / name)
    yield
