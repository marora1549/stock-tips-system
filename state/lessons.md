# Lessons journal

Appended by every EOD run. Newest at the bottom. `[machine]` = computed from the ledger, `[analyst]` = Claude's review.


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

### 2026-09-11 [analyst]
2026-09-11: V2RETAIL stopped at 213.56 day 3, -3.89%, breaking the 214.63 6-touch support at ~1.5x ATR — real breakdown, not noise. Pattern (squeeze+momentum+pullback) was genuine but ADX 13.9 flagged 'no trend' at entry and composite still scored it 73 BUY; weight ADX harder against squeeze setups. First resolved outcome for broker:motilal (50->23), brokerage_gnews/mc_stock_ideas_gnews (50->35 each), n_resolved=1 — no auto-disable/commendation threshold reached. fund-audit: nothing settled, no inversion; markets_mojo bias unchanged +6.5/n=4, under the 8-pt bar. CGPOWER/LALPATHLAB untouched, cash freed to Rs30,342.

### 2026-09-11 [analyst]
2026-09-11 (Friday input growth): registered chartink_rsi_oversold_bounce at confidence 0 — the existing 3 screener sources (52w breakout, EMA20 pullback, Bollinger squeeze) are all trend-continuation setups; nothing in the source table screens a reversal-from-oversold bounce, and double_bottom_confirmed is a named TA pattern with no dedicated feeder. Clause: RSI crossing back above 30 with an up day and volume >1.2x 20d avg, liquid names only. No login/payment required (public Chartink scan).

### 2026-09-15 [analyst]
2026-09-15: quiet day, no stop/target/time-stop events, day 5 for CGPOWER/LALPATHLAB (deadline 2026-10-20). CGPOWER -4.1% has drifted to within 0.2% of its 855.9 stop on no unusual volume -- worth a look tomorrow, not yet a breakdown; LALPATHLAB +1.3% still clean toward T1. All sources still n_resolved=1 (V2RETAIL only), so no auto-disable/commendation thresholds fire. fund-audit: nothing settled in any fundamentals band, so no inversion to report -- score remains unproven. markets_mojo bias unchanged at +6.5/n=4, still under the 8-point bar. Book full at 2 open (cash Rs30,342), no new picks regardless.

### 2026-09-17 [analyst]
2026-09-17: only event was KPIL's fill at 1403.5, 2.2% below its 1428.52-1442.88 entry zone (plan 1435.7) -- favorable slippage on a monthly chartink_squeeze pick, not a gap-up to cancel; pace flag already on record (38d to T1 vs 30d clock) so this one is a watch for the time stop, not a hold-capable free pass. CGPOWER -1.7%, LALPATHLAB +2.3%, both clean inside SL, no action. No source crossed n_resolved>=8 (max is 1 across 50 sources), so no auto-disable or commendation to report. fund-audit: no inversion (nothing settled in any fundamentals band, 92 EIEL still the only 20+pt gap on record) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated, said plainly again.

### 2026-09-18 [analyst]
2026-09-18: quiet day, no stop/target/time-stop events. CGPOWER recovered to -0.32% (892 vs 855.9 SL), no longer near breakdown flagged 9/15; LALPATHLAB +0.8% clean toward T1; KPIL +3.0%, still on watch for its 30d time-stop pace flag from 9/17. All sources still n_resolved<=1 (max 1 of 50), so no auto-disable/commendation threshold fires. fund-audit: nothing settled in any fundamentals band (75-100 has 1 scored, 0 settled) -- no inversion to report, score remains unproven. markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar. Book full at 3 open, cash Rs869, no new picks regardless.

### 2026-09-18 [analyst]
2026-09-18 (Friday input growth): registered chartink_volume_shock at confidence 0 -- the 4 existing screener sources (52w breakout, EMA20 pullback, Bollinger squeeze, RSI oversold bounce) all require an established trend or consolidation; nothing screens a fresh volume spark before it clears the 52-week high, which is where several early-stage breakouts get missed. Clause: volume > 3x 20d avg on an up day (>=2%), liquid cash names only (>Rs5cr 20d turnover), price > Rs20. No login/payment required (public Chartink scan).

### 2026-09-21 [analyst]
2026-09-21: quiet day, no stop/target/time-stop events after the weekend gap. CGPOWER +1.52%, LALPATHLAB +2.3%, KPIL +2.59%, all clean inside SL, deadlines (Oct 20/29) far off, no action. No source crossed n_resolved>=8 (still 0 of 50+), so no auto-disable/commendation to report. fund-audit: no inversion (75-100 band has 1 scored, 0 settled, score remains unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar. Book full at 3 open, cash Rs869, no new picks regardless.

### 2026-09-22 [analyst]
2026-09-22: quiet day, no stop/target/time-stop events. CGPOWER +0.13%, LALPATHLAB +1.51%, KPIL -0.24%, all clean inside SL, deadlines (Oct 20/29) far off, no action. No source crossed n_resolved>=8 (still 0 of 50+), so no auto-disable/commendation to report. fund-audit: no inversion (75-100 band still 1 scored, 0 settled, score remains unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated. Book full at 3 open, cash Rs869, no new picks regardless.

### 2026-09-23 [analyst]
2026-09-23: quiet day, no stop/target/time-stop events. CGPOWER flat (895 vs 855.9 SL, +0.01%), LALPATHLAB +2.28% clean toward T1, KPIL +0.59%, all inside SL, deadlines (Oct 20/29) far off, no action. No source at n_resolved>=8 (max 1 of 50+), no auto-disable/commendation to report. fund-audit: no inversion (75-100 band still 1 scored, 0 settled, unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated. Book full at 3 open, cash Rs869, no new picks regardless.
