"""Paper-trading ledger — state/ledger.json.

{
  "capital_inr": 100000,
  "cash_inr": 100000,                 # uncommitted capital
  "positions": [ ...open/hold... ],
  "closed": [ ...closed... ],
  "equity_curve": [ {date, equity} ]
}

Position lifecycle
------------------
open  ──T1 hit──▶ 40% booked, SL→entry   ──T2──▶ 30% booked, SL→T1  ──T3──▶ closed
  │
  ├── SL hit ──────────────────────────────────────────────────────────▶ closed (stop_loss)
  └── time stop (no T1 by deadline)
          ├── fund_score >= hold threshold ──▶ status "hold" (capital stays parked, tracked, no time stop)
          └── else ────────────────────────▶ closed (time_stop_gain / time_stop_loss)

Fills are simulated conservatively from daily bars: entry at next open (morning
run books at that day's open once the EOD run sees the bar), stops/targets
checked against the day's low/high, gap-through stops fill at the open.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..util import STATE_DIR, now_ist, read_json, settings, today_str, write_json
from ..data import prices
from ..learning import confidence

log = logging.getLogger(__name__)
PATH = STATE_DIR / "ledger.json"


def load() -> dict:
    cap = settings()["capital"]["total_inr"]
    return read_json(PATH, {"capital_inr": cap, "cash_inr": cap, "positions": [], "closed": [], "equity_curve": [], "created": today_str()})


def save(led: dict) -> None:
    write_json(PATH, led)


def trading_days_between(a: str, b: str) -> int:
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return len(pd.bdate_range(d0, d1)) - 1 if d1 > d0 else 0


def open_position(led: dict, pick: dict, capital_inr: float) -> dict | None:
    """Create a *pending* position from a morning pick. Filled by the EOD run at that day's open."""
    if any(p["symbol"] == pick["symbol"] for p in led["positions"]):
        log.info("%s already in book — skipping", pick["symbol"])
        return None
    plan = pick["plan"]
    entry = plan["entry"]
    qty = int(capital_inr / entry + 1e-6)
    if qty <= 0:
        return None
    # Booked before 09:15 IST → fills at today's open; booked later → next trading day's open
    now = now_ist()
    open_day = now.date() if (now.hour, now.minute) < (9, 15) else pd.bdate_range(now.date(), periods=2)[-1].date()
    pos = {
        "pos_id": f"{open_day}-{pick['symbol']}", "tip_id": pick["tip_id"], "symbol": pick["symbol"], "company": pick.get("company"),
        "opened": str(open_day), "booked": now.strftime("%Y-%m-%d %H:%M"), "status": "pending",   # pending → open at first EOD on/after `opened`
        "entry_plan": entry, "entry": None, "qty": qty, "qty_open": qty, "capital_inr": round(qty * entry, 2),
        "stop_loss": plan["stop_loss"], "initial_stop": plan["stop_loss"], "targets": plan["targets"], "targets_hit": [],
        "timeframe": plan["timeframe"], "time_stop_days": plan["time_stop_days"], "deadline": None,
        "source_id": pick["source_id"], "corroborating_sources": pick.get("corroborating_sources", []),
        "ta_confidence": pick["ta_confidence"], "fund_score": pick["fund_score"], "composite": pick["composite"],
        "bucket": "hold-capable" if pick["fund_score"] >= settings()["scoring"]["hold_bucket_fund_score"] else "hot-potato",
        "patterns": pick.get("ta", {}).get("patterns", []), "exits": [], "realised_inr": 0.0, "max_favourable_pct": 0.0, "notes": [],
    }
    led["positions"].append(pos)
    led["cash_inr"] = round(led["cash_inr"] - pos["capital_inr"], 2)
    return pos


def _book(pos: dict, qty: int, price: float, reason: str, on: str) -> float:
    qty = min(qty, pos["qty_open"])
    if qty <= 0:
        return 0.0
    pnl = (price - pos["entry"]) * qty
    pos["exits"].append({"date": on, "qty": qty, "price": round(price, 2), "reason": reason, "pnl_inr": round(pnl, 2)})
    pos["qty_open"] -= qty
    pos["realised_inr"] = round(pos["realised_inr"] + pnl, 2)
    return pnl


def _close(led: dict, pos: dict, outcome: str, on: str) -> None:
    pos["status"] = "closed"
    pos["closed"] = on
    pos["outcome"] = outcome
    invested = pos["entry"] * pos["qty"]
    pos["pnl_inr"] = round(pos["realised_inr"], 2)
    pos["pnl_pct"] = round(pos["realised_inr"] / invested * 100, 2) if invested else 0.0
    pos["days_held"] = trading_days_between(pos["opened"], on)
    led["cash_inr"] = round(led["cash_inr"] + invested + pos["realised_inr"], 2)
    led["positions"] = [p for p in led["positions"] if p["pos_id"] != pos["pos_id"]]
    led["closed"].append(pos)


