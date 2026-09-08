"""The page's read-only pre-flight on a pasted Markets Mojo screen, run under node.

It never guesses a symbol — that is the Python importer's job against the NSE master. What it must
get right is the count, the direction of each call, and the three numbers it shows back, because
that is what the analyst checks before pressing Import.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "index.html"
FIX = ROOT / "tests" / "fixtures"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")

NEEDED = ("MOJO_CALL", "MOJO_MCAP", "MOJO_FIELDS", "MOJO_LABELS")


def preview(pastes):
    """Pull parseMojo and the constants it leans on out of the page, and run the real code."""
    body = "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", HTML.read_text(encoding="utf-8"), re.S))
    parts = []
    for name in NEEDED:
        m = re.search(r"^var " + name + r" = .*?;$", body, re.S | re.M)
        assert m, f"{name} is no longer a top-level var in docs/index.html"
        parts.append(m.group(0))
    for fn in ("mojoNum", "mojoFinish", "parseMojo"):
        m = re.search(r"^function " + fn + r"\(.*?^\}", body, re.S | re.M)
        assert m, f"{fn} is no longer a top-level function in docs/index.html"
        parts.append(m.group(0))
    script = "\n".join(parts) + "\nconsole.log(JSON.stringify(" + json.dumps(pastes) + ".map(parseMojo)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


TABLE = (FIX / "mojo_table.txt").read_text(encoding="utf-8")
DETAIL = (FIX / "mojo_detail.txt").read_text(encoding="utf-8")


def test_the_bulk_table_is_counted_correctly():
    rows = preview([TABLE])[0]
    assert len(rows) == 19
    assert rows[0] == {"company": "Kennametal India", "action": "buy", "direction": "long",
                       "entry": 4700.70, "target": 5168.90, "stop": 4385.73,
                       "call_type": "Monthly", "date": "07-Sep-2026"}


def test_the_five_sell_calls_are_marked_as_shorts():
    rows = preview([TABLE])[0]
    shorts = [r["company"] for r in rows if r["direction"] == "short"]
    assert shorts == ["Firstsour.Solu.", "Container Corpn.", "Deepak Nitrite",
                      "Indian Hotels Co", "Adani Enterp."]


def test_prices_with_commas_are_one_number():
    rows = preview([TABLE])[0]
    maruti = [r for r in rows if r["company"] == "Maruti Suzuki"][0]
    assert (maruti["entry"], maruti["target"]) == (13371.25, 14708.37)


def test_the_detail_panel_is_read_and_its_missing_name_is_left_blank():
    rows = preview([DETAIL])[0]
    assert len(rows) == 1
    assert rows[0]["company"] == ""          # so the page can ask for it rather than invent one
    assert (rows[0]["entry"], rows[0]["target"], rows[0]["stop"]) == (4700.70, 5168.90, 4385.73)


def test_a_name_pasted_with_the_detail_panel_is_kept():
    assert preview(["Kennametal India\n" + DETAIL])[0][0]["company"] == "Kennametal India"


def test_it_reads_the_same_calls_the_importer_does():
    """The page and the Python importer must not disagree about what a paste contains."""
    from stocktips.sources import mojo
    for paste in (TABLE, DETAIL):
        js = preview([paste])[0]
        py = mojo.parse(paste)
        assert len(js) == len(py)
        for a, b in zip(js, py):
            assert a["company"] == b["company_raw"]
            assert a["action"] == b["action"] and a["direction"] == b["direction"]
            assert a["entry"] == b["src_entry"]
            assert [a["target"]] == b["src_targets"]
            assert a["stop"] == b["src_stop"]


def test_junk_reads_as_nothing_rather_than_as_a_call():
    assert preview(["", "hello there", "Buy\n\nMonthly\n\n"]) == [[], [], []]
