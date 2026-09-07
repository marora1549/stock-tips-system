"""Markdown reports for the morning and EOD runs (committed to reports/<date>/)."""
from __future__ import annotations

from .learning import confidence, journal
from .portfolio import ledger as ledgermod
from .util import now_ist, settings


def _inr(x):
    return f"₹{x:,.0f}" if x is not None else "—"


def pick_block(p: dict, rank: int | None = None, alloc: dict | None = None) -> str:
    pl = p["plan"]
    t = p["ta"]
    head = f"### {rank}. {p['company'] or p['symbol']} (NSE: {p['symbol']}) — {p['verdict']} · composite {p['composite']}" if rank else f"### {p['symbol']} — {p['verdict']} · {p['composite']}"
    lines = [head, ""]
    lines.append(f"**Plan ({pl['timeframe']}, mandate ≥{pl['mandate_pct']:g}%):** entry ₹{pl['entry']:,} (zone {pl['entry_zone'][0]:,}–{pl['entry_zone'][1]:,}) · "
                 f"**SL ₹{pl['stop_loss']:,}** (−{pl['stop_loss_pct']}%, {pl['stop_basis']}) · "
                 f"**T1 ₹{pl['targets'][0]:,}** (+{pl['target_pct'][0]}%) · **T2 ₹{pl['targets'][1]:,}** (+{pl['target_pct'][1]}%) · **T3 ₹{pl['targets'][2]:,}** (+{pl['target_pct'][2]}%) · "
                 f"R:R@T2 {pl['reward_risk_t2']} · time stop {pl['time_stop_days']} trading days")
    ex = settings()["exits"]
    lines.append(f"Stepped exit: book {ex['t1_fraction']:.0%} at T1 (SL→entry), {ex['t2_fraction']:.0%} at T2 (SL→T1), rest at T3.")
    if alloc and alloc.get("alloc_inr"):
        lines.append(f"**Paper allocation: {_inr(alloc['alloc_inr'])} ≈ {alloc.get('alloc_qty')} shares.**")
    lines.append("")
    lines.append(f"- **TA confidence {p['ta_confidence']}/100** — trend `{t['trend']}`, RSI {t['rsi']}, ADX {t['adx']}, ATR {t['atr_pct']}%, vol {t['vol_ratio']}× avg, "
                 f"{t['dist_52w_high_pct']}% from 52w high, 5d {t['chg_5d_pct']:+}% / 20d {t['chg_20d_pct']:+}%; patterns: {', '.join(t['patterns']) or 'none'}")
    lines.append(f"  - reasons: {'; '.join(pl['reasons'])}")
    if p.get("resistances"):
        res = ", ".join("₹{:,}({})".format(r["price"], r["touches"]) for r in p["resistances"])
        sup = ", ".join("₹{:,}({})".format(s["price"], s["touches"]) for s in p["supports"])
        lines.append(f"  - resistances: {res} · supports: {sup}")
    lines.append(f"- **Fundamentals {p['fund_score']}/100 → {p['bucket']}** — {'; '.join(p['fund_why'])}")
    src = p["source_id"] + (f" (+{len(p['corroborating_sources'])} corroborating: {', '.join(p['corroborating_sources'][:3])})" if p["corroborating_sources"] else "")
    lines.append(f"- **Source** `{src}` · source confidence {p['source_confidence']}/100 · {p['n_mentions']} mention(s)"
                 + (f" · source target(s) ₹{', ₹'.join(f'{x:,}' for x in p['src_targets'])}" if p["src_targets"] else "") + (f" · source SL ₹{p['src_stop']:,}" if p.get("src_stop") else ""))
    if p.get("sentence"):
        lines.append(f"  - > {p['sentence'][:220].strip()}")
    for u in (p.get("urls") or [])[:2]:
        lines.append(f"  - {u}")
    return "\n".join(lines)


