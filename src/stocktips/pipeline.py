"""The morning pipeline: gather → structure → analyse → rank → allocate → report.

Stages write intermediate JSON into reports/<date>/ so the Claude layer in the
scheduled run can step in between `gather` and `analyze` (to fix extraction the
regexes flagged `needs_review`) and after `analyze` (to write the narrative).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from .analysis import catalyst, intraday as intradaymod, plan as planmod, scoring, ta
from .data import fundamentals, prices, sparks
from .learning import confidence, eventscore
from .portfolio import allocate as allocmod, daybook, ledger as ledgermod
from .sources import events, extract, fetchers
from .util import (CONFIG_DIR, REPORTS_DIR, load_yaml, now_ist, read_json, settings, sources_config,
                   today_str, write_json)

MAX_SYMBOLS_PRICED = 40      # how many distinct symbols one pre-open run will fetch data for

# the TA fields the intraday card carries; the positional card's list lives in cli.py
ANALYSIS_TA_FIELDS = ("trend", "rsi", "adx", "atr_pct", "vol_ratio", "chg_1d_pct", "chg_5d_pct",
                      "dist_52w_high_pct", "dist_ema200_pct", "avg_turnover_cr", "high_52w",
                      "momentum_score", "last_bar_date")

log = logging.getLogger(__name__)


def day_dir(d: str | None = None):
    p = REPORTS_DIR / (d or today_str())
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ gather
def gather(max_age_hours: float = 36) -> dict:
    """Fetch every enabled source, extract candidate tips, write tips_raw.json."""
    conf = confidence.load()
    out = {"date": today_str(), "sources": {}, "tips": [], "docs": []}
    for src in sources_config():
        if not src.get("enabled", True):
            continue
        state = conf.get(src["id"], {})
        if not state.get("enabled", True):
            log.info("%s disabled by confidence rule — skipped", src["id"])
            continue
        docs = fetchers.fetch_source(src, max_age_hours=max_age_hours)
        tips = []
        for d in docs:
            if d.get("scan"):
                tips.append(extract.scan_tip(d, src["id"], src.get("default_timeframe")))
            else:
                tips += extract.extract(d["text"], source_id=src["id"], url=d["url"], title=d["title"], published=d["published"],
                                        default_timeframe=src.get("default_timeframe"))
            out["docs"].append({"source_id": src["id"], "url": d["url"], "title": d["title"], "published": d["published"], "chars": len(d["text"]),
                                "text": d["text"][:6000]})
        out["sources"][src["id"]] = {"docs": len(docs), "tips": len(tips)}
        out["tips"] += tips
        confidence.ensure(conf, src["id"])
    # brokerage sub-sources: a named house/analyst becomes the primary source, the publisher corroborates
    for t in out["tips"]:
        b = t.get("brokerage")
        if isinstance(b, str):
            t["publisher_source_id"] = t["source_id"]
            t["source_id"] = f"broker:{b}"
            confidence.ensure(conf, t["source_id"])
    confidence.save(conf)
    write_json(day_dir() / "tips_raw.json", out)
    log.info("gathered %d tips from %d sources", len(out["tips"]), len(out["sources"]))
    return out


# ------------------------------------------------------------------ structure (merge duplicates)
def structure(raw: dict | None = None, reviewed: list[dict] | None = None) -> list[dict]:
    """Merge per-symbol. `reviewed` (optional) is the Claude-corrected tip list replacing tips_raw's tips."""
    raw = raw or read_json(day_dir() / "tips_raw.json", {"tips": []})
    tips = reviewed if reviewed is not None else raw["tips"]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in tips:
        if not t.get("symbol") or t.get("action") != "buy":
            continue
        if t.get("dropped"):
            continue
        groups[t["symbol"]].append(t)
    merged = []
    for sym, ts in groups.items():
        ts.sort(key=lambda t: (-t.get("extraction_confidence", 0), t.get("needs_review", True)))
        lead = ts[0]
        srcs = []
        for t in ts:
            for s in (t["source_id"], t.get("publisher_source_id")):
                if s and s not in srcs:
                    srcs.append(s)
        targets = sorted({x for t in ts for x in (t.get("src_targets") or [])})
        stops = [t["src_stop"] for t in ts if t.get("src_stop")]
        merged.append({
            "symbol": sym, "company": lead.get("company"), "tip_id": lead["id"], "source_id": srcs[0], "corroborating_sources": srcs[1:],
            "n_mentions": len(ts), "src_targets": targets, "src_stop": min(stops) if stops else None,
            "src_entry": lead.get("src_entry"), "src_duration": next((t["src_duration"] for t in ts if t.get("src_duration")), None),
            "default_timeframe": lead.get("default_timeframe"), "sentence": lead.get("sentence"), "urls": list({t["url"] for t in ts if t.get("url")})[:5],
            "needs_review": all(t.get("needs_review") for t in ts), "extraction_confidence": max(t.get("extraction_confidence", 0) for t in ts),
            "brokerages": sorted({t["brokerage"] for t in ts if isinstance(t.get("brokerage"), str)}),
        })
    write_json(day_dir() / "tips_structured.json", merged)
    return merged


