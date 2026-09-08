"""The trade, once the news has earned one — and the rule that stops you buying the top.

`catalyst.py` decides *whether*. This decides *at what price*, and its most important output is
often "not at the open".

GE Vernova is the case that shaped it. The news was right, the company was right, and a market order
at 09:15 on 8 September would still have been a bad trade: it gapped up, ran to about +12% inside the
first hour and closed near +9%. Buying the open was buying most of the way into the top. So nothing
here ever says "buy it" — it hands over a rule keyed on what the open actually does:

    gap ≤ +2%      buy the break of the opening-range high; stop under the opening-range low
    gap +2 to +5%  the same, but only if that range closes strong on real volume
    gap > +5%      no fresh entry at the open. A pullback that reclaims VWAP, or nothing.

Targets are measured moves of the opening range rather than round percentages, because the range the
market itself just made is the only honest estimate of what it can travel next. Everything is capped
by the daily ATR — a +15% target on a stock that moves 3% a day is arithmetic, not a plan — the stop
is never wider than 1.5%, and the position is flat by 15:10 whatever it is doing.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pandas as pd

from ..util import settings

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_T = time(9, 15)
SESSION_MINUTES = 375        # 09:15 to 15:30
TRIGGER_BUFFER_PCT = 0.05    # how far above the range high counts as a break, not a touch


def cfg() -> dict:
    return settings().get("intraday", {}) or {}


def _t(hhmm: str, default: time) -> time:
    try:
        h, m = str(hhmm).split(":")
        return time(int(h), int(m))
    except Exception:
        return default


# ------------------------------------------------------------------ the gap
def gap_band(gap_pct: float | None, c: dict | None = None) -> str:
    """flat · modest · wide · runaway · gap_down — the branch of the plan that applies."""
    c = c or cfg()
    if gap_pct is None:
        return "unknown"
    if gap_pct <= -1.0:
        return "gap_down"
    if gap_pct <= 0.5:
        return "flat"
    if gap_pct <= float(c.get("gap_modest_pct", 2.0)):
        return "modest"
    if gap_pct <= float(c.get("gap_wide_pct", 5.0)):
        return "wide"
    return "runaway"


BAND_RULE = {
    "flat": "buy the break of the opening-range high",
    "modest": "buy the break of the opening-range high",
    "wide": "buy the opening-range break only if it closes strong on real volume",
    "runaway": "no fresh entry at the open — wait for a pullback that reclaims VWAP, or stand aside",
    "gap_down": "the market disagrees with the news — stand aside and let it settle",
    "unknown": "no opening price yet",
}


# ------------------------------------------------------------------ before the open
def preopen_plan(prev_close: float, ta: dict | None = None, c: dict | None = None) -> dict:
    """The conditional plan, written before anyone knows how it will open.

    Everything that does not depend on the gap is fixed here — the reference close, the day's
    plausible range, the stop cap, the clock — and the gap-dependent part is stated as the ladder,
    so the 08:00 email is a decision rule rather than a hope.
    """
    c = c or cfg()
    ta = ta or {}
    atr_pct = ta.get("atr_pct")
    day_range = round(prev_close * (atr_pct or 2.5) / 100, 2)
    ladder = []
    for band, upper in (("flat", 0.5), ("modest", float(c.get("gap_modest_pct", 2.0))),
                        ("wide", float(c.get("gap_wide_pct", 5.0))), ("runaway", None)):
        ladder.append({
            "band": band,
            "gap_upto_pct": upper,
            "rule": BAND_RULE[band],
            "acts": band not in ("runaway",),
        })
    return {
        "reference_close": round(prev_close, 2),
        "atr_pct": atr_pct,
        "expected_day_range_inr": day_range,
        "expected_day_range_pct": round((atr_pct or 2.5), 2),
        "opening_range_minutes": int(c.get("opening_range_minutes", 15)),
        "gap_ladder": ladder,
        "max_stop_pct": float(c.get("max_stop_pct", 1.5)),
        "min_stop_pct": float(c.get("min_stop_pct", 0.5)),
        "no_new_entry_after": str(c.get("no_new_entry_after", "14:00")),
        "force_flat_at": str(c.get("force_flat_at", "15:10")),
        "note": ("The levels are not knowable before the open — they come from the range the market "
                 "makes in its first minutes. What is knowable is the rule, and the rule is above."),
    }


# ------------------------------------------------------------------ after the open
def vwap(bars: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price through the session — the line a gap has to hold."""
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    vol = bars["volume"].fillna(0)
    cum_v = vol.cumsum().replace(0, pd.NA)
    return (typical * vol).cumsum() / cum_v


