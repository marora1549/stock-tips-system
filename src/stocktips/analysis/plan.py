"""Turn a TA snapshot into an executable trade plan: entry, SL, T1/T2/T3, timeframe, TA confidence.

Design principles
-----------------
* Targets come from *structure* first (swing resistances, 52w high), *volatility*
  second (ATR multiples) — never from the tip-sheet's "₹X target" alone.
* Stop-loss sits below structure (recent swing low / support), bounded by ATR so
  a low-volatility name isn't given a needlessly wide stop.
* Every point of TA confidence is explained in `reasons`, so the EOD run can
  later learn which reasons were actually predictive.
"""
from __future__ import annotations

import re

from ..util import settings

TF_ORDER = {"intraday": 0, "weekly": 1, "monthly": 2, "long": 3}


_MONTHS_RE = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|\d{1,2})\s*(?:-|–|to)?\s*(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|\d{1,2})?\s*months?\b")
_WEEKS_RE = re.compile(r"\b(one|two|three|four|\d{1,2})\s*(?:-|–|to)?\s*(?:one|two|three|four|\d{1,2})?\s*weeks?\b|\b(\d{1,2})\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*(?:trading\s*)?(?:days|sessions)\b")


def classify_timeframe(text: str | None, src_target_pct: float | None, default: str = "weekly") -> str:
    t = (text or "").lower()
    if any(k in t for k in ("intraday", "for today", "today's trade", "day trade", "buy today sell", "btst", "stbt")):
        return "intraday"
    if any(k in t for k in ("12 months", "12-month", "one year", "1 year", "1-year", "long term", "long-term", "fy27", "fy28", "next 2 years", "multibagger", "12m")):
        return "long"
    if any(k in t for k in ("1 month", "one month", "4 weeks", "3 months", "3-month", "quarter", "2 months", "6 months", "6-month", "medium term", "positional", "30 days", "1-month", "3 months")):
        return "monthly"
    m = _MONTHS_RE.search(t)
    if m:
        first = m.group(1)
        n = int(first) if first.isdigit() else ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"].index(first) + 1
        return "long" if n >= 12 else "monthly"
    if _WEEKS_RE.search(t):
        return "weekly"
    if any(k in t for k in ("this week", "weekly", "1-2 weeks", "2 weeks", "short term", "short-term", "near term", "near-term", "next few sessions", "few sessions", "1 week", "2-3 weeks", "5-7 days", "7 days", "10 days", "swing")):
        return "weekly"
    if src_target_pct is not None:
        if src_target_pct >= 15:
            return "long"
        if src_target_pct >= 7:
            return "monthly"
        if src_target_pct > 0:
            return "weekly"
    return default