# ------------------------------------------------------------------ analyse
def analyze(structured: list[dict] | None = None, min_extraction_conf: float = 0.5) -> list[dict]:
    structured = structured if structured is not None else read_json(day_dir() / "tips_structured.json", [])
    conf = confidence.load()
    spark_cache = sparks.load()
    cfg = settings()
    results = []
    for t in structured:
        if t.get("extraction_confidence", 0) < min_extraction_conf and t["n_mentions"] < 2:
            continue   # unreviewed low-confidence extraction: leave for the analyst layer
        df = prices.history(t["symbol"])
        if df is None:
            log.info("%s: no price history", t["symbol"])
            continue
        sparks.remember(spark_cache, t["symbol"], df)
        snap = ta.analyze(df)
        ltp = snap["close"]
        src_tgt_pct = (max(t["src_targets"]) / ltp - 1) * 100 if t.get("src_targets") else None
        tf = planmod.classify_timeframe((t.get("src_duration") or "") + " " + (t.get("sentence") or ""), src_tgt_pct, default=t.get("default_timeframe") or "weekly")
        plan = planmod.build_plan(snap, tf, entry=None, src_targets=t.get("src_targets"), src_stop=t.get("src_stop"))
        f = fundamentals.fetch(t["symbol"])
        fscore, fwhy = fundamentals.score(f)
        # source weight: primary source, nudged by corroboration
        w = confidence.weight(conf.get(t["source_id"], {}).get("score", 0.0))
        if t["corroborating_sources"]:
            ws = [confidence.weight(conf.get(s, {}).get("score", 0.0)) for s in t["corroborating_sources"]]
            w = min(1.0, w + 0.05 * len(ws) + 0.1 * (sum(ws) / len(ws) - 0.5))
        comp = scoring.composite(plan["ta_confidence"], fscore, w)
        verdict, bucket = scoring.verdict(comp, plan, fscore)
        # stale-entry check: if source quoted an entry and price has already run > 4% past it, downgrade
        if t.get("src_entry") and ltp > t["src_entry"] * 1.04:
            comp -= 6
            plan["reasons"].append(f"-6 price already {((ltp / t['src_entry']) - 1) * 100:.1f}% above source entry ₹{t['src_entry']:g}")
            verdict, bucket = scoring.verdict(comp, plan, fscore)
        results.append({
            **{k: t[k] for k in ("symbol", "company", "tip_id", "source_id", "corroborating_sources", "n_mentions", "src_targets", "src_stop", "src_entry", "urls", "brokerages", "sentence")},
            "ltp": ltp, "plan": plan, "ta": {k: snap[k] for k in ("trend", "rsi", "atr_pct", "adx", "vol_ratio", "patterns", "dist_52w_high_pct", "dist_ema20_pct", "dist_ema200_pct", "avg_turnover_cr", "chg_5d_pct", "chg_20d_pct", "high_52w", "last_bar_date", "momentum_score", "drift_pct_day", "efficiency", "amplitude_pct_day", "up_day_share")},
            "resistances": snap["resistances"][:4], "supports": snap["supports"][:4],
            "ta_confidence": plan["ta_confidence"], "fund_score": fscore, "fund_why": fwhy, "fundamentals": {k: v for k, v in (f or {}).items() if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity", "promoter_pct", "sales_growth_3_years", "profit_growth_3_years", "np_yoy_growth_pct")},
            "source_weight": round(w, 3), "source_confidence": confidence.display(conf.get(t["source_id"], {}).get("score", 0.0)),
            "composite": comp, "verdict": verdict, "bucket": bucket,
            "tags": scoring.tags(plan, snap, fscore, t["n_mentions"], len(t["corroborating_sources"])),
        })
        for s in [t["source_id"]] + t["corroborating_sources"]:
            confidence.note_tip(conf, s)
    confidence.save(conf)
    sparks.save(spark_cache)
    results.sort(key=lambda r: -r["composite"])
    write_json(day_dir() / "analysis.json", results)
    return results


# ------------------------------------------------------------------ allocate + book
def pick_and_book(results: list[dict] | None = None, book: bool = True) -> dict:
    results = results if results is not None else read_json(day_dir() / "analysis.json", [])
    led = ledgermod.load()
    held = {p["symbol"] for p in led["positions"]}
    open_count = len([p for p in led["positions"] if p["status"] in ("open", "pending")])
    room = max(0, settings()["capital"]["max_open_positions"] - open_count)
    picks = allocmod.allocate(results, ledgermod.deployable_cash(led), held, capital_inr=led["capital_inr"])
    chosen = [p for p in picks if p.get("alloc_inr", 0) > 0][:room]
    booked = []
    if book:
        for p in chosen:
            pos = ledgermod.open_position(led, p, p["alloc_inr"])
            if pos:
                booked.append(pos["pos_id"])
        ledgermod.save(led)
    out = {"date": today_str(), "top": [p for p in results if p["verdict"] in ("STRONG BUY", "BUY")][:settings()["scoring"]["top_n"]],
           "chosen": [{k: p[k] for k in ("symbol", "composite", "alloc_inr", "alloc_qty")} for p in chosen], "booked": booked,
           "cash_after": led["cash_inr"], "watch": [p["symbol"] for p in results if p["verdict"] == "WATCH"][:8]}
    write_json(day_dir() / "picks.json", out)
    return out


# ==================================================================== the intraday desk
def news_sources() -> list[dict]:
    """The corporate-news registry, kept apart from the tip sources on purpose."""
    return (load_yaml(CONFIG_DIR / "news_sources.yaml") or {}).get("sources") or []


NEWS_DOCS_PER_SOURCE = 8     # articles hydrated per wire
NEWS_DOCS_TOTAL = 55         # articles hydrated per run, across all wires
NEWS_DEADLINE_S = 420        # and a wall clock, because 09:15 does not wait


def gather_news(max_age_hours: float = 20, deadline_s: float | None = None,
                per_source: int | None = None, total: int | None = None) -> dict:
    """Fetch the corporate wires and read events out of them → reports/<date>/news_raw.json.

    20 hours by default rather than the tip pipeline's 36: this run is about what the market has not
    seen yet, and yesterday morning's story has been priced for a day and a half.

    **Budgeted, because this run has a deadline.** Every article costs a fetch, and a Google News
    link costs two more to decode before that. Thirteen wires at twenty-five articles each is nearly
    a thousand requests, which took the first live run past eighteen minutes and still going — for a
    run that has to be finished, scored and emailed before 09:15. So: a cap per wire, a cap per run,
    and a wall clock. When the budget runs out the run says so in its summary rather than pretending
    it read everything; a wire that is consistently cut off is an argument for reordering the list,
    not for raising the cap.
    """
    deadline_s = NEWS_DEADLINE_S if deadline_s is None else deadline_s
    per_source = NEWS_DOCS_PER_SOURCE if per_source is None else per_source
    budget = NEWS_DOCS_TOTAL if total is None else total
    started = time.monotonic()

    conf = confidence.load()
    usd = float(settings().get("data", {}).get("usd_inr", 88.0))
    out = {"date": today_str(), "sources": {}, "events": [], "docs": [],
           "budget": {"per_source": per_source, "total": budget, "deadline_s": deadline_s},
           "cut_short": []}
    for src in news_sources():
        if not src.get("enabled", True):
            continue
        if not conf.get(src["id"], {}).get("enabled", True):
            log.info("%s disabled by confidence rule — skipped", src["id"])
            continue
        spent = time.monotonic() - started
        if budget <= 0 or spent > deadline_s:
            out["cut_short"].append({"source_id": src["id"],
                                     "why": "out of article budget" if budget <= 0
                                            else f"past the {deadline_s:.0f}s deadline"})
            out["sources"][src["id"]] = {"docs": 0, "events": 0, "skipped": True}
            continue
        docs = fetchers.fetch_source(src, max_age_hours=max_age_hours,
                                     limit=min(per_source, budget))
        budget -= len(docs)
        found = []
        for d in docs:
            found += events.scan(d, src["id"], usd_inr=usd)
            out["docs"].append({"source_id": src["id"], "url": d["url"], "title": d["title"],
                                "published": d["published"], "chars": len(d["text"])})
        out["sources"][src["id"]] = {"docs": len(docs), "events": len(found)}
        out["events"] += found
        confidence.ensure(conf, src["id"])
    confidence.save(conf)
    out["events"] = events.merge(out["events"])
    out["seconds"] = round(time.monotonic() - started, 1)
    write_json(day_dir() / "news_raw.json", out)
    log.info("gathered %d events from %d wires in %.0fs (%d cut short)",
             len(out["events"]), len(out["sources"]), out["seconds"], len(out["cut_short"]))
    return out


def _ceiling(ev: dict, fresh: dict) -> int:
    """The most this event could score if every unknown broke its way.

    Granting the best materiality band, perfect fundamentals, the best plausible chart bonus and the
    freshness the story actually has. Deliberately optimistic, because its job is to *order* the
    queue of symbols worth paying for — not to reject anything. A gate tight enough to reject would
    also drop true positives, and a missed GE Vernova costs more than a wasted request.
    """
    directness = float(ev.get("directness") or 1.0)
    base = float(ev.get("event_prior") or 0) * float(ev.get("certainty") or 1.0) * directness
    corroboration = min(6, 3 * len(ev.get("corroborating_sources") or []))
    return int(round(base + 26 * directness + 10 + 13 + fresh["points"] + corroboration))


def preopen(raw: dict | None = None, now=None, limit: int = 8, date: str | None = None) -> dict:
    """Score every overnight event and write the pre-open card → reports/<date>/preopen.json.

    This is the run whose output is an email at 08:00. Everything expensive — prices, fundamentals —
    is fetched only for names that already cleared the cheap checks, because a wire can produce
    fifty events and forty of them are about companies whose charts nobody needs to see.
    """
    cfg = settings().get("intraday", {}) or {}
    conf = confidence.load()
    class_state = eventscore.load()
    now = now or now_ist()
    # The run is dated by the session it is for, not by the wall clock. A pre-open run fired at
    # 08:00 IST and a replay handed an explicit `now` must both write into the day they are about,
    # and `today_str()` has already rolled over for anyone running this from a UTC evening.
    date = date or now.date().isoformat()
    raw = raw if raw is not None else read_json(day_dir(date) / "news_raw.json", None) or gather_news()

    ranked, skipped = [], []
    spark_cache = sparks.load()

    # Free checks first. Then order what is left by the most it could possibly score and price only
    # that many symbols, because everything past this point costs a Yahoo request and a Screener
    # request — and those two are what rate-limit and take a whole run down with them.
    queue = []
    for ev in raw["events"]:
        fresh = catalyst.freshness(ev.get("published_utc"), now)
        drop = (fresh["why"] if fresh["window"] == "stale"
                else "too indirect for the news to matter to it"
                if ev["directness"] < events.DIRECTNESS_FLOOR else None)
        if drop:
            skipped.append({**{k: ev[k] for k in ("symbol", "event", "title", "source_id")}, "why": drop})
            continue
        queue.append((_ceiling(ev, fresh), ev))
    queue.sort(key=lambda x: -x[0])

    # one chart and one fundamentals page per symbol, however many events name it
    charts: dict[str, object] = {}
    books: dict[str, tuple] = {}
    for ceiling, ev in queue:
        sym = ev["symbol"]
        if sym not in charts:
            if len(charts) >= MAX_SYMBOLS_PRICED:
                skipped.append({**{k: ev[k] for k in ("symbol", "event", "title", "source_id")},
                                "why": f"queue was full at {MAX_SYMBOLS_PRICED} symbols and this "
                                       f"scored at most {ceiling}"})
                continue
            charts[sym] = prices.history(sym)
        df = charts[sym]
        if df is None:
            skipped.append({**{k: ev[k] for k in ("symbol", "event", "title", "source_id")},
                            "why": "no price history"})
            continue
        snap = ta.analyze(df)
        if sym not in books:
            f = fundamentals.fetch(sym)
            books[sym] = (f, *fundamentals.score(f))
        f, fscore, fwhy = books[sym]
        cat = catalyst.score(
            ev, fundamentals=f, fund_score=fscore, ta=snap,
            class_prior=eventscore.prior(class_state, ev["event"], ev.get("event_prior", 0)),
            source_weight=confidence.weight(conf.get(ev["source_id"], {}).get("score", 0.0)),
            now=now)
        plan = intradaymod.preopen_plan(snap["close"], snap, cfg)
        sparks.remember(spark_cache, ev["symbol"], df)
        ranked.append({
            **ev, **cat, "plan": plan, "fund_score": fscore, "fund_why": fwhy,
            "ltp": snap["close"],
            "ta": {k: snap.get(k) for k in ANALYSIS_TA_FIELDS},
            "fundamentals": {k: v for k, v in (f or {}).items()
                             if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity",
                                      "promoter_pct", "revenue_ttm_cr", "revenue_basis",
                                      "sales_growth_3_years", "profit_growth_3_years")},
            "class_score": eventscore.display(class_state, ev["event"]),
        })

    sparks.save(spark_cache)
    ranked.sort(key=lambda r: (-r["catalyst"], r["symbol"]))
    contenders_ = [r for r in ranked if r["verdict"] == "TRADE"][:limit]
    out = {
        "date": date, "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "sources": raw.get("sources", {}), "events_read": len(raw["events"]),
        "trade": contenders_,
        "watch": [r for r in ranked if r["verdict"] == "WATCH"][:limit],
        "avoid": [r for r in ranked if r["verdict"] == "AVOID"][:limit],
        "skipped": skipped[:40],
        "settings": {k: cfg.get(k) for k in ("gap_modest_pct", "gap_wide_pct", "max_stop_pct",
                                             "force_flat_at", "notional_inr", "risk_per_trade_pct",
                                             "max_positions")},
    }
    write_json(day_dir(date) / "preopen.json", out)
    log.info("pre-open: %d events → %d TRADE, %d WATCH, %d AVOID",
             len(raw["events"]), len(out["trade"]), len(out["watch"]), len(out["avoid"]))
    return out


