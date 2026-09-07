"""Confidence-weighted allocation of deployable cash across today's picks."""
from __future__ import annotations

from ..util import settings


def allocate(picks: list[dict], cash: float, already_held: set[str]) -> list[dict]:
    """picks: analysed candidates sorted by composite desc. Returns picks with `alloc_inr` set (may be 0)."""
    cfg = settings()
    cap_total = cfg["capital"]["total_inr"]
    max_one = cap_total * cfg["capital"]["max_single_stock_pct"] / 100
    min_one = cap_total * cfg["capital"]["min_allocation_pct"] / 100
    thr = cfg["scoring"]["pick_threshold"]
    top_n = cfg["scoring"]["top_n"]

    eligible = [p for p in picks if p["verdict"] in ("BUY", "STRONG BUY") and p["symbol"] not in already_held][:top_n]
    for p in picks:
        p["alloc_inr"] = 0.0
    if not eligible or cash < min_one:
        return picks
    weights = [max(1.0, p["composite"] - thr + 5) for p in eligible]      # excess conviction above threshold
    total_w = sum(weights)
    remaining = cash
    for p, w in zip(eligible, weights):
        amt = min(max_one, cash * w / total_w, remaining)
        if amt < min_one:
            continue
        qty = int(amt // p["plan"]["entry"])
        if qty <= 0:
            continue
        p["alloc_qty"] = qty
        p["alloc_inr"] = round(qty * p["plan"]["entry"], 2)
        remaining -= p["alloc_inr"]
    # leftover from rounding goes to the top pick if it stays under the single-stock cap
    top = eligible[0]
    if top.get("alloc_qty") and remaining >= top["plan"]["entry"]:
        extra = int(min(remaining, max_one - top["alloc_inr"]) // top["plan"]["entry"])
        if extra > 0:
            top["alloc_qty"] += extra
            top["alloc_inr"] = round(top["alloc_qty"] * top["plan"]["entry"], 2)
    return picks
