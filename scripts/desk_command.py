#!/usr/bin/env python3
"""Run one `stocktips` command from environment variables — the bridge the dashboard drives.

The dashboard has no server. It asks GitHub to run the `desk` workflow, and that workflow calls this
script. Inputs arrive as environment variables and are turned into an argv list here, in Python, so
nothing a browser sends is ever interpreted by a shell: a `--note` of `"; rm -rf /"` is one string
argument and stays one string argument.

    DESK_COMMAND=book DESK_SYMBOL=CGPOWER DESK_AMOUNT=25000 python scripts/desk_command.py

Every command is one the analyst could have typed by hand; this only removes the typing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# command -> how its inputs map onto the CLI. "pos" is a positional argument; everything else is a
# flag. Anything not listed here cannot be dispatched, whatever the caller asks for.
SPEC: dict[str, dict] = {
    "book":      {"pos": "symbol", "flags": {"amount": "--capital", "note": None}, "needs": ["symbol"]},
    "close":     {"pos": "symbol", "flags": {"price": "--price", "note": "--note"}, "needs": ["symbol"]},
    "capital":   {"pos": None, "flags": {"amount": "--add", "withdraw": "--withdraw", "note": "--note"},
                  "needs": ["one_of:amount,withdraw"]},
    "add-tip":   {"pos": None, "flags": {"source": "--source", "symbol": "--symbol", "company": "--company",
                                         "entry": "--entry", "target": "--target", "stop": "--stop",
                                         "timeframe": "--timeframe", "action": "--action", "text": "--text",
                                         "url": "--url"},
                  "needs": ["source", "symbol"]},
    "lesson":    {"pos": "text", "flags": {}, "needs": ["text"]},
    "add-source": {"pos": None, "flags": {"source": "--id", "kind": "--kind", "channel": "--channel",
                                          "url": "--url", "query": "--query", "note": "--name"},
                   "needs": ["source", "kind"]},
    "analyze":   {"pos": None, "flags": {}, "needs": []},
    "structure": {"pos": None, "flags": {}, "needs": []},
    "gather":    {"pos": None, "flags": {}, "needs": []},
    "pick":      {"pos": None, "flags": {}, "needs": [], "bare": ["--no-book"]},
    "pick-book": {"cli": "pick", "pos": None, "flags": {}, "needs": []},
    "eod":       {"pos": None, "flags": {}, "needs": [], "bare": ["--force"]},
    "morning":   {"pos": None, "flags": {}, "needs": [], "bare": ["--force", "--skip-review"]},
    "status":    {"pos": None, "flags": {}, "needs": []},
    "dashboard-data": {"pos": None, "flags": {}, "needs": []},
}


def env(name: str) -> str:
    return (os.environ.get("DESK_" + name.upper().replace("-", "_")) or "").strip()


def build_argv() -> list[str]:
    command = env("command")
    if command not in SPEC:
        sys.exit(f"unknown command {command!r} — allowed: {', '.join(sorted(SPEC))}")
    spec = SPEC[command]
    argv = [spec.get("cli", command)]

    for need in spec["needs"]:
        if need.startswith("one_of:"):
            options = need.split(":", 1)[1].split(",")
            if not any(env(o) for o in options):
                sys.exit(f"{command} needs one of: {', '.join(options)}")
        elif not env(need):
            sys.exit(f"{command} needs {need}")

    if spec["pos"]:
        argv.append(env(spec["pos"]))
    for key, flag in spec["flags"].items():
        value = env(key)
        if value and flag:
            argv += [flag, value]
    argv += spec.get("bare", [])
    return argv


def main() -> None:
    argv = build_argv()
    print("::group::stocktips " + " ".join(argv))
    print(json.dumps({"argv": argv, "actor": os.environ.get("GITHUB_ACTOR", "?")}))
    from stocktips.cli import main as cli_main
    try:
        cli_main(argv)
    except SystemExit as e:                     # the CLI's own refusals are the useful output
        if e.code not in (0, None):
            print("::endgroup::")
            print(f"::error::{e.code}")
            raise
    print("::endgroup::")


if __name__ == "__main__":
    main()
