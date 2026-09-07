# stock-tips-system

A self-learning pipeline that gathers Indian stock tips from cluttered public sources, vets them with its own technical analysis, gives each an exact entry / stop-loss / three stepped targets, scores the source's track record, and paper-trades ₹1,00,000 in rotation — twice a day, unattended, from a scheduled Claude task.

**Status: paper trading.** Nothing here places real orders. The point of the first months is to build a track record you can trust (`state/ledger.json`, `state/sources_confidence.json`) before any broker integration.

## How a day works

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
config/sources.yaml      the source registry (add a source = add a YAML block; confidence starts at 0)
config/holidays.yaml     NSE holidays (verify each December)
state/                   the brain — committed on every run
  ledger.json            paper positions, closed trades, equity curve
  sources_confidence.json per-source score / hit-rates / expectancy / auto-disable
  lessons.md             machine + analyst lessons, appended daily
  universe_cache.json    NSE symbol master (weekly refresh, seed in data/EQUITY_L.csv)
reports/<date>/          tips_raw.json → tips_reviewed.json → tips_structured.json → analysis.json → picks.json → morning.md / eod.md
prompts/                 analyst_persona.md (loaded every run), morning_run.md, eod_run.md (the scheduled-task playbooks)
docs/                    static dashboard (GitHub Pages): index.html reads data.json — the book, suggestions, and the three controls that queue a CLI command
src/stocktips/           the package — data/, sources/, analysis/, portfolio/, learning/, pipeline.py, report.py, cli.py
tests/                   ledger lifecycle, extraction, plan geometry (no network)
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
python -m stocktips analyze-symbol TATASTEEL --tf weekly
python -m stocktips add-source --kind telegram --id tg_foo --channel foo --name "Telegram — @foo"
python -m stocktips lesson "Breakouts on 1.5x volume kept failing in a falling Nifty — require Nifty > 20EMA for breakout picks."
python -m pytest -q tests
```

## The scoring, in one paragraph

Every candidate gets three independent 0–100 numbers. **TA confidence** starts at 40 and earns/loses points for trend regime (EMA 20/50/200 stack), RSI zone, MACD slope, ADX, volume vs 20-day average, named patterns (60-day breakout on volume, pullback to 20-EMA in an uptrend, Bollinger squeeze, double bottom), reward:risk to T2, and kill-switches (overextended, gap day, illiquid, stop too wide, target below mandate). **Fundamentals** starts at 50 and moves with ROCE/ROE, P/E, 3-year sales and profit CAGR, debt/equity, promoter holding and its trend, pledges, last-quarter PAT and market cap (Screener.in). **Source confidence** is 50 for an untested source and moves with realised outcomes: +10 for T1, +5 each for T2/T3, −15 for a stop-loss, −6 for a losing time stop, with 5% decay per outcome so a source can redeem itself; a source with ≥ 8 outcomes and score < −40 is auto-disabled. Composite = 0.5·TA + 0.2·Fund + 0.3·Source; ≥ 65 BUY, ≥ 78 STRONG BUY. Capital is split across the top 3 in proportion to conviction above the threshold, capped at 50% per name.

## Targets and stops

Stops go a hair below the nearest qualifying swing support (≥ 0.6 ATR away, ≤ 8%), else 1.5 ATR (weekly) / 2.5 ATR (monthly). Targets go to successive swing resistances when one sits in the expected band, else 1.5 / 3 / 4.5 ATR (weekly) or 3 / 5 / 8 ATR (monthly); the 52-week high is a natural T3 when it is in reach. Exits are stepped 40/30/30 with the stop trailing to breakeven after T1 and to T1 after T2. A weekly idea that hasn't hit T1 in 10 trading days (30 for monthly) is time-stopped: exited if the fundamentals score is < 65 ("hot potato"), parked in the HOLD bucket if ≥ 65.

## The dashboard

`docs/index.html` is one self-contained page (vanilla JS, Chart.js from cdnjs, Newsreader + IBM Plex from
Google Fonts) reading `docs/data.json`. It separates the two things that must never be confused:

* **The book** — what the ledger actually tracks: pending, open and hold positions with entry, quantity,
  stop, T1/T2/T3 (a tick on each target already hit), last price, P&L, horizon and time-stop date. Every
  row opens into the scores it was booked on, its patterns, its exits and its notes.
* **Suggestions** — every BUY-grade name from the latest `analysis.json` that is *not* in the book,
  whether or not there is capital for it. Filterable by horizon, by what is affordable today, and by
  symbol or source. Each row opens into the TA reasons with their point contributions, the tape (RSI,
  ADX, ATR, volume, distance from the 52-week high), the fundamentals breakdown, and the tip itself —
  including a **Tipster said** column that carries the source's claimed target and stop and is never used
  as a level.

A figures band across the top carries equity, the time-weighted return, deployable cash, position count,
realised P&L and the per-stock ceiling.

### The three controls

GitHub Pages is static, so no button writes `state/ledger.json`. Each one checks the live caps, queues the
intent in `localStorage`, and prints the single command that commits it. The queue entry clears itself the
moment `data.json` comes back reflecting it, so the ledger is always the only source of truth.

| Control | Where | Command it prints |
|---|---|---|
| **Take** | a suggestion | `python -m stocktips book V2RETAIL --capital 19668` |
| **Exit** / **Cancel** | a position | `python -m stocktips close CGPOWER --note "..."` |
| **Add capital** | the figures band | `python -m stocktips capital --add 50000` |

### Capital and the honest return

`capital.total_inr` in settings.yaml only *seeds* a new ledger. After that `capital_inr` in
`state/ledger.json` is the live base, and it moves only through `stocktips capital`, which appends a dated
entry to `cash_flows`. Every percentage rule — 50% per stock, the 15% minimum position — is a percentage of
that live base, so a top-up widens them.

Return is **time-weighted**: each sub-period of the equity curve is chained against its own opening base,
where the base is the previous close plus whatever capital arrived since. Without that, adding ₹50,000 to a
₹1,00,000 book would read as a +50% day and every later number would be measured against the wrong base.
`stats()` also reports `simple_return_pct` beside it for reference.

### Discretionary exits

The plan's own exits — stop, stepped targets, time stop — run in the EOD run without you. `close` is for
the other case: freeing capital because a better idea arrived. A *pending* position was never filled, so it
is cancelled and its capital returned, and **no outcome is attributed to the source** — nothing happened.
An *open* or *hold* position is sold at the last close (or `--price`) and recorded as `manual_exit`: the
realised return counts towards the source's expectancy, but its score is left alone, because the tip did
not resolve — it was pre-empted.

## Adding sources

The system is only as good as its inputs. Kinds implemented: `gnews` (Google News RSS query, any publisher), `page` (a listing page), `rss`, `chartink` (a scan clause — system-generated candidates), `telegram` (public channel via `t.me/s/`). Planned: `youtube` (transcripts), `x`. Brokerages and named analysts found *inside* articles become sub-sources (`broker:motilal`, `broker:bagadia`) and are scored separately from the paper that carried the call.

## Going live (later)

Only when the paper ledger shows a positive expectancy over a meaningful sample. The natural path is Zerodha Kite Connect (`kiteconnect` Python SDK): the morning run would place CNC limit orders at the entry zone with a GTT OCO for stop and T1, and the EOD run would reconcile fills against the ledger. That layer is intentionally absent from this repo today.

_Not investment advice. Paper trading only._