def session_bars(bars: pd.DataFrame, day: str | None = None) -> pd.DataFrame:
    """Just today's bars, from a frame that may carry several sessions."""
    if bars is None or bars.empty:
        return bars
    idx = bars.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize(IST)
    want = day or str(idx[-1].date())
    return bars[[str(ts.date()) == str(want) for ts in idx]]


def opening_range(bars: pd.DataFrame, minutes: int | None = None, day: str | None = None) -> dict | None:
    """The first `minutes` of the session: its high, low, where it closed in its own range, volume."""
    minutes = minutes or int(cfg().get("opening_range_minutes", 15))
    today = session_bars(bars, day)
    if today is None or today.empty:
        return None
    start = today.index[0]
    cutoff = start + timedelta(minutes=minutes)
    window = today[today.index < cutoff]
    if window.empty:
        window = today.iloc[:1]
    hi, lo = float(window["high"].max()), float(window["low"].min())
    last = float(window["close"].iloc[-1])
    span = hi - lo
    return {
        "open": round(float(window["open"].iloc[0]), 2),
        "high": round(hi, 2), "low": round(lo, 2), "close": round(last, 2),
        "span_inr": round(span, 2), "span_pct": round(span / lo * 100, 2) if lo else None,
        "close_position": round((last - lo) / span, 3) if span > 0 else 0.5,
        "volume": float(window["volume"].fillna(0).sum()),
        "bars": len(window), "minutes": minutes,
        "from": str(window.index[0].time())[:5], "to": str(window.index[-1].time())[:5],
    }


def _normal_window_volume(daily: pd.DataFrame | None, minutes: int) -> float | None:
    """What `minutes` of a normal session's volume looks like, for comparison.

    The opening minutes are always busier than the average slice, so this is a floor to beat, not a
    fair like-for-like: clearing 3× a flat pro-rata share is roughly a genuinely heavy open.
    """
    if daily is None or daily.empty or "volume" not in daily:
        return None
    avg = float(daily["volume"].tail(20).mean())
    return avg * minutes / SESSION_MINUTES if avg else None


