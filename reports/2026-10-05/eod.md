# End-of-day ledger update — Mon 05 Oct 2026, 15:46 IST

Equity ₹97,084 (-2.92%) · cash ₹127 · realised ₹-4,834 · open 3 · hold 0 · closed 4 · win rate 0% · avg win None% / avg loss -3.78%

## Events
- KOTAKBANK: FILLED 63 @ 418.0 (plan 418.35); SL 407.2, T [453.2, 466.4, 488.75], deadline 2026-11-16

## Source confidence changes
- none

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
| LALPATHLAB | open | 1881.4 | 1971.300048828125 | 4.78% | 1860.75 | [] | 2026-10-20 | hold-capable |
| PETRONET | open | 285.1 | 290.0 | 1.72% | 276.86 | [] | 2026-11-11 | hold-capable |
| KOTAKBANK | open | 418.0 | 416.0 | -0.48% | 407.2 | [] | 2026-11-16 | hold-capable |

## Recent lessons
 | 3 | 0 | -3.59 |
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

### 2026-10-01 [analyst]
2026-10-01 desk review: HEROMOTOCO stop 5140.67 (-4.36%), 4th straight hold-capable loss (0/4). Stop was ~1.9% away, inside ~1 ATR, so noise-sized; the fill 5375 sat under plan 5390 and price faded from day one, so the pattern (momentum_aligned/pullback) gave no follow-through and the tip likely arrived after the move. Fund score (>=65) not yet earning its keep: 0% hit in 75-100 band, 2 settled, too few to call. fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt). chartink_ema_pullback -15, chartink_squeeze -21.8; Motilal -29 and brokerage_gnews -14.6 lag, none auto-disabled (n_resolved<8). No source at >=60% T1. Thursday: no new source.
