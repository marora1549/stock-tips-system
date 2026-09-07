# End-of-day run playbook (scheduled task, 15:45 IST, Mon–Fri)

You are running unattended. Work inside the `stock-tips-system` repo. Load `prompts/analyst_persona.md` first.

## 0. Setup
```bash
git clone https://github.com/<owner>/stock-tips-system.git 2>/dev/null || (cd stock-tips-system && git pull --ff-only)
cd stock-tips-system && pip install -q -r requirements.txt --break-system-packages
export PYTHONPATH=src
```
Weekend/holiday → one-line `reports/<date>/eod.md`, commit, stop.

## 1. Mark to market
```bash
python -m stocktips eod
```
This fills this morning's pending positions at today's open, walks today's bar for stop-losses and targets (stepped exits), applies time stops (hot potatoes exit; hold-capable names move to the HOLD bucket), updates `state/sources_confidence.json` with every realised outcome, appends machine lessons to `state/lessons.md`, and writes `reports/<date>/eod.md`.

If the market was closed today the command reports no bars — do not force anything.

## 2. Review like an analyst (≤ 15 lines, appended to eod.md under "Desk review")
For every event in the report, one sentence of honest attribution:
* Stop hit: was the stop inside normal noise (< 1 ATR)? Was the pattern real? Did the source's tip arrive after the move?
* Target hit: which reason in `plan.reasons` deserves the credit? Would a tighter/looser target have been better?
* Time stop / hold: was the fundamentals score right to park it?
* Pending cancelled on gap-up: note which source's calls keep gapping — that is information about the source's timing.
Then check `state/sources_confidence.json` for any source whose `n_resolved ≥ 8` and `score < −40` — it has been auto-disabled; say so. Any source with ≥ 10 resolved outcomes and T1 hit-rate ≥ 60% deserves a sentence too.

Record the review:
```bash
python -m stocktips lesson "<your ≤ 600-char review; concrete, dated, no hedging>"
```

## 3. Grow the input side (Fridays, or whenever the source table is thin)
The system is only as good as its inputs. On Fridays, spend a few minutes finding **one** new candidate source (a public Telegram channel, a brokerage's public research page, a new Chartink scan idea, a columnist the extraction keeps missing) and register it at confidence 0:
```bash
python -m stocktips add-source --kind telegram --id tg_<channel> --channel <channel> --name "Telegram — @<channel>" --category tipster
```
Record why you added it in the lesson. Never add a source that requires login or payment.

## 4. Commit, push, notify
```bash
python -m stocktips dashboard-data
git add -A && git commit -qm "eod $(date +%F)" && git push
```
Final message (≤ 700 chars):
```
🧾 <date> EOD — equity ₹<equity> (<ret>%), cash ₹<cash>, open <n>, hold <n>
Events: <one line per event, or "quiet day">
Source moves: <source ±score>, …
Lesson: <one sentence>
```
