# The intraday desk — design

*Written 8 Sep 2026, from one trade that got away.*

## What actually happened

On 7 September, Power Grid issued the letter naming **GE Vernova T&D India** (`GVT&D`) L1 bidder for
a 6,000 MW ±800 kV HVDC terminal station at Barmer II. No rupee value in the announcement. The stock
rose 7.4% that day. On 8 September, Nomura put the contract at **₹12,980 crore** and raised its
target; the stock opened higher, ran to about +12%, and closed around +9% on the day.

The desk owner read the story mid-morning on the 8th, after the move.

**That was a timing loss, not an analysis loss.** The judgement was right — strong balance sheet,
enormous order, obvious re-rating. What was missing was a piece of paper on the desk at 08:00 saying
so. That is the whole product.

## The signal has a clock

Everything about whether this is tradable is *when the news landed*:

```
15:30 IST ─────────── overnight ─────────── 09:15 IST ────── session ────── 15:30 IST
           ▲ the entire move is still ahead of you        ▲ you are chasing
           └── this is the only window worth an email ────┘
```

An order win published at 19:40 is a gift; the same story republished at 11:00 the next day is a
trap that looks identical in an RSS feed. So freshness is not a tiebreaker in the score — it is
close to the whole score. A **pre-open run at 08:00 IST** is the deliverable. Everything else in
this document exists to make that one email trustworthy.

## Four problems the positional pipeline does not solve

The existing pipeline reads press *recommendations* — "buy X, target Y, stop Z" — and its whole
extractor is built around those three numbers. Corporate news has none of them.

**1. Events, not recommendations.** `sources/events.py` looks for a different shape: who, what
happened, how big, how sure. "Emerges as L1 bidder" is an event class of its own — in Indian PSU
tendering L1 converts to an order almost always, but not certainly, so it carries a certainty
weight rather than being treated as signed.

**2. The named company is often not the tradable one.** The headline says *Power Grid secures the
project*. POWERGRID is a ₹3 lakh crore utility that will not move 9% on a ₹26,000cr capex plan. The
name that moves is the one that *supplies the HVDC terminal* — GVT&D, and behind it POWERINDIA,
SIEMENS, ABB. `config/themes.yaml` encodes that: event keyword → the theme → the NSE names that
actually trade on it, each with a directness weight. This file is the system's domain knowledge and
it is meant to grow every time a story teaches it something.

**3. Size is often absent, and always relative.** GVT&D's announcement gave a capacity, not a value.
So themes carry a **cost-per-unit** rule (an HVDC LCC terminal runs about ₹2.1 crore per MW), which
turns "6,000 MW" into "≈₹12,600cr" — within 3% of Nomura's number, from the capacity alone. Then
what matters is not the rupees but the ratio: **order value ÷ trailing annual revenue**. ₹13,000cr
against roughly ₹3,900cr of revenue is 3.3 years of sales in one letter. The same order at Larsen &
Toubro would be a rounding error. Materiality is the single biggest term in the score, and when it
cannot be computed the run says so instead of guessing high.

