"""Composite score = TA × fundamentals × source-trust, plus a plain-English verdict."""
from __future__ import annotations

from ..util import settings


def composite(ta_conf: int, fund_score: int, source_weight: float) -> int:
    w = settings()["scoring"]
    return int(round(w["w_ta"] * ta_conf + w["w_fund"] * fund_score + w["w_src"] * (source_weight * 100)))


def verdict(comp: int, plan: dict, fund_score: int) -> tuple[str, str]:
    cfg = settings()["scoring"]
    if not plan["tradeable"]:
        if plan["timeframe"] == "intraday":
            return "SKIP", "intraday — outside mandate"
        return "SKIP", "fails risk rules (" + "; ".join(r for r in plan["reasons"] if r.startswith("-")) [:160] + ")"
    if comp >= cfg["pick_threshold"] + 13:
        v = "STRONG BUY"
    elif comp >= cfg["pick_threshold"]:
        v = "BUY"
    elif comp >= cfg["pick_threshold"] - 10:
        v = "WATCH"
    else:
        v = "AVOID"
    bucket = "hold-capable (fundamentally sound — can be held through a stall)" if fund_score >= cfg["hold_bucket_fund_score"] else "hot potato (momentum only — exit at target or stop, never hold)"
    return v, bucket


def tags(plan: dict, ta: dict, fund_score: int, n_mentions: int = 1, corroborating: int = 0) -> list[dict]:
    """Short labels for what kind of idea this is, so a glance answers "why would I take this?".

    Each tag is {key, label, tone, why} — the UI shows label and colours by tone; `why` is the number
    behind it, so nothing is decorative. Tone: good / warn / bad / flat.
    """
    out: list[dict] = []
    ta_conf = plan.get("ta_confidence") or 0
    mom = ta.get("momentum_score")
    eta = (plan.get("eta_days") or [None])[0]
    clock = plan.get("time_stop_days")

    if fund_score >= 80:
        out.append({"key": "fundamentals", "label": "Fundamentals", "tone": "good", "why": f"business score {fund_score}"})
    elif fund_score >= 65:
        out.append({"key": "fundamentals", "label": "Sound books", "tone": "good", "why": f"business score {fund_score}"})
    elif fund_score < 45:
        out.append({"key": "weak-books", "label": "Weak books", "tone": "bad", "why": f"business score {fund_score}"})

    if ta_conf >= 80:
        out.append({"key": "technicals", "label": "Chart", "tone": "good", "why": f"TA confidence {ta_conf}"})
    elif ta_conf >= 70:
        out.append({"key": "technicals", "label": "Clean chart", "tone": "good", "why": f"TA confidence {ta_conf}"})

    if mom is not None and mom >= 70 and eta and clock and eta <= max(2, clock // 3):
        out.append({"key": "momentum", "label": "Fast mover", "tone": "good",
                    "why": f"{plan.get('pace_pct_day')}%/session — T1 about {eta} sessions out"})
    elif mom is not None and mom <= 25:
        out.append({"key": "sluggish", "label": "Sluggish", "tone": "warn",
                    "why": f"pace {plan.get('pace_pct_day')}%/session — mostly chop"})

    if eta and clock and eta > clock:
        out.append({"key": "slow-clock", "label": "Beats the clock?", "tone": "warn",
                    "why": f"T1 needs about {eta} sessions against a {clock}-session stop"})

    if plan.get("reward_risk_t2") and plan["reward_risk_t2"] >= 3:
        out.append({"key": "asymmetric", "label": "Asymmetric", "tone": "good",
                    "why": f"reward:risk to T2 is {plan['reward_risk_t2']}"})

    if (plan.get("stop_loss_pct") or 0) <= 3:
        out.append({"key": "tight-stop", "label": "Tight stop", "tone": "good",
                    "why": f"stop only {plan.get('stop_loss_pct')}% away"})

    if corroborating >= 1 or n_mentions >= 3:
        out.append({"key": "corroborated", "label": f"{max(n_mentions, corroborating + 1)} sources", "tone": "flat",
                    "why": "the same name from more than one place"})

    trend = (ta.get("trend") or "").replace("_", " ")
    if trend in ("strong up", "up"):
        out.append({"key": "trend", "label": "Strong uptrend" if trend == "strong up" else "Uptrend",
                    "tone": "flat", "why": f"EMA 20/50/200 stack reads {trend}"})

    if fund_score < settings()["scoring"]["hold_bucket_fund_score"]:
        out.append({"key": "hot-potato", "label": "Hot potato", "tone": "warn",
                    "why": "momentum only — exit at target or stop, never hold through a stall"})
    return out