def intraday_watch(now=None, date: str | None = None) -> dict:
    """The session check: what the open actually did, and which plans the rule now allows.

    Called at 09:35 for the opening range, again mid-session, and at 15:20 to settle. It is the only
    place a paper trade is opened, and it opens one only because the trigger printed on the tape —
    not because the news was good.
    """
    cfg = settings().get("intraday", {}) or {}
    now = now or now_ist()
    date = date or now.date().isoformat()
    card = read_json(day_dir(date) / "preopen.json", None)
    if not card:
        return {"date": date, "error": (
            f"no reports/{date}/preopen.json — either the 08:00 pre-open run did not happen, or it "
            f"ran and could not push its card. `git log --oneline -3` distinguishes them: a pre-open "
            f"commit for {date} means the push failed, which is usually a routine created without "
            f"the repository attached as a source. This run does not invent candidates of its own.")}
    book = daybook.load()
    rec = daybook.record_candidates(book, card.get("trade", []), date)

    watched = card.get("trade", []) + card.get("watch", [])
    live = []
    for cand in watched:
        sym = cand["symbol"]
        bars = prices.history(sym, interval="5m")
        daily = prices.history(sym)
        if bars is None or bars.empty:
            live.append({**_intraday_card(cand), "state": "no-data",
                         "reasons": ["no intraday bars — the feed has nothing for this symbol yet"]})
            continue
        prev_close = cand.get("plan", {}).get("reference_close") or cand.get("ltp")
        plan = intradaymod.session_plan(prev_close, bars, cand.get("ta") or {}, daily, now=now, c=cfg, day=date)
        size = intradaymod.size_for(plan, cfg) if plan.get("trigger") else {"qty": 0}
        row = {**_intraday_card(cand), **plan, "size": size}
        if plan.get("trigger"):
            row["order_line"] = intradaymod.order_line(sym, plan, size.get("qty") or 0)
        # a trade is written only when the tape triggered it, and only for a TRADE-grade catalyst
        if (plan.get("state") in ("triggered", "stopped", "done") and cand.get("verdict") == "TRADE"
                and (size.get("qty") or 0) > 0):
            daybook.open_trade(book, symbol=sym, plan=plan, qty=size["qty"], event=cand, date=date)
        live.append(row)

    live.sort(key=lambda r: (r.get("state") != "triggered", -(r.get("catalyst") or 0)))
    out = {"date": date, "checked_at": now.strftime("%Y-%m-%d %H:%M"), "candidates": live,
           "trades": rec["trades"], "book": daybook.stats(book),
           "settled": rec.get("settled", False)}
    daybook.save(book)
    write_json(day_dir(date) / "intraday.json", out)
    return out


