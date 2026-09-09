"""Markdown reports for the morning and EOD runs (committed to reports/<date>/)."""
from __future__ import annotations

from .learning import confidence, journal
from .portfolio import ledger as ledgermod
from .util import now_ist, settings


def _inr(x):
    return f"₹{x:,.0f}" if x is not None else "—"


def order_line(symbol: str, qty: int, entry: float, stop: float, targets: list[float]) -> str:
    """The exact Zerodha order to place at 9:15 — used by reports, `book` and the dashboard."""
    t = " / ".join(f"{x:,.2f}" for x in (targets or []))
    return f"BUY {qty} {symbol} NSE CNC limit ₹{entry:,.2f} · SL-M ₹{stop:,.2f} · GTT ₹{t}"


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


# ==================================================================== the pre-open email
def _ratio_words(c: dict) -> str:
    r, size, rev = c.get("materiality_ratio"), c.get("size_inr_cr"), c.get("revenue_ttm_cr")
    if r and size and rev:
        est = ", estimated from the capacity" if c.get("size_estimated") else ""
        return f"₹{size:,.0f}cr against ₹{rev:,.0f}cr of revenue — **{r:.1f}× a year's sales**{est}"
    if size:
        return f"₹{size:,.0f}cr{', estimated from the capacity' if c.get('size_estimated') else ''}"
    return "no size given and none estimable"


def preopen_card(c: dict, rank: int) -> str:
    plan = c.get("plan") or {}
    ta = c.get("ta") or {}
    lines = [f"### {rank}. {c['symbol']} — {c.get('company', '')}",
             "",
             f"**{c.get('event_label')}** · catalyst **{c.get('catalyst')}** · {c.get('verdict')} — {c.get('verdict_note')}",
             "",
             f"> {c.get('title', '')}  ",
             f"> {c.get('source_id', '')} · [story]({c.get('url', '')}) · published {c.get('published', '')}",
             "",
             f"- Size: {_ratio_words(c)}",
             f"- Why this name: {c.get('why_this_name', '')} ({c.get('route')})",
             f"- Business: fundamentals {c.get('fund_score')}/100"
             + (" — " + "; ".join(c.get("fund_caps") or []) if c.get("fund_caps") else ""),]
    for fl in (c.get("fund_flags") or []):
        lines.append(f"  - ⚑ {fl}")
    for con in (c.get("screener_cons") or [])[:3]:
        lines.append(f"  - Screener says: {con}")
    lines += [
             f"- Chart: last close ₹{c.get('ltp'):,.2f}, {ta.get('trend', '?')}, ATR {ta.get('atr_pct')}%, "
             f"{abs(ta.get('dist_52w_high_pct') or 0):.1f}% off the 52-week high, "
             f"₹{ta.get('avg_turnover_cr') or 0:,.0f}cr a day",
             ""]
    if plan.get("gap_ladder"):
        lines += ["**The plan depends on the open:**", ""]
        for step in plan["gap_ladder"]:
            upto = f"up to {step['gap_upto_pct']:+g}%" if step["gap_upto_pct"] is not None else "above that"
            lines.append(f"- gap {upto} → {step['rule']}")
        lines += ["",
                  f"Stop never wider than {plan.get('max_stop_pct')}%. No new entry after "
                  f"{plan.get('no_new_entry_after')}. Flat by {plan.get('force_flat_at')}.",
                  ""]
    lines += ["<details><summary>the arithmetic</summary>", ""]
    lines += [f"- {r}" for r in (c.get("reasons") or [])]
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def preopen(card: dict) -> str:
    """The 08:00 email. First line has to stand alone — it may be all that gets read on a phone."""
    trade, watch, avoid = card.get("trade") or [], card.get("watch") or [], card.get("avoid") or []
    date, at = card.get("date"), card.get("generated_at", "")
    if not trade and not watch and not avoid:
        head = f"# Pre-open {date} — nothing worth trading on the news"
    elif not trade:
        head = (f"# Pre-open {date} — no trade, {len(watch)} to watch: "
                + ", ".join(c["symbol"] for c in watch[:4]))
    else:
        head = (f"# Pre-open {date} — {len(trade)} to trade: "
                + ", ".join(f"{c['symbol']} ({c['catalyst']})" for c in trade))

    src = card.get("sources") or {}
    fed = [s for s, v in src.items() if (v or {}).get("docs")]
    cut = [s for s, v in src.items() if (v or {}).get("skipped")]
    out = [head, "",
           f"*{at} IST · {card.get('events_read', 0)} events read from {len(fed)} of {len(src)} wires"
           + (f", {len(cut)} not reached before the deadline" if cut else "")
           + " · paper trading only, nothing here places an order.*", ""]
    if cut:
        out += [f"> {len(cut)} wire{'s' if len(cut) > 1 else ''} were not reached: "
                f"{', '.join(cut)}. A story the desk never fetched is a different failure from one "
                f"it read and scored low.", ""]

    if trade:
        out += ["## Trade", "", "These cleared the bar. Every level comes from the chart, and the "
                "plan is a rule about the open — not an instruction to buy at 09:15.", ""]
        out += [preopen_card(c, i) for i, c in enumerate(trade, 1)]
    if watch:
        out += ["## Watch", "",
                "Real news, not enough on its own. Worth a glance at how they open — but note the "
                "route: a sympathy play is a peer of the company the story is actually about.", "",
                "| Symbol | Event | Catalyst | Size | Fundamentals | Route | Story |",
                "|---|---|---:|---:|---:|---|---|"]
        for c in watch:
            r = c.get("materiality_ratio")
            size = (f"{r:.1f}× revenue" if r else
                    (f"₹{c['size_inr_cr']:,.0f}cr" if c.get("size_inr_cr") else "—"))
            route = c.get("route") or "—"
            if route == "sympathy":
                route = f"sympathy ({(c.get('directness') or 0):.0%})"
            out.append(f"| {c['symbol']} | {c.get('event_label')} | {c.get('catalyst')} | {size} | "
                       f"{c.get('fund_score')} | {route} | [link]({c.get('url', '')}) |")
        out.append("")
    if avoid:
        out += ["## Avoid", "",
                "Negative catalysts. Do not buy these today, and exit them if you hold them.", ""]
        for c in avoid:
            out.append(f"- **{c['symbol']}** — {c.get('event_label')}: {c.get('title', '')} "
                       f"([story]({c.get('url', '')}))")
        out.append("")

    skipped = card.get("skipped") or []
    if skipped:
        out += ["<details><summary>" + f"{len(skipped)} events read and dropped" + "</summary>", ""]
        out += [f"- {s['symbol']} ({s.get('event')}) — {s.get('why')}" for s in skipped[:25]]
        out += ["", "</details>", ""]
    st = card.get("settings") or {}
    out += ["---", "",
            f"Day book: ₹{st.get('notional_inr', 0):,.0f} notional, at most {st.get('max_positions')} "
            f"positions, {st.get('risk_per_trade_pct')}% of notional risked per trade. "
            f"Gap ladder {st.get('gap_modest_pct')}% / {st.get('gap_wide_pct')}%. "
            f"Flat by {st.get('force_flat_at')}."]
    return "\n".join(out)


