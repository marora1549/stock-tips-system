"""The two dashboard failures that a Python test suite cannot see.

`docs/index.html` is one self-contained file of vanilla JS, and `docs/data.json` is what it reads.
Neither is exercised by pytest, and both have broken the portal outright:

* **A syntax error in the page script blanks the whole dashboard.** Nothing renders, and there is
  no error anywhere a routine would look. Every edit to that file has been checked by hand with
  `node --check` on the extracted scripts, every single time, which is exactly the kind of
  discipline that holds until the one time it does not.

* **A NaN in the payload blanks it just as completely.** `json.dump` writes bare `NaN`, which is
  not JSON, so `JSON.parse` throws on load and the page renders nothing. `util.write_json` uses
  `allow_nan=False` now; this checks the file that shipped, not the function that wrote it.

Exits non-zero with the reason. Run by CI, and safe to run by hand.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "index.html"
DATA = ROOT / "docs" / "data.json"

BAD_JSON_LITERALS = re.compile(r"(?<![\"\w])(NaN|Infinity|-Infinity)(?![\"\w])")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def check_page_script() -> None:
    if not PAGE.exists():
        fail(f"{PAGE.relative_to(ROOT)} is missing")
    html = PAGE.read_text(encoding="utf-8")
    scripts = [m.group(1) for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                               html, re.S)]
    if not scripts:
        fail("no inline <script> found in docs/index.html — has the page been gutted?")

    node = shutil.which("node")
    if node is None:
        print("WARN  node not found, skipping the JavaScript syntax check")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(scripts))
        path = fh.name
    r = subprocess.run([node, "--check", path], capture_output=True, text=True)
    if r.returncode != 0:
        fail("the dashboard's inline JavaScript does not parse, so the page will render "
             f"nothing:\n{r.stderr.strip()}")
    print(f"PASS  {len(scripts)} inline script block(s) parse")


def check_data() -> None:
    if not DATA.exists():
        fail(f"{DATA.relative_to(ROOT)} is missing")
    raw = DATA.read_text(encoding="utf-8")

    # json.loads accepts NaN and Infinity; the browser's JSON.parse does not. Checking with
    # Python alone would pass a file that blanks the page.
    stray = BAD_JSON_LITERALS.search(raw)
    if stray:
        line = raw[:stray.start()].count("\n") + 1
        fail(f"docs/data.json contains a bare {stray.group(1)} at line {line}. JSON.parse rejects "
             f"it, so the whole dashboard renders blank.")
    try:
        doc = json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(
            ValueError(f"bare {c} in the payload")))
    except ValueError as e:
        fail(f"docs/data.json is not valid JSON: {e}")

    for key in ("generated", "stats", "positions", "settings"):
        if key not in doc:
            fail(f"docs/data.json has no {key!r} — the page reads it on load")
    print(f"PASS  docs/data.json parses as strict JSON ({len(doc)} top-level keys)")


if __name__ == "__main__":
    check_page_script()
    check_data()
    print("dashboard OK")