def build_plan(ta: dict, timeframe: str, entry: float | None = None, src_targets: list[float] | None = None,
               src_stop: float | None = None) -> dict:
    cfg = settings()
    mand, risk = cfg["mandate"], cfg["risk"]
    px = entry or ta["close"]
    atr_ = ta["atr"]
    tf = timeframe if timeframe in TF_ORDER else "weekly"
    monthly_like = tf in ("monthly", "long")

    # ---------------- stop-loss
    k_sl = 2.5 if monthly_like else 1.5
    atr_stop = px - k_sl * atr_
    struct_candidates = [s["price"] for s in ta["supports"] if s["price"] < px * 0.995]
    swing = ta["recent_swing_low"]
    if swing < px * 0.995:
        struct_candidates.append(swing)
    # nearest structural support that is not absurdly close (>= 0.6 ATR below) and not too far (<= max SL)
    struct_ok = [s for s in struct_candidates if px - s >= 0.6 * atr_ and (px - s) / px * 100 <= risk["max_stop_loss_pct"] + 1.0]
    if struct_ok:
        base = max(struct_ok)                 # nearest qualifying support
        sl = base * 0.995                     # a hair below it (stops hunted at round supports)
        sl_basis = "below support"
    else:
        sl = atr_stop
        sl_basis = f"{k_sl}×ATR"
    if monthly_like and sl > atr_stop and ta["ema50"] < px and ta["ema50"] > sl:
        sl = max(sl, min(atr_stop, ta["ema50"] * 0.99))
        sl_basis += " / near 50EMA"
    sl = round(min(sl, px * (1 - 0.007)), 2)
    sl_pct = round((px - sl) / px * 100, 2)
    risk_per_share = px - sl

    # ---------------- targets
    res = [r["price"] for r in ta["resistances"] if r["price"] > px * 1.005]
    mults = (3.0, 5.0, 8.0) if monthly_like else (1.5, 3.0, 4.5)
    targets: list[float] = []
    basis: list[str] = []
    floor_gap = 0.8 * atr_ if not monthly_like else 1.5 * atr_
    for i, m in enumerate(mults):
        prev = targets[-1] if targets else px
        atr_t = px + m * atr_
        lo_bound = max(prev + floor_gap, px + (m - 0.6) * atr_)
        hi_bound = px + (m + 1.2) * atr_
        struct = [r for r in res if lo_bound <= r <= hi_bound]
        if struct:
            t = min(struct)
            basis.append("resistance")
        else:
            t = max(atr_t, prev + floor_gap)
            basis.append(f"{m:g}×ATR")
        targets.append(round(t, 2))
    # the 52w high is a natural T3 if it sits within reach
    if ta["high_52w"] > targets[1] * 1.005 and ta["high_52w"] < px * (1.25 if monthly_like else 1.12):
        targets[2] = round(ta["high_52w"], 2)
        basis[2] = "52w high"
    tgt_pct = [round((t / px - 1) * 100, 2) for t in targets]
    rr_t2 = round((targets[1] - px) / risk_per_share, 2) if risk_per_share > 0 else 0

    mandate_pct = mand["monthly_target_pct"] if monthly_like else mand["weekly_target_pct"]
    time_stop = mand["monthly_time_stop_days"] if monthly_like else mand["weekly_time_stop_days"]

    # ---------------- TA confidence
    conf, reasons = 40.0, []

    def add(p, why):
        nonlocal conf
        conf += p
        reasons.append(f"{'+' if p >= 0 else ''}{p:g} {why}")

    tr = ta["trend"]
    add({"strong_up": 14, "up": 8, "sideways": -4, "down": -14, "strong_down": -24}[tr], f"trend {tr}")
    r = ta["rsi"]
    if 50 <= r <= 68:
        add(7, f"RSI {r} healthy momentum")
    elif 40 <= r < 50:
        add(2, f"RSI {r} neutral")
    elif r > 75:
        add(-10, f"RSI {r} overbought")
    elif r < 35:
        add(-6, f"RSI {r} weak")
    if ta["macd_hist"] > 0 and ta["macd_hist_rising"]:
        add(5, "MACD histogram positive & rising")
    elif ta["macd_hist"] < 0 and not ta["macd_hist_rising"]:
        add(-6, "MACD histogram negative & falling")
    if ta["adx"] is not None:
        if ta["adx"] >= 25 and tr in ("strong_up", "up"):
            add(4, f"ADX {ta['adx']} trending")
        elif ta["adx"] < 15:
            add(-3, f"ADX {ta['adx']} no trend")
    vr = ta["vol_ratio"] or 1
    if vr >= 1.5 and ta["chg_1d_pct"] > 0:
        add(5, f"volume {vr}× avg on up day")
    elif vr >= 1.5 and ta["chg_1d_pct"] < 0:
        add(-6, f"volume {vr}× avg on DOWN day (distribution)")
    for p in ta["patterns"]:
        pts = {"breakout_60d_high_volume": 8, "breakout_60d_low_volume": 1, "pullback_to_ema20_in_uptrend": 6, "pullback_to_ema50_in_uptrend": 4,
               "bollinger_squeeze": 3, "double_bottom_confirmed": 6, "momentum_aligned": 4, "at_52w_high": 2,
               "overextended": -14, "oversold_in_downtrend": -8, "gap_or_spike_today": -8, "volume_spike": 1}.get(p, 0)
        if pts:
            add(pts, f"pattern {p}")
    # proximity to first resistance (chasing into a wall)
    if res and (res[0] / px - 1) * 100 < 1.2 and basis[0] != "resistance":
        add(-8, f"resistance ₹{res[0]:g} within 1.2% overhead")
    if rr_t2 < risk["min_reward_risk_t2"]:
        add(-15, f"reward:risk to T2 only {rr_t2}")
    elif rr_t2 >= 2.5:
        add(4, f"reward:risk to T2 {rr_t2}")
    if sl_pct > risk["max_stop_loss_pct"]:
        add(-12, f"stop {sl_pct}% wider than {risk['max_stop_loss_pct']}% limit")
    if tgt_pct[2] < mandate_pct:
        add(-10, f"T3 {tgt_pct[2]}% < {mandate_pct}% mandate for {tf}")
    if ta["avg_turnover_cr"] < risk["min_avg_turnover_cr"]:
        add(-15, f"illiquid: avg turnover ₹{ta['avg_turnover_cr']} cr")
    if ta["close"] < risk["min_price_inr"]:
        add(-20, "penny stock")
    if src_targets:
        st = max(src_targets)
        if st < targets[0]:
            add(-4, f"source target ₹{st:g} below our T1 — source sees less upside")
        elif st > px * (1.6 if monthly_like else 1.25):
            add(-3, f"source target ₹{st:g} implausibly far for {tf}")
    conf = int(max(0, min(95, round(conf))))

    ok = tf != "intraday" or mand["intraday_allowed"]
    return {
        "timeframe": tf, "entry": round(px, 2), "entry_zone": [round(px * 0.995, 2), round(px * 1.005, 2)],
        "stop_loss": sl, "stop_loss_pct": sl_pct, "stop_basis": sl_basis,
        "targets": targets, "target_pct": tgt_pct, "target_basis": basis,
        "reward_risk_t2": rr_t2, "mandate_pct": mandate_pct, "time_stop_days": time_stop,
        "ta_confidence": conf, "reasons": reasons,
        "tradeable": ok and sl_pct <= risk["max_stop_loss_pct"] and rr_t2 >= risk["min_reward_risk_t2"] and ta["avg_turnover_cr"] >= risk["min_avg_turnover_cr"] and ta["close"] >= risk["min_price_inr"],
        "src_targets": src_targets or [], "src_stop": src_stop,
    }