def session_plan(prev_close: float, bars: pd.DataFrame, ta: dict | None = None,
                 daily: pd.DataFrame | None = None, now: datetime | None = None,
                 c: dict | None = None, day: str | None = None) -> dict:
    """The real plan, now that the open is known: levels, trigger, stop, targets, and whether to act.

    `state` is the honest answer at the moment it is called — `waiting` for a trigger that has not
    printed, `triggered` once it has, `voided` when the rule says stand aside, `done` after the
    forced-flat time.
    """
    c = c or cfg()
    ta = ta or {}
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)

    today = session_bars(bars, day)
    if today is None or today.empty:
        return {"state": "no-data", "band": "unknown", "reasons": ["no intraday bars for today"]}

    orng = opening_range(bars, int(c.get("opening_range_minutes", 15)), day)
    open_px = orng["open"]
    gap_pct = round((open_px / prev_close - 1) * 100, 2) if prev_close else None
    band = gap_band(gap_pct, c)
    reasons: list[str] = [f"opened at ₹{open_px:,.2f}, a {gap_pct:+.2f}% gap on ₹{prev_close:,.2f}",
                          f"first {orng['minutes']} minutes ran ₹{orng['low']:,.2f}–₹{orng['high']:,.2f} "
                          f"({orng['span_pct']:.2f}%) and closed {orng['close_position']:.0%} up that range"]

    vw = vwap(today)
    vwap_now = round(float(vw.iloc[-1]), 2) if len(vw) and pd.notna(vw.iloc[-1]) else None
    last_px = round(float(today["close"].iloc[-1]), 2)
    day_high = round(float(today["high"].max()), 2)
    day_low = round(float(today["low"].min()), 2)

    norm_vol = _normal_window_volume(daily, orng["minutes"])
    vol_mult = round(orng["volume"] / norm_vol, 2) if norm_vol else None

    # ---------------------------------------------------------------- does the rule let us act?
    acts, why_not = True, None
    if band in ("runaway", "gap_down", "unknown"):
        acts, why_not = False, BAND_RULE[band]
    elif band == "wide":
        need_close = float(c.get("or_close_in_top_third", 0.66))
        need_vol = float(c.get("or_volume_multiple", 3.0))
        if orng["close_position"] < need_close:
            acts, why_not = False, (f"a {gap_pct:+.1f}% gap needs the opening range to close above "
                                    f"{need_close:.0%} of itself; it closed at {orng['close_position']:.0%}")
        elif vol_mult is not None and vol_mult < need_vol:
            acts, why_not = False, (f"a {gap_pct:+.1f}% gap needs {need_vol:g}× a normal opening "
                                    f"volume; it did {vol_mult:g}×")
        else:
            reasons.append(f"wide gap, but the range closed strong"
                           + (f" on {vol_mult:g}× normal opening volume" if vol_mult else ""))

    # ---------------------------------------------------------------- levels
    plan: dict = {
        "band": band, "band_rule": BAND_RULE[band], "gap_pct": gap_pct, "open": open_px,
        "prev_close": round(prev_close, 2), "opening_range": orng, "vwap": vwap_now,
        "last": last_px, "day_high": day_high, "day_low": day_low,
        "or_volume_multiple": vol_mult,
        "from_open_pct": round((last_px / open_px - 1) * 100, 2) if open_px else None,
        "acts": acts, "why_not": why_not, "reasons": reasons,
    }

    if not acts:
        # the runaway branch still has one way in, and it is worth naming precisely
        if band == "runaway" and vwap_now is not None:
            # Only after the opening range: for the first bars the running VWAP is barely more than
            # that bar's own typical price, so every low sits "below VWAP" and the test would always
            # read as a pullback that never happened.
            after = today[today.index >= today.index[0] + timedelta(minutes=orng["minutes"])]
            below = bool(len(after) and (after["low"] < vw.reindex(after.index)).any())
            reclaimed = bool(below and last_px > vwap_now)
            plan["watch"] = {
                "kind": "vwap_reclaim",
                "vwap": vwap_now,
                "has_traded_below_vwap": below,
                "reclaimed_now": reclaimed,
                "note": (f"it has traded below VWAP ₹{vwap_now:,.2f} and is back above it — a 5-minute "
                         f"close holding there is the only entry this gap allows"
                         if reclaimed else
                         f"waiting for a pullback to VWAP ₹{vwap_now:,.2f}; there is no entry until then"),
            }
        plan["state"] = "voided"
        return plan

    # a break has to be a break: a hair above the range high, not a touch of it
    trigger = round(orng["high"] + max(0.05, round(orng["high"] * TRIGGER_BUFFER_PCT / 100, 2)), 2)
    max_stop = float(c.get("max_stop_pct", 1.5))
    min_stop = float(c.get("min_stop_pct", 0.5))
    raw_stop = orng["low"]
    stop = raw_stop
    stop_note = "under the opening-range low"
    if (trigger - raw_stop) / trigger * 100 > max_stop:
        stop = round(trigger * (1 - max_stop / 100), 2)
        stop_note = f"tightened to the {max_stop:g}% cap — the opening range was too wide to risk"
    elif (trigger - raw_stop) / trigger * 100 < min_stop:
        stop = round(trigger * (1 - min_stop / 100), 2)
        stop_note = f"widened to the {min_stop:g}% floor — the opening range was too tight to survive noise"
    risk = round(trigger - stop, 2)

    r_unit = max(orng["span_inr"], risk)
    atr_cap = open_px * (1 + float(c.get("max_target_atr", 1.5)) * (ta.get("atr_pct") or 2.5) / 100)
    targets, target_basis = [], []
    for mult in (c.get("target_r") or [1.0, 1.75, 2.5]):
        raw = trigger + float(mult) * r_unit
        capped = min(raw, atr_cap)
        targets.append(round(capped, 2))
        target_basis.append(f"{mult:g}× the opening range" if capped >= raw - 0.01
                            else f"{float(c.get('max_target_atr', 1.5)):g}× the daily ATR (the {mult:g}× "
                                 f"measured move was further than this stock travels in a day)")
    targets = sorted(set(targets))
    while len(targets) < 3:
        targets.append(targets[-1])

    flat_at = _t(str(c.get("force_flat_at", "15:10")), time(15, 10))
    cutoff = _t(str(c.get("no_new_entry_after", "14:00")), time(14, 0))
    ran = walk(today, trigger, stop, targets)

    if ran["stopped"]:
        state = "stopped"
    elif ran["triggered"]:
        state = "done" if now.time() >= flat_at else "triggered"
    elif now.time() >= flat_at:
        state = "done"
    elif now.time() >= cutoff:
        state = "expired"
    else:
        state = "waiting"

    plan.update({
        "state": state, "trigger": trigger, "stop": stop, "stop_note": stop_note,
        "stop_pct": round((trigger - stop) / trigger * 100, 2), "risk_inr": risk,
        "targets": targets, "target_basis": target_basis,
        "target_pct": [round((t / trigger - 1) * 100, 2) for t in targets],
        "reward_risk_t2": round((targets[1] - trigger) / risk, 2) if risk > 0 else None,
        "force_flat_at": str(c.get("force_flat_at", "15:10")),
        **{k: ran[k] for k in ("triggered", "stopped", "targets_hit", "entered_at", "stopped_at",
                               "max_favourable", "entry_bar_same_bar_stop")},
        "max_favourable_pct": ran.get("max_favourable_pct"),
    })
    plan["reasons"] = reasons + [
        f"trigger ₹{trigger:,.2f} on a break of the range high; stop ₹{stop:,.2f} {stop_note} "
        f"({plan['stop_pct']:.2f}% risk)",
        f"targets ₹{targets[0]:,.2f} / ₹{targets[1]:,.2f} / ₹{targets[2]:,.2f} — {target_basis[0]}",
        f"flat by {plan['force_flat_at']} whatever it is doing",
    ]
    return plan


