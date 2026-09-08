"""`python -m stocktips <command>`

  gather            fetch all sources → reports/<date>/tips_raw.json
  add-tip           log a tip you were sent by hand (add-tip --source manual:mohan --symbol TATASTEEL ...)
  import-tips       paste a Markets Mojo table or call panel → tips (import-tips --file paste.txt)
  contenders        rank every analysed idea head to head → the final top 3
  structure         merge duplicates → tips_structured.json   (--reviewed FILE to use Claude-corrected tips)
  analyze           TA + fundamentals + scoring → analysis.json
  pick              allocate + book paper positions → picks.json    (--no-book for a dry run)
  book              formalise ONE analysed suggestion into a tracked paper position (book CGPOWER [--capital 25000])
  close             discretionary exit: cancel a pending position or sell an open one (close CGPOWER [--price 940])
  capital           deposit or withdraw capital (capital --add 50000 / --withdraw 20000)
  morning           gather → structure → analyze → pick → reports/<date>/morning.md   (--no-book)
  preopen           08:00: overnight corporate news → catalyst scores → reports/<date>/preopen.md
  intraday          session check: the real gap and opening range  (--close to settle and grade)
  read              score one story you found yourself (read --url ... / --text ... [--add])
  daybook           the intraday record, and what each kind of news has been worth
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
from .analysis import contenders, plan as planmod, scoring, ta
from .data import fundamentals, prices, sparks, symbols
from .learning import confidence, eventscore, journal
from .portfolio import daybook
from .sources import mojo
from .portfolio import ledger as ledgermod
from .util import (CONFIG_DIR, REPORTS_DIR, ROOT, STATE_DIR, now_ist, read_json, settings, short_hash,
                   today_str, write_json)


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


def _tip_record(*, source, symbol, company, action="buy", entry=None, targets=(), stop=None,
                timeframe="weekly", text=None, url=None, extracted_by="manual",
                extraction_confidence=0.9, symbol_confidence=1.0, symbol_method="manual", published=None):
    """One tip in the shape `structure`/`analyze` expect, whoever it came from.

    The source's entry, targets and stop are recorded as claims. Nothing downstream treats them as
    levels — `build_plan` reads the chart and only glances at them.
    """
    tgt = sorted(float(t) for t in targets if t)
    return {
        "id": short_hash(f"{source}|{symbol}|{tgt}|{today_str()}"), "source_id": source, "brokerage": None,
        "url": url or "", "title": (text or "")[:120],
        "published": published or now_ist().strftime("%a, %d %b %Y %H:%M:%S %z"),
        "company": company, "symbol": symbol,
        "symbol_confidence": symbol_confidence, "symbol_method": symbol_method,
        "action": action, "src_entry": entry, "src_entry_hi": None, "src_targets": tgt,
        "src_stop": stop, "src_upside_pct": None, "src_duration": timeframe,
        "default_timeframe": timeframe, "sentence": text or f"{action} {symbol}",
        "extracted_by": extracted_by, "extraction_confidence": extraction_confidence, "needs_review": False,
    }


def cmd_add_tip(a):
    """A tip from WhatsApp, Telegram, a friend, a screenshot — logged so its source gets graded too.

    Manual sources start at confidence 0 like every other source and earn their weight from outcomes;
    a tip from the desk owner gets no bonus for being his.
    """
    master = symbols.master()
    sym, sym_conf, how = master.resolve(a.symbol)
    if sym is None:
        sys.exit(f"could not resolve {a.symbol!r} to an NSE symbol ({how}) — check the spelling, or watch for a "
                 f"demerger/rename (Tata Motors → TMCV/TMPV, Zomato → ETERNAL). Not guessing.")
    if sym != a.symbol.upper():
        print(f"resolved {a.symbol!r} → {sym} ({how}, {sym_conf:.2f})")
    day = pipeline.day_dir()
    path = day / "tips_raw.json"
    raw = read_json(path, None) or {"date": today_str(), "sources": {}, "tips": [], "docs": []}
    if any(t["symbol"] == sym and t["source_id"] == a.source for t in raw["tips"]):
        log.warning("%s from %s is already in today's tips — adding a second entry", sym, a.source)
    targets = [float(x) for x in (a.target or "").replace(" ", "").split(",") if x] if a.target else []
    tip = _tip_record(source=a.source, symbol=sym, company=a.company or master.name_of(sym), action=a.action,
                      entry=a.entry, targets=targets, stop=a.stop, timeframe=a.timeframe, text=a.text,
                      url=a.url, extracted_by="manual", symbol_method="manual:" + how)
    raw["tips"].append(tip)
    raw["sources"][a.source] = raw["sources"].get(a.source, 0) + 1
    write_json(path, raw)
    conf = confidence.load()
    confidence.ensure(conf, a.source)
    confidence.save(conf)
    print(tip["id"])
    print(json.dumps({"tip_id": tip["id"], "symbol": sym, "company": tip["company"], "source_id": a.source,
                      "src_targets": tip["src_targets"], "src_stop": a.stop, "timeframe": a.timeframe,
                      "file": str(path), "tips_today": len(raw["tips"]),
                      "source_confidence": confidence.display(conf[a.source]["score"])}, indent=1))


def cmd_import_tips(a):
    """Paste a Markets Mojo screen — the table or one call's panel — and let it become tips.

    Nothing about it is trusting: the names are matched against the NSE master offline, a name that
    could be two companies is **skipped with its candidates** rather than guessed, and Mojo's own
    entry/target/stop are filed as claims. Their Sell calls are logged so the source still gets
    graded on them, but `structure` drops non-buy calls, so a short can never reach the book.
    """
    text = a.text
    if a.file:
        text = Path(a.file).read_text(encoding="utf-8", errors="replace")
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not (text or "").strip():
        sys.exit("nothing to import — pass --text, --file, or pipe the paste in on stdin")

    rows = mojo.parse(text)
    if not rows:
        sys.exit("could not read a single call out of that paste — the Markets Mojo table (name, Buy/Sell, "
                 "call type, then the eleven columns) or one call's detail panel are the two shapes it knows")

    master = symbols.master()
    day = pipeline.day_dir()
    path = day / "tips_raw.json"
    raw = read_json(path, None) or {"date": today_str(), "sources": {}, "tips": [], "docs": []}
    existing = {(t["symbol"], t["source_id"], tuple(t.get("src_targets") or [])) for t in raw["tips"]}

    imported, duplicates, skipped, logged_only = [], [], [], []
    for row in rows:
        name = row["company_raw"]
        if not name and a.symbol:
            name = a.symbol
        hit = mojo.resolve_name(name, master)
        if not hit["symbol"]:
            skipped.append({"name": name or "(no name in the paste)", "reason": hit["method"],
                            "entry": row["src_entry"], "target": (row["src_targets"] or [None])[0],
                            "candidates": hit["candidates"][:4]})
            continue
        sym = hit["symbol"]
        key = (sym, a.source, tuple(sorted(row["src_targets"])))
        if key in existing:
            duplicates.append(sym)
            continue
        sentence = (f"{row['action']} {sym} · {row['call_type'] or row['timeframe']} · their entry "
                    f"₹{row['src_entry']:,.2f}, target ₹{(row['src_targets'] or [0])[0]:,.2f}"
                    + (f", stop ₹{row['src_stop']:,.2f}" if row["src_stop"] else "")
                    + (f" · called {row['entry_date']}" if row["entry_date"] else ""))
        tip = _tip_record(source=a.source, symbol=sym, company=hit["company"], action=row["action"],
                          entry=row["src_entry"], targets=row["src_targets"], stop=row["src_stop"],
                          timeframe=row["timeframe"], text=sentence, url=a.url,
                          extracted_by="mojo", extraction_confidence=round(min(0.9, hit["confidence"]), 3),
                          symbol_confidence=hit["confidence"], symbol_method="mojo:" + hit["method"])
        tip["src_claim"] = {k: row[k] for k in ("performance_pct", "returns_till_target_pct", "days_since",
                                               "entry_date", "sector", "mcap", "direction", "call_type")}
        if row["action"] != "buy":
            logged_only.append(sym)
        if not a.dry_run:
            raw["tips"].append(tip)
            raw["sources"][a.source] = raw["sources"].get(a.source, 0) + 1
            existing.add(key)
        imported.append({"symbol": sym, "company": hit["company"], "action": row["action"],
                         "confidence": hit["confidence"], "method": hit["method"],
                         "src_entry": row["src_entry"], "src_target": (row["src_targets"] or [None])[0],
                         "src_stop": row["src_stop"], "id": None if a.dry_run else tip["id"]})

    if not a.dry_run and imported:
        write_json(path, raw)
        conf = confidence.load()
        confidence.ensure(conf, a.source)          # starts at 0 like every other source
        confidence.save(conf)

    out = {"source_id": a.source, "rows_read": len(rows), "imported": imported,
           "duplicates": duplicates, "skipped": skipped,
           "logged_not_bookable": logged_only, "dry_run": bool(a.dry_run),
           "file": None if a.dry_run else str(path), "tips_today": len(raw["tips"])}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    if skipped:
        print(f"\n{len(skipped)} row(s) need a name I will not guess at:", file=sys.stderr)
        for sk in skipped:
            cands = ", ".join(f"{c['symbol']} ({c['company']})" for c in sk["candidates"]) or "no close match"
            print(f"  {sk['name']}: {sk['reason']} — candidates: {cands}", file=sys.stderr)
        print("  re-run one of these with: add-tip --source " + a.source + " --symbol <SYMBOL> ...", file=sys.stderr)
    if logged_only:
        print(f"\nlogged but never bookable (this desk is long-only): {', '.join(logged_only)}", file=sys.stderr)


def cmd_contenders(a):
    """The head-to-head: every analysed idea ranked against every other, top few named."""
    day = a.date or (sorted(p.name for p in REPORTS_DIR.iterdir() if p.is_dir())[-1] if REPORTS_DIR.exists() else today_str())
    results = read_json(REPORTS_DIR / day / "analysis.json", [])
    if not results:
        sys.exit(f"no analysis.json for {day} — run analyze first")
    led = ledgermod.load()
    held = {p["symbol"] for p in led["positions"] if p["status"] in ("open", "pending")}
    top = contenders.rank([_suggestion(r) for r in results], n=a.top, held=held)
    print(json.dumps({"day": day, "ideas_considered": len(results), "contenders": top}, indent=1, ensure_ascii=False))


def cmd_preopen(a):
    """The 08:00 run: read overnight corporate news and say what to do about it before the open.

    Its output is an email, so the report's first line has to stand alone — that may be all that
    gets read on a phone at eight in the morning.
    """
    closed = _market_closed(today_str())
    if closed and not a.force:
        print(f"market closed today ({closed}) — nothing opens, so there is nothing to be early for")
        return
    day = a.date or now_ist().date().isoformat()
    raw = None if a.refresh else read_json(pipeline.day_dir(day) / "news_raw.json", None)
    if raw is None:
        raw = pipeline.gather_news(max_age_hours=a.max_age)
    card = pipeline.preopen(raw, limit=a.limit, date=day)
    md = report.preopen(card)
    (pipeline.day_dir(day) / "preopen.md").write_text(md, encoding="utf-8")
    book = daybook.load()
    daybook.record_candidates(book, card.get("trade", []))
    daybook.save(book)
    if not a.no_dashboard:
        cmd_dashboard_data(a)
    print(md)


def cmd_intraday(a):
    """The session runs: 09:35 for the opening range, midday for the trail, 15:20 to settle."""
    if a.close:
        out = pipeline.intraday_close(date=a.date)
        if not a.no_dashboard:
            cmd_dashboard_data(a)
        print(json.dumps({"date": out["date"], "exits": out["exits"],
                          "graded": len(out["graded"]), "book": out["book"]}, indent=1))
        return
    card = pipeline.intraday_watch(date=a.date)
    if card.get("error"):
        sys.exit(card["error"])
    md = report.intraday(card)
    (pipeline.day_dir(a.date) / "intraday.md").write_text(md, encoding="utf-8")
    if not a.no_dashboard:
        cmd_dashboard_data(a)
    print(md)


def cmd_daybook(a):
    """The intraday record: what it has actually made, and what each kind of news has been worth."""
    book = daybook.load()
    print(json.dumps({"stats": daybook.stats(book),
                      "event_classes": eventscore.summary(eventscore.load()),
                      "recent": book.get("closed", [])[-8:]}, indent=1))


def cmd_read(a):
    """Score one story you found yourself — the path for the article read too late.

    Same extractor, same beneficiary map, same catalyst score as the 08:00 run, so the answer sits
    beside that run's rather than being a second opinion arrived at differently.
    """
    text = a.text
    if a.file:
        text = Path(a.file).read_text(encoding="utf-8", errors="replace")
    if not text and not a.url and not sys.stdin.isatty():
        text = sys.stdin.read()
    story = pipeline.read_one_story(text=text, url=a.url, title=a.title, published=a.published,
                                   source_id=a.source, date=a.date)
    if story.get("error") and not story.get("candidates"):
        sys.exit(story["error"])
    print(report.one_story(story))
    if a.add:
        res = pipeline.add_to_preopen(story, date=a.date)
        if res.get("error"):
            print("\n" + res["error"], file=sys.stderr)
        else:
            print("\nadded to " + res["date"] + ": " + (", ".join(res["added"]) or "nothing scored high enough"))
            if not a.no_dashboard:
                cmd_dashboard_data(a)


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
                   "corroborating_sources", "brokerages", "fund_why", "tags")
TA_FIELDS = ("trend", "rsi", "adx", "atr_pct", "vol_ratio", "chg_5d_pct", "chg_20d_pct", "dist_52w_high_pct",
             "dist_ema20_pct", "patterns", "avg_turnover_cr", "last_bar_date", "momentum_score", "drift_pct_day",
             "efficiency", "amplitude_pct_day", "up_day_share")


def _suggestion(p: dict) -> dict:
    """One analysed candidate, shaped for the page.

    Tags are recomputed here rather than only read, so a record written before tags existed still
    arrives labelled — the momentum tags simply stay absent until there is a pace to measure.
    """
    ta_snap = {k: (p.get("ta") or {}).get(k) for k in TA_FIELDS}
    out = {k: p.get(k) for k in ANALYSIS_FIELDS}
    out["ta"] = ta_snap
    out["urls"] = (p.get("urls") or [])[:2]
    if not out.get("tags"):
        out["tags"] = scoring.tags(p.get("plan") or {}, p.get("ta") or {}, p.get("fund_score") or 0,
                                   p.get("n_mentions") or 1, len(p.get("corroborating_sources") or []))
    return out


def _pos_for_dashboard(pos: dict, on: str | None = None) -> dict:
    """Ledger position + the derived numbers the dashboard shows (never written back to state/)."""
    d = dict(pos)
    base = d.get("entry") or d.get("entry_plan")
    if base:
        if d.get("stop_loss") is not None:
            d["stop_loss_pct"] = round((d["stop_loss"] / base - 1) * 100, 2)
        d["target_pct"] = [round((t / base - 1) * 100, 2) for t in (d.get("targets") or [])]
        d["order_line"] = report.order_line(d["symbol"], d.get("qty_open") or d.get("qty") or 0, base,
                                            d.get("stop_loss") or 0.0, d.get("targets") or [])
        # how far along the road to T1 it actually is, and whether it is keeping to its own timetable
        t1 = (d.get("targets") or [None])[0]
        ltp = d.get("ltp")
        if t1 and ltp and t1 > base:
            d["progress_t1_pct"] = max(0, min(100, round((ltp - base) / (t1 - base) * 100)))
        if d.get("status") in ("open", "hold") and d.get("opened"):
            elapsed = ledgermod.trading_days_between(d["opened"], on or today_str())
            d["days_elapsed"] = elapsed
            eta = (d.get("eta_days") or [None])[0]
            if eta:
                d["eta_t1_days"] = eta
                d["pace"] = ("hit" if 1 in (d.get("targets_hit") or [])
                             else "behind" if elapsed > eta else "on-track")
                d["days_left_on_eta"] = eta - elapsed
    return d


def _intraday_for_dashboard(cand: dict, session: dict) -> dict:
    """One pre-open candidate, married to whatever the session has since made of it."""
    keys = ("symbol", "company", "event", "event_label", "catalyst", "verdict", "verdict_note",
            "size_inr_cr", "size_estimated", "size_basis", "materiality_ratio", "revenue_ttm_cr",
            "fund_score", "fund_why", "source_id", "corroborating_sources", "url", "title",
            "published", "directness", "route", "why_this_name", "theme", "ltp", "ta",
            "fundamentals", "freshness", "class_score", "plan", "certainty", "n_reports")
    out = {k: cand.get(k) for k in keys}
    out["catalyst_reasons"] = cand.get("reasons") or []
    live = next((c for c in (session.get("candidates") or []) if c.get("symbol") == cand["symbol"]), None)
    if live:
        out["session"] = {k: live.get(k) for k in
                          ("state", "band", "band_rule", "gap_pct", "open", "prev_close", "vwap",
                           "last", "day_high", "day_low", "from_open_pct", "opening_range",
                           "or_volume_multiple", "acts", "why_not", "watch", "trigger", "stop",
                           "stop_pct", "stop_note", "targets", "target_pct", "target_basis",
                           "reward_risk_t2", "targets_hit", "triggered", "stopped", "entered_at",
                           "stopped_at", "max_favourable_pct", "size", "order_line", "reasons")}
    return out


def cmd_dashboard_data(a):
    led = ledgermod.load()
    conf = confidence.summary(confidence.load())
    spark_cache = sparks.load()
    days = sorted([p.name for p in REPORTS_DIR.iterdir() if p.is_dir()]) if REPORTS_DIR.exists() else []
    latest = read_json(REPORTS_DIR / days[-1] / "picks.json", {}) if days else {}
    analysis = read_json(REPORTS_DIR / days[-1] / "analysis.json", []) if days else []
    cfg = settings()
    cap = cfg["capital"]
    n_live = len([p for p in led["positions"] if p["status"] in ("open", "pending")])
    live = {p["symbol"] for p in led["positions"] if p["status"] in ("open", "pending")}
    cash = ledgermod.deployable_cash(led)
    # rank the same records the page shows, so a contender carries the tags its idea card carries
    suggestions = [_suggestion(p) for p in analysis]
    # the intraday desk's own payload: today's card, the session state, and the trained brain
    intra_day = None
    for d in reversed(days[-6:]):
        if (REPORTS_DIR / d / "preopen.json").exists():
            intra_day = d
            break
    pre = read_json(REPORTS_DIR / intra_day / "preopen.json", {}) if intra_day else {}
    session = read_json(REPORTS_DIR / intra_day / "intraday.json", {}) if intra_day else {}
    book = daybook.load()
    classes = eventscore.load()

    data = {"generated": today_str(), "stats": ledgermod.stats(led),
            "positions": [_pos_for_dashboard(p) for p in led["positions"]],
            "sparks": {sym: sparks.series(spark_cache, sym) for sym in
                       {p["symbol"] for p in led["positions"]} |
                       {p["symbol"] for p in analysis[:40] if p.get("verdict") in ("BUY", "STRONG BUY")}
                       if sparks.series(spark_cache, sym)},
            "actions_log": (read_json(STATE_DIR / "actions_log.json", {}).get("runs") or [])[-12:],
            "closed": led["closed"][-50:], "equity_curve": led["equity_curve"],
            "sources": conf, "latest_picks": latest,
            "latest_analysis": suggestions,
            "contenders": contenders.rank(suggestions, n=3, held=live),
            "analysis_day": days[-1] if days else None,
            "cash_flows": led.get("cash_flows", []),
            "book": {"max_open_positions": cap["max_open_positions"], "open_or_pending": n_live,
                     "slots_left": max(0, cap["max_open_positions"] - n_live), "deployable_cash": cash,
                     "capital_inr": led["capital_inr"],
                     "min_alloc_inr": round(led["capital_inr"] * cap["min_allocation_pct"] / 100, 2),
                     "max_alloc_inr": round(led["capital_inr"] * cap["max_single_stock_pct"] / 100, 2),
                     "min_allocation_pct": cap["min_allocation_pct"], "max_single_stock_pct": cap["max_single_stock_pct"]},
            "intraday": {
                "day": intra_day,
                "generated_at": pre.get("generated_at"),
                "checked_at": session.get("checked_at"),
                "events_read": pre.get("events_read", 0),
                "wires": pre.get("sources", {}),
                "trade": [_intraday_for_dashboard(c, session) for c in (pre.get("trade") or [])],
                "watch": [_intraday_for_dashboard(c, session) for c in (pre.get("watch") or [])],
                "avoid": [{k: c.get(k) for k in ("symbol", "company", "event_label", "title", "url",
                                                 "source_id", "catalyst", "verdict_note")}
                          for c in (pre.get("avoid") or [])],
                "skipped": (pre.get("skipped") or [])[:20],
                "trades": session.get("trades") or [],
                "stats": daybook.stats(book),
                "closed": (book.get("closed") or [])[-30:],
                "event_classes": eventscore.summary(classes),
                "settings": pre.get("settings") or {k: (settings().get("intraday", {}) or {}).get(k)
                                                    for k in ("gap_modest_pct", "gap_wide_pct",
                                                              "max_stop_pct", "force_flat_at",
                                                              "notional_inr", "risk_per_trade_pct",
                                                              "max_positions")},
            },
            "report_days": days[-60:], "lessons_tail": journal.tail(4000),
            "settings": {k: settings()[k] for k in ("capital", "mandate", "risk", "exits", "scoring")}}
    write_json(ROOT / "docs" / "data.json", data)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stocktips", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("morning"); p.add_argument("--no-book", action="store_true"); p.add_argument("--skip-review", action="store_true"); p.add_argument("--max-age", type=float, default=36); p.add_argument("--force", action="store_true", help="run even on a weekend/holiday"); p.set_defaults(fn=cmd_morning)
    p = sub.add_parser("gather"); p.add_argument("--max-age", type=float, default=36); p.set_defaults(fn=cmd_gather)
    p = sub.add_parser("add-tip")
    p.add_argument("--source", required=True, help="manual:<who> — e.g. manual:mohan, manual:tg_friend")
    p.add_argument("--symbol", required=True)
    for k in ("company", "text", "url"):
        p.add_argument("--" + k)
    p.add_argument("--entry", type=float, default=None)
    p.add_argument("--target", help="one price or a comma-separated list")
    p.add_argument("--stop", type=float, default=None)
    p.add_argument("--timeframe", choices=["weekly", "monthly", "long", "intraday"], default="weekly")
    p.add_argument("--action", choices=["buy", "sell", "hold"], default="buy")
    p.set_defaults(fn=cmd_add_tip)
    p = sub.add_parser("import-tips")
    p.add_argument("--source", default="mojo", help="source id these calls are graded under (default: mojo)")
    p.add_argument("--file", help="file holding the pasted screen")
    p.add_argument("--text", help="the pasted screen itself")
    p.add_argument("--symbol", help="name for a detail-panel paste that did not include one")
    p.add_argument("--url", default="https://www.marketsmojo.com/")
    p.add_argument("--dry-run", action="store_true", help="show what would be imported, write nothing")
    p.set_defaults(fn=cmd_import_tips)
    p = sub.add_parser("contenders"); p.add_argument("--top", type=int, default=3); p.add_argument("--date", default=None); p.set_defaults(fn=cmd_contenders)
    p = sub.add_parser("structure"); p.add_argument("--reviewed"); p.set_defaults(fn=cmd_structure)
    p = sub.add_parser("analyze"); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("pick"); p.add_argument("--no-book", action="store_true"); p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("book"); p.add_argument("symbol"); p.add_argument("--capital", type=float, default=None, help="rupees to deploy (default: deployable cash split over the free slots, capped per stock)"); p.add_argument("--date", default=None, help="report day whose analysis.json to book from (default: latest)"); p.add_argument("--force", action="store_true", help="override verdict / cap / slot checks"); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_book)
    p = sub.add_parser("close"); p.add_argument("symbol"); p.add_argument("--price", type=float, default=None, help="exit price (default: last close)"); p.add_argument("--note", default=None, help="why you exited — goes in the position notes"); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_close)
    p = sub.add_parser("capital"); p.add_argument("--add", type=float, default=None); p.add_argument("--withdraw", type=float, default=None); p.add_argument("--note", default=None); p.add_argument("--no-dashboard", action="store_true"); p.set_defaults(fn=cmd_capital)
    p = sub.add_parser("preopen")
    p.add_argument("--max-age", type=float, default=20, help="how far back to read news (hours)")
    p.add_argument("--refresh", action="store_true", help="re-fetch the wires instead of reusing news_raw.json")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--date", default=None, help="the session this run is for (default: today in IST)")
    p.add_argument("--force", action="store_true", help="run even on a weekend/holiday")
    p.add_argument("--no-dashboard", action="store_true")
    p.set_defaults(fn=cmd_preopen)
    p = sub.add_parser("intraday")
    p.add_argument("--close", action="store_true", help="settle the day's trades and grade the news")
    p.add_argument("--date", default=None)
    p.add_argument("--no-dashboard", action="store_true")
    p.set_defaults(fn=cmd_intraday)
    p = sub.add_parser("read")
    p.add_argument("--url", help="the story's URL — fetched and read")
    p.add_argument("--text", help="the article body, pasted")
    p.add_argument("--file", help="a file holding the article body")
    p.add_argument("--title", help="the headline, if the paste does not start with it")
    p.add_argument("--published", help="RFC-822 or ISO timestamp; defaults to now, which usually "
                                       "means the freshness term marks it as already seen")
    p.add_argument("--source", default="manual:read", help="source id it is graded under")
    p.add_argument("--date", default=None)
    p.add_argument("--add", action="store_true", help="fold it into today's pre-open card")
    p.add_argument("--no-dashboard", action="store_true")
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("daybook"); p.set_defaults(fn=cmd_daybook)
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
