# Morning run playbook (scheduled task, 08:15 IST, Mon–Fri)

You are running unattended. Follow this exactly; do not ask questions. Work inside the `stock-tips-system` repo (clone if absent). Load `prompts/analyst_persona.md` first and stay in that role for the whole run.

## 0. Setup
```bash
git clone https://github.com/marora1549/stock-tips-system.git 2>/dev/null || (cd stock-tips-system && git pull --ff-only)
cd stock-tips-system && pip install -q -r requirements.txt --break-system-packages
export PYTHONPATH=src
python -m stocktips selfcheck; canaries=$?
# What else is out there that this run is not running
curl -s "https://api.github.com/repos/marora1549/stock-tips-system/pulls?state=open" \
  | python -c "import json,sys;[print(f\"OPEN PR #{p['number']}: {p['title']} ({p['head']['ref']})\") for p in json.load(sys.stdin)]" 2>/dev/null
```

**If `selfcheck` exits non-zero, that is the first thing in your email, before the picks.** It
means the code in this container is older than the corrections in this repository's history — and
the output will otherwise look completely normal. On 10 September the 08:00 run mailed a card
scoring Enviro Infra 92, a number that had been corrected to 32 the day before, because the
correction was on a branch and this clone takes `main`. Nothing failed. The run succeeded, the
email arrived, and only a person reading it against a paid research note caught it.

So when a canary fails: name which ones, name the open PR if the listing shows one, say plainly
that **the fundamentals numbers in this email are not current**, and run everything else anyway —
the prices, the news and the technicals are all live and still worth having.
If today is an NSE holiday (check `config/holidays.yaml`, else reason from the date), or a weekend, write a one-line `reports/<date>/morning.md` saying so, commit, and stop.

## 1. Gather
```bash
python -m stocktips gather --max-age 36
```
Read `reports/<date>/tips_raw.json`. Also read the tail of `state/lessons.md` — the system's own learnings apply today.

## 2. Review the extraction (this is where you earn your keep)
The regexes are deliberately conservative. For every tip with `needs_review: true`, and for every `doc` whose text obviously contains recommendations the regexes missed, read the source text (`docs[].text`) and produce `reports/<date>/tips_reviewed.json` — the **full corrected tip list** (same schema as `tips_raw.json → tips`):
* fix wrong symbols, drop non-tips (market commentary, index views, mutual funds, IPO news, "hold" without a level), drop anything older than 36h or about F&O/intraday;
* fill `src_targets`, `src_stop`, `src_entry`, `src_duration`, `brokerage` from the text where present;
* set `action` to buy/sell/hold, `extracted_by: "claude"`, `needs_review: false`, `extraction_confidence` 0.6–0.95;
* mark tips you reject with `"dropped": true` and a `drop_reason`.
Keep tips you did not touch unchanged. Never invent a target that is not in the text.

```bash
python -m stocktips structure --reviewed reports/<date>/tips_reviewed.json
python -m stocktips analyze
```

## 3. Sanity-check the top of `reports/<date>/analysis.json`
For each candidate with verdict BUY/STRONG BUY (top ~8), apply the persona's kill-switches by eye: is the "pattern" real, is the stop inside noise, has the stock already moved today (check `ta.chg_5d_pct`), is there earnings/results/ex-date risk in the next 3 sessions (search the doc texts and, if the WebSearch tool is available, the news)? If a candidate must be excluded, edit `analysis.json` to set `"verdict": "SKIP"` and add `"analyst_note": "<reason>"`. Do not promote anything the numbers scored WATCH.

## 4. Pick and book (paper)
```bash
python -m stocktips pick
```
This allocates confidence-weighted paper capital across the top 3 (≤50% each, ≤4 open positions) and writes `reports/<date>/morning.md` + `picks.json`.

## 5. Write the human layer
Prepend to `reports/<date>/morning.md` a section **"Desk view"** of ≤ 12 lines: market context in one line (Nifty trend from any candidate's index mention or the ET "Ahead of Market" piece), then for each of the top 3: one sentence on *why this chart*, one on *what would make you wrong* (the stop's logic), and the exact order to place at 9:15 in Zerodha terms (`BUY <qty> <SYMBOL> NSE CNC limit ₹<entry> · SL-M ₹<stop> · GTT targets ₹T1/T2/T3`). If there are no picks, say "No trade today" and why.

## 6. Commit, push, notify
```bash
python -m stocktips dashboard-data
git add -A && git commit -qm "morning $(date +%F): <n> picks"
# Push to main, rebasing on anything an interactive session landed while this run was working.
pushed=""
for i in 1 2 3; do
  git pull --rebase --autostash -q origin main && git push -q origin HEAD:main && pushed="main" && break
  sleep $((i * 4))
done
# If main still refuses, never leave the run's work stranded in this container: park it on a
# claude/-prefixed branch, which the push proxy always accepts.
if [ -z "$pushed" ]; then
  branch="claude/morning-$(date +%F)"
  git push -q -u origin "HEAD:$branch" && pushed="$branch"
fi
echo "pushed to: ${pushed:-NOTHING}"
```
If `pushed` is anything other than `main`, name that branch in the notification and say the ledger needs
merging by hand — the state is only real once it is on `main`, which is what the next run clones from.
If it printed `NOTHING`, say that plainly: this run's work exists nowhere but a container that is about
to be reclaimed.
Your final message (this becomes the push/email notification) must be ≤ 900 characters:
```
📈 <date> picks (paper ₹<equity>, <ret>%)
1. SYMBOL — BUY <qty> @ ₹entry | SL ₹x | T ₹a / ₹b / ₹c | comp NN (TA nn · fund nn · src nn) | <tf>
2. …
3. …
Watch: … | Open book: … | Full report: reports/<date>/morning.md
```

---

## Operational notes for the unattended run

Nobody is watching, so do not ask questions — make the calls yourself and finish the run. Push to `main`;
every run leaves a commit behind, even a no-trade day. Your final turn message is what gets emailed, so it
must stand alone in exactly the step-6 format above; if the run failed before it could book anything, say
so plainly there instead of implying success. Paper trading only — nothing here places real orders.
