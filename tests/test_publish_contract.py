"""Every run must reach the website by itself.

The desk owner had to open a pull request and merge it before the portal caught up with what the
08:00 run had already computed. Two causes, both invisible from the page:

* the pre-open and session runs pushed to their own `claude/*` branch, not to main, and GitHub
  Pages serves main;
* neither of them regenerated `docs/data.json` at all, so even a merged card left the payload
  showing whatever the last run that happened to do both had left behind.

`stocktips publish` is now the single way any run reaches the reader, and a routine pushing
straight to main is only safe because publish refuses to push a site it cannot prove renders.
These tests hold that contract: every playbook uses it, nobody hand-rolls a push around it, and
the refusal is real.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS = ["preopen_run.md", "morning_run.md", "eod_run.md", "session_run.md"]


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_every_playbook_publishes_through_the_one_command(name):
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    assert "stocktips publish" in text, f"{name} does not publish, so its run never reaches the site"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_no_playbook_hand_rolls_a_push_around_it(name):
    """A bare `git push` lands on whatever branch the run happens to be on — which is how the
    pre-open card kept ending up somewhere the website does not read."""
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    assert "git push" not in text, (
        f"{name} pushes by hand; publish is the only path to main so the rebase, the render check "
        f"and the fallback branch all stay in one place")


def test_publish_refuses_a_site_that_would_not_render():
    """The guard that makes an unattended push to main defensible. A bare NaN in the payload makes
    JSON.parse throw and the whole dashboard renders blank — with no reviewer left to catch it."""
    data = ROOT / "docs" / "data.json"
    original = data.read_text(encoding="utf-8")
    try:
        data.write_text(original.replace('"generated"', '"probe": NaN, "generated"', 1),
                        encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_dashboard.py")],
                           cwd=ROOT, capture_output=True, text=True)
        assert r.returncode != 0, "a bare NaN must fail the render check publish gates on"
        assert "NaN" in r.stdout
    finally:
        data.write_text(original, encoding="utf-8")


def test_publish_targets_main_and_says_so_when_it_misses():
    """Main is the only branch GitHub Pages serves."""
    src = (ROOT / "src" / "stocktips" / "cli.py").read_text(encoding="utf-8")
    body = src[src.index("def cmd_publish"):src.index("def cmd_dashboard_data")]
    assert '"HEAD:main"' in body, "publish must push to main"
    assert "--rebase" in body, "and rebase onto whatever another run landed meanwhile"
    assert "sys.exit" in body, "and fail loudly when the site did not update"
    assert re.search(r"check\.returncode\s*!=\s*0", body), "and gate on the render check"