def mark_to_market(led: dict, conf: dict, on: str | None = None, report: dict | None = None) -> list[str]:
    """EOD update: fill pendings at today's open, walk today's bar for stops/targets, apply time stops.

    Returns a list of human-readable events. Updates source confidence in `conf` as outcomes realise.
    Pass `report` to have data availability counted into it: `eligible` positions that should have had a
    bar today, `no_data` fetch failures, `stale` last-bars older than `on`. A run where no_data ==
    eligible > 0 is a data outage, not a quiet day — the caller decides what to do about it.
    """
    on = on or today_str()
    events: list[str] = []
    counts = {"eligible": 0, "no_data": 0, "stale": 0, "marked": 0}
    ex = settings()["exits"]
    hold_thr = settings()["scoring"]["hold_bucket_fund_score"]
    for pos in list(led["positions"]):
        # a pending position dated for a later session isn't due a bar yet, so it can neither be
        # "missing" one nor count as marked — it is simply not part of today's data question
        due = not (pos["status"] == "pending" and pos["opened"] > on)
        counts["eligible"] += 1 if due else 0
        df = prices.history(pos["symbol"], days=120)
        if df is None or df.empty:
            counts["no_data"] += 1 if due else 0
            events.append(f"{pos['symbol']}: no price data today")
            continue
        bar = df.iloc[-1]
        bar_date = str(df.index[-1].date())
        if bar_date != on:
            counts["stale"] += 1 if due else 0
            log.info("%s: last bar %s != %s (holiday or data lag) — skipping", pos["symbol"], bar_date, on)
            continue
        counts["marked"] += 1 if due else 0
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
        srcs = [(pos["source_id"], 1.0)] + [(s, 0.5) for s in pos.get("corroborating_sources", [])]

        # ---- fill pending at the open
        if pos["status"] == "pending":
            if pos["opened"] > on:
                continue
            if o > pos["entry_plan"] * 1.03:
                # gapped >3% above plan: don't chase; cancel
                events.append(f"{pos['symbol']}: CANCELLED — opened {o} vs plan {pos['entry_plan']} (gap > 3%)")
                led["cash_inr"] = round(led["cash_inr"] + pos["capital_inr"], 2)
                led["positions"] = [p for p in led["positions"] if p["pos_id"] != pos["pos_id"]]
                continue
            pos["entry"] = round(o, 2)
            pos["status"] = "open"
            led["cash_inr"] = round(led["cash_inr"] + pos["capital_inr"] - o * pos["qty"], 2)   # true the cash to the actual fill
            pos["capital_inr"] = round(o * pos["qty"], 2)
            pos["deadline"] = str(pd.bdate_range(date.fromisoformat(on), periods=pos["time_stop_days"] + 1)[-1].date())
            # re-anchor SL/targets if fill differs materially from plan (keep the structure levels, but never a stop above fill)
            if pos["stop_loss"] >= o:
                pos["stop_loss"] = round(o * (1 - 0.015), 2)
            events.append(f"{pos['symbol']}: FILLED {pos['qty']} @ {o} (plan {pos['entry_plan']}); SL {pos['stop_loss']}, T {pos['targets']}, deadline {pos['deadline']}")

        if pos["status"] not in ("open", "hold"):
            continue
        pos["max_favourable_pct"] = round(max(pos.get("max_favourable_pct", 0.0), (h / pos["entry"] - 1) * 100), 2)
        pos["ltp"] = c
        pos["unrealised_pct"] = round((c / pos["entry"] - 1) * 100, 2)

        # ---- stop-loss (gap-through fills at open)
        if l <= pos["stop_loss"] and pos["qty_open"] > 0:
            fill = min(o, pos["stop_loss"]) if o < pos["stop_loss"] else pos["stop_loss"]
            _book(pos, pos["qty_open"], fill, "stop_loss", on)
            was_t1 = 1 in pos["targets_hit"]
            outcome = "manual_exit" if was_t1 else "stop_loss"   # a breakeven/trailing stop after T1 is not a failed tip
            _close(led, pos, "trailing_stop" if was_t1 else "stop_loss", on)
            for sid, share in srcs:
                confidence.record_outcome(conf, sid, symbol=pos["symbol"], outcome=outcome, ret_pct=pos["pnl_pct"], share=share)
            events.append(f"{pos['symbol']}: {'TRAILING STOP' if was_t1 else 'STOP-LOSS'} @ {fill} → closed, P&L ₹{pos['pnl_inr']} ({pos['pnl_pct']}%)")
            continue

        # ---- targets (in order; several can hit in one bar)
        fracs = [ex["t1_fraction"], ex["t2_fraction"], ex["t3_fraction"]]
        for i, tgt in enumerate(pos["targets"], start=1):
            if i in pos["targets_hit"] or h < tgt or pos["qty_open"] <= 0:
                continue
            fill = max(o, tgt) if o > tgt else tgt
            qty = int(round(pos["qty"] * fracs[i - 1])) if i < 3 else pos["qty_open"]
            _book(pos, qty, fill, f"t{i}", on)
            pos["targets_hit"].append(i)
            days = trading_days_between(pos["opened"], on)
            for sid, share in srcs:
                confidence.record_outcome(conf, sid, symbol=pos["symbol"], outcome=f"t{i}", ret_pct=(fill / pos["entry"] - 1) * 100, days=days, share=share)
            if i == 1 and ex.get("trail_after_t1") == "breakeven":
                pos["stop_loss"] = max(pos["stop_loss"], round(pos["entry"], 2))
            if i == 2 and ex.get("trail_after_t2") == "t1":
                pos["stop_loss"] = max(pos["stop_loss"], pos["targets"][0])
            events.append(f"{pos['symbol']}: T{i} HIT @ {fill} — booked {qty} sh (+₹{pos['exits'][-1]['pnl_inr']}), SL → {pos['stop_loss']}")
            if pos["qty_open"] <= 0:
                _close(led, pos, "t3", on)
                events.append(f"{pos['symbol']}: ALL TARGETS DONE → closed, P&L ₹{pos['pnl_inr']} ({pos['pnl_pct']}%)")
                break
        if pos["status"] == "closed":
            continue

        # ---- time stop
        if pos["status"] == "open" and pos["deadline"] and on >= pos["deadline"] and 1 not in pos["targets_hit"]:
            if pos["fund_score"] >= hold_thr:
                pos["status"] = "hold"
                pos["notes"].append(f"{on}: time stop reached without T1; fundamentals {pos['fund_score']} ≥ {hold_thr} → moved to HOLD bucket")
                events.append(f"{pos['symbol']}: time stop reached, fundamentals strong → HOLD (capital parked, ₹{pos['capital_inr']})")
                for sid, share in srcs:
                    confidence.record_outcome(conf, sid, symbol=pos["symbol"], outcome="time_stop_gain" if c > pos["entry"] else "time_stop_loss", ret_pct=(c / pos["entry"] - 1) * 100, share=share)
            else:
                _book(pos, pos["qty_open"], c, "time_stop", on)
                outcome = "time_stop_gain" if pos["realised_inr"] > 0 else "time_stop_loss"
                _close(led, pos, outcome, on)
                for sid, share in srcs:
                    confidence.record_outcome(conf, sid, symbol=pos["symbol"], outcome=outcome, ret_pct=pos["pnl_pct"], share=share)
                events.append(f"{pos['symbol']}: TIME STOP (no T1 in {pos['time_stop_days']}d, hot potato) → exited @ {c}, P&L ₹{pos['pnl_inr']} ({pos['pnl_pct']}%)")

    # ---- equity curve
    equity = led["cash_inr"] + sum(p.get("ltp", p.get("entry") or p["entry_plan"]) * p["qty_open"] for p in led["positions"] if p["status"] in ("open", "hold")) \
        + sum(p["capital_inr"] for p in led["positions"] if p["status"] == "pending")
    led["equity_curve"] = [e for e in led["equity_curve"] if e["date"] != on] + [{"date": on, "equity": round(equity, 2)}]
    if report is not None:
        report.update(counts)
    return events


def deployable_cash(led: dict) -> float:
    return max(0.0, led["cash_inr"])


def stats(led: dict) -> dict:
    closed = led["closed"]
    wins = [p for p in closed if p["pnl_inr"] > 0]
    eq = led["equity_curve"][-1]["equity"] if led["equity_curve"] else led["capital_inr"]
    return {
        "capital": led["capital_inr"], "equity": eq, "return_pct": round((eq / led["capital_inr"] - 1) * 100, 2),
        "cash": led["cash_inr"], "open": len([p for p in led["positions"] if p["status"] == "open"]),
        "pending": len([p for p in led["positions"] if p["status"] == "pending"]), "hold": len([p for p in led["positions"] if p["status"] == "hold"]),
        "closed": len(closed), "win_rate": round(len(wins) / len(closed) * 100) if closed else None,
        "avg_win_pct": round(sum(p["pnl_pct"] for p in wins) / len(wins), 2) if wins else None,
        "avg_loss_pct": round(sum(p["pnl_pct"] for p in closed if p["pnl_inr"] <= 0) / max(1, len(closed) - len(wins)), 2) if len(closed) > len(wins) else None,
        "realised_inr": round(sum(p["pnl_inr"] for p in closed), 2),
    }
