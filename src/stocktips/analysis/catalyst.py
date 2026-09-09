"""How much a piece of news is worth, in one number, with the arithmetic shown.

The desk owner read the GE Vernova story at mid-morning and the move was gone. The judgement was
never the problem — strong balance sheet, enormous order, obvious re-rating. What was missing was a
number on a page at 08:00 saying *this one, today, before the open*. This module is that number.

Additive, every term carrying its reason in words, in the same shape as `build_plan`'s `reasons`, so
the email explains itself and a wrong call can be traced to the line that caused it:

    event class      what happened, and how firm it is
    materiality      the order against a year of the company's own revenue — the biggest term
    fundamentals     a pop on a weak balance sheet fades; on a strong one it re-rates
    the chart        near a breakout helps; below the 200-day and already-run hurt
    freshness        overnight is the whole product; yesterday afternoon is a trap
    corroboration    two independent desks reporting it beats one
    liquidity        a veto, not a penalty — a position you cannot exit is not a position

Nothing here reads a price target out of the news, because corporate news does not carry one. The
levels come from `analysis.intraday`, off the chart.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_T, CLOSE_T = time(9, 15), time(15, 30)

TRADE_AT = 62
WATCH_AT = 45

# Materiality bands: order value ÷ trailing twelve months of revenue. ₹13,000cr against ₹3,900cr of
# revenue is 3.3 years of sales arriving in one letter, and that ratio — not the rupee number — is
# what moves a stock 9%. The same order at Larsen & Toubro would be a rounding error.
MATERIALITY = [
    (1.00, 26, "more than a full year of revenue"),
    (0.50, 18, "over half a year of revenue"),
    (0.25, 12, "a quarter of a year's revenue"),
    (0.10, 7, "a tenth of a year's revenue"),
    (0.00, 2, "small against revenue"),
]
MIN_TURNOVER_CR = 5.0        # below this the exit is worse than the entry
MIN_PRICE = 20.0


def _band(ratio: float) -> tuple[int, str]:
    for floor, points, words in MATERIALITY:
        if ratio >= floor:
            return points, words
    return 0, "immaterial"


def freshness(published_utc: str | None, now: datetime | None = None) -> dict:
    """Where the news landed against the market clock — which is most of whether it is tradable.

    An order win on the wire at 19:40 is a gift: the whole move is still ahead of the open. The same
    story republished at 11:00 the next day looks identical in an RSS feed and is a trap. So this is
    not a tiebreaker in the score, it is close to the whole score.
    """
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    if not published_utc:
        return {"points": -6, "window": "unknown", "why": "no publication time on the story"}
    try:
        pub = datetime.fromisoformat(str(published_utc).replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        return {"points": -6, "window": "unknown", "why": "unreadable publication time"}

    age_h = (now - pub).total_seconds() / 3600
    if age_h < 0:
        return {"points": 0, "window": "future", "why": "publication time is in the future"}
    if age_h > 36:
        return {"points": -20, "window": "stale", "why": f"{age_h / 24:.1f} days old"}

    at = pub.time()
    during_session = OPEN_T <= at <= CLOSE_T
    if during_session:
        # priced in during that session; only worth anything if that session was long enough ago to
        # have been a small move, and even then it is a fade risk
        return {"points": -8, "window": "in-session",
                "why": f"published {pub:%H:%M} during the session — the market has already seen it"}
    if age_h <= 18:
        return {"points": 12, "window": "overnight",
                "why": f"published {pub:%a %H:%M}, outside market hours — the move is still ahead of the open"}
    return {"points": 4, "window": "overnight-old",
            "why": f"published {pub:%a %H:%M} outside market hours, {age_h:.0f}h ago"}


def score(event: dict, *, fundamentals: dict | None = None, fund_score: int | None = None,
          ta: dict | None = None, class_prior: float | None = None, source_weight: float = 0.5,
          now: datetime | None = None) -> dict:
    """→ {catalyst, verdict, reasons, materiality_ratio, ...}. Pure arithmetic on what it is given."""
    f = fundamentals or {}
    t = ta or {}
    reasons: list[str] = []
    points = 0.0

    def add(p: float, why: str):
        nonlocal points
        points += p
        reasons.append(f"{p:+.0f} {why}" if p else f" 0 {why}")

    # ---------------------------------------------------------------- the event
    prior = class_prior if class_prior is not None else event.get("event_prior", 0)
    certainty = float(event.get("certainty") or 1.0)
    directness = float(event.get("directness") or 1.0)
    base = prior * certainty * directness
    words = event.get("event_label", event.get("event", "event"))
    detail = []
    if certainty < 1:
        detail.append(f"{certainty:.0%} firm")
    if directness < 1:
        detail.append(f"{event.get('route', 'indirect')} at {directness:.0%}")
    add(base, words + (f" ({', '.join(detail)})" if detail else ""))

    # ---------------------------------------------------------------- materiality
    size = event.get("size_inr_cr")
    revenue = f.get("revenue_ttm_cr")
    ratio = None
    if size and not event.get("size_is_own_order", True):
        # the order belongs to the company this one is a peer of, so there is no ratio to take
        add(0, f"₹{size:,.0f}cr, but that is the order the winner took — this name is a peer, so "
               f"there is no materiality to measure against its own revenue")
        size = None
    elif size and revenue and revenue > 0:
        ratio = size / revenue
        pts, band = _band(ratio)
        est = " (estimated from capacity)" if event.get("size_estimated") else ""
        add(pts * directness, f"₹{size:,.0f}cr against ₹{revenue:,.0f}cr of revenue — {ratio:.1f}× a year's "
                              f"sales, {band}{est}")
    elif size and f.get("market_cap_cr"):
        ratio_mc = size / f["market_cap_cr"]
        pts = 14 if ratio_mc >= 0.25 else 8 if ratio_mc >= 0.10 else 3
        add(pts * directness, f"₹{size:,.0f}cr is {ratio_mc:.0%} of market cap (no revenue figure, so "
                              f"market cap is standing in)")
    elif size:
        add(4, f"₹{size:,.0f}cr, but nothing to measure it against")
    else:
        add(0, "no size in the announcement and none estimable — materiality unknown")

    # ---------------------------------------------------------------- the company
    if fund_score is not None:
        add(10 if fund_score >= 70 else 4 if fund_score >= 50 else -10 if fund_score < 40 else 0,
            f"fundamentals {fund_score}/100" +
            (" — a pop on a weak balance sheet fades" if fund_score < 40 else ""))

    # ---------------------------------------------------------------- the chart
    veto = None
    if t:
        turnover = t.get("avg_turnover_cr")
        if turnover is not None and turnover < MIN_TURNOVER_CR:
            veto = f"20-day turnover ₹{turnover:.1f}cr — too thin to exit at the plan's prices"
        chg1 = t.get("chg_1d_pct")
        if chg1 is not None and chg1 >= 6:
            add(-14, f"already up {chg1:.1f}% in the last session — the move may be behind you")
        elif chg1 is not None and chg1 <= -4:
            add(3, f"down {abs(chg1):.1f}% into the news — less crowded")
        d52 = t.get("dist_52w_high_pct")
        if d52 is not None and abs(d52) <= 3 and (t.get("vol_ratio") or 0) >= 1.2:
            add(8, f"{abs(d52):.1f}% from the 52-week high on {t['vol_ratio']:.1f}× volume — breakout-ready")
        e200 = t.get("dist_ema200_pct")
        if e200 is not None and e200 < 0:
            add(-6, f"{abs(e200):.1f}% below the 200-day average — fighting the trend")
        if (t.get("adx") or 0) >= 25 and str(t.get("trend", "")).endswith("up"):
            add(5, f"ADX {t['adx']:.0f} with the trend up — moves carry here")
        if t.get("close") is not None and t["close"] < MIN_PRICE:
            veto = f"₹{t['close']:.2f} a share — below the desk's price floor"

    # ---------------------------------------------------------------- when it landed
    fr = freshness(event.get("published_utc"), now)
    add(fr["points"], fr["why"])

    # ---------------------------------------------------------------- who else said it
    n_extra = len(event.get("corroborating_sources") or [])
    if n_extra:
        add(min(6, 3 * n_extra), f"reported independently by {n_extra} other source"
                                 f"{'s' if n_extra > 1 else ''}")
    if source_weight is not None and source_weight != 0.5:
        add(round((source_weight - 0.5) * 12, 1),
            f"{event.get('source_id', 'source')} has earned a weight of {source_weight:.2f}")

    catalyst = int(round(max(-100, min(100, points))))
    negative = (event.get("sign") or 1) < 0

    if veto:
        verdict, note = "SKIP", veto
    elif negative:
        verdict, note = "AVOID", "a negative catalyst — do not buy this today, and exit it if you hold it"
    elif catalyst >= TRADE_AT:
        verdict, note = "TRADE", "worth a plan for the open"
    elif catalyst >= WATCH_AT:
        verdict, note = "WATCH", "real but not enough on its own — watch how it opens"
    else:
        verdict, note = "SKIP", "not enough to act on"

    return {
        "catalyst": catalyst, "verdict": verdict, "verdict_note": note, "reasons": reasons,
        "materiality_ratio": round(ratio, 3) if ratio else None,
        "revenue_ttm_cr": revenue, "size_inr_cr": size, "size_estimated": event.get("size_estimated", False),
        "freshness": fr, "veto": veto, "class_prior_used": prior,
        "direction": "short" if negative else "long",
    }