def _intraday_card(cand: dict) -> dict:
    """The parts of a pre-open candidate the session view carries forward."""
    keys = ("symbol", "company", "event", "event_label", "catalyst", "verdict", "verdict_note",
            "reasons", "size_inr_cr", "size_estimated", "materiality_ratio", "revenue_ttm_cr",
            "fund_score", "fund_why", "source_id", "corroborating_sources", "url", "title",
            "directness", "route", "why_this_name", "theme", "ltp", "ta", "fundamentals",
            "freshness", "class_score", "published")
    out = {k: cand.get(k) for k in keys}
    out["catalyst_reasons"] = cand.get("reasons") or []
    out["reasons"] = []
    return out


def intraday_close(now=None, date: str | None = None) -> dict:
    """Settle the day: exit every open trade at what the tape gave, then grade the news.

    The exit is taken from the bars rather than asked for: the stop if it was breached, the highest
    target that traded, else the price at the forced-flat time. Grading uses open→high and
    open→close for *every* candidate, including the ones that never triggered — a piece of news that
    moved a stock 4% is evidence about that class of news whether or not the plan caught it.
    """
    now = now or now_ist()
    date = date or now.date().isoformat()
    card = read_json(day_dir(date) / "preopen.json", None) or {}
    book = daybook.load()
    rec = daybook.day(book, date)
    conf = confidence.load()
    classes = eventscore.load()
    settled, graded = [], []

    watched = (card.get("trade") or []) + (card.get("watch") or [])
    # One story that moves four related names is one piece of evidence about that kind of news, not
    # four. The Barmer story surfaced GE Vernova and three sympathy plays; grading the class once per
    # name would let a single afternoon define it. The most direct beneficiary is the observation.
    counts_for: dict[tuple, str] = {}
    for cand in sorted(watched, key=lambda c: -(c.get("directness") or 0)):
        key = (cand.get("event"), cand.get("url") or cand.get("title"))
        counts_for.setdefault(key, cand["symbol"])

    for cand in watched:
        sym = cand["symbol"]
        bars = prices.history(sym, interval="5m")
        today = intradaymod.session_bars(bars, date) if bars is not None else None
        if today is None or today.empty:
            continue
        open_px = float(today["open"].iloc[0])
        high = float(today["high"].max())
        close_px = float(today["close"].iloc[-1])
        o2h = round((high / open_px - 1) * 100, 2)
        o2c = round((close_px / open_px - 1) * 100, 2)

        # grade the news itself, whether or not a trade happened — a story that moved a stock 4% is
        # evidence about that class of news even if no plan ever triggered
        key = (cand.get("event"), cand.get("url") or cand.get("title"))
        counted = counts_for.get(key) == sym
        if counted:
            eventscore.note_outcome(classes, cand["event"], open_to_high_pct=o2h, open_to_close_pct=o2c,
                                    symbol=sym, seed_prior=cand.get("event_prior") or 0, on=date)
        graded.append({"symbol": sym, "event": cand["event"], "open_to_high_pct": o2h,
                       "open_to_close_pct": o2c, "verdict": cand.get("verdict"),
                       "catalyst": cand.get("catalyst"), "triggered": None,
                       "counted_for_class": counted})

        trade = next((t for t in rec["trades"] if t["symbol"] == sym and t["status"] == "open"), None)
        if trade is None:
            continue
        graded[-1]["triggered"] = True
        exit_px, reason = _settled_exit(today, trade, now)
        daybook.settle_trade(book, sym, exit_price=exit_px, reason=reason, date=date,
                             open_to_high_pct=o2h, open_to_close_pct=o2c)
        settled.append({"symbol": sym, "exit": exit_px, "reason": reason,
                        "pnl_inr": trade.get("pnl_inr"), "r_multiple": trade.get("r_multiple")})
        # and grade the wire that carried it, on the trade's own R
        _note_news_source(conf, trade)

    rec["settled"] = True
    daybook.save(book)
    eventscore.save(classes)
    confidence.save(conf)
    out = {"date": date, "settled_at": now.strftime("%Y-%m-%d %H:%M"), "exits": settled,
           "graded": graded, "book": daybook.stats(book), "classes": eventscore.summary(classes)}
    write_json(day_dir(date) / "intraday_close.json", out)
    log.info("intraday close %s: %d exits, %d events graded", date, len(settled), len(graded))
    return out


