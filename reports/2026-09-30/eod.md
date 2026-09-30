# End-of-day ledger update — Wed 30 Sep 2026, 15:47 IST

Equity ₹97,167 (-2.83%) · cash ₹758 · realised ₹-3,662 · open 3 · hold 0 · closed 3 · win rate 0% · avg win None% / avg loss -3.59%

## Events
- PETRONET: FILLED 142 @ 285.1000061035156 (plan 289.85); SL 276.86, T [307.19, 318.75, 326.4], deadline 2026-11-11

## Source confidence changes
- none

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
| LALPATHLAB | open | 1881.4 | 1987.0 | 5.61% | 1860.75 | [] | 2026-10-20 | hold-capable |
| HEROMOTOCO | open | 5375.0 | 5241.0 | -2.49% | 5140.67 | [] | 2026-10-13 | hold-capable |
| PETRONET | open | 285.1 | 284.5 | -0.21% | 276.86 | [] | 2026-11-11 | hold-capable |

## Recent lessons
outed a bogus 'Broker downgrade' to BHEL/THERMAX/TRITURBINE/LT. All 8 events stripped from today's news_raw.json before publish (backup kept alongside). This is a code fix, not a hand-edit: solar_manufacturing needs 'gw' gated on a solar-specific co-occurring term, and power_generation's 'nuclear' keyword needs narrowing (e.g. 'nuclear power plant'/'nuclear reactor') or a require: clause like solar_manufacturing already has, plus a regression fixture on this Suzlon/Iran-war pair in tests/test_events (or wherever theme routing is tested).

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

### 2026-09-29 [analyst]
2026-09-29 desk review: CGPOWER stop-loss @855.9 (-4.36%, 3rd straight hold-capable/bollinger_squeeze loss; 0/3 wins, n too small to change rules). Pattern failure vs noise not verified against ATR; fund score (>=65) has not earned its keep yet: fund-audit shows 0 inversion, no bias (markets_mojo gap +6.5 <8pt), still only 1 settled in 75-100 band. HEROMOTOCO filled 5375 (plan 5390), already -3.1% on day one. Motilal (-29, conf 9) and brokerage_gnews (-14.6) keep taking hits; none auto-disabled (n_resolved<8). No source at >=60% T1 hit-rate.
