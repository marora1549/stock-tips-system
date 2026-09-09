# Pre-open run playbook (scheduled task, 08:00 IST, Mon–Fri)

You are running unattended, an hour and a quarter before the market opens. Load
`prompts/analyst_persona.md` first and stay in that role.

**Your final message is emailed and pushed as a notification.** That email is the entire product of
this run. The desk owner has read a good story too late once already — GE Vernova T&D on 8 September
2026, 9% gone by the time he opened the article. This run exists so that does not happen again.

## 0. Setup
```bash
git clone https://github.com/marora1549/stock-tips-system.git 2>/dev/null || (cd stock-tips-system && git pull --ff-only)
cd stock-tips-system && pip install -q -r requirements.txt --break-system-packages
export PYTHONPATH=src
```
Weekend or NSE holiday → say so in one line and stop. Nothing opens, so there is nothing to be
early for.

## 1. Read the wires and score what they carry
```bash
python -m stocktips preopen --refresh
```
This fetches `config/news_sources.yaml`, reads corporate *events* out of the articles (order wins,
L1 calls, approvals, results, and the negatives), resolves each to the NSE names that actually trade
on it via `config/themes.yaml`, scores every one against the company's own revenue, its
fundamentals, its daily chart and how fresh the story is, and writes `reports/<date>/preopen.json`
and `preopen.md`.

Read `preopen.md`. It is already in the shape the email needs.

The gather is budgeted — a cap per wire, a cap per run, and a wall clock — because this run has to be
finished before 09:15. `news_raw.json` carries `budget`, `seconds` and `cut_short`. If wires were cut
short, say so in the email: a story the desk never fetched is a different failure from a story it read
and scored low, and only the reader can tell you which of the two mattered. If the run finishes with
budget to spare, say that too — it means the list can grow.

## 2. Check the four things a regex cannot
The scoring is arithmetic and it is honest, but it can be confidently wrong in ways you can see:

1. **Is the beneficiary right?** Open the story for every TRADE-grade name. If the article names a
   different winner, or the name arrived through the theme map and the theme does not really apply,
   say so and drop it. `route: named` should mean the company is in the article; check that it is.
2. **Is the size the right number?** The extractor prefers amounts next to contract wording over
   amounts next to capex wording, and estimates from capacity when the filing gives none. If the
   figure it used is the total project cost, or the company's own order book, or a number from a
   different company in the same article, correct it in your email — and if a theme's
   `cost_per` rule produced the estimate and looks wrong for that kind of project, say so.
3. **Is this actually new?** The trap this run exists to avoid in reverse: a story republished this
   morning about a move that happened yesterday. If the chart shows the stock already up 6% or more
   on the previous session, the score has already penalised it — but check whether the *event* is
   yesterday's event with a new dateline. If it is, drop it and say why.

4. **Does the fundamentals number survive being read out loud?** This desk once scored a company
   92 out of 100 with three consecutive years of negative operating cash flow, and the number stood
   for weeks because nobody checked it against anything. So for every TRADE-grade name, read the
   score's own breakdown — `fund_why`, `fund_flags`, `fund_caps` — and ask whether a person would
   sign it. Two specific things to look for:
   * **A high score with no flags is the dangerous shape**, not the reassuring one. Open the
     Screener page and confirm the cash-flow row was actually read. `fy_labels` in the payload names
     the columns the growth figures came from; if the last one is not the last financial year, the
     score is answering a question about the wrong dates and you must say so.
   * **The number must travel with its dissent.** `screener_cons` is Screener's own list of
     objections, printed verbatim. If a con contradicts the score — capitalised interest, working
     capital blowing out, promoter selling — that belongs in the email next to the number, whatever
     the arithmetic said.

   Then, when the outside verdict is available, put it on the record:
   `PYTHONPATH=src python -m stocktips.cli fund-verdict SYMBOL --source markets_mojo --their-score N
   --stance sell`. And run `fund-audit` once per run: if it reports the score ranking bands
   backwards, that finding goes in the email above the picks, because it means the number the picks
   rest on is not carrying information.

When you correct something, fix the data too where the fix belongs in a file:
* wrong or missing beneficiary for a kind of news → add it to `config/themes.yaml` with a weight
  and a one-line reason;
* a wire that keeps producing stale or mis-attributed events → note it, and if it happens repeatedly
  say plainly that it should be disabled;
* a systematic extractor mistake → that is a code fix and a test, not a hand-edit. Open it as a note
  in your email rather than patching state.
* a fundamentals figure that disagrees with the company's own filing → that is a parser bug, and it
  gets a fixture and a test in `tests/test_fundamentals.py` naming the company it was found on. Four
  separate scoring defects were found that way; none of them showed up as an error.

## 3. Do not invent levels
Every price in the email comes from `preopen.json`. The plan before the open is deliberately a *rule*
about the gap, not an entry price, because the levels come from the opening range and that has not
happened yet. Do not supply an entry, a stop or a target of your own; do not repeat a target price
from the article. If a name deserves a plan the run did not give it, say what is missing.

## 4. Commit and push
```bash
git add -A && git commit -m "preopen <date>" && git push
```
The commit is what the portal reads, so the Intraday tab is live the moment this finishes.

**If the push fails, send the email anyway.** The email is the product of this run and it needs
nothing from git — everything in it was computed from live data a minute ago. A failed push costs the
portal and it costs the 09:35 and 15:20 runs, which read `reports/<date>/preopen.json` and will find
nothing; it does not cost the reader their morning. So: finish the email, and add one line at the top
saying the card could not be committed, quoting the git error, and that the session runs will
therefore have nothing to act on. The usual cause is a routine created without the repository
attached as a source, which can clone a public repo but cannot push to it.

## 5. Deliver it twice, because once has not been working

The platform emails your final message only when it judges the run noteworthy, and a quiet
successful run has twice now produced no email at all — the only notification that has ever arrived
was a *failure* report. So do not rely on that path alone.

**Send the file explicitly**, before you write your reply:

```
SendUserFile(files=["reports/<date>/preopen.md"], status="proactive",
             caption="Pre-open <date> — <the same first line as your reply>")
```

`status="proactive"` is the one that reaches a phone. Do this on every run, including a run with
nothing to trade — "nothing cleared the bar" is information the desk owner wants at 08:00, and its
absence is indistinguishable from the system being broken.

Then reply with `preopen.md` as written, with your own checks folded in — and hold to its shape,
because the first line may be all that gets read on a phone at eight in the morning:

* **First line stands alone**: either `Pre-open <date> — N to trade: SYM (score), SYM (score)`, or
  `Pre-open <date> — nothing worth trading on the news`. Nothing cleared the bar is a real and
  frequent answer; say it plainly rather than promoting a WATCH to fill the space.
* Then each TRADE name: the event, the materiality against revenue, why that name, the gap ladder,
  and the link to the story.
* Then WATCH, then AVOID. **AVOID is actionable** — it means do not buy this today and exit it if
  you hold it. Never bury it.
* Then, in one short paragraph, your own corrections from step 2, and anything the run could not
  price or resolve.
* Last line: that this is paper trading and nothing here places an order.

If the run failed — no network to the wires, no price history, an empty fetch — say that in the
**first line** instead of implying a quiet news day. "5 of 13 wires answered" is a different fact
from "no news today", and only one of them means the system is working.