def _settled_exit(today, trade: dict, now) -> tuple[float, str]:
    """What the tape actually gave: the stop if breached, else the best target reached, else the
    price at the forced-flat time. Order matters, and the stop is checked first — assuming the
    target came first when both printed in one bar would flatter every record the desk keeps."""
    ran = intradaymod.walk(today, trade["entry"], trade["stop"], trade.get("targets") or [])
    if ran["stopped"]:
        return trade["stop"], ("stopped in the entry bar" if ran["entry_bar_same_bar_stop"] else "stop")
    hit = ran["targets_hit"]
    targets = trade.get("targets") or []
    if hit:
        return targets[min(hit, len(targets)) - 1], f"target_{min(hit, len(targets))}"
    flat = str((settings().get("intraday", {}) or {}).get("force_flat_at", "15:10"))
    upto = today[[str(ts.time())[:5] <= flat for ts in today.index]]
    last = upto if not upto.empty else today
    return round(float(last["close"].iloc[-1]), 2), f"squared off at {flat}"


def _note_news_source(conf: dict, trade: dict) -> None:
    """Move the news source's confidence on the trade's R, using the same scale as tip outcomes."""
    sid = trade.get("source_id")
    if not sid:
        return
    row = confidence.ensure(conf, sid)
    r = trade.get("r_multiple")
    if r is None:
        return
    sc = settings().get("source_confidence", {})
    decay = float(sc.get("decay_per_outcome", 0.95))
    delta = max(-15.0, min(15.0, r * 6.0))
    row["score"] = round(float(row.get("score") or 0.0) * decay + delta, 3)
    row["n_resolved"] = int(row.get("n_resolved") or 0) + 1
    row["sum_return_pct"] = round(float(row.get("sum_return_pct") or 0.0) + (trade.get("return_pct") or 0.0), 2)
    row["history"] = (row.get("history") or [] + [])[-99:] + [{
        "date": trade.get("date"), "symbol": trade.get("symbol"), "outcome": trade.get("exit_reason"),
        "ret_pct": trade.get("return_pct"), "delta": round(delta, 2), "kind": "intraday",
    }]
    row["last_seen"] = trade.get("date") or today_str()

