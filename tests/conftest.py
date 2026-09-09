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
    ("stocktips.learning.fundcalib", "CALIB", "fundamentals_calibration.json"),
    ("stocktips.learning.fundcalib", "VERDICTS", "fundamentals_verdicts.json"),
]


def _seed_universe(path: Path) -> None:
    """Pre-fill the redirected symbol master from the bundled EQUITY_L.csv.

    Without this every test session finds an empty cache, tries archives.nseindia.com three times
    with a sleep between each, and only then falls back to the seed — six seconds of blocked
    requests per session, and a suite that is only offline by accident. The parse is the same one
    SymbolMaster does, kept in step by the test below.
    """
    import csv
    import io
    import json
    import re
    from datetime import datetime

    csv_path = ROOT / "data" / "EQUITY_L.csv"
    if not csv_path.exists():
        return
    rows = []
    for row in csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))):
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if row.get("SERIES") not in ("EQ", "BE", "BZ"):
            continue
        if re.search(r"\b(ETF|Bees|Liquid|Gold|Silver|Nifty|Sensex|Index Fund|Mutual Fund|FOF)\b",
                     row["NAME OF COMPANY"], re.I):
            continue
        rows.append({"symbol": row["SYMBOL"], "name": row["NAME OF COMPANY"],
                     "isin": row.get("ISIN NUMBER"), "series": row["SERIES"]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched": datetime.now().isoformat(), "rows": rows}), encoding="utf-8")


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch, tmp_path):
    import importlib
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    _seed_universe(state / "universe_cache.json")
    # a master already built from the real state must not leak into a test that expects the seed
    try:
        importlib.import_module("stocktips.data.symbols")._master = None
    except Exception:
        pass
    # `SymbolMaster.resolve` falls through to Moneycontrol's autosuggest when its fuzzy match is
    # weak. No test should depend on a live third-party endpoint for that, and one did — so it
    # answers "no idea" here by default. A test that wants a different answer can patch it back.
    try:
        monkeypatch.setattr(importlib.import_module("stocktips.data.symbols"), "mc_suggest",
                            lambda query: None)
    except Exception:
        pass
    for module, attr, name in REDIRECT:
        try:
            mod = importlib.import_module(module)
        except Exception:                     # a module this test never imports cannot leak either
            continue
        assert hasattr(mod, attr), f"{module}.{attr} has moved — this guard is now blind"
        monkeypatch.setattr(mod, attr, state / name)
    yield
