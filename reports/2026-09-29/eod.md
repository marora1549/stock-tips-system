# End-of-day ledger update — Tue 29 Sep 2026, 15:47 IST

Equity ₹96,538 (-3.46%) · cash ₹41,242 · realised ₹-3,662 · open 2 · hold 0 · closed 3 · win rate 0% · avg win None% / avg loss -3.59%

## Events
- CGPOWER: STOP-LOSS @ 855.9 → closed, P&L ₹-1755.0 (-4.36%)
- HEROMOTOCO: FILLED 5 @ 5375.0 (plan 5390.0); SL 5140.67, T [5551.39, 5803.0, 5937.0], deadline 2026-10-13

## Source confidence changes
- `broker:motilal`: -15.0 → -29.2 (confidence 23 → 9)
- `brokerage_gnews`: -7.5 → -14.6 (confidence 35 → 24)

## What the ledger says works (all closed positions)
| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 3 | 0 | -3.59 |
| pattern=bollinger_squeeze | 3 | 0 | -3.59 |
| pattern=momentum_aligned | 3 | 0 | -3.59 |
| ta_conf=>=70 | 3 | 0 | -3.59 |
| fund=>=65 | 3 | 0 | -3.59 |
| pattern=pullback_to_ema20_in_uptrend | 2 | 0 | -4.12 |
| timeframe=monthly | 2 | 0 | -3.44 |

## Open book
| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |
|---|---|---|---|---|---|---|---|---|
| LALPATHLAB | open | 1881.4 | 1950.4000244140625 | 3.67% | 1860.75 | [] | 2026-10-20 | hold-capable |
| HEROMOTOCO | open | 5375.0 | 5208.0 | -3.11% | 5140.67 | [] | 2026-10-13 | hold-capable |

## Recent lessons
for looking same-day. Dropped from trade after WebFetch confirmed the original publish date; the market has had 11 weeks to price it, and the chart (strong_down, 37.9% off 52w high) is consistent with stale news, not a fresh beat. Also found two theme-routing bugs polluting AVOID: solar_manufacturing's ' gw ' keyword matched Suzlon's (wind) '6.1 GW record deliveries' phrase and sympathy-routed WAAREEENER/PREMIERENE/WEBELSOLAR, which had nothing to do with Suzlon's results; power_generation's 'nuclear' keyword matched an unrelated Trump/Iran-war geopolitics story and routed a bogus 'Broker downgrade' to BHEL/THERMAX/TRITURBINE/LT. All 8 events stripped from today's news_raw.json before publish (backup kept alongside). This is a code fix, not a hand-edit: solar_manufacturing needs 'gw' gated on a solar-specific co-occurring term, and power_generation's 'nuclear' keyword needs narrowing (e.g. 'nuclear power plant'/'nuclear reactor') or a require: clause like solar_manufacturing already has, plus a regression fixture on this Suzlon/Iran-war pair in tests/test_events (or wherever theme routing is tested).

### 2026-09-28 [machine]
Events: KPIL: STOP-LOSS @ 1368.22 → closed, P&L ₹-740.88 (-2.51%)

| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 2 | 0 | -3.20 |
| pattern=bollinger_squeeze | 2 | 0 | -3.20 |
| pattern=momentum_aligned | 2 | 0 | -3.20 |
| ta_conf=>=70 | 2 | 0 | -3.20 |
| fund=>=65 | 2 | 0 | -3.20 |

### 2026-09-28 [analyst]
KPIL: stop hit in 8 days, only 0.94 ATR from the actual gap-down fill (1403.5), not the planned entry (1435.7) -- the fill landing 2.2% below plan quietly tightened the effective stop from 4.7% to 2.51%, after price had touched +4.07% favourable. Pattern (bollinger_squeeze) and hold-capable fundamentals (87) were sound; reads as a fill-price artifact, not a bad call. chartink_squeeze now at n_resolved=1, score -15 -- one point, not evidence yet. fund-audit: no inversion, no bias (markets_mojo mean gap +6.5, under the 8pt bar); still unproven, only 1 settled in the 75-100 band.

### 2026-09-29 [machine]
Events: CGPOWER: STOP-LOSS @ 855.9 → closed, P&L ₹-1755.0 (-4.36%)

| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 3 | 0 | -3.59 |
| pattern=bollinger_squeeze | 3 | 0 | -3.59 |
| pattern=momentum_aligned | 3 | 0 | -3.59 |
| ta_conf=>=70 | 3 | 0 | -3.59 |
| fund=>=65 | 3 | 0 | -3.59 |
| pattern=pullback_to_ema20_in_uptrend | 2 | 0 | -4.12 |
| timeframe=monthly | 2 | 0 | -3.44 |
