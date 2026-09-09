"""The intraday day book — paper trades that live and die inside one session.

Kept in its own file rather than in `state/ledger.json` on purpose. The positional ledger is a
record of a ₹1,00,000 corpus held over weeks; this is a record of positions opened after 09:15 and
closed before 15:10. Mixing them makes both unreadable: an equity curve cannot mean anything if half
its entries are round trips inside a single bar of the other half.

Nothing here is ever hand-edited, and nothing here places an order. A trade is written when the
plan's trigger actually printed on the tape, and settled at the close from the bars — so the record
is what the market did, not what anyone hoped it would do.

state/daybook.json:

    {"notional_inr": 100000,
     "days":   {"2026-09-08": {"candidates": [...], "trades": [...], "settled": true}},
     "closed": [ {date, symbol, event, entry, exit, exit_reason, pnl_inr, r_multiple, ...} ],
     "flows":  [] }
"""
from __future__ import annotations

from ..util import STATE_DIR, now_ist, read_json, settings, today_str, write_json

PATH = STATE_DIR / "daybook.json"


def load() -> dict:
    d = read_json(PATH, None) or {}
    d.setdefault("notional_inr", float(settings().get("intraday", {}).get("notional_inr", 100000)))
    d.setdefault("days", {})
    d.setdefault("closed", [])
    return d


def save(d: dict) -> None:
    write_json(PATH, d)


def day(d: dict, date: str | None = None) -> dict:
    date = date or today_str()
    return d["days"].setdefault(date, {"date": date, "candidates": [], "trades": [], "settled": False})


def record_candidates(d: dict, cands: list[dict], date: str | None = None) -> dict:
    """What the 08:00 run put on the desk. Kept whether or not any of them ever traded, because a
    candidate that was right and never triggered is evidence about the plan, not about the news."""
    rec = day(d, date)
    rec["candidates"] = [{k: c.get(k) for k in
                          ("symbol", "company", "event", "event_label", "catalyst", "verdict",
                           "size_inr_cr", "materiality_ratio", "fund_score", "source_id", "url",
                           "title", "directness", "route", "ltp")} for c in cands]
    return rec


def open_trade(d: dict, *, symbol: str, plan: dict, qty: int, event: dict, date: str | None = None) -> dict | None:
    """Write a trade because the trigger printed. Refuses a second entry in the same name, and
    refuses to exceed the day's position count — two names is already a lot to watch."""
    c = settings().get("intraday", {}) or {}
    rec = day(d, date)
    if any(t["symbol"] == symbol for t in rec["trades"]):
        return None
    live = [t for t in rec["trades"] if t["status"] == "open"]
    if len(live) >= int(c.get("max_positions", 2)):
        return None
    if not qty or not plan.get("trigger"):
        return None
    t = {
        "symbol": symbol, "company": event.get("company"), "date": rec["date"],
        "event": event.get("event"), "event_label": event.get("event_label"),
        "source_id": event.get("source_id"), "catalyst": event.get("catalyst"),
        "entry": plan["trigger"], "entered_at": plan.get("entered_at"),
        "stop": plan["stop"], "targets": plan.get("targets") or [],
        "qty": int(qty), "capital_inr": round(qty * plan["trigger"], 2),
        "risk_inr": round(qty * (plan["trigger"] - plan["stop"]), 2),
        "band": plan.get("band"), "gap_pct": plan.get("gap_pct"), "open": plan.get("open"),
        "status": "open", "exit": None, "exit_reason": None, "pnl_inr": None, "r_multiple": None,
        "opened_at": now_ist().strftime("%Y-%m-%d %H:%M"),
    }
    rec["trades"].append(t)
    return t


def settle_trade(d: dict, symbol: str, *, exit_price: float, reason: str, date: str | None = None,
                 open_to_high_pct: float | None = None, open_to_close_pct: float | None = None) -> dict | None:
    """Close a trade at what the tape actually gave, and move it into the closed list."""
    rec = day(d, date)
    t = next((x for x in rec["trades"] if x["symbol"] == symbol and x["status"] == "open"), None)
    if t is None:
        return None
    risk_per_share = t["entry"] - t["stop"]
    t.update(status="closed", exit=round(float(exit_price), 2), exit_reason=reason,
             pnl_inr=round((float(exit_price) - t["entry"]) * t["qty"], 2),
             return_pct=round((float(exit_price) / t["entry"] - 1) * 100, 2),
             r_multiple=round((float(exit_price) - t["entry"]) / risk_per_share, 2) if risk_per_share > 0 else None,
             open_to_high_pct=open_to_high_pct, open_to_close_pct=open_to_close_pct,
             closed_at=now_ist().strftime("%Y-%m-%d %H:%M"))
    d["closed"] = (d["closed"] + [dict(t)])[-400:]
    return t


def stats(d: dict | None = None) -> dict:
    """The day book's record. Sum of P&L against notional — no compounding, because each day starts
    from the same notional and a day trade never carries capital forward."""
    d = d or load()
    closed = d.get("closed", [])
    notional = float(d.get("notional_inr") or 100000)
    wins = [t for t in closed if (t.get("pnl_inr") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_inr") or 0) <= 0]
    pnl = round(sum(t.get("pnl_inr") or 0 for t in closed), 2)
    rs = [t["r_multiple"] for t in closed if t.get("r_multiple") is not None]
    days = d.get("days", {})
    # grouped from `closed`, the same list every other number here comes from. Reading it off
    # days[].trades instead gave a second source of truth that disagreed with the total.
    by_day: dict[str, float] = {}
    for t in closed:
        date = t.get("date")
        if date:
            by_day[date] = round(by_day.get(date, 0.0) + (t.get("pnl_inr") or 0), 2)
    open_now = [t for r in days.values() for t in r.get("trades", []) if t.get("status") == "open"]
    return {
        "notional_inr": notional,
        "n_trades": len(closed), "n_open": len(open_now),
        "open_symbols": [t["symbol"] for t in open_now],
        "n_wins": len(wins), "n_losses": len(losses),
        "hit_rate": round(len(wins) / len(closed), 3) if closed else None,
        "pnl_inr": pnl, "return_on_notional_pct": round(pnl / notional * 100, 2) if notional else None,
        "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        "best_inr": round(max((t.get("pnl_inr") or 0 for t in closed), default=0), 2),
        "worst_inr": round(min((t.get("pnl_inr") or 0 for t in closed), default=0), 2),
        "avg_win_inr": round(sum(t["pnl_inr"] for t in wins) / len(wins), 2) if wins else None,
        "avg_loss_inr": round(sum(t["pnl_inr"] for t in losses) / len(losses), 2) if losses else None,
        "n_days_traded": len([v for v in by_day.values() if v]),
        "pnl_by_day": dict(sorted(by_day.items())[-30:]),
        "n_candidates_seen": sum(len(r.get("candidates", [])) for r in days.values()),
    }
