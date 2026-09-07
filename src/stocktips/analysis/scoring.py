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
