"""What each kind of news has actually been worth — the part of the desk that gets trained.

`sources/events.py` carries a prior for every event class: an order win is worth 30, an MoU 12, a
broker upgrade 10. Those numbers are estimates written by hand on one evening, and treating them as
facts would be the whole system's weakest link. So they are seeds.

state/event_classes.json:

    {"order_win": {"prior": 30, "adjust": 4.2, "n": 17, "n_up": 11,
                   "sum_open_to_high_pct": 61.4, "history": [...]}}

`prior + adjust` is the weight the catalyst scorer actually uses. `adjust` moves on outcomes, using
the same decay the tip sources use, and is clamped so thirty observations can halve or double a
class's weight but never invert its sign — an order win that has disappointed lately is worth less,
not negative.

What an event is graded on is deliberately not "did the trade make money", because that conflates
the news with the execution. It is graded on **open→high**: how far the stock travelled from the
open on the day the desk read the news. That is the thing the news either did or did not cause, and
it is measurable whether or not a plan triggered.
"""
from __future__ import annotations

from ..util import STATE_DIR, read_json, settings, today_str, write_json

PATH = STATE_DIR / "event_classes.json"

# a class can be halved or doubled by evidence, but not turned into its opposite
MAX_ADJUST_FRACTION = 1.0
HISTORY = 120


def load() -> dict:
    return read_json(PATH, {})


def save(d: dict) -> None:
    write_json(PATH, d)


def _blank(event: str, prior: float) -> dict:
    return {"id": event, "prior": prior, "adjust": 0.0, "n": 0, "n_up": 0,
            "sum_open_to_high_pct": 0.0, "sum_open_to_close_pct": 0.0,
            "history": [], "first_seen": today_str(), "last_seen": today_str()}


def ensure(d: dict, event: str, prior: float = 0.0) -> dict:
    if event not in d:
        d[event] = _blank(event, prior)
    row = d[event]
    if prior and not row.get("prior"):
        row["prior"] = prior
    return row


def prior(d: dict, event: str, seed: float) -> float:
    """The weight to score with: the seed, moved by whatever this class has actually done."""
    row = d.get(event)
    if not row:
        return seed
    base = row.get("prior") or seed
    cap = abs(base) * MAX_ADJUST_FRACTION
    adjust = max(-cap, min(cap, float(row.get("adjust") or 0.0)))
    return round(base + adjust, 2)


def display(d: dict, event: str) -> dict:
    """What the page shows about a class: its record, in the units it was graded on."""
    row = d.get(event)
    if not row or not row.get("n"):
        return {"n": 0, "avg_open_to_high_pct": None, "hit_rate": None, "adjust": 0.0, "untested": True}
    n = row["n"]
    return {
        "n": n,
        "avg_open_to_high_pct": round(row["sum_open_to_high_pct"] / n, 2),
        "avg_open_to_close_pct": round(row["sum_open_to_close_pct"] / n, 2),
        "hit_rate": round(row["n_up"] / n, 3),
        "adjust": round(float(row.get("adjust") or 0.0), 2),
        "untested": False,
    }


def note_outcome(d: dict, event: str, *, open_to_high_pct: float, open_to_close_pct: float,
                 symbol: str = "", seed_prior: float = 0.0, on: str | None = None) -> dict:
    """Record what one event's stock actually did from the open, and move the class's weight.

    The reward curve follows how the plan actually trades. It buys a break of the opening range and
    takes profit into strength, so **open→high is what a class is mostly paid for** — travel is the
    thing the news either caused or did not. Open→close is a penalty and only when negative: a class
    that reliably opens up two and a half percent and closes down two is a fade, and a fade must not
    accumulate weight just because the high looked good. Both are clamped, because one GE Vernova
    should not be allowed to define a class on its own.
    """
    row = ensure(d, event, seed_prior)
    decay = float(settings().get("source_confidence", {}).get("decay_per_outcome", 0.95))

    travel = max(-6.0, min(6.0, float(open_to_high_pct)))
    faded = min(0.0, max(-6.0, float(open_to_close_pct)))
    delta = travel * 0.9 + faded * 0.9
    if travel < 0.5:
        delta -= 1.0                     # never went anywhere from the open: the news did nothing

    row["adjust"] = round(float(row.get("adjust") or 0.0) * decay + delta, 3)
    row["n"] += 1
    row["n_up"] += 1 if open_to_high_pct >= 1.0 else 0
    row["sum_open_to_high_pct"] = round(row["sum_open_to_high_pct"] + float(open_to_high_pct), 2)
    row["sum_open_to_close_pct"] = round(row["sum_open_to_close_pct"] + float(open_to_close_pct), 2)
    row["last_seen"] = on or today_str()
    row["history"] = (row["history"] + [{
        "date": on or today_str(), "symbol": symbol,
        "open_to_high_pct": round(float(open_to_high_pct), 2),
        "open_to_close_pct": round(float(open_to_close_pct), 2),
        "delta": round(delta, 2),
    }])[-HISTORY:]
    return row


def summary(d: dict) -> list[dict]:
    """Every class the desk has an opinion about, best-travelling first — the trained brain."""
    out = []
    for event, row in d.items():
        shown = display(d, event)
        out.append({"event": event, "prior": row.get("prior"), "effective": prior(d, event, row.get("prior") or 0),
                    **shown})
    out.sort(key=lambda r: (r["untested"], -(r["avg_open_to_high_pct"] or 0)))
    return out
