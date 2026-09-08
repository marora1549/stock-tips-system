"""The morning pipeline: gather → structure → analyse → rank → allocate → report.

Stages write intermediate JSON into reports/<date>/ so the Claude layer in the
scheduled run can step in between `gather` and `analyze` (to fix extraction the
regexes flagged `needs_review`) and after `analyze` (to write the narrative).
"""
from __future__ import annotations

import logging
from collections import defaultdict

from .analysis import plan as planmod, scoring, ta
from .data import fundamentals, prices, sparks
from .learning import confidence
from .portfolio import allocate as allocmod, ledger as ledgermod
from .sources import extract, fetchers
from .util import REPORTS_DIR, read_json, settings, sources_config, today_str, write_json

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
