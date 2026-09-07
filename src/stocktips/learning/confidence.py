"""Per-source confidence — the system's memory of who to believe.

state/sources_confidence.json:
{
  "<source_id>": {
     "score": 0.0,            # raw, starts at 0, decays toward recent behaviour
     "n_tips": 0, "n_resolved": 0, "n_t1": 0, "n_t2": 0, "n_t3": 0, "n_sl": 0, "n_timestop": 0,
     "sum_return_pct": 0.0,   # realised % return of resolved tips (for expectancy)
     "avg_days_to_t1": null,
     "history": [ {date, symbol, outcome, ret_pct, delta} ... ]   # last 100
     "enabled": true, "first_seen": "...", "last_seen": "..."
  }
}

Source ids
----------
* config sources.yaml ids                       (et_recos_gnews, chartink_52w_breakout, ...)
* broker:<slug>  — a brokerage/analyst named in the text, scored separately from
                   the newspaper that carried the call
"""
from __future__ import annotations

import math
from datetime import datetime

from ..util import STATE_DIR, read_json, settings, today_str, write_json

PATH = STATE_DIR / "sources_confidence.json"


def load() -> dict:
    return read_json(PATH, {})


def save(d: dict) -> None:
    write_json(PATH, d)


def _blank(source_id: str) -> dict:
    return {"score": 0.0, "n_tips": 0, "n_resolved": 0, "n_t1": 0, "n_t2": 0, "n_t3": 0, "n_sl": 0, "n_timestop": 0,
            "sum_return_pct": 0.0, "days_to_t1": [], "history": [], "enabled": True,
            "first_seen": today_str(), "last_seen": today_str(), "id": source_id}


def ensure(d: dict, source_id: str) -> dict:
    if source_id not in d:
        d[source_id] = _blank(source_id)
    return d[source_id]


def weight(score: float) -> float:
    """Map raw score → (0,1) weight for the composite. 0 → 0.5 (neutral prior)."""
    return 0.5 + 0.5 * math.tanh(score / settings()["source_confidence"]["tanh_scale"])


def display(score: float) -> int:
    """0–100 for humans: 50 = untested, >50 trusted, <50 distrusted."""
    return int(round(weight(score) * 100))


def note_tip(d: dict, source_id: str) -> None:
    s = ensure(d, source_id)
    s["n_tips"] += 1
    s["last_seen"] = today_str()


def record_outcome(d: dict, source_id: str, *, symbol: str, outcome: str, ret_pct: float, days: int | None = None, share: float = 1.0) -> float:
    """Apply a realised outcome. `share` < 1 for corroborating (secondary) sources.

    outcome ∈ {t1, t2, t3, stop_loss, time_stop_gain, time_stop_loss, manual_exit}
    Returns the delta applied.
    """
    cfg = settings()["source_confidence"]
    s = ensure(d, source_id)
    delta = {"t1": cfg["reward_t1"], "t2": cfg["reward_t2"], "t3": cfg["reward_t3"], "stop_loss": cfg["penalty_stop_loss"],
             "time_stop_loss": cfg["penalty_time_stop_loss"], "time_stop_gain": cfg["reward_time_stop_gain"], "manual_exit": 0}.get(outcome, 0) * share
    s["score"] = s["score"] * cfg["decay_per_outcome"] + delta
    if outcome == "t1":
        s["n_t1"] += 1
        if days is not None:
            s["days_to_t1"] = (s.get("days_to_t1") or [])[-49:] + [days]
    elif outcome == "t2":
        s["n_t2"] += 1
    elif outcome == "t3":
        s["n_t3"] += 1
    elif outcome == "stop_loss":
        s["n_sl"] += 1
    elif outcome.startswith("time_stop"):
        s["n_timestop"] += 1
    # a position "resolves" once at its terminal event (stop / time-stop / t3 / manual). t1,t2 are milestones.
    if outcome in ("stop_loss", "time_stop_loss", "time_stop_gain", "t3", "manual_exit"):
        s["n_resolved"] += 1
        s["sum_return_pct"] += ret_pct
    s["history"] = (s.get("history") or [])[-99:] + [{"date": today_str(), "symbol": symbol, "outcome": outcome, "ret_pct": round(ret_pct, 2), "delta": round(delta, 2)}]
    s["last_seen"] = today_str()
    if s["n_resolved"] >= cfg["min_outcomes_to_disable"] and s["score"] < cfg["disable_below"]:
        s["enabled"] = False
    return delta


def summary(d: dict) -> list[dict]:
    out = []
    for sid, s in d.items():
        n_res = s.get("n_resolved", 0)
        out.append({
            "source_id": sid, "score": round(s["score"], 1), "confidence": display(s["score"]), "weight": round(weight(s["score"]), 3),
            "n_tips": s["n_tips"], "n_resolved": n_res, "t1_hit_rate": round(s["n_t1"] / max(1, s["n_tips"]) * 100) if s["n_tips"] else None,
            "stop_rate": round(s["n_sl"] / max(1, n_res) * 100) if n_res else None,
            "expectancy_pct": round(s["sum_return_pct"] / n_res, 2) if n_res else None,
            "avg_days_to_t1": round(sum(s["days_to_t1"]) / len(s["days_to_t1"]), 1) if s.get("days_to_t1") else None,
            "enabled": s.get("enabled", True), "last_seen": s.get("last_seen"),
        })
    return sorted(out, key=lambda x: -x["score"])