def walk(today: pd.DataFrame, trigger: float, stop: float, targets: list[float]) -> dict:
    """Replay the session in order: did the trigger print, and what came next.

    Order matters and testing the whole day at once gets it wrong. In the modest-gap case the
    opening-range low sits below the stop, but that low happened *before* the break of the range —
    reporting it as a stop-out would file a winning trade as a loss. So entry is the first bar whose
    high reaches the trigger, and only bars from there count against the stop.

    Within a single bar the sequence is unknowable from OHLC, so if the entry bar also breaches the
    stop it is recorded as stopped, flagged `same_bar`. Assuming the good order would flatter every
    result the desk ever grades itself on.
    """
    out = {"triggered": False, "entered_at": None, "entry_bar_same_bar_stop": False,
           "stopped": False, "stopped_at": None, "targets_hit": 0, "max_favourable": None}
    if today is None or today.empty or not trigger:
        return out
    rows = list(today.iterrows())
    entry_i = next((i for i, (_, r) in enumerate(rows) if float(r["high"]) >= trigger), None)
    if entry_i is None:
        return out
    out["triggered"] = True
    out["entered_at"] = str(rows[entry_i][0].time())[:5]

    best = trigger
    for i in range(entry_i, len(rows)):
        ts, r = rows[i]
        hi, lo = float(r["high"]), float(r["low"])
        best = max(best, hi)
        if lo <= stop:
            out["stopped"] = True
            out["stopped_at"] = str(ts.time())[:5]
            out["entry_bar_same_bar_stop"] = (i == entry_i)
            if i == entry_i:                     # cannot know whether the high or the low came first
                best = trigger
            break
        out["targets_hit"] = max(out["targets_hit"], sum(1 for t in targets if hi >= t))
    out["max_favourable"] = round(best, 2)
    out["max_favourable_pct"] = round((best / trigger - 1) * 100, 2)
    return out


def size_for(plan: dict, c: dict | None = None) -> dict:
    """Quantity from the risk budget, not from the cash — the stop decides the size."""
    c = c or cfg()
    notional = float(c.get("notional_inr", 100000))
    trigger, stop = plan.get("trigger"), plan.get("stop")
    if not trigger or not stop or trigger <= stop:
        return {"qty": 0, "why": "no trigger and stop to size against"}
    risk_budget = notional * float(c.get("risk_per_trade_pct", 0.75)) / 100
    per_share = trigger - stop
    qty_by_risk = int(risk_budget // per_share)
    cap = notional * float(c.get("max_per_trade_pct", 40)) / 100
    qty_by_cap = int(cap // trigger)
    qty = max(0, min(qty_by_risk, qty_by_cap))
    return {
        "qty": qty, "capital_inr": round(qty * trigger, 2), "risk_inr": round(qty * per_share, 2),
        "risk_budget_inr": round(risk_budget, 2),
        "why": (f"{qty} shares — ₹{risk_budget:,.0f} of risk at ₹{per_share:,.2f} a share"
                if qty == qty_by_risk else
                f"{qty} shares — held back by the {c.get('max_per_trade_pct', 40)}% per-trade cap"),
        "binding": "risk" if qty == qty_by_risk else "cap",
    }


def order_line(symbol: str, plan: dict, qty: int) -> str:
    """The line to type into Zerodha. Paper only — nothing here places an order."""
    t = plan.get("targets") or []
    return (f"BUY {qty} {symbol} NSE MIS SL-limit trigger ₹{plan.get('trigger'):,.2f} "
            f"· SL-M ₹{plan.get('stop'):,.2f} · exit ₹" +
            " / ₹".join(f"{x:,.2f}" for x in t[:3]) +
            f" · square off by {plan.get('force_flat_at', '15:10')}")
