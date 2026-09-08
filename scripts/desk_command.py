#!/usr/bin/env python3
"""Run one `stocktips` command from environment variables — the bridge the dashboard drives.

The dashboard has no server. It asks GitHub to run the `desk` workflow, and that workflow calls this
script. Inputs arrive as environment variables and are turned into an argv list here, in Python, so
nothing a browser sends is ever interpreted by a shell: a `--note` of `"; rm -rf /"` is one string
argument and stays one string argument.

    DESK_COMMAND=book DESK_SYMBOL=CGPOWER DESK_AMOUNT=25000 python scripts/desk_command.py

`workflow_dispatch` allows only ten inputs, and the desk needs more than ten fields, so the common
ones have their own input and the rest ride along as JSON in `DESK_ARGS`:

    DESK_COMMAND=add-tip DESK_SOURCE=manual:mohan DESK_SYMBOL=INFY \
      DESK_ARGS='{"target": "1700,1800", "stop": "1490", "timeframe": "monthly"}'

Every command is one the analyst could have typed by hand; this only removes the typing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# command -> how its inputs map onto the CLI. "pos" is a positional argument, "flags" take a value,
# "bools" are present-or-absent switches, "bare" is always appended. Anything not listed here cannot
# be dispatched, whatever the caller asks for.
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
    "import-tips": {"pos": None, "flags": {"source": "--source", "text": "--text", "symbol": "--symbol",
                                           "url": "--url"},
                    "bools": {"dry_run": "--dry-run"}, "needs": ["text"]},
    "contenders": {"pos": None, "flags": {"amount": "--top"}, "needs": []},
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

FALSEY = {"", "0", "false", "no", "off"}


def inputs() -> dict[str, str]:
    """Every input this dispatch carried: the DESK_* variables, then whatever DESK_ARGS adds.

    A malformed DESK_ARGS is refused rather than half-read — a dropped `--stop` is not a typo to
    shrug at. Its keys never overwrite a real input, so `symbol` cannot be smuggled past a check.
    """
    got = {k[5:].lower(): v.strip() for k, v in os.environ.items() if k.startswith("DESK_") and v.strip()}
    blob = got.pop("args", "")
    if blob:
        try:
            extra = json.loads(blob)
        except ValueError as e:
            sys.exit(f"DESK_ARGS is not valid JSON: {e}")
        if not isinstance(extra, dict):
            sys.exit("DESK_ARGS must be a JSON object of input names to values")
        for key, value in extra.items():
            name = str(key).strip().lower().replace("-", "_")
            if value is None or name in got:
                continue
            got[name] = str(value).strip() if not isinstance(value, bool) else ("1" if value else "")
    return {k: v for k, v in got.items() if v}


def build_argv(given: dict[str, str] | None = None) -> list[str]:
    got = given if given is not None else inputs()
    command = got.get("command", "")
    if command not in SPEC:
        sys.exit(f"unknown command {command!r} — allowed: {', '.join(sorted(SPEC))}")
    spec = SPEC[command]
    argv = [spec.get("cli", command)]

    for need in spec["needs"]:
        if need.startswith("one_of:"):
            options = need.split(":", 1)[1].split(",")
            if not any(got.get(o) for o in options):
                sys.exit(f"{command} needs one of: {', '.join(options)}")
        elif not got.get(need):
            sys.exit(f"{command} needs {need}")

    if spec["pos"]:
        argv.append(got[spec["pos"]])
    for key, flag in spec["flags"].items():
        value = got.get(key)
        if value and flag:
            argv += [flag, value]
    for key, flag in spec.get("bools", {}).items():
        if got.get(key, "").lower() not in FALSEY:
            argv.append(flag)
    argv += spec.get("bare", [])
    return argv


def main() -> None:
    got = inputs()
    argv = build_argv(got)
    print("::group::stocktips " + " ".join(argv[:2]))
    # the paste for import-tips can be thousands of lines; log its size, not its body
    print(json.dumps({"command": got.get("command"), "argv": [a[:80] for a in argv],
                      "input_bytes": {k: len(v) for k, v in got.items() if len(v) > 200},
                      "actor": os.environ.get("GITHUB_ACTOR", "?")}))
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
