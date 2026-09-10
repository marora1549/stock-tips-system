"""Known-answer checks the desk runs on itself, in the container, before it trusts its own output.

The failure this exists to prevent, exactly as it happened:

    09 Sep, interactive session  — the fundamentals scorer is rebuilt. Enviro Infra goes from 92
                                   to 32. 190 tests pass. Pushed to a branch.
    10 Sep, 08:00 routine        — clones `main`, which does not have the rebuild, and mails a
                                   card scoring Enviro Infra 92 and AU Small Finance 67.

Nothing was broken. The tests passed, the routine succeeded, the email arrived. The code that was
fixed and the code that ran were simply not the same code, and no part of the system was in a
position to notice — a passing test suite says the repository is correct, it says nothing about
what is in the container.

So these run at the start of every routine, against whatever code that container actually holds.
Each one is a specific past failure reduced to a number that must come out a certain way. They are
deliberately not a copy of the test suite: a test proves the code in the repository is right, and
a canary proves the code **in this run** is the code that was fixed. If a canary fails, the run is
executing something older than its own history, and it must say so at the top of the email before
it says anything else — because the output will look completely normal.

`python -m stocktips selfcheck` exits non-zero when any canary fails.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .data import fundamentals as fu

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

# A bank with a clean book that earns well. Not a fixture file, because the point of this canary is
# that a lender is *scored at all* — the shape of the input is the test.
GOOD_BANK = {
    "is_lender": True, "lender_note": "canary", "net_npa_pct": 0.76, "gross_npa_pct": 2.1,
    "net_npa_rising": False, "roa_pct": 1.51, "roe": 14.2, "nim_pct": 5.21,
    "nii_growth_1y_pct": 13.7, "assets_growth_pct": 21.5, "book_value": 267.0, "price": 1060.0,
    "pe": 27.9, "institutional_pct": 68.79,
    "debt_to_equity": 5.4, "cfo_cr": -9000.0, "cfo_negative_streak": 6,
}

FLAWLESS = {
    "roce": 60.0, "roe": 45.0, "pe": 20.0, "market_cap_cr": 900000.0, "promoter_pct": 60.0,
    "pledged_pct": 0.0, "fii_pct": 20.0, "dii_pct": 15.0, "debt_to_equity": 0.0,
    "sales_growth_3_years": 40.0, "profit_growth_3_years": 45.0, "sales_growth_1y_pct": 38.0,
    "sales_growth_prev_1y_pct": 36.0, "profit_growth_1y_pct": 44.0,
    "profit_growth_prev_1y_pct": 42.0, "np_yoy_growth_pct": 40.0, "revenue_fy_cr": 200000.0,
    "profit_fy_cr": 40000.0, "cfo_cr": 48000.0, "cfo_negative_streak": 0,
    "borrowings_growth_pct": 0.0, "interest_cover": 90.0, "book_value": 100.0, "price": 300.0,
}

# A minimal profit-and-loss section, enough for the parser to find the rows it must find.
PL_TABLE = """<section id="profit-loss">
<thead><tr><th class="text"></th><th>Mar 2025</th><th>Mar 2026</th><th>TTM</th></tr></thead>
<tbody>
<tr><td class="text">Sales</td><td>33,000</td><td>38,736</td><td>40,100</td></tr>
<tr><td class="text">Net Profit</td><td>11,000</td><td>12,800</td><td>13,200</td></tr>
</tbody></section>"""

TTM_TABLE = """
<thead><tr><th class="text"></th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th>
  <th>TTM</th></tr></thead>
<tbody><tr><td class="text">Sales</td><td>100</td><td>146</td><td>157</td><td>173</td></tr></tbody>
"""


def _eiel() -> dict:
    return json.loads((FIXTURES / "fundamentals_eiel.json").read_text(encoding="utf-8"))


def canaries() -> list[dict]:
    """Each entry: what went wrong once, and the number that proves it is still fixed.

    Every check runs inside its own guard. A container old enough that `assess` does not exist yet
    is the loudest possible version of the failure being tested for, and it must come back as a
    FAIL with a readable reason — not as a traceback that a routine might treat as "the tool is
    broken, carry on without it".
    """
    out: list[dict] = []

    def check(name: str, want: str, was: str, fn):
        try:
            found, ok = fn()
        except Exception as e:                       # noqa: BLE001 — an old API is the finding
            found, ok = f"{type(e).__name__}: {e}", False
        out.append({"name": name, "found": found, "want": want, "ok": bool(ok), "was": was})

    def eiel_score():
        got = fu.assess(_eiel())["score"]
        return got, got < 45
    check("a cash-burning company is not excellent", "under 45",
          "scored 92 for three years of negative operating cash flow", eiel_score)

    def burn_capped():
        got = fu.assess({k: v for k, v in _eiel().items()
                      if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity",
                               "promoter_pct", "revenue_fy_cr", "profit_fy_cr",
                               "sales_growth_3_years", "profit_growth_3_years",
                               "cfo_cr", "cfo_negative_streak")})["score"]
        return got, got <= 45
    check("a flaw sets a ceiling, it is not one vote in nine", "at most 45",
          "good ratios outvoted a cash burn", burn_capped)

    def ceiling():
        got = fu.assess(FLAWLESS)["score"]
        return got, got <= 90
    check("nothing reaches 90", "at most 90",
          "Infosys scored 97 and GE Vernova T&D 100", ceiling)

    def ttm():
        vals, labels = fu._period_values(TTM_TABLE, "Sales")
        growth = fu._pair_growth(vals, "sales")
        return labels[-1:], (labels[-1:] == ["Mar 2026"]
                             and round(growth["sales_growth_prev_1y_pct"]) == 46)
    check("the TTM column is not a financial year", "['Mar 2026'], and 46% the year before",
          "growth was read one column late, hiding a 46% to 7% collapse", ttm)

    def bank_scored():
        got = fu.assess(GOOD_BANK)
        return got["score"], got["score"] >= 75 and not got.get("unrated")
    check("a good bank scores as a good bank", "at least 75, and rated",
          "AU Small Finance, in Mojo's top 1%, was ranked last of four on 67", bank_scored)

    def bank_reason():
        joined = " ".join(fu.assess(GOOD_BANK)["why"])
        return ("mentions cash flow" if "cash flow" in joined else "no industrial reasons",
                "cash flow" not in joined)
    check("a lender is never given an industrial reason", "no industrial reasons",
          "Bajaj Finance was capped for 'cash flow negative 12 years running'", bank_reason)

    # This one has to test the **parse**, not the scorer. Handing `profit_fy_cr` to `assess`
    # directly passes on the broken version too, because the bug was never in the arithmetic —
    # it was that nothing ever read net profit off the annual table, so the arithmetic ran on an
    # assumed 10% margin. A canary that supplies the missing input cannot see the missing input.
    def conversion():
        got = fu._parse(PL_TABLE).get("profit_fy_cr")
        return got, got == 12800.0
    check("net profit is read off the annual table", "12800.0",
          "it was never parsed, so cash conversion ran on an assumed 10% margin and Adani Ports "
          "showed 526% conversion", conversion)
    return out


def head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


def branch() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


def run() -> tuple[bool, list[dict]]:
    rows = canaries()
    return all(r["ok"] for r in rows), rows
