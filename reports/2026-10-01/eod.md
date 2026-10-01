# End-of-day ledger update — Thu 01 Oct 2026, 15:46 IST

Equity ₹97,078 (-2.92%) · cash ₹26,461 · realised ₹-4,834 · open 2 · hold 0 · closed 4 · win rate 0% · avg win None% / avg loss -3.78%

## Events
- HEROMOTOCO: STOP-LOSS @ 5140.67 → closed, P&L ₹-1171.65 (-4.36%)

## Source confidence changes
- `chartink_ema_pullback`: +0.0 → -15.0 (confidence 50 → 23)
- `chartink_squeeze`: -15.0 → -21.8 (confidence 23 → 15)

## What the ledger says works (all closed positions)
| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 4 | 0 | -3.78 |
| pattern=bollinger_squeeze | 4 | 0 | -3.78 |
| pattern=momentum_aligned | 4 | 0 | -3.78 |
| ta_conf=>=70 | 4 | 0 | -3.78 |
| fund=>=65 | 4 | 0 | -3.78 |
| pattern=pullback_to_ema20_in_uptrend | 3 | 0 | -4.20 |
| timeframe=monthly | 2 | 0 | -3.44 |

## Open book
| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |
|---|---|---|---|---|---|---|---|---|
| LALPATHLAB | open | 1881.4 | 2005.0999755859375 | 6.57% | 1860.75 | [] | 2026-10-20 | hold-capable |
| PETRONET | open | 285.1 | 285.5 | 0.14% | 276.86 | [] | 2026-11-11 | hold-capable |

## Recent lessons
ll (1403.5), not the planned entry (1435.7) -- the fill landing 2.2% below plan quietly tightened the effective stop from 4.7% to 2.51%, after price had touched +4.07% favourable. Pattern (bollinger_squeeze) and hold-capable fundamentals (87) were sound; reads as a fill-price artifact, not a bad call. chartink_squeeze now at n_resolved=1, score -15 -- one point, not evidence yet. fund-audit: no inversion, no bias (markets_mojo mean gap +6.5, under the 8pt bar); still unproven, only 1 settled in the 75-100 band.

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

### 2026-09-30 [analyst]
2026-09-30 desk review: only event was PETRONET fill 285.10 (plan 289.85, 1.6% below plan, gap-down fill; no stop/target hit). Book: LALPATHLAB +5.6% (T1 unhit), HEROMOTOCO -2.5% (stop 5140.67 is 1.9% away, inside ~1 ATR), PETRONET -0.2%. Still 0/3 closed, all hold-capable. fund-audit: no inversion, no bias (markets_mojo gap +6.5, under 8pt); only 1 settled in 75-100 band so fund score remains unproven. No source auto-disabled (max n_resolved=2); none at 60% T1 hit-rate. Not Friday: no new source added.

### 2026-10-01 [machine]
Events: HEROMOTOCO: STOP-LOSS @ 5140.67 → closed, P&L ₹-1171.65 (-4.36%)

| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 4 | 0 | -3.78 |
| pattern=bollinger_squeeze | 4 | 0 | -3.78 |
| pattern=momentum_aligned | 4 | 0 | -3.78 |
| ta_conf=>=70 | 4 | 0 | -3.78 |
| fund=>=65 | 4 | 0 | -3.78 |
| pattern=pullback_to_ema20_in_uptrend | 3 | 0 | -4.20 |
| timeframe=monthly | 2 | 0 | -3.44 |
