"""Whether the fundamentals score has ever been right — the audit the score could not survive.

Enviro Infra scored 92 out of 100 while burning cash for a third straight year, and nothing in the
system objected. Not a test, not a failed request, not a warning. The score was wrong for weeks and
the only reason anyone found out is that the desk owner read a paid research note and said so.

That is the defect worth fixing, and it is not the arithmetic. The arithmetic has now been rebuilt
twice; it will be wrong again. What was missing is any mechanism by which *being wrong shows up on
its own*. Every other opinion this system holds is graded — a tip source by its outcomes, an event
class by open-to-high travel — and the fundamentals score, the most confident number the system
printed, was graded by nobody.

Two ledgers close that.

state/fundamentals_calibration.json — the score against what the stock then did
--------------------------------------------------------------------------------
    {"buckets": {"0-40": {"n": 12, "n_up": 4, "sum_return_pct": -18.4, ...}, ...},
     "entries": [{"date", "symbol", "score", "flags", "unrated", "outcome", "ret_pct"} ...]}

A score is recorded when a position is opened and settled when it closes. The question it answers is
narrow on purpose: **do the names I score highly do better than the names I score poorly?** If the
80-plus bucket does not out-return the sub-40 bucket, the score is not carrying information, and
`inversions()` says so in words rather than leaving it to be noticed.

state/fundamentals_verdicts.json — the score against somebody else's
---------------------------------------------------------------------
    {"EIEL": [{"date", "source": "markets_mojo", "their_score": 37, "their_stance": "sell",
               "my_score": 92, "gap": 55, "note": "..."}]}

Outcomes take weeks. A second opinion is available the moment it is read, and disagreement is the
earliest possible warning. This records every one, and `bias()` reports the signed mean gap — so
"I am running twelve points generous to Markets Mojo across nine names" becomes a fact on a page
instead of a thing nobody counted.

Neither ledger changes a score. Both are deliberately read-only with respect to the scorer: a
number that quietly tuned itself toward Markets Mojo would just be Markets Mojo with extra steps,
and a bucket table that fed back into the weights would chase noise on a handful of trades. They
report. Acting on what they report is a decision taken with the evidence in view.
"""
from __future__ import annotations

from ..util import STATE_DIR, read_json, today_str, write_json

CALIB = STATE_DIR / "fundamentals_calibration.json"
VERDICTS = STATE_DIR / "fundamentals_verdicts.json"

BUCKETS = ((0, 40), (40, 60), (60, 75), (75, 101))
ENTRIES = 400
# Below this many settled trades a bucket's return is noise and is reported as such rather than
# compared. Four names is not evidence about a scoring band.
MIN_N = 5


