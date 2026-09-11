# End-of-day ledger update — Fri 11 Sep 2026, 15:46 IST

Equity ₹99,882 (-0.12%) · cash ₹30,342 · realised ₹-1,166 · open 2 · hold 0 · closed 1 · win rate 0% · avg win None% / avg loss -3.89%

## Events
- V2RETAIL: STOP-LOSS @ 213.56 → closed, P&L ₹-1166.4 (-3.89%)

## Source confidence changes
- `broker:motilal`: +0.0 → -15.0 (confidence 50 → 23)
- `brokerage_gnews`: +0.0 → -7.5 (confidence 50 → 35)
- `mc_stock_ideas_gnews`: +0.0 → -7.5 (confidence 50 → 35)

## What the ledger says works (all closed positions)
| factor | n | win% | avg ret% |
|---|---|---|---|

## Open book
| symbol | status | entry | LTP | unrealised | SL | hit | deadline | bucket |
|---|---|---|---|---|---|---|---|---|
| CGPOWER | open | 894.9 | 909.0 | 1.58% | 855.9 | [] | 2026-10-20 | hold-capable |
| LALPATHLAB | open | 1881.4 | 1909.0 | 1.47% | 1860.75 | [] | 2026-10-20 | hold-capable |

## Recent lessons
y every EOD run. Newest at the bottom. `[machine]` = computed from the ledger, `[analyst]` = Claude's review.


### 2026-09-08 [analyst]
Day 1 (2026-09-07): morning run booked CGPOWER/V2RETAIL/LALPATHLAB as pending after 09:15, so opened=2026-09-08 by design — EOD correctly showed zero events, not a bug. All sources sit at neutral confidence 50 with n_resolved=0; no auto-disable or commendation checks possible yet. Watch tomorrow's open for gap-ups, especially V2RETAIL (Motilal target carried by 5 outlets, crowded calls gap).

### 2026-09-08 [analyst]
2026-09-08: all 3 pendings (CGPOWER, V2RETAIL, LALPATHLAB) filled clean at open, every fill below plan (no gap-ups) — V2RETAIL's flagged crowded-call gap risk didn't show up today, one data point only. No stop/target/time-stop hits, day 1 for all three. All sources still n_resolved=0, so no auto-disable or commendation checks fire yet — desk needs its first resolved trade. Capital fully committed (cash Rs1,512), no room for new picks until a position resolves.

### 2026-09-09 [analyst]
2026-09-09: quiet day, no stop/target/time-stop events — day 2 for all three positions (deadline 2026-10-20, plenty of runway). CGPOWER +3.6% and LALPATHLAB +2.0% tracking toward T1 cleanly on no unusual volume; V2RETAIL -1.1% is normal chop, well inside its 855.9/213.56 stops, no reason to touch it. All sources still n_resolved=0 (up to 57 tips logged for mc_stock_ideas_gnews/et_recos_page) — desk has zero closed trades so no auto-disable or commendation checks can fire yet; book is full (cash Rs1,512) so today added no new picks regardless.

### 2026-09-10 [analyst]
2026-09-10: quiet day, no stop/target/time-stop events, day 3 for all three (deadline 2026-10-20). CGPOWER +2.2% and LALPATHLAB +1.9% still tracking clean toward T1; V2RETAIL -1.8% is normal chop, inside its 213.56 stop, no action. All sources still n_resolved=0 (47 registered), so no auto-disable or commendation checks fire yet, and fund-audit shows no inversion (nothing settled) — the fundamentals score remains unproven, not validated. fund-audit bias check: markets_mojo mean gap +6.5 over n=4, under the 8-point threshold, so not reportable as bias yet; EIEL's superseded 92 stays the standing worst-gap example (+55 vs markets_mojo's 37 sell) until a real trade settles. Book full (cash Rs1,512), no room for new picks.

### 2026-09-11 [machine]
Events: V2RETAIL: STOP-LOSS @ 213.56 → closed, P&L ₹-1166.4 (-3.89%)

| factor | n | win% | avg ret% |
|---|---|---|---|

## Desk review
- Stop hit: V2RETAIL closed day 3 at 213.56, exactly the planned stop, ₹-1,166 (-3.89%). Entry-to-stop was ~1.5× the 2.67% ATR read at entry and broke the 214.63 support (6 touches on the map) — a real breakdown, not inside-noise chop. The pattern read (bollinger_squeeze + momentum_aligned + pullback_to_ema20) was real on the chart, but ADX sat at 13.9 ("-3 no trend") even as the other reasons scored it 79 TA/73 composite — a squeeze without real trend strength is the classic false start, and that's exactly how this one broke. Worth weighting ADX harder against squeeze setups going forward. The Motilal tip itself wasn't stale (chg_20d +2.3%, 13.8% off 52w high) — this isn't a "source called it after the move" case.
- Source moves: first resolved outcome for all three names tied to this tip — `broker:motilal` 50→23, `brokerage_gnews` and `mc_stock_ideas_gnews` both 50→35. All at n_resolved=1, so neither the auto-disable bar (n_resolved≥8, score<-40) nor the commendation bar (n_resolved≥10, T1 hit-rate≥60%) can fire yet; this is one data point on each, not a verdict on Motilal.
- `fund-audit`: no inversion — V2RETAIL's stop-loss exit isn't a fundamentals-band settlement, so still zero settled trades in any band; the 77 fund score on this name is neither vindicated nor indicted by a TA stop. No reportable bias either: markets_mojo mean gap unchanged at +6.5 over n=4, still under the 8-point/3-name bar. EIEL's superseded 92 (vs markets_mojo 37, gap +55) remains the standing worst-gap record.
- Book: CGPOWER (+1.58%) and LALPATHLAB (+1.47%) untouched today, both still tracking clean toward T1 with five weeks of runway (deadline 2026-10-20). The V2RETAIL exit freed cash to ₹30,342 — room for up to 3 fresh positions whenever the morning screen turns up a qualifying idea.
