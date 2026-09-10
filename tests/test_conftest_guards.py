"""The guards the suite relies on, checked rather than assumed.

Two claims have been made in every commit message here — "no live state touched" and "zero
outbound requests" — and both have been false at least once. The state redirection was added after
two fixtures wrote the real ledger and a probe script overwrote the real source scores. The network
claim was true, but nothing enforced it, so it was one careless fixture away from becoming a lie
that only showed up as an intermittent CI failure months later.

These test the guards themselves. A guard nobody checks is a comment.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from stocktips.util import STATE_DIR


def test_state_paths_are_redirected_away_from_the_real_repo():
    """Every module that writes into state/ binds its path at import. If one is added and not
    registered in REDIRECT, this notices — before it overwrites the desk's own history."""
    import importlib

    from conftest import REDIRECT

    real = (Path(__file__).resolve().parents[1] / "state").resolve()
    for module, attr, _name in REDIRECT:
        mod = importlib.import_module(module)
        bound = Path(getattr(mod, attr)).resolve()
        assert real not in bound.parents, f"{module}.{attr} still points into the real state/"


def test_every_state_writing_module_is_registered():
    """The guard is only as good as its list, and the list is hand-maintained."""
    import re

    from conftest import REDIRECT

    src = Path(__file__).resolve().parents[1] / "src" / "stocktips"
    registered = {(m, a) for m, a, _ in REDIRECT}
    missing = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^([A-Z_]+)\s*=\s*STATE_DIR\s*/", text, re.M):
            module = "stocktips." + str(path.relative_to(src).with_suffix("")).replace("/", ".")
            module = module.replace(".__init__", "")
            if (module, m.group(1)) not in registered:
                missing.append(f"{module}.{m.group(1)}")
    assert not missing, ("these write into state/ but tests/conftest.py does not redirect them, "
                         f"so a test could overwrite the desk's real records: {missing}")


@pytest.mark.skipif(not os.environ.get("STOCKTIPS_NO_NETWORK"),
                    reason="the network guard is only armed when STOCKTIPS_NO_NETWORK is set")
def test_an_outbound_request_is_refused_when_the_guard_is_armed():
    """CI arms this. A socket-level allowlist could not do the job — in a sandbox whose
    HTTPS_PROXY points at 127.0.0.1, every call to Screener looks like localhost and sails
    through — so the guard sits at the requests layer, where this codebase's traffic actually is.
    """
    import requests

    from stocktips.util import http

    for call in (lambda: requests.get("https://www.screener.in/", timeout=5),
                 lambda: requests.Session().get("https://www.screener.in/", timeout=5),
                 lambda: http().get("https://www.screener.in/", use_cache=False)):
        with pytest.raises(RuntimeError, match="tried to fetch"):
            call()
