# End-of-day ledger update — Tue 03 Nov 2026, 15:46 IST

Equity ₹99,699 (-0.3%) · cash ₹11,193 · realised ₹-5,144 · open 3 · hold 0 · closed 5 · win rate 0% · avg win None% / avg loss -3.24%

## Events
- nothing happened in the book today

## Source confidence changes
- none

## What the ledger says works (all closed positions)
| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 5 | 0 | -3.24 |
| pattern=bollinger_squeeze | 5 | 0 | -3.24 |
| ta_conf=>=70 | 5 | 0 | -3.24 |
| fund=>=65 | 5 | 0 | -3.24 |
| pattern=momentum_aligned | 4 | 0 | -3.78 |
| pattern=pullback_to_ema20_in_uptrend | 4 | 0 | -3.43 |
| timeframe=monthly | 3 | 0 | -2.66 |

## Open book
| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |
|---|---|---|---|---|---|---|---|---|
| PETRONET | open | 285.1 | 303.0 | 6.28% | 276.86 | [] | 2026-11-11 | hold-capable |
| KOTAKBANK | open | 418.0 | 464.6499938964844 | 11.16% | 418.0 | [1] | 2026-11-16 | hold-capable |
| PNB | open | 122.5 | 120.97000122070312 | -1.25% | 113.95 | [] | 2026-12-02 | hot-potato |

## Recent lessons
026-10-28 [analyst]
2026-10-28 desk review: quiet day, no stops/targets/time-stops. PETRONET -0.1% (hold-capable, gave back its +3.8% from yesterday), KOTAKBANK +5.3% (hold-capable, T1 unhit), PNB -1.8% (hot-potato, entry 122.5, stop 113.95); equity 95,710 (-4.3%), cash -137, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled at -3.4%, too few to grade. chartink_squeeze -35.7 (n=3), 4 pts from auto-disable; none auto-disabled, none at 60% T1. Wednesday: no new source.

### 2026-10-29 [machine]
Events: KOTAKBANK: T1 HIT @ 453.2 — booked 25 sh (+₹880.0), SL → 418.0

| factor | n | win% | avg ret% |
|---|---|---|---|
| bucket=hold-capable | 5 | 0 | -3.24 |
| pattern=bollinger_squeeze | 5 | 0 | -3.24 |
| ta_conf=>=70 | 5 | 0 | -3.24 |
| fund=>=65 | 5 | 0 | -3.24 |
| pattern=momentum_aligned | 4 | 0 | -3.78 |
| pattern=pullback_to_ema20_in_uptrend | 4 | 0 | -3.43 |
| timeframe=monthly | 3 | 0 | -2.66 |

### 2026-10-29 [analyst]
2026-10-29 desk review: KOTAKBANK T1 @453.2 (25sh +880), stop→418 breakeven, 38sh open; PETRONET +1.4%, PNB +1.1%. LEDGER BUG: partial exits never credited cash, so equity read 86,861 (-13.1%) vs true 98,191 (-1.8%); fixed _close/T-exit to credit proceeds at partial exit, cash +11,330 corrected. Earlier -4% equity readings were unaffected (no partials before today). fund-audit: no inversion, no bias, 75-100 band 2 settled -3.4%, too few to grade. No source auto-disabled. Thursday: no new source.

### 2026-10-30 [analyst]
2026-10-30 desk review: quiet day, no stops/targets/time-stops. PETRONET +1.5%, KOTAKBANK +10.4% (hold-capable, T1 hit 29 Oct, stop at breakeven 418), PNB +0.3% (hot-potato); equity 98,098 (-1.9%), cash 11,193, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled -3.4%, too few to grade. chartink_squeeze -35.7 (n=3) still enabled; none auto-disabled. Friday: added tg_stockpro_online (public, no login, active feed) at confidence 0 to widen input side.

### 2026-11-02 [analyst]
2026-11-02 desk review: quiet day, no stops/targets/time-stops. PETRONET +5.6% (hold-capable, T1 unhit), KOTAKBANK +9.7% (T1 hit 29 Oct, stop at breakeven 418), PNB +0.5% (hot-potato); equity 99,649 (-0.35%), cash 11,193, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled -3.4%, too few to grade. No source auto-disabled, none at 60% T1. Monday: no new source.