**4. A good story on a bad chart is still a bad trade.** Fundamentals gate it (the user's "strong
foundation" — `fundamentals.score` already exists), the daily chart contextualises it, and
liquidity vetoes it: below about ₹5cr of daily turnover the position cannot be exited at the price
the plan assumes, so it is not a candidate at any score.

## Scoring a catalyst

Additive, with every term carrying its reason in words — the same house style as `build_plan`, so
the email explains itself and a wrong call can be traced to a line.

```
event class          order win +30 · L1 bidder +24 · approval +26 · earnings beat +22
                     upgrade +10 · MoU +12 · index inclusion +18
                     and the negatives: QIP −16 · pledge −18 · downgrade −14 · raid −22
materiality          ≥1.0× revenue +26 · 0.5–1.0× +18 · 0.25–0.5× +12 · <0.10× +2 · unknown 0
fundamentals         score ≥70 +10 · 50–69 +4 · <40 −10
chart context        near 52w high on volume +8 · below 200EMA −6 · already ran >6% yesterday −14
freshness            overnight +12 · during yesterday's session −8 · older than 36h −20
corroboration        a second independent publisher on the same event +6
liquidity            under ₹5cr/day turnover — veto, not a penalty
```

`TRADE` at 62, `WATCH` at 45, `SKIP` below, `AVOID` for the negative classes — and `AVOID` is
actionable, because it means *do not buy this today and exit it if you hold it*.

## The plan that stops you buying the top

This is the part that would have changed the 8th. The system does not say "buy GVT&D". It hands over
a rule keyed on what the open actually does, because a +11% gap and a +1% gap are not the same trade:

```
gap ≤ +2%     buy the break of the first 15-minute high; stop under the 15-minute low
gap +2 to +5% same, but only if those 15 minutes close in the top third on >3× average volume
gap > +5%     NO fresh entry at the open. Either a pullback that reclaims VWAP, or nothing.
```

The third line is the discipline. GVT&D gapped hard and topped at +12% within the first hour;
buying the open would have been buying that top. Waiting for a VWAP reclaim either gets a real entry
or keeps the money.

Targets are measured moves off the opening range rather than round percentages, the stop is never
wider than 1.5%, and everything is flat by 15:10 — intraday means intraday, and an unclosed day
trade is how a small loss becomes a position.

## Training it

Every candidate is graded at the close on what it actually did: the gap, open→high, open→close,
whether the trigger fired, and whether T1 or the stop came first. Those outcomes move two sets of
scores using the decay-and-tanh machinery the tip sources already use:

* **the news source** — `sahi.com` and Business Standard's capital-market wire are not equally
  early or equally right, and after thirty events the file will say which;
* **the event class** — the priors above are my estimates. They are seeded, not fixed. If "MoU"
  turns out to be worth nothing and "index inclusion" turns out to be worth a lot, the numbers move
  and the emails change with them.

That is what training means here: no model to fit, just an honest ledger of what each kind of news
was worth, kept in git.

## Routines are the infrastructure

Four new ones, each reading its playbook from the repo so the schedule can change without editing
the trigger:

```
08:00 IST   preopen          read overnight news → rank → EMAIL. the deliverable.
09:35 IST   intraday         the real gap and opening range; triggered / waiting / voided
11:30 IST   intraday         trail stops, note exits
15:20 IST   intraday --close force flat, grade the classes and the sources
```

Cron will not go below hourly, but nothing here needs to: separate triggers at chosen minutes give
exactly the four moments that matter. The existing 08:15 morning and 15:45 EOD runs are untouched.

## Should this move off GitHub Pages?

The honest answer tonight is **no, and here is the line that would change it.**

What the product needs is an email at 08:00 and a page that shows the plan and how it went. A
routine sends the email; a static page reads a committed JSON. Pages costs nothing, every change is
a diff with history, the page opens on a phone, and there is no server to wake up at 07:55 and no
credential sitting on a box. Adding a server buys nothing for the 08:00 email — which is the part
that would have made money on the 8th.

Three things, and only these three, would force a move:

1. **Sub-minute reaction.** If the strategy becomes "be in within 90 seconds of the wire", a
   cron-driven runner is the wrong shape and a long-lived process watching a websocket is the right
   one. Note that this is a *different strategy*, not a faster version of this one.
2. **Live quotes in the page during the session.** Today the page shows what the last routine
   committed, so during the session it is as stale as the last check (09:35, 11:30, 15:20). Refresh
   at will costs a small always-on endpoint holding a broker or vendor feed.
3. **Real orders.** A Zerodha API key cannot live in a browser's localStorage, and it should not
   live in a GitHub secret either. Placing orders means a server with a vault, and it also means
   this stops being paper trading — a much bigger decision than a hosting one.

Until one of those is actually wanted, a server would add an ops surface, a monthly bill and a
secret to rotate, in exchange for nothing the 08:00 email needs. If tomorrow the answer to "did the
email arrive before the open, and was it right?" is yes twice, the hosting question is settled for a
while.

## What cannot be verified from this session

This container's egress proxy refuses every market-data host — Yahoo, Moneycontrol, Screener,
sahi.com — so nothing here was tested against live prices or a live fetch. Everything is built
against fixtures, including the 7 September GVT&D story replayed end to end as a regression test.
The routine environment has the network access this one lacks, which is why tomorrow's 08:00 run is
the real first test. Two things to watch on that run: symbols containing `&` (`GVT&D`, `M&M`) going
into URLs unquoted, and whether the intraday 5-minute endpoint returns enough history pre-open.