def bucket_of(score: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= score < hi:
            return f"{lo}-{hi - 1 if hi == 101 else hi}"
    return "0-40"


# ------------------------------------------------------------------ score against outcome

def load() -> dict:
    return read_json(CALIB, {"buckets": {}, "entries": []})


def save(d: dict) -> None:
    write_json(CALIB, d)


def _blank_bucket(name: str) -> dict:
    return {"id": name, "n": 0, "n_settled": 0, "n_up": 0, "sum_return_pct": 0.0,
            "n_flagged": 0, "first_seen": today_str()}


def note_entry(d: dict, symbol: str, *, score: int, flags: list[str] | None = None,
               caps: list[str] | None = None, unrated: bool = False,
               on: str | None = None) -> dict:
    """Record what the score said about a name on the day a position in it was opened."""
    name = bucket_of(score)
    b = d.setdefault("buckets", {}).setdefault(name, _blank_bucket(name))
    b["n"] += 1
    if flags:
        b["n_flagged"] += 1
    entry = {"date": on or today_str(), "symbol": symbol, "score": int(score),
             "bucket": name, "flags": list(flags or []), "caps": list(caps or []),
             "unrated": bool(unrated), "outcome": None, "ret_pct": None}
    d.setdefault("entries", []).append(entry)
    d["entries"] = d["entries"][-ENTRIES:]
    return entry


def settle(d: dict, symbol: str, *, outcome: str, ret_pct: float,
           on: str | None = None) -> dict | None:
    """Attach the realised result to the most recent open entry for a symbol.

    Matched newest-first and only against an unsettled entry, so re-entering the same name later
    does not overwrite the earlier trade's record.
    """
    for entry in reversed(d.get("entries", [])):
        if entry["symbol"] != symbol or entry["outcome"] is not None:
            continue
        entry["outcome"] = outcome
        entry["ret_pct"] = round(float(ret_pct), 2)
        entry["settled_on"] = on or today_str()
        b = d.setdefault("buckets", {}).setdefault(entry["bucket"], _blank_bucket(entry["bucket"]))
        b["n_settled"] += 1
        b["n_up"] += 1 if ret_pct > 0 else 0
        b["sum_return_pct"] = round(b["sum_return_pct"] + float(ret_pct), 2)
        b["last_settled"] = on or today_str()
        return entry
    return None


def table(d: dict) -> list[dict]:
    """Each score band and what the names in it actually returned, worst band first."""
    out = []
    for lo, hi in BUCKETS:
        name = f"{lo}-{hi - 1 if hi == 101 else hi}"
        b = (d.get("buckets") or {}).get(name) or _blank_bucket(name)
        n = b["n_settled"]
        out.append({
            "bucket": name, "n_scored": b["n"], "n_settled": n,
            "avg_return_pct": round(b["sum_return_pct"] / n, 2) if n else None,
            "hit_rate": round(b["n_up"] / n, 3) if n else None,
            "thin": n < MIN_N,
        })
    return out


def inversions(d: dict) -> list[str]:
    """Where a higher score has produced a worse result — the score failing to carry information.

    Compares only bands with enough settled trades to mean anything, and states the finding in
    words, because a table of numbers is something a person has to remember to read.
    """
    rows = [r for r in table(d) if not r["thin"] and r["avg_return_pct"] is not None]
    found = []
    for i, lower in enumerate(rows):
        for higher in rows[i + 1:]:
            if higher["avg_return_pct"] < lower["avg_return_pct"]:
                found.append(
                    f"names scored {higher['bucket']} have averaged "
                    f"{higher['avg_return_pct']:+.1f}% against {lower['avg_return_pct']:+.1f}% for "
                    f"names scored {lower['bucket']} ({higher['n_settled']} and "
                    f"{lower['n_settled']} settled) — the score is ranking these two bands "
                    f"backwards")
    return found


# ------------------------------------------------------------------ score against second opinion

def load_verdicts() -> dict:
    return read_json(VERDICTS, {})


def save_verdicts(d: dict) -> None:
    write_json(VERDICTS, d)


def note_verdict(d: dict, symbol: str, *, source: str, their_score: float | None,
                 their_stance: str = "", my_score: float | None = None, note: str = "",
                 on: str | None = None) -> dict:
    """Record an outside verdict next to mine, whether or not it agrees."""
    row = {"date": on or today_str(), "source": source,
           "their_score": None if their_score is None else round(float(their_score), 1),
           "their_stance": their_stance, "my_score": None if my_score is None else int(my_score),
           "note": note}
    if row["their_score"] is not None and row["my_score"] is not None:
        row["gap"] = round(row["my_score"] - row["their_score"], 1)
    d.setdefault(symbol.upper(), []).append(row)
    return row


def _superseded(rows: list[dict], i: int) -> bool:
    """Was this comparison replaced by a later one, from the same desk, on the same day?

    Fixing the scorer and re-comparing the same company writes a second row. Both belong in the
    history — the +55 on Enviro Infra is the record of what went wrong and it is not being quietly
    deleted — but counting both in the bias would let a corrected mistake keep reporting itself
    forever. A row stands unless a later row for the same source and date replaces it.
    """
    r = rows[i]
    return any(later["source"] == r["source"] and later.get("date") == r.get("date")
               for later in rows[i + 1:])


def bias(d: dict, source: str | None = None) -> list[dict]:
    """Am I systematically generous or harsh, and against whom?

    Signed mean gap, not absolute: a scorer that is twenty points high on every name is a different
    and more fixable problem than one that is twenty points off in both directions.
    """
    by: dict[str, list[float]] = {}
    for rows in d.values():
        for i, r in enumerate(rows):
            if r.get("gap") is None or (source and r["source"] != source):
                continue
            if _superseded(rows, i):
                continue
            by.setdefault(r["source"], []).append(r["gap"])
    out = []
    for src, gaps in sorted(by.items()):
        mean = sum(gaps) / len(gaps)
        out.append({
            "source": src, "n": len(gaps),
            "mean_gap": round(mean, 1),
            "mean_abs_gap": round(sum(abs(g) for g in gaps) / len(gaps), 1),
            "worst": round(max(gaps, key=abs), 1),
            "reading": ("too few to say" if len(gaps) < 3 else
                        f"running {abs(mean):.0f} points {'generous' if mean > 0 else 'harsh'} "
                        f"against {src} across {len(gaps)} names" if abs(mean) >= 8 else
                        f"broadly in line with {src}"),
        })
    return out


def disagreements(d: dict, threshold: float = 20.0) -> list[dict]:
    """Every name where an outside verdict and mine were more than `threshold` points apart.

    This is the standing list of cases to go and look at. EIEL is the first entry, at 55 points.
    """
    out = []
    for symbol, rows in d.items():
        for i, r in enumerate(rows):
            if r.get("gap") is not None and abs(r["gap"]) >= threshold:
                out.append({"symbol": symbol, "superseded": _superseded(rows, i), **r})
    out.sort(key=lambda r: -abs(r["gap"]))
    return out