def morning(results: list[dict], picks: dict, raw: dict) -> str:
    led = ledgermod.load()
    st = ledgermod.stats(led)
    conf = confidence.summary(confidence.load())
    now = now_ist().strftime("%a %d %b %Y, %H:%M IST")
    top = picks["top"]
    chosen = {c["symbol"]: c for c in picks["chosen"]}
    out = [f"# Morning picks — {now}", ""]
    out.append(f"Paper book: equity {_inr(st['equity'])} ({st['return_pct']:+}%) · cash {_inr(st['cash'])} · open {st['open']} · pending {st['pending']} · hold {st['hold']} · closed {st['closed']}"
               + (f" · win rate {st['win_rate']}%" if st['win_rate'] is not None else ""))
    out.append(f"Gathered **{len(raw['tips'])} raw tips** from {len(raw['sources'])} sources → {len(results)} analysed → {len(top)} actionable.")
    out.append("")
    if not top:
        out.append("**No tip cleared the bar today.** That is a valid outcome — cash is a position. Watchlist below.")
    for i, p in enumerate(top, 1):
        out.append(pick_block(p, i, chosen.get(p["symbol"])))
        out.append("")
    if picks.get("watch"):
        out.append(f"**Watch (WATCH verdict, not actionable yet):** {', '.join(picks['watch'])}")
    others = [p for p in results if p not in top]
    if others:
        out.append("")
        out.append("<details><summary>All analysed candidates</summary>\n")
        out.append("| symbol | verdict | comp | TA | fund | src | tf | LTP | SL | T1 | T2 | T3 | R:R | source |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p in results:
            pl = p["plan"]
            out.append(f"| {p['symbol']} | {p['verdict']} | {p['composite']} | {p['ta_confidence']} | {p['fund_score']} | {p['source_confidence']} | {pl['timeframe']} | {p['ltp']:,.1f} | {pl['stop_loss']:,} | {pl['targets'][0]:,} | {pl['targets'][1]:,} | {pl['targets'][2]:,} | {pl['reward_risk_t2']} | {p['source_id']} |")
        out.append("\n</details>")
    if led["positions"]:
        out.append("")
        out.append("## Open book")
        out.append("| symbol | status | entry | qty | SL | targets hit | unrealised | deadline | bucket |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for p in led["positions"]:
            out.append(f"| {p['symbol']} | {p['status']} | {p.get('entry') or p['entry_plan']} | {p['qty_open']}/{p['qty']} | {p['stop_loss']} | {p['targets_hit']} | {p.get('unrealised_pct', '—')}% | {p.get('deadline') or '—'} | {p['bucket']} |")
    out.append("")
    out.append("## Source confidence (top / bottom)")
    out.append("| source | conf | score | tips | resolved | T1 hit% | stop% | expectancy% |")
    out.append("|---|---|---|---|---|---|---|---|")
    shown = conf[:8] + ([{"source_id": "…"}] if len(conf) > 12 else []) + (conf[-4:] if len(conf) > 12 else conf[8:])
    for s in shown:
        if s["source_id"] == "…":
            out.append("| … | | | | | | | |")
            continue
        out.append(f"| {s['source_id']} | {s['confidence']} | {s['score']} | {s['n_tips']} | {s['n_resolved']} | {s['t1_hit_rate'] if s['t1_hit_rate'] is not None else '—'} | {s['stop_rate'] if s['stop_rate'] is not None else '—'} | {s['expectancy_pct'] if s['expectancy_pct'] is not None else '—'} |")
    out.append("")
    out.append("_Paper trading. Not investment advice. Every level above is derived from the daily chart as of the last close; re-check LTP at 9:15 before placing orders._")
    return "\n".join(out)


def eod(events: list[str], led: dict, conf_before: dict, conf_after: dict, machine_lessons: str) -> str:
    now = now_ist().strftime("%a %d %b %Y, %H:%M IST")
    st = ledgermod.stats(led)
    out = [f"# End-of-day ledger update — {now}", ""]
    out.append(f"Equity {_inr(st['equity'])} ({st['return_pct']:+}%) · cash {_inr(st['cash'])} · realised {_inr(st['realised_inr'])} · open {st['open']} · hold {st['hold']} · closed {st['closed']}"
               + (f" · win rate {st['win_rate']}% · avg win {st['avg_win_pct']}% / avg loss {st['avg_loss_pct']}%" if st['win_rate'] is not None else ""))
    out.append("")
    out.append("## Events")
    out += [f"- {e}" for e in events] or ["- nothing happened in the book today"]
    changed = []
    for sid, s in conf_after.items():
        b = conf_before.get(sid, {}).get("score", 0.0)
        if abs(s["score"] - b) > 1e-9:
            changed.append(f"- `{sid}`: {b:+.1f} → {s['score']:+.1f} (confidence {confidence.display(b)} → {confidence.display(s['score'])})")
    out.append("")
    out.append("## Source confidence changes")
    out += changed or ["- none"]
    out.append("")
    out.append("## What the ledger says works (all closed positions)")
    out.append(machine_lessons)
    if led["positions"]:
        out.append("")
        out.append("## Open book")
        out.append("| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for p in led["positions"]:
            out.append(f"| {p['symbol']} | {p['status']} | {p.get('entry') or p['entry_plan']} | {p.get('ltp', '—')} | {p.get('unrealised_pct', '—')}% | {p['stop_loss']} | {p['targets_hit']} | {p.get('deadline') or '—'} | {p['bucket']} |")
    out.append("")
    out.append("## Recent lessons")
    out.append(journal.tail(2500) or "_none yet_")
    return "\n".join(out)