def read_one_story(text: str | None = None, url: str | None = None, *, title: str | None = None,
                   published: str | None = None, source_id: str = "manual:read",
                   now=None, date: str | None = None) -> dict:
    """Score one story the desk owner found for themselves.

    The GE Vernova article was read at mid-morning on a phone. This is the path for exactly that: a
    URL or a pasted body goes through the same extractor, the same beneficiary map and the same
    catalyst score as the 08:00 run, so the answer is comparable rather than a second opinion from a
    different method. The freshness term will usually mark it in-session and dock it, which is the
    honest reading — by the time you are reading it, the market has too.
    """
    now = now or now_ist()
    date = date or now.date().isoformat()
    cfg = settings().get("intraday", {}) or {}
    body = text or ""
    if url and not body.strip():
        body = fetchers.article_text(url)
        if not body:
            return {"error": f"could not read anything at {url}", "candidates": []}
    if not body.strip():
        return {"error": "nothing to read — pass the article text or a URL", "candidates": []}

    lines = [ln.strip() for ln in body.replace("\r\n", "\n").split("\n") if ln.strip()]
    doc = {
        "url": url or "",
        # a pasted article's first line is nearly always its headline
        "title": (title or (lines[0] if lines and len(lines[0]) < 200 else ""))[:200],
        "published": published or now.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "text": body,
    }
    found = events.merge(events.scan(doc, source_id,
                                     usd_inr=float(settings().get("data", {}).get("usd_inr", 88.0))))
    if not found:
        return {"error": "read it, but found no corporate event and no NSE name it implicates",
                "candidates": [], "title": doc["title"]}

    conf = confidence.load()
    confidence.ensure(conf, source_id)
    confidence.save(conf)
    classes = eventscore.load()
    out = []
    for ev in found:
        df = prices.history(ev["symbol"])
        if df is None:
            out.append({**ev, "verdict": "SKIP", "verdict_note": "no price history for this symbol",
                        "catalyst": None, "reasons": []})
            continue
        snap = ta.analyze(df)
        f = fundamentals.fetch(ev["symbol"])
        fscore, fwhy = fundamentals.score(f)
        cat = catalyst.score(ev, fundamentals=f, fund_score=fscore, ta=snap,
                             class_prior=eventscore.prior(classes, ev["event"], ev.get("event_prior", 0)),
                             source_weight=confidence.weight(conf.get(source_id, {}).get("score", 0.0)),
                             now=now)
        out.append({**ev, **cat, "fund_score": fscore, "fund_why": fwhy, "ltp": snap["close"],
                    "ta": {k: snap.get(k) for k in ANALYSIS_TA_FIELDS},
                    "fundamentals": {k: v for k, v in (f or {}).items()
                                     if k in ("market_cap_cr", "pe", "roce", "roe", "debt_to_equity",
                                              "promoter_pct", "revenue_ttm_cr", "revenue_basis")},
                    "plan": intradaymod.preopen_plan(snap["close"], snap, cfg),
                    "class_score": eventscore.display(classes, ev["event"])})
    out.sort(key=lambda r: -(r.get("catalyst") or -999))

    # The freshness term measures when the news landed, not when you read it — so an overnight story
    # pasted at 10:30 still scores +12, which is right about the news and silent about the thing
    # that actually cost money last time. Say it separately.
    warning = None
    at = now.time()
    if catalyst.OPEN_T <= at <= catalyst.CLOSE_T:
        mins = (now.hour * 60 + now.minute) - (catalyst.OPEN_T.hour * 60 + catalyst.OPEN_T.minute)
        warning = (f"The market has been open {mins} minutes. The score above is what this news was "
                   f"worth at the open; whatever it was going to do to the price has partly or "
                   f"wholly happened. Check the day's range before acting on any of it.")
    return {"date": date, "read_at": now.strftime("%Y-%m-%d %H:%M"), "title": doc["title"],
            "url": doc["url"], "source_id": source_id, "candidates": out,
            "read_during_session": warning}


def add_to_preopen(story: dict, date: str | None = None) -> dict:
    """Fold a hand-read story into today's card, so the portal and the session runs pick it up."""
    date = date or story.get("date") or today_str()
    card = read_json(day_dir(date) / "preopen.json", None)
    if card is None:
        return {"error": f"no preopen.json for {date} — run preopen first, then add to it"}
    added = []
    for c in story.get("candidates") or []:
        bucket = {"TRADE": "trade", "WATCH": "watch", "AVOID": "avoid"}.get(c.get("verdict"))
        if not bucket:
            continue
        rows = card.setdefault(bucket, [])
        if any(r.get("symbol") == c["symbol"] and r.get("event") == c.get("event") for r in rows):
            continue
        rows.append(c)
        added.append(f"{c['symbol']} → {bucket}")
    for key in ("trade", "watch"):
        card[key] = sorted(card.get(key) or [], key=lambda r: -(r.get("catalyst") or 0))
    card["hand_read"] = (card.get("hand_read") or []) + [{
        "title": story.get("title"), "url": story.get("url"), "at": story.get("read_at"),
        "added": added}]
    write_json(day_dir(date) / "preopen.json", card)
    return {"date": date, "added": added}
