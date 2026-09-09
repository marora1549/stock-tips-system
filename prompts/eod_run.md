# End-of-day run playbook (scheduled task, 15:45 IST, Mon–Fri)

You are running unattended. Work inside the `stock-tips-system` repo. Load `prompts/analyst_persona.md` first.

## 0. Setup
```bash
git clone https://github.com/marora1549/stock-tips-system.git 2>/dev/null || (cd stock-tips-system && git pull --ff-only)
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

`eod` exits **non-zero** with `DATA OUTAGE` when it could not price a single position that was due a bar.
That is an infrastructure failure, not a quiet day: do not paper over it. Still write the review, commit
and push (the report is the record), and make the outage the first line of the notification.

## 2. Review like an analyst (≤ 15 lines, appended to eod.md under "Desk review")
For every event in the report, one sentence of honest attribution:
* Stop hit: was the stop inside normal noise (< 1 ATR)? Was the pattern real? Did the source's tip arrive after the move?
* Target hit: which reason in `plan.reasons` deserves the credit? Would a tighter/looser target have been better?
* Time stop / hold: was the fundamentals score right to park it? A position closing today has just
  settled its score in `state/fundamentals_calibration.json` — say whether the score earned its
  keep on this one, in a clause.
* Pending cancelled on gap-up: note which source's calls keep gapping — that is information about the source's timing.
Then check `state/sources_confidence.json` for any source whose `n_resolved ≥ 8` and `score < −40` — it has been auto-disabled; say so. Any source with ≥ 10 resolved outcomes and T1 hit-rate ≥ 60% deserves a sentence too.

Then run `PYTHONPATH=src python -m stocktips.cli fund-audit`. Two findings are reportable and
neither is optional:
* **an inversion** — names scored highly returning less than names scored poorly, over enough
  settled trades to mean it. That is the fundamentals score failing to carry information, and it
  goes at the top of the review, not in a footnote.
* **a bias** — running eight points or more generous against an outside desk across three or more
  names. Say the number and the direction.

If neither is present and nothing has settled, say that too: an ungraded score is an opinion, and
Enviro Infra's 92 stood for weeks precisely because nobody said so out loud.

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
git add -A && git commit -qm "eod $(date +%F)"
# Push to main, rebasing on anything an interactive session landed while this run was working.
pushed=""
for i in 1 2 3; do
  git pull --rebase --autostash -q origin main && git push -q origin HEAD:main && pushed="main" && break
  sleep $((i * 4))
done
# If main still refuses, never leave the run's work stranded in this container: park it on a
# claude/-prefixed branch, which the push proxy always accepts.
if [ -z "$pushed" ]; then
  branch="claude/eod-$(date +%F)"
  git push -q -u origin "HEAD:$branch" && pushed="$branch"
fi
echo "pushed to: ${pushed:-NOTHING}"
```
If `pushed` is anything other than `main`, name that branch in the notification and say the ledger needs
merging by hand — the state is only real once it is on `main`, which is what the next run clones from.
If it printed `NOTHING`, say that plainly: this run's work exists nowhere but a container that is about
to be reclaimed.
Final message (≤ 700 chars):
```
🧾 <date> EOD — equity ₹<equity> (<ret>%), cash ₹<cash>, open <n>, hold <n>
Events: <one line per event, or "quiet day">
Source moves: <source ±score>, …
Lesson: <one sentence>
```

---

## Operational notes for the unattended run

Nobody is watching, so do not ask questions — make the calls yourself and finish the run. Push to `main`;
every run leaves a commit behind, even a no-trade day. Your final turn message is what gets emailed, so it
must stand alone in exactly the step-4 format above; if the run failed before it could mark to market, say
so plainly there instead of implying success. Paper trading only — nothing here places real orders.
