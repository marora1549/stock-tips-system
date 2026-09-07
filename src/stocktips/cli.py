"""`python -m stocktips <command>`

  gather            fetch all sources → reports/<date>/tips_raw.json
  structure         merge duplicates → tips_structured.json   (--reviewed FILE to use Claude-corrected tips)
  analyze           TA + fundamentals + scoring → analysis.json
  pick              allocate + book paper positions → picks.json    (--no-book for a dry run)
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
    reviewed = read_json(a.reviewed, None) if a.reviewed else read_json(pipeline.day_dir() / "tips_reviewed.json", None)
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


def cmd_eod(a):
    closed = _market_closed(a.date or today_str())
    if closed and not a.force:
        (pipeline.day_dir(a.date) / "eod.md").write_text(f"# {a.date or today_str()} — market closed ({closed}); no run.\n", encoding="utf-8")
        print(f"market closed ({closed}) — nothing to do (use --force to override)")
        return
    led = ledgermod.load()
    conf_before = json.loads(json.dumps(confidence.load()))
    conf = confidence.load()
    events = ledgermod.mark_to_market(led, conf, on=a.date)
    ledgermod.save(led)
    confidence.save(conf)
    lessons = journal.pattern_stats(led["closed"])
    if events and any(k in " ".join(events) for k in ("HIT", "STOP", "TIME", "HOLD")):
        journal.append("Events: " + " | ".join(e for e in events if any(k in e for k in ("HIT", "STOP", "TIME", "HOLD"))) + "\n\n" + lessons, kind="machine")
    md = report.eod(events, led, conf_before, conf, lessons)
    (pipeline.day_dir(a.date) / "eod.md").write_text(md, encoding="utf-8")
    cmd_dashboard_data(a)
    print(md)


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


def cmd_dashboard_data(a):
    led = ledgermod.load()
    conf = confidence.summary(confidence.load())
    days = sorted([p.name for p in REPORTS_DIR.iterdir() if p.is_dir()]) if REPORTS_DIR.exists() else []
    latest = read_json(REPORTS_DIR / days[-1] / "picks.json", {}) if days else {}
    analysis = read_json(REPORTS_DIR / days[-1] / "analysis.json", []) if days else []
    data = {"generated": today_str(), "stats": ledgermod.stats(led), "positions": led["positions"], "closed": led["closed"][-50:], "equity_curve": led["equity_curve"],
            "sources": conf, "latest_picks": latest, "latest_analysis": [{k: p[k] for k in ("symbol", "company", "verdict", "composite", "ta_confidence", "fund_score", "source_confidence", "ltp", "plan", "source_id", "bucket")} for p in analysis],
            "report_days": days[-60:], "lessons_tail": journal.tail(4000), "settings": {k: settings()[k] for k in ("capital", "mandate", "risk", "exits", "scoring")}}
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
