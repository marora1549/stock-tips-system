# End-of-day ledger update — Mon 28 Sep 2026, 15:47 IST

Equity ₹97,658 (-2.34%) · cash ₹29,601 · realised ₹-1,907 · open 2 · hold 0 · closed 2 · win rate 0% · avg win None% / avg loss -3.2%

## Events
- KPIL: STOP-LOSS @ 1368.22 → closed, P&L ₹-740.88 (-2.51%)

## Source confidence changes
- `chartink_squeeze`: +0.0 → -15.0 (confidence 50 → 23)

## What the ledger says works (all closed positions)
| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 2 | 0 | -3.20 |
| pattern=bollinger_squeeze | 2 | 0 | -3.20 |
| pattern=momentum_aligned | 2 | 0 | -3.20 |
| ta_conf=>=70 | 2 | 0 | -3.20 |
| fund=>=65 | 2 | 0 | -3.20 |

## Open book
| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |
|---|---|---|---|---|---|---|---|---|
| CGPOWER | open | 894.9 | 865.0 | -3.34% | 855.9 | [] | 2026-10-20 | hold-capable |
| LALPATHLAB | open | 1881.4 | 1942.0999755859375 | 3.23% | 1860.75 | [] | 2026-10-20 | hold-capable |

## Recent lessons
75-100 band still 1 scored, 0 settled, unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated. Book full at 3 open, cash Rs869, no new picks regardless.

### 2026-09-25 [analyst]
2026-09-25 (Friday input growth): registered chartink_double_bottom at confidence 0 -- the 5 existing screener sources (52w breakout, EMA20 pullback, Bollinger squeeze, RSI oversold bounce, volume shock) are all single-leg momentum/consolidation setups; the persona names confirmed double bottom as a valid pattern but nothing screens it. Clause: current low within 3% of a prior low over a 30-day lookback, breakout above the interim high on >1.3x 20d avg volume, liquid cash names only (>Rs5cr 20d turnover), price > Rs20. No login/payment required (public Chartink scan).

### 2026-09-28 [analyst]
2026-09-28 (preopen): the only TRADE-grade catalyst, TCS 'earnings beat', was a stale story -- Goodreturns republished its July 9 2026 Q1FY27 results piece with a Sept 27 dateline, and freshness scoring gave it +12 for looking same-day. Dropped from trade after WebFetch confirmed the original publish date; the market has had 11 weeks to price it, and the chart (strong_down, 37.9% off 52w high) is consistent with stale news, not a fresh beat. Also found two theme-routing bugs polluting AVOID: solar_manufacturing's ' gw ' keyword matched Suzlon's (wind) '6.1 GW record deliveries' phrase and sympathy-routed WAAREEENER/PREMIERENE/WEBELSOLAR, which had nothing to do with Suzlon's results; power_generation's 'nuclear' keyword matched an unrelated Trump/Iran-war geopolitics story and routed a bogus 'Broker downgrade' to BHEL/THERMAX/TRITURBINE/LT. All 8 events stripped from today's news_raw.json before publish (backup kept alongside). This is a code fix, not a hand-edit: solar_manufacturing needs 'gw' gated on a solar-specific co-occurring term, and power_generation's 'nuclear' keyword needs narrowing (e.g. 'nuclear power plant'/'nuclear reactor') or a require: clause like solar_manufacturing already has, plus a regression fixture on this Suzlon/Iran-war pair in tests/test_events (or wherever theme routing is tested).

### 2026-09-28 [machine]
Events: KPIL: STOP-LOSS @ 1368.22 → closed, P&L ₹-740.88 (-2.51%)

| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 2 | 0 | -3.20 |
| pattern=bollinger_squeeze | 2 | 0 | -3.20 |
| pattern=momentum_aligned | 2 | 0 | -3.20 |
| ta_conf=>=70 | 2 | 0 | -3.20 |
| fund=>=65 | 2 | 0 | -3.20 |
