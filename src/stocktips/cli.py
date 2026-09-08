"""`python -m stocktips <command>`

  gather            fetch all sources → reports/<date>/tips_raw.json
  structure         merge duplicates → tips_structured.json   (--reviewed FILE to use Claude-corrected tips)
  analyze           TA + fundamentals + scoring → analysis.json
  pick              allocate + book paper positions → picks.json    (--no-book for a dry run)
  book              formalise ONE analysed suggestion into a tracked paper position (book CGPOWER [--capital 25000])
  close             discretionary exit: cancel a pending position or sell an open one (close CGPOWER [--price 940])
  capital           deposit or withdraw capital (capital --add 50000 / --withdraw 20000)
  morning           gather → structure → analyze → pick → reports/<date>/morning.md   (--no-book)
  eod               mark-to-market, update source confidence, machine lessons → reports/<date>/eod.md
  status            one-screen summary of the book and sources
  analyze-symbol    ad-hoc: full TA plan for one NSE symbol  (analyze-symbol TCS --tf monthly)
  add-source        append a source to config/sources.yaml   (add-source --kind telegram --id tg_x --channel x --name "...")
  lesson            append an analyst lesson to state/lessons.md  (lesson "text")
  dashboard-data    write docs/data.json for the static dashboard
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from . import pipeline, report
from .analysis import plan as planmod, ta
from .data import fundamentals, prices
from .learning import confidence, journal
from .portfolio import ledger as ledgermod
from .util import CONFIG_DIR, REPORTS_DIR, ROOT, read_json, settings, today_str, write_json


def _market_closed(day: str) -> str | None:
    from datetime import date as _d
    d = _d.fromisoformat(day)
    if d.weekday() >= 5:
        return "weekend"
    hol = read_json_yaml(CONFIG_DIR / "holidays.yaml").get("holidays", {}).get(d.year, [])
    if any(str(h) == day for h in hol):
        return "NSE holiday"
    return None


def read_json_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def cmd_morning(a):
    closed = _market_closed(today_str())
    if closed and not a.force:
        (pipeline.day_dir() / "morning.md").write_text(f"# {today_str()} — market closed ({closed}); no run.\n", encoding="utf-8")
        print(f"market closed today ({closed}) — nothing to do (use --force to override)")
        return
    raw = pipeline.gather(max_age_hours=a.max_age)
    reviewed = read_json(pipeline.day_dir() / "tips_reviewed.json", None) if not a.skip_review else None
    structured = pipeline.structure(raw, reviewed)
    results = pipeline.analyze(structured)
    picks = pipeline.pick_and_book(results, book=not a.no_book)
    md = report.morning(results, picks, raw)
    (pipeline.day_dir() / "morning.md").write_text(md, encoding="utf-8")
    cmd_dashboard_data(a)
    print(md)


def cmd_gather(a):
    raw = pipeline.gather(max_age_hours=a.max_age)
    n_rev = sum(1 for t in raw["tips"] if t.get("needs_review"))
    print(json.dumps({"tips": len(raw["tips"]), "needs_review": n_rev, "sources": raw["sources"], "file": str(pipeline.day_dir() / "tips_raw.json")}, indent=1))


def cmd_structure(a):
    reviewed = read_json(Path(a.reviewed), None) if a.reviewed else read_json(pipeline.day_dir() / "tips_reviewed.json", None)
    s = pipeline.structure(None, reviewed)
    print(json.dumps([{k: t[k] for k in ("symbol", "source_id", "n_mentions", "src_targets", "src_stop", "extraction_confidence", "needs_review")} for t in s], indent=1))


def cmd_analyze(a):
    r = pipeline.analyze()
    for p in r:
        pl = p["plan"]
        print(f"{p['symbol']:12s} {p['verdict']:10s} comp {p['composite']:3d} TA {p['ta_confidence']:3d} fund {p['fund_score']:3d} src {p['source_confidence']:3d} "
              f"{pl['timeframe']:8s} ltp {p['ltp']:9.2f} SL {pl['stop_loss']:9.2f} T {pl['targets']} rr {pl['reward_risk_t2']}  {p['source_id']}")


def cmd_pick(a):
    raw = read_json(pipeline.day_dir() / "tips_raw.json", {"tips": [], "sources": {}})
    results = read_json(pipeline.day_dir() / "analysis.json", [])
    picks = pipeline.pick_and_book(results, book=not a.no_book)
    md = report.morning(results, picks, raw)
    (pipeline.day_dir() / "morning.md").write_text(md, encoding="utf-8")
    cmd_dashboard_data(a)
    print(md)


def _latest_analysis_day(day: str | None) -> str:
    if day:
        return day
    days = sorted(p.name for p in REPORTS_DIR.iterdir() if p.is_dir() and (p / "analysis.json").exists()) if REPORTS_DIR.exists() else []
    if not days:
        sys.exit("no analysis.json in reports/ — run `analyze` first")
    return days[-1]


def cmd_book(a):
    """Formalise one suggestion into a tracked paper position (what the dashboard's Formalise button asks for)."""
    day = _latest_analysis_day(a.date)
    results = read_json(REPORTS_DIR / day / "analysis.json", [])
    sym = a.symbol.upper()
    cand = next((p for p in results if p["symbol"] == sym), None)
    if cand is None:
        sys.exit(f"{sym} not in reports/{day}/analysis.json — analysed today: {len(results)} names")
    if cand["verdict"] not in ("BUY", "STRONG BUY") and not a.force:
        sys.exit(f"{sym} is {cand['verdict']} (composite {cand['composite']}), not a BUY — use --force to override")
    if not cand["plan"].get("tradeable") and not a.force:
        sys.exit(f"{sym} plan is not tradeable (stop/RR/mandate kill-switch) — use --force to override")

    cfg = settings()
    led = ledgermod.load()
    cap_total = led["capital_inr"]                    # live base, so a capital top-up widens the caps
    max_one = cap_total * cfg["capital"]["max_single_stock_pct"] / 100
    min_one = cap_total * cfg["capital"]["min_allocation_pct"] / 100
    if any(p["symbol"] == sym for p in led["positions"]):
        sys.exit(f"{sym} is already in the book — nothing to do")
    n_live = len([p for p in led["positions"] if p["status"] in ("open", "pending")])
    room = cfg["capital"]["max_open_positions"] - n_live
    if room <= 0 and not a.force:
        sys.exit(f"no room: {n_live} open/pending vs cap {cfg['capital']['max_open_positions']} — close something first")
    cash = ledgermod.deployable_cash(led)
    # default: spread the deployable cash over the free slots (>= the minimum, <= the per-stock cap),
    # so formalising one name doesn't starve the slots left for the rest
    fair_share = max(min_one, cash / max(1, room))
    amt = float(a.capital) if a.capital else min(max_one, fair_share, cash)
    if amt > cash + 1e-6:
        sys.exit(f"only {cash:,.2f} deployable cash, asked for {amt:,.2f}")
    if amt > max_one + 1e-6 and not a.force:
        sys.exit(f"{amt:,.2f} exceeds the {cfg['capital']['max_single_stock_pct']}%/stock cap ({max_one:,.2f})")
    if amt < min_one and not a.force:
        sys.exit(f"{amt:,.2f} is below the {cfg['capital']['min_allocation_pct']}% minimum allocation ({min_one:,.2f}) — deployable cash {cash:,.2f}")

    pos = ledgermod.open_position(led, cand, amt)
    if pos is None:
        sys.exit(f"could not book {sym} (qty would be 0 at entry {cand['plan']['entry']})")
    ledgermod.save(led)
    pl = cand["plan"]
    print(report.order_line(sym, pos["qty"], pl["entry"], pl["stop_loss"], pl["targets"]))
    print(json.dumps({"pos_id": pos["pos_id"], "symbol": sym, "qty": pos["qty"], "capital_inr": pos["capital_inr"],
                      "entry_plan": pos["entry_plan"], "stop_loss": pos["stop_loss"], "targets": pos["targets"],
                      "timeframe": pos["timeframe"], "bucket": pos["bucket"], "fills_at_open_on": pos["opened"],
                      "cash_after": led["cash_inr"], "from_analysis": day}, indent=1))
    if not a.no_dashboard:
        cmd_dashboard_data(a)


def cmd_close(a):
    """The analyst's own exit — freeing capital for a better idea is a decision, not a rule."""
    led = ledgermod.load()
    conf = confidence.load()
    try:
        pos, event = ledgermod.close_position(led, conf, a.symbol, price=a.price, note=a.note)
    except (KeyError, ValueError) as e:
        sys.exit(str(e))
    ledgermod.save(led)
    confidence.save(conf)
    print(event)
    print(json.dumps({"symbol": pos["symbol"], "outcome": pos["outcome"], "qty": pos["qty"],
                      "entry": pos.get("entry"), "exit": (pos["exits"][-1]["price"] if pos.get("exits") else None),
                      "pnl_inr": pos.get("pnl_inr"), "pnl_pct": pos.get("pnl_pct"),
                      "cash_after": led["cash_inr"], "slots_open": len([p for p in led["positions"] if p["status"] in ("open", "pending")])}, indent=1))
    if not a.no_dashboard:
        cmd_dashboard_data(a)


def cmd_capital(a):
    """Move the capital base. Recorded as a dated ledger event so the return stays honest."""
    amount = (a.add or 0) - (a.withdraw or 0)
    if not amount:
        sys.exit("pass --add or --withdraw with a rupee amount")
    led = ledgermod.load()
    before = (led["capital_inr"], led["cash_inr"])
    try:
        ev = ledgermod.cash_flow(led, amount, note=a.note)
    except ValueError as e:
        sys.exit(str(e))
    ledgermod.save(led)
    st = ledgermod.stats(led)
    print(f"capital ₹{before[0]:,.2f} → ₹{led['capital_inr']:,.2f}")
    print(f"cash    ₹{before[1]:,.2f} → ₹{led['cash_inr']:,.2f}")
    print(f"ledger event: {ev['date']} {ev['note']} ₹{abs(amount):,.2f}")
    print(f"per-stock cap now ₹{led['capital_inr'] * settings()['capital']['max_single_stock_pct'] / 100:,.2f}"
          f" · time-weighted return {st['return_pct']}%")
    if not a.no_dashboard:
        cmd_dashboard_data(a)


def cmd_eod(a):
    closed = _market_closed(a.date or today_str())
    if closed and not a.force:
        (pipeline.day_dir(a.date) / "eod.md").write_text(f"# {a.date or today_str()} — market closed ({closed}); no run.\n", encoding="utf-8")
        print(f"market closed ({closed}) — nothing to do (use --force to override)")
        return
    led = ledgermod.load()
    conf_before = json.loads(json.dumps(confidence.load()))
    conf = confidence.load()
    data_report: dict = {}
    events = ledgermod.mark_to_market(led, conf, on=a.date, report=data_report)
    ledgermod.save(led)
    confidence.save(conf)
    lessons = journal.pattern_stats(led["closed"])
    if events and any(k in " ".join(events) for k in ("HIT", "STOP", "TIME", "HOLD")):
        journal.append("Events: " + " | ".join(e for e in events if any(k in e for k in ("HIT", "STOP", "TIME", "HOLD"))) + "\n\n" + lessons, kind="machine")
    md = report.eod(events, led, conf_before, conf, lessons)
    (pipeline.day_dir(a.date) / "eod.md").write_text(md, encoding="utf-8")
    cmd_dashboard_data(a)
    print(md)
    # A run that could not price a single position is an outage, not a quiet day. Say so and exit
    # non-zero so the scheduled run shows red instead of a green "nothing happened in the book today".
    if data_report.get("eligible") and data_report["no_data"] == data_report["eligible"]:
        sys.exit(f"DATA OUTAGE: no price data for any of the {data_report['eligible']} position(s) due a bar on "
                 f"{a.date or today_str()} — nothing was marked to market, the ledger is unchanged, and the report "
                 f"above says 'quiet day' only because there was nothing to read. Check network access to the price "
                 f"source before trusting the next run.")


def cmd_status(a):
    led = ledgermod.load()
    print(json.dumps(ledgermod.stats(led), indent=1))
    for p in led["positions"]:
        print(f"  {p['symbol']:12s} {p['status']:8s} entry {p.get('entry') or p['entry_plan']} qty {p['qty_open']}/{p['qty']} SL {p['stop_loss']} T {p['targets']} hit {p['targets_hit']} deadline {p.get('deadline')} {p['bucket']}")
    print("\nsources:")
    for s in confidence.summary(confidence.load())[:25]:
        print(f"  {s['source_id']:34s} conf {s['confidence']:3d} score {s['score']:+6.1f} tips {s['n_tips']:3d} resolved {s['n_resolved']:3d} T1% {s['t1_hit_rate']} exp% {s['expectancy_pct']}")


def cmd_analyze_symbol(a):
    df = prices.history(a.symbol)
    if df is None:
        sys.exit(f"no data for {a.symbol}")
    snap = ta.analyze(df)
    pl = planmod.build_plan(snap, a.tf)
    f = fundamentals.fetch(a.symbol)
    fs, why = fundamentals.score(f)
    print(json.dumps({"symbol": a.symbol, "ta": {k: v for k, v in snap.items() if k not in ("resistances", "supports")}, "resistances": snap["resistances"], "supports": snap["supports"],
                      "plan": pl, "fund_score": fs, "fund_why": why, "fundamentals": f}, indent=1, default=str))


def cmd_add_source(a):
    path = CONFIG_DIR / "sources.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if any(s["id"] == a.id for s in cfg["sources"]):
        sys.exit(f"source {a.id} already exists")
    src = {"id": a.id, "name": a.name or a.id, "kind": a.kind, "category": a.category, "enabled": True}
    for k in ("url", "query", "publisher", "channel", "handle", "clause", "link_pattern", "default_timeframe"):
        v = getattr(a, k, None)
        if v:
            src[k] = v
    cfg["sources"].append(src)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    conf = confidence.load()
    confidence.ensure(conf, a.id)
    confidence.save(conf)
    print(f"added {a.id} ({a.kind}) at confidence 0")


def cmd_lesson(a):
    journal.append(a.text, kind="analyst")
    print("lesson recorded")


ANALYSIS_FIELDS = ("symbol", "company", "verdict", "composite", "ta_confidence", "fund_score", "source_confidence",
                   "ltp", "plan", "source_id", "bucket", "tip_id", "n_mentions", "src_entry", "src_targets", "src_stop",
                   "corroborating_sources", "brokerages", "fund_why")
TA_FIELDS = ("trend", "rsi", "adx", "atr_pct", "vol_ratio", "chg_5d_pct", "chg_20d_pct", "dist_52w_high_pct",
             "dist_ema20_pct", "patterns", "avg_turnover_cr", "last_bar_date")


def _pos_for_dashboard(pos: dict) -> dict:
    """Ledger position + the derived levels the dashboard shows (never written back to state/)."""
    d = dict(pos)
    base = d.get("entry") or d.get("entry_plan")
    if base:
        if d.get("stop_loss") is not None:
            d["stop_loss_pct"] = round((d["stop_loss"] / base - 1) * 100, 2)
        d["target_pct"] = [round((t / base - 1) * 100, 2) for t in (d.get("targets") or [])]
        d["order_line"] = report.order_line(d["symbol"], d.get("qty_open") or d.get("qty") or 0, base, d.get("stop_loss") or 0.0, d.get("targets") or [])
    return d


def cmd_dashboard_data(a):
    led = ledgermod.load()
    conf = confidence.summary(confidence.load())
    days = sorted([p.name for p in REPORTS_DIR.iterdir() if p.is_dir()]) if REPORTS_DIR.exists() else []
    latest = read_json(REPORTS_DIR / days[-1] / "picks.json", {}) if days else {}
    analysis = read_json(REPORTS_DIR / days[-1] / "analysis.json", []) if days else []
    cfg = settings()
    cap = cfg["capital"]
    n_live = len([p for p in led["positions"] if p["status"] in ("open", "pending")])
    cash = ledgermod.deployable_cash(led)
    data = {"generated": today_str(), "stats": ledgermod.stats(led),
            "positions": [_pos_for_dashboard(p) for p in led["positions"]],
            "closed": led["closed"][-50:], "equity_curve": led["equity_curve"],
            "sources": conf, "latest_picks": latest,
            "latest_analysis": [dict({k: p.get(k) for k in ANALYSIS_FIELDS},
                                     ta={k: (p.get("ta") or {}).get(k) for k in TA_FIELDS},
                                     urls=(p.get("urls") or [])[:2]) for p in analysis],
            "analysis_day": days[-1] if days else None,
            "cash_flows": led.get("cash_flows", []),
            "book": {"max_open_positions": cap["max_open_positions"], "open_or_pending": n_live,
                     "slots_left": max(0, cap["max_open_positions"] - n_live), "deployable_cash": cash,
                     "capital_inr": led["capital_inr"],
                     "min_alloc_inr": round(led["capital_inr"] * cap["min_allocation_pct"] / 100, 2),
                     "max_alloc_inr": round(led["capital_inr"] * cap["max_single_stock_pct"] / 100, 2),
                     "min_allocation_pct": cap["min_allocation_pct"], "max_single_stock_pct": cap["max_single_stock_pct"]},
            "report_days": days[-60:], "lessons_tail": journal.tail(4000),
            "settings": {k: settings()[k] for k in ("capital", "mandate", "risk", "exits", "scoring")}}
    write_json(ROOT / "docs" / "data.json", data)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stocktips", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("morning"); p.add_argument("--no-book", action="store_true"); p.add_argument("--skip-review", action="store_true"); p.add_argument("--max-age", type=float, default=36); p.add_argument("--force", action="store_true", help="run even on a weekend/holiday"); p.set_defaults(fn=cmd_morning)
    p = sub.add_parser("gather"); p.add_argument("--max-age", type=float, default=36); p.set_defaults(fn=cmd_gather)
    p = sub.add_parser("structure"); p.add_argument("--reviewed"); p.set_defaults(fn=cmd_structure)
    p = sub.add_parser("analyze"); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("pick"); p.add_argument("--no-book", action="store_true"); p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("book"); p.add_argument("symbol"); p.add_argument("--capital", type=float, default=None, help="rupees to deploy (default: deployable cash split over the free slots, capped per stock)"); p.add_argument("--date", default=None, help="report day whose analysis.json to book from (default: latest)"); p.add_argument("--force", action="store_true", help="override verdict / cap / slot checks"); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_book)
    p = sub.add_parser("close"); p.add_argument("symbol"); p.add_argument("--price", type=float, default=None, help="exit price (default: last close)"); p.add_argument("--note", default=None, help="why you exited — goes in the position notes"); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_close)
    p = sub.add_parser("capital"); p.add_argument("--add", type=float, default=None); p.add_argument("--withdraw", type=float, default=None); p.add_argument("--note", default=None); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_capital)
    p = sub.add_parser("eod"); p.add_argument("--date", default=None); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_eod)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("analyze-symbol"); p.add_argument("symbol"); p.add_argument("--tf", default="weekly"); p.set_defaults(fn=cmd_analyze_symbol)
    p = sub.add_parser("add-source")
    for k in ("id", "kind"):
        p.add_argument("--" + k, required=True)
    for k in ("name", "url", "query", "publisher", "channel", "handle", "clause", "link_pattern", "default_timeframe"):
        p.add_argument("--" + k.replace("_", "-"), dest=k)
    p.add_argument("--category", default="tipster"); p.set_defaults(fn=cmd_add_source)
    p = sub.add_parser("lesson"); p.add_argument("text"); p.set_defaults(fn=cmd_lesson)
    p = sub.add_parser("dashboard-data"); p.set_defaults(fn=cmd_dashboard_data)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    a.fn(a)


if __name__ == "__main__":
    main()
