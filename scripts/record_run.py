#!/usr/bin/env python3
"""Append one dashboard-dispatched command to state/actions_log.json, then re-emit data.json.

The dashboard can read GitHub's own run list, but only while a token is loaded. This log lives in the
repo instead, so the last twenty actions — what was asked, what the command answered, who asked —
are visible on the page to anyone who can see it, with no token at all.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktips.util import STATE_DIR, now_ist, read_json, write_json  # noqa: E402

PATH = STATE_DIR / "actions_log.json"
KEEP = 20
MAX_OUTPUT = 1400


def env(name: str) -> str:
    return (os.environ.get("DESK_" + name.upper()) or "").strip()


def main() -> None:
    output = ""
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        output = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    # keep the tail: the useful part of a CLI answer is at the end
    lines = [ln for ln in output.splitlines() if not ln.startswith("::group::") and not ln.startswith("::endgroup::")]
    tail = "\n".join(lines)[-MAX_OUTPUT:].strip()

    log = read_json(PATH, {"runs": []})
    log["runs"] = (log.get("runs") or [])[-(KEEP - 1):] + [{
        "at": now_ist().strftime("%Y-%m-%d %H:%M"),
        "command": env("command"),
        "symbol": env("symbol") or None,
        "amount": env("amount") or None,
        "by": env("actor") or None,
        "run_url": env("run_url") or None,
        "output": tail,
    }]
    write_json(PATH, log)
    print(f"recorded run: {env('command')} {env('symbol')}")

    from stocktips.cli import main as cli_main
    cli_main(["dashboard-data"])


if __name__ == "__main__":
    main()
