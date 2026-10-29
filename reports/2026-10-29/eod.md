# End-of-day ledger update — Thu 29 Oct 2026, 15:48 IST

Equity ₹98,191 (-1.81%) · cash ₹11,193 · realised ₹-5,144 · open 3 · hold 0 · closed 5 · win rate 0% · avg win None% / avg loss -3.24%

## Events
- KOTAKBANK: T1 HIT @ 453.2 — booked 25 sh (+₹880.0), SL → 418.0

## Source confidence changes
- `broker:pl`: +0.0 → +10.0 (confidence 50 → 69)
- `mc_stock_ideas_gnews`: -7.5 → -2.1 (confidence 35 → 46)

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
| PETRONET | open | 285.1 | 289.1499938964844 | 1.42% | 276.86 | [] | 2026-11-11 | hold-capable |
| KOTAKBANK | open | 418.0 | 459.0 | 9.81% | 418.0 | [1] | 2026-11-16 | hold-capable |
| PNB | open | 122.5 | 123.9000015258789 | 1.14% | 113.95 | [] | 2026-12-02 | hot-potato |

## Recent lessons
e-stops. PETRONET +0.4%, KOTAKBANK +3.0% (hold-capable, T1 unhit), PNB -1.7% (hot-potato, entry 122.5 vs LTP 120.37, stop 113.95); equity 95,324 (-4.7%), cash -137, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled at -3.4%, too few to grade. chartink_squeeze -35.7 (n=3), 4 pts from auto-disable; none auto-disabled, none at 60% T1. Friday: added tg_stockmarketindia_official at confidence 0 (public, no login; mostly generic levels/F&O-ban posts, so expect low yield).

### 2026-10-26 [analyst]
2026-10-26 desk review: quiet day, no stops/targets/time-stops. PETRONET +2.3%, KOTAKBANK +5.4% (hold-capable, T1 unhit), PNB -1.3% (hot-potato, entry 122.5, stop 113.95); equity 96,864 (-3.1%), cash -137, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled at -3.4%, too few to grade. chartink_squeeze -35.7 (n=3), 4 pts from auto-disable; none auto-disabled, none at 60% T1. Monday: no new source.

### 2026-10-27 [analyst]
2026-10-27 desk review: quiet day, no stops/targets/time-stops. PETRONET +3.8%, KOTAKBANK +5.9% (hold-capable, T1 unhit), PNB -1.0% (hot-potato, entry 122.5, stop 113.95); equity 97,665 (-2.3%), cash -137, closed book 0/5 (avg -3.24%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled at -3.4%, too few to grade. chartink_squeeze -35.7 (n=3), 4 pts from auto-disable; none auto-disabled, none at 60% T1. Tuesday: no new source.

### 2026-10-28 [analyst]
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

## Desk review
- KOTAKBANK T1 @ 453.2 (25 sh, +₹880), stop → breakeven 418.0. Credit to the pullback_to_ema20_in_uptrend/volume_spike reasons; hold-capable (fund 85) name paid off in 17 trading days, still 38 sh open toward T2 466.4.
- PETRONET +1.4%, PNB +1.1% (hot-potato, entry 122.5, stop 113.95): no events.
- Ledger bug found and fixed: partial exits never credited cash, so equity showed ₹86,861 (-13.1%) instead of ₹98,191 (-1.8%). `_close` now credits only un-credited proceeds; KOTAKBANK cash corrected by ₹11,330.
- fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled at -3.4%, too few to grade. No source auto-disabled; broker:pl +10 (T1 credit).