def intraday(card: dict) -> str:
    """The session check, for the 09:35 and midday runs."""
    rows = card.get("candidates") or []
    acted = [r for r in rows if r.get("state") in ("triggered", "stopped", "done")]
    head = (f"# Session {card.get('date')} {card.get('checked_at', '')[-5:]} — "
            + (", ".join(f"{r['symbol']} {r['state']}" for r in acted) if acted
               else f"nothing triggered ({len(rows)} watched)"))
    out = [head, ""]
    if not rows:
        return head + "\n\nNo pre-open candidates for today.\n"
    out += ["| Symbol | Gap | Band | State | Trigger | Stop | Targets | Now | From open |",
            "|---|---:|---|---|---:|---:|---|---:|---:|"]
    for r in rows:
        tg = " / ".join(f"{t:,.0f}" for t in (r.get("targets") or [])) or "—"
        out.append(f"| {r['symbol']} | {r.get('gap_pct', '—')}% | {r.get('band', '—')} | "
                   f"{r.get('state', '—')} | {r.get('trigger') or '—'} | {r.get('stop') or '—'} | {tg} | "
                   f"{r.get('last') or '—'} | {r.get('from_open_pct', '—')}% |")
    out.append("")
    for r in rows:
        if r.get("why_not"):
            out.append(f"- **{r['symbol']}** stood aside: {r['why_not']}")
        elif r.get("order_line") and r.get("verdict") == "TRADE":
            out.append(f"- **{r['symbol']}** — `{r['order_line']}`")
        elif r.get("trigger") and r.get("verdict") != "TRADE":
            # a WATCH name gets its levels, not a line to paste into a broker
            out.append(f"- **{r['symbol']}** is on watch, not on the book: the break is "
                       f"₹{r['trigger']:,.2f} with a stop at ₹{r['stop']:,.2f} if you decide it earns one")
    b = card.get("book") or {}
    live = f", {b['n_open']} still open ({', '.join(b.get('open_symbols') or [])})" if b.get("n_open") else ""
    out += ["", f"Day book: {b.get('n_trades', 0)} closed{live}, ₹{b.get('pnl_inr', 0):,.0f} realised on "
                f"₹{b.get('notional_inr', 0):,.0f} notional. Paper only."]
    return "\n".join(out)


def one_story(story: dict) -> str:
    """One hand-read story, scored — printed for the CLI and for the portal's paste box."""
    if story.get("error") and not story.get("candidates"):
        return f"# Could not use that story\n\n{story['error']}\n"
    out = [f"# {story.get('title') or 'Story'}", "",
           f"*read {story.get('read_at', '')} · {story.get('source_id', '')}"
           + (f" · [source]({story['url']})" if story.get("url") else "") + "*", ""]
    if story.get("read_during_session"):
        out += ["> **Read during the session.** " + story["read_during_session"], ""]
    cands = story.get("candidates") or []
    if not cands:
        out += [story.get("error") or "No NSE name implicated.", ""]
        return "\n".join(out)
    lead = cands[0]
    verdicts = ", ".join(f"{c['symbol']} {c.get('verdict')}"
                         + (f" ({c['catalyst']})" if c.get("catalyst") is not None else "")
                         for c in cands[:4])
    out[0] = f"# {lead['symbol']} {lead.get('verdict')} — {story.get('title') or 'story'}"
    out.insert(3, f"**{verdicts}**")
    out.insert(4, "")
    for i, c in enumerate(cands, 1):
        if c.get("catalyst") is None:
            out += [f"### {i}. {c['symbol']} — {c.get('verdict_note') or 'not scored'}", ""]
            continue
        out += [preopen_card(c, i)]
    return "\n".join(out)
