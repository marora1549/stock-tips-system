# Session run playbook (scheduled tasks, 09:35 / 11:30 / 15:20 IST, Mon–Fri)

You are running unattended during market hours, on a day whose pre-open card already exists. Load
`prompts/analyst_persona.md` first.

## 0. Setup
```bash
git clone https://github.com/marora1549/stock-tips-system.git 2>/dev/null || (cd stock-tips-system && git pull --ff-only)
cd stock-tips-system && pip install -q -r requirements.txt --break-system-packages
export PYTHONPATH=src
```
Weekend or holiday → stop. No `reports/<date>/preopen.json` → say so in one line and stop; there is
nothing to watch and this run must not invent candidates of its own.

When the card is missing, say which of the two it is, because they need different fixes: the 08:00
run did not happen, or it happened and could not push. `git log --oneline -3` tells you — a pre-open
commit for today means the second, which is usually a routine created without the repository
attached as a source (it can clone a public repo but not push to it).

## 1. Which run is this
Look at the clock, because the three firings do different work.

**09:35 — the opening range.** The first fifteen minutes have printed, so the levels now exist.
```bash
python -m stocktips intraday
```
This computes the real gap, the real opening range and VWAP, decides per the gap ladder whether the
rule allows a trade, and opens a paper day trade **only** where the trigger actually printed on the
tape and the catalyst was TRADE-grade. Report, per name: the gap, the band, and either the order
line or the reason it stood aside.

The single most valuable thing you can say here is *stand aside*. A name that gapped past +5% has no
entry at the open — only a pullback that reclaims VWAP — and saying so plainly is worth more than
finding something to do.

**11:30 — the middle of the day.** Same command. Report what changed: triggers that fired since,
stops that were hit, targets reached, and anything now past its no-new-entry time. Do not re-plan a
name whose rule has already voided it.

**15:20 — settle and grade.**
```bash
python -m stocktips intraday --close
```
Every open day trade is closed at what the tape actually gave — the stop if it was breached, else the
best target that traded, else the price at the forced-flat time — and then **every** candidate is
graded on how far it travelled from the open, whether or not a plan ever triggered. Those outcomes
move the per-class weights in `state/event_classes.json` and the wires' confidence in
`state/sources_confidence.json`. That is the system learning; do not touch either file by hand.

## 2. Say the honest thing about the day
Two or three sentences, and prefer the uncomfortable version:
* a stop hit inside the first twenty minutes usually means the opening range was noise, not a range;
* a trade that never triggered while the stock ran anyway means the trigger was too far above the
  range high — say it, because that is a fixable rule and not bad luck;
* a name that gapped past the ladder and then ran all day is the rule costing money. Note it. If it
  keeps happening the threshold is wrong, and after enough instances that is a settings change with
  evidence behind it, not a feeling.

## 3. Commit and push
```bash
git add -A && git commit -m "intraday <date> <hh:mm>" && git push
```

## 4. The reply
One short message. First line: the state of the day — `Session <date> 09:35 — GVT&D triggered at
₹2,045, ALKEM stood aside (+5.6% gap)`, or `Session <date> 09:35 — nothing triggered`. Then the table
from `reports/<date>/intraday.md`, then your two sentences. At 15:20 add the day's P&L, the running
day-book record, and any class whose weight moved.

Paper trading throughout. Nothing in this run places an order, and never write one as an instruction
— the order lines are for the desk owner to place or ignore.
