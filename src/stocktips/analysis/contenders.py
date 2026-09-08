"""Rank every analysed idea against every other one and name the final few contenders.

`analyze` scores each tip on its own merits — chart, fundamentals, and how well its source has done.
That leaves a long list. This picks the ones actually worth the next rupee, on top of the composite:

* **the clock** — two ideas with the same composite are not equal if one reaches T1 in eight sessions
  and the other needs forty. `plan.eta_days` against the timeframe's own time stop decides it.
* **momentum** — the drift the chart is actually running at, not the target the tipster wants.
* **corroboration** — the same name from two independent sources is worth more than one shouting.
* **claim stretch** — a tipster asking for far more than the chart offers is a warning, not a bonus.

Every contender carries `vs_source`: their entry, target and stop beside ours, so the divergence is
on the page rather than in someone's head. Their numbers are never used as levels — only compared.
"""
from __future__ import annotations

TIME_STOP_FALLBACK = {"intraday": 1, "weekly": 10, "monthly": 30, "long": 90}


def _clock(plan: dict) -> tuple[float, str]:
    """Reward reaching T1 well inside the timeframe; punish a target the drift cannot reach."""
    horizon = plan.get("time_stop_days") or TIME_STOP_FALLBACK.get(plan.get("timeframe"), 30)
    eta = plan.get("eta_days")
    if not eta or eta <= 0:
        return -8.0, "no measurable drift — T1 has no date on it"
    ratio = eta / max(horizon, 1)
    if ratio > 1:
        return -8.0, f"T1 needs ~{eta:.0f} sessions, past the {horizon}-day stop"
    return round(10 * (1 - ratio), 1), f"T1 in ~{eta:.0f} sessions of {horizon}"


def _stretch(result: dict) -> tuple[float, str | None]:
    """How much more the tipster wants than the chart offers."""
    src = [t for t in (result.get("src_targets") or []) if t]
    tgts = result["plan"].get("targets") or []
    if not src or not tgts:
        return 0.0, None
    ltp = result.get("ltp") or 0
    if ltp <= 0:
        return 0.0, None
    theirs = (max(src) / ltp - 1) * 100
    ours = (max(tgts) / ltp - 1) * 100
    if ours <= 0 or theirs <= ours * 1.5:
        return 0.0, None
    return -4.0, f"their target wants {theirs:.1f}% where the chart offers {ours:.1f}%"


def vs_source(result: dict) -> dict:
    """The tipster's claim beside our plan — compared, never adopted."""
    plan, ltp = result["plan"], result.get("ltp") or 0
    src = sorted(t for t in (result.get("src_targets") or []) if t)
    tgts = plan.get("targets") or []
    out = {
        "src_entry": result.get("src_entry"), "src_target": max(src) if src else None,
        "src_stop": result.get("src_stop"),
        "our_entry": plan.get("entry"), "our_targets": tgts, "our_stop": plan.get("stop_loss"),
        "src_upside_pct": round((max(src) / ltp - 1) * 100, 2) if src and ltp else None,
        "our_upside_pct": round((max(tgts) / ltp - 1) * 100, 2) if tgts and ltp else None,
        "src_risk_pct": round((1 - result["src_stop"] / ltp) * 100, 2) if result.get("src_stop") and ltp else None,
        "our_risk_pct": plan.get("stop_loss_pct"),
        "notes": [],
    }
    if out["src_entry"] and ltp:
        drift = (ltp / out["src_entry"] - 1) * 100
        if abs(drift) >= 1:
            out["notes"].append(f"price is {drift:+.1f}% against their ₹{out['src_entry']:,.2f} entry")
    if out["src_target"] and tgts:
        if out["src_target"] > max(tgts):
            out["notes"].append(f"their ₹{out['src_target']:,.2f} target sits above our T3 ₹{max(tgts):,.2f}")
        elif out["src_target"] < min(tgts):
            out["notes"].append(f"their ₹{out['src_target']:,.2f} target is below even our T1 ₹{min(tgts):,.2f}")
        else:
            out["notes"].append(f"their target lands inside our ladder (T1 ₹{min(tgts):,.2f}–T3 ₹{max(tgts):,.2f})")
    if result.get("src_stop") and plan.get("stop_loss"):
        if result["src_stop"] < plan["stop_loss"]:
            out["notes"].append(f"their stop ₹{result['src_stop']:,.2f} is looser than ours ₹{plan['stop_loss']:,.2f}")
        else:
            out["notes"].append(f"their stop ₹{result['src_stop']:,.2f} is tighter than ours ₹{plan['stop_loss']:,.2f}")
    return out


def rank(results: list[dict], n: int = 3, held: set[str] | None = None) -> list[dict]:
    """Score every idea head to head; return the top `n` with the arithmetic that put them there."""
    held = held or set()
    scored: list[dict] = []
    for r in results:
        plan = r.get("plan") or {}
        if not plan.get("tradeable", True):
            continue
        base = float(r.get("composite") or 0)
        clock, clock_why = _clock(plan)
        mom = r.get("ta", {}).get("momentum_score") or plan.get("momentum_score") or 0
        mom_pts = round(6 * mom / 100, 1)
        extra = min(2, len(r.get("corroborating_sources") or []))
        corr = 4.0 * extra
        stretch, stretch_why = _stretch(r)
        why = [f"{base:.0f} composite (TA {r.get('ta_confidence')}, fund {r.get('fund_score')}, src {r.get('source_confidence')})",
               f"{clock:+.1f} clock — {clock_why}"]
        if mom_pts:
            why.append(f"{mom_pts:+.1f} momentum {mom}/100")
        if corr:
            why.append(f"{corr:+.1f} corroborated by {extra} other source{'s' if extra > 1 else ''}")
        if stretch_why:
            why.append(f"{stretch:+.1f} {stretch_why}")
        scored.append({
            "symbol": r["symbol"], "company": r.get("company"), "source_id": r.get("source_id"),
            "corroborating_sources": r.get("corroborating_sources") or [],
            "verdict": r.get("verdict"), "bucket": r.get("bucket"), "composite": r.get("composite"),
            "ta_confidence": r.get("ta_confidence"), "fund_score": r.get("fund_score"),
            "source_confidence": r.get("source_confidence"), "ltp": r.get("ltp"),
            "eta_days": plan.get("eta_days"), "momentum_score": mom, "timeframe": plan.get("timeframe"),
            "reward_risk_t2": plan.get("reward_risk_t2"), "tags": r.get("tags") or [],
            "contender_score": round(base + clock + mom_pts + corr + stretch, 1),
            "why": why, "held": r["symbol"] in held, "vs_source": vs_source(r),
        })
    scored.sort(key=lambda x: (-x["contender_score"], x["symbol"]))
    # one contender per symbol: the same name tipped twice is one idea, not two
    seen: set[str] = set()
    top: list[dict] = []
    for c in scored:
        if c["symbol"] in seen:
            continue
        seen.add(c["symbol"])
        top.append(c)
        if len(top) >= n:
            break
    for i, c in enumerate(top, 1):
        c["rank"] = i
    return top
