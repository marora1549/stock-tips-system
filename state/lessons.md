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

### 2026-09-24 [analyst]
2026-09-24: quiet day, no stop/target/time-stop events. CGPOWER -0.92% (886.7 vs 894.9 entry, SL 855.9), LALPATHLAB +4.25% clean toward T1, KPIL -0.28%, all inside SL, deadlines (Oct 20/29) far off, no action. No source at n_resolved>=8 (max 1 of 50+), no auto-disable/commendation to report. fund-audit: no inversion (75-100 band still 1 scored, 0 settled, unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated. Book full at 3 open, cash Rs869, no new picks regardless.

### 2026-09-25 [analyst]
2026-09-25: quiet day, no stop/target/time-stop events. CGPOWER -0.99% (886.0 vs 894.9 entry, SL 855.9), LALPATHLAB +3.77% clean toward T1, KPIL -0.88%, all inside SL, deadlines (Oct 20/29) far off, no action. No source at n_resolved>=8 (max 1 of 50+, V2RETAIL SL closed weeks back), no auto-disable/commendation to report. fund-audit: no inversion (75-100 band still 1 scored, 0 settled, unproven) and markets_mojo bias unchanged at +6.5/n=4, under the 8-point bar -- unproven, not validated. Book full at 3 open, cash Rs869, no new picks regardless.

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

### 2026-10-05 [analyst]
2026-10-05 desk review: only event was KOTAKBANK fill 418.00 (plan 418.35, ~flat; closed 416.0, -0.5% on day one); no stop/target/time-stop hit. Book: LALPATHLAB +4.8% (T1 unhit), PETRONET +1.7%, KOTAKBANK -0.5%; all hold-capable. Still 0/4 closed (avg -3.78%). fund-audit: no inversion, no bias (markets_mojo gap +6.5, under 8pt); 75-100 band 2 settled, too few to read, so fund score remains unproven. No source auto-disabled, none at 60% T1. Not Friday: no new source.

### 2026-10-06 [analyst]
2026-10-06 desk review: quiet day, no events. LALPATHLAB +4.4%, PETRONET +4.35%, KOTAKBANK +3.3%, all hold-capable, T1/stops untouched. Still 0/4 closed (avg -3.78%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled, too few to grade the score. No source auto-disabled, none at 60% T1. Not Friday: no new source.

### 2026-10-07 [analyst]
2026-10-07 desk review: quiet day, no events, no stops/targets/time-stops. LALPATHLAB +3.4%, PETRONET +4.2%, KOTAKBANK +5.3%, all hold-capable, T1 unhit, stops intact. Equity 99,197 (-0.8%), still 0/4 closed (avg -3.78%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled, too few to grade the score. No source auto-disabled (max n_resolved=2), none at 60% T1. Not Friday: no new source.

### 2026-10-08 [analyst]
2026-10-08 desk review: quiet day, no events, no stops/targets/time-stops. LALPATHLAB +0.9%, PETRONET +1.2%, KOTAKBANK +4.1%, all hold-capable, T1 unhit, stops intact; equity 96,982 (-3.0%), up-gains faded ~2pts from yesterday, still 0/4 closed (avg -3.78%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled, too few to grade the score. No source auto-disabled (max n_resolved=2), none at 60% T1. Not Friday: no new source.

### 2026-10-09 [analyst]
2026-10-09 desk review: quiet day, no events, no stops/targets/time-stops. LALPATHLAB +2.8%, PETRONET +2.2%, KOTAKBANK +5.5%, all hold-capable, T1 unhit, stops intact; equity 98,307 (-1.7%), still 0/4 closed (avg -3.78%). fund-audit: no inversion, no bias (markets_mojo gap +6.5 <8pt); 75-100 band 2 settled, too few to grade score. No source auto-disabled (max n_resolved=2), none at 60% T1. Friday: new-source add (tg_stockpro_online candidate) was blocked by permission classifier; none added.
