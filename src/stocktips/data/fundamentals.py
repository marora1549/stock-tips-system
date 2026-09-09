"""Fundamentals from Screener.in — a 0–100 score, and the reasons it is not a higher one.

Rebuilt after this module scored Enviro Infra Engineers **92 out of 100** while Markets Mojo, on
the same company, said SELL at 37 — and Mojo was right. The anatomy of the 92 is worth keeping,
because every one of the four defects behind it was a different kind of mistake:

1. **Nothing read the cash flow.** Nine additive terms, all levels or three-year averages, in a
   company whose operating cash flow had been negative three years running while borrowings rose
   80%. Not underweighted — absent.

2. **The flaw could only ever be one vote in nine.** Adding a cash term would not have fixed that:
   good ratios outvote a cash burn arithmetically. So a finding now sets a **ceiling** the rest of
   the sheet cannot lift the score above, and `assess` returns those ceilings alongside the number.

3. **Correlated strengths were each paid in full.** ROCE, ROE and margin are three readings of one
   fact. Counting it three times is how a strong company came out at 97 and another at 100 — the
   same defect as the 92, seen from the other end. `BUDGET` caps what each *dimension* is worth,
   once, however many ratios happen to express it. The positive budgets sum to 40 over a base of
   50, so 90 is the highest score this module can produce: a public ratio page cannot tell the
   90th percentile from the 99th, and the last ten points are withheld rather than invented.

4. **A column was read by position, not by name.** Screener's profit-and-loss table ends in a TTM
   column; its cash-flow table does not. So the growth pair compared TTM-against-FY26 with
   FY26-against-FY25, and Enviro Infra's real deceleration — 46.2% down to 7.5% — came out as a
   mild 10.3% against 7.5%. That bug survived the entire rebuild above and was found only by
   pointing the parser at the live page. Every period figure now travels with the column label it
   came from, and `_self_check` tests the sheet against expectations that a real one must satisfy.

What the module now also does is **decline**. It refuses to grade a bank or an NBFC, where
borrowings are the raw material and a negative operating cash flow is what growth looks like; it
caps itself at 60 when the page contradicts itself, and at 75 when a section could not be read,
because "I did not see the cash flow" is not "the cash flow is fine". And it carries Screener's own
Pros and Cons through verbatim, so the number always travels next to an outside voice that can
disagree with it.

Whether any of this is working is not for this module to assert. `learning/fundcalib.py` grades the
score against realised outcomes and against outside verdicts, which is the check that was missing
when the 92 stood for weeks.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import date, timedelta
from urllib.parse import quote

from ..util import http

log = logging.getLogger(__name__)

SCREENER = "https://www.screener.in/company/{sym}/{mode}"


def _num(s: str) -> float | None:
    s = html.unescape(s).replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


# A column heading that names a financial period. Anything else in the header row — Screener's
# trailing "TTM" column, most of all — is not a year, and must not be read as one.
DATE_HEADER = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*'?\s*\d{2,4}")


def _row_cells(block: str, row_name: str) -> list[float | None]:
    """One table row, **positionally** — an unreadable cell stays a hole instead of closing up.

    `_row_values` used to drop blanks, which silently slides every later value into an earlier
    period. That is the same class of error as reading TTM as a year: the arithmetic still works,
    it just answers a question about the wrong dates.
    """
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not cells:
            continue
        label = re.sub(r"<[^>]+>", " ", cells[0])
        label = re.sub(r"\s+", " ", html.unescape(label)).replace("+", "").strip()
        if label.lower() == row_name.lower():
            return [_num(re.sub(r"<[^>]+>", " ", c)) for c in cells[1:]]
    return []


def _row_values(block: str, row_name: str) -> list[float]:
    """Values of a table row whose first cell *contains* row_name (cells may wrap the label in a <button>)."""
    return [v for v in _row_cells(block, row_name) if v is not None]


def _col_labels(block: str) -> list[str]:
    """A table's column headings, so a series can be tied to the periods it actually belongs to."""
    th = re.search(r"<thead.*?</thead>", block, re.S)
    if not th:
        return []
    cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
             for c in re.findall(r"<th[^>]*>(.*?)</th>", th.group(0), re.S)]
    return cells[1:]      # the first heading belongs to the row-label column


def _period_values(block: str, row_name: str) -> tuple[list[float], list[str]]:
    """A row trimmed to its dated columns, with the labels it was trimmed to.

    Screener's profit-and-loss table ends in a TTM column; its cash-flow table does not. Reading
    both as "the last N periods" shifted the P&L by one, so `_pair_growth` was comparing
    TTM-against-FY26 with FY26-against-FY25 — and Enviro Infra's real deceleration, 46.2% down to
    7.5%, vanished into a mild 10.3% against 7.5%. The flags happened to catch that company
    anyway; on a name without a cash burn the whole deceleration term would simply never fire.

    Returning the labels alongside the numbers is the point: every period figure this module
    publishes can now be checked against the column it came from, and `_self_check` does exactly
    that instead of trusting the position.
    """
    cells = _row_cells(block, row_name)
    labels = _col_labels(block)
    if not cells:
        return [], []
    if len(labels) < len(cells):                      # header unreadable — no basis to trim
        return [v for v in cells if v is not None], labels
    keep = [i for i, lab in enumerate(labels[:len(cells)])
            if DATE_HEADER.search(lab) and cells[i] is not None]
    if not keep:
        return [v for v in cells if v is not None], labels[:len(cells)]
    return [cells[i] for i in keep], [labels[i] for i in keep]


def _labelled_value(block: str, row_name: str, heading: str) -> float | None:
    """One cell, addressed by its column heading rather than its position — e.g. the TTM column."""
    cells = _row_cells(block, row_name)
    for i, lab in enumerate(_col_labels(block)[:len(cells)]):
        if heading.lower() in lab.lower():
            return cells[i]
    return None


def _parse(h: str) -> dict:
    d: dict = {}
    # Top ratio strip
    for m in re.finditer(r'<li[^>]*class="flex flex-space-between"[^>]*>.*?<span class="name">\s*(.*?)\s*</span>.*?<span class="number">\s*(.*?)\s*</span>(.*?)</li>', h, re.S):
        name = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        val = _num(m.group(2))
        if name == "High / Low":
            nums = re.findall(r"[\d,]+(?:\.\d+)?", html.unescape(m.group(2) + m.group(3)))
            if len(nums) >= 2:
                d["high_52w"], d["low_52w"] = _num(nums[0]), _num(nums[1])
            continue
        key = {"Market Cap": "market_cap_cr", "Current Price": "price", "Stock P/E": "pe", "Book Value": "book_value",
               "Dividend Yield": "div_yield", "ROCE": "roce", "ROE": "roe", "Face Value": "face_value"}.get(name)
        if key:
            d[key] = val

    # Growth tables (Compounded Sales/Profit Growth, Stock Price CAGR, Return on Equity) — take TTM/1Y and 3Y
    for label, key in (("Compounded Sales Growth", "sales_growth"), ("Compounded Profit Growth", "profit_growth"),
                       ("Stock Price CAGR", "price_cagr"), ("Return on Equity", "roe_hist")):
        m = re.search(label + r".*?</table>", h, re.S)
        if m:
            rows = re.findall(r"<td[^>]*>\s*([^<]+?)\s*:\s*</td>\s*<td[^>]*>\s*([^<]+?)\s*</td>", m.group(0))
            for period, val in rows:
                p = period.strip().lower().replace(" ", "_")   # 10_years, 5_years, 3_years, ttm/1_year
                d[f"{key}_{p}"] = _num(val)

    # Shareholding: promoter %, pledge if present, FII/DII latest
    sh = re.search(r'id="shareholding".*?</section>', h, re.S)
    if sh:
        blk = sh.group(0)
        for who, key in (("Promoters", "promoter_pct"), ("FIIs", "fii_pct"), ("DIIs", "dii_pct")):
            vals = _period_values(blk, who)[0]
            if vals:
                d[key] = vals[-1]
                if len(vals) >= 5:
                    d[key + "_chg_4q"] = round(vals[-1] - vals[-5], 2)
    m = re.search(r"pledged[^<]*?<[^>]*>\s*([\d.]+)\s*%", h, re.I | re.S) or re.search(r"Pledged percentage[^\d]*([\d.]+)", h, re.I)
    if m:
        d["pledged_pct"] = float(m.group(1))

    # Balance sheet: borrowings vs reserves+equity for debt/equity
    bs = re.search(r'id="balance-sheet".*?</section>', h, re.S)
    if bs:
        blk = bs.group(0)
        def last(row_name):
            vals = _row_values(blk, row_name)
            return vals[-1] if vals else None
        eq, res, bor = last("Equity Capital"), last("Reserves"), last("Borrowings")
        if bor is not None and eq is not None:
            net_worth = (eq or 0) + (res or 0)
            d["debt_to_equity"] = round(bor / net_worth, 2) if net_worth > 0 else 9.99

    # Quarterly: last 2 quarters net profit for trend, and trailing revenue
    qs = re.search(r'id="quarters".*?</section>', h, re.S)
    if qs:
        vals = _period_values(qs.group(0), "Net Profit")[0]
        if True:
            if len(vals) >= 5:
                d["np_latest_q"], d["np_yoy_q"] = vals[-1], vals[-5]
                d["np_yoy_growth_pct"] = round((vals[-1] / abs(vals[-5]) - 1) * 100, 1) if vals[-5] else None
        # Trailing twelve months of sales — the denominator for "is this order material?". The last
        # four quarters beat the last annual column, which can be nine months stale by Q3.
        sales_q, sq_labels = _period_values(qs.group(0), "Sales")
        if not sales_q:
            sales_q, sq_labels = _period_values(qs.group(0), "Revenue")
        if len(sales_q) >= 4:
            d["revenue_ttm_cr"] = round(sum(sales_q[-4:]), 2)
            d["revenue_basis"] = "trailing 4 quarters"
            d["revenue_ttm_labels"] = sq_labels[-4:]

    # Annual sales, as the fallback and for the growth read
    pl = re.search(r'id="profit-loss".*?</section>', h, re.S)
    if pl:
        blk = pl.group(0)
        row = "Sales" if _row_cells(blk, "Sales") else "Revenue"
        sales_y, fy = _period_values(blk, row)
        if sales_y:
            d["fy_labels"] = fy[-5:]
            d["revenue_fy_cr"] = sales_y[-1]
            d["revenue_fy_label"] = fy[-1] if fy else None
            # the trailing figure has its own column when Screener publishes one; falling back to
            # the last financial year is a fallback, and says so
            ttm = _labelled_value(blk, row, "TTM")
            if ttm is not None:
                d.setdefault("revenue_ttm_cr", ttm)
                d.setdefault("revenue_basis", "trailing twelve months")
            else:
                d.setdefault("revenue_ttm_cr", sales_y[-1])
                d.setdefault("revenue_basis", "last reported financial year")
        # Last year against the year before it. A three-year CAGR averages a boom with the bust
        # that follows it: Enviro Infra's sales CAGR was 50% while the latest year grew 7.5%, and the
        # CAGR is what the score was reading.
        d.update(_pair_growth(sales_y, "sales"))
        d.update(_pair_growth(_period_values(blk, "Net Profit")[0], "profit"))
        d.update(_pair_growth(_period_values(blk, "Operating Profit")[0], "opm_abs"))
        opm = _period_values(blk, "OPM %")[0]
        if len(opm) >= 2:
            d["opm_pct"], d["opm_pct_prev"] = opm[-1], opm[-2]

    # Cash flow. The most important section in the file and it was not being read at all.
    cf = re.search(r'id="cash-flow".*?</section>', h, re.S)
    if cf:
        ops, cf_labels = (0, 0)
        for name in ("Cash from Operating Activity", "Cash from Operating Activity +",
                     "Net Cash Flow from Operating Activities"):
            ops, cf_labels = _period_values(cf.group(0), name)
            if ops:
                break
        if ops:
            d["cfo_labels"] = cf_labels[-5:]
            d["cfo_series_cr"] = ops[-5:]
            d["cfo_cr"] = ops[-1]
            d["cfo_negative_years"] = sum(1 for v in ops[-3:] if v < 0)
            d["cfo_negative_streak"] = 0
            for v in reversed(ops):
                if v < 0:
                    d["cfo_negative_streak"] += 1
                else:
                    break

    # Borrowings over time, not just the latest level — the direction is the signal
    if bs:
        bor_series, bor_labels = _period_values(bs.group(0), "Borrowings")
        if len(bor_series) >= 2 and bor_series[-2]:
            d["borrowings_labels"] = bor_labels[-2:]
            d["borrowings_cr"] = bor_series[-1]
            d["borrowings_growth_pct"] = round((bor_series[-1] / abs(bor_series[-2]) - 1) * 100, 1)

    # Quarterly interest and operating profit, for the coverage trend
    if qs:
        blk = qs.group(0)
        interest, q_labels = _period_values(blk, "Interest")
        op, op_labels = _period_values(blk, "Operating Profit")
        if interest and op and q_labels == op_labels and len(interest) == len(op):
            d["quarter_labels"] = q_labels[-5:]
            # Interest cover only means something when there is interest to cover. HAL's cover runs
            # past 1,000× because it has almost no debt, and my first self-check called that a
            # misparse — the expectation was wrong, not the page. A company whose interest bill is
            # under 2% of operating profit does not have a debt-service question, so it is not asked
            # one: the cover terms sit out rather than paying a bonus for a ratio near infinity.
            if sum(interest[-4:]) < 0.02 * abs(sum(op[-4:]) or 1):
                d["interest_immaterial"] = True
                d["interest_note"] = "interest is under 2% of operating profit — effectively debt-free"
                interest = []
            cov = [round(o / i, 2) for o, i in zip(op, interest) if i]
            if len(cov) >= 3:
                window = cov[-5:]
                d["interest_cover_series"] = window
                d["interest_cover"] = window[-1]
                # deteriorating means "lowest in the window", not "fell every single quarter" —
                # 9.11, 8.81, 6.78, 6.89, 5.23 is plainly deteriorating and fails a strict test on
                # the one quarter that ticked up
                d["interest_cover_falling"] = window[-1] == min(window) and window[-1] < window[0]
        if len(interest) >= 5 and interest[-5]:
            d["interest_growth_yoy_pct"] = round((interest[-1] / abs(interest[-5]) - 1) * 100, 1)

    # Screener's own Pros and Cons, verbatim. This is the part of the page worth having that no
    # score of mine can replace: an independent read, in words, from someone else's arithmetic. The
    # desk owner's objection to a single confident number was fair, and the answer is not a better
    # number on its own — it is a number with a dissenting voice printed next to it.
    for kind in ("pros", "cons"):
        m = re.search(r'class="[^"]*\b' + kind + r'\b[^"]*"[^>]*>(.*?)</div>', h, re.S | re.I)
        if not m:
            continue
        items = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", li))).strip()
                 for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)]
        items = [i for i in items if 8 < len(i) < 300]
        if items:
            d["screener_" + kind] = items[:8]

    # Who else owns it. Institutions doing their own diligence and staying out is information.
    inst = sum(d.get(k) or 0 for k in ("fii_pct", "dii_pct"))
    if inst:
        d["institutional_pct"] = round(inst, 2)

    # What business is this? Screener names the sector and industry in the breadcrumb, and it
    # decides whether this module is entitled to an opinion at all.
    for title, key in (("Sector", "sector"), ("Broad Industry", "industry")):
        m = re.search(r'title="' + title + r'"\s*>\s*([^<]+?)\s*</a>', h, re.S)
        if m:
            d[key] = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    both = f"{d.get('sector','')} {d.get('industry','')}".lower()
    if any(t in both for t in ("bank", "financial services", "insurance", "nbfc",
                               "finance", "capital market")):
        d["model_misfit"] = (f"Screener files it under {d.get('industry') or d.get('sector')}, "
                             "where borrowings are the raw material and interest is the cost of "
                             "goods — debt ratios, interest cover and operating cash flow do not "
                             "mean here what they mean elsewhere")

    warn = _self_check(d)
    if warn:
        d["parse_warnings"] = warn
    return d


def _self_check(d: dict) -> list[str]:
    """Does this sheet make sense on its own terms?

    The TTM bug was not caught by a test or by a failed request. It was caught by reading one
    company's numbers next to a second opinion and noticing that a figure I had published, 10.3%,
    was not the figure the company had reported, 7.46%. Nothing in the code objected, because
    nothing in the code had an expectation to violate.

    So these are the expectations. Each is a statement that must be true of any real sheet —
    a period column is a period, two independent reads of the same quantity agree in order of
    magnitude, a percentage is between -100 and 100, holdings sum to at most the whole company.
    A violation does not raise: a fundamentals score must survive a bad page. It goes on the record
    and `score()` caps the result at 60, because a number I cannot reconcile is worse than a number
    I do not have, and it must never be presented as a clean read.
    """
    w: list[str] = []

    labs = d.get("fy_labels") or []
    if labs and not DATE_HEADER.search(labs[-1]):
        w.append(f"the annual table's last column reads {labs[-1]!r}, which is not a financial year")
    # "a figure is present" was the only question the old checks asked. Whether it was *current*
    # was not, and GE Vernova T&D scored 55 off a single Dec 2010 column because of it.
    if labs:
        m = re.search(r"(\d{4})", labs[-1])
        stale = date.today().year - int(m.group(1)) if m else None
        if stale is not None and stale > 2:
            w.append(f"the last annual column is {labs[-1]}, {stale} years old — this is not a current sheet")
        if len(labs) < 3:
            w.append(f"only {len(labs)} annual column(s) on the page — too few to read a trend from")
    for key, name in (("cfo_labels", "cash flow"), ("borrowings_labels", "borrowings")):
        other = d.get(key) or []
        if labs and other and other[-1] != labs[-1]:
            w.append(f"{name} ends at {other[-1]} but the P&L ends at {labs[-1]} — "
                     "two sections read to different dates")

    ttm, fy = d.get("revenue_ttm_cr"), d.get("revenue_fy_cr")
    if ttm and fy and not 0.4 <= ttm / fy <= 2.6:
        w.append(f"trailing revenue ₹{ttm:,.0f}cr against last year's ₹{fy:,.0f}cr — "
                 "one of the two is misread")

    for key in ("sales_growth_1y_pct", "profit_growth_1y_pct",
                "sales_growth_prev_1y_pct", "profit_growth_prev_1y_pct"):
        v = d.get(key)
        if v is not None and not -100.0 <= v <= 900.0:
            w.append(f"{key.replace('_', ' ')} came out at {v:,.0f}% — the growth read is unsafe")

    for key in ("promoter_pct", "fii_pct", "dii_pct", "opm_pct", "opm_pct_prev", "pledged_pct"):
        v = d.get(key)
        if v is not None and not -100.0 <= v <= 100.0:
            w.append(f"{key.replace('_', ' ')} parsed as {v:g}, which is not a percentage")
    held = (d.get("promoter_pct") or 0) + (d.get("institutional_pct") or 0)
    if held > 100.5:
        w.append(f"promoter plus institutional holding comes to {held:.1f}% — "
                 "the shareholding table is misread")


    if d.get("pe") is not None and not -1000 <= d["pe"] <= 5000:
        w.append(f"P/E parsed as {d['pe']:g}")
    return w


def _pair_growth(series: list[float], name: str) -> dict:
    """Latest year's growth and the year before's, so deceleration is visible."""
    out: dict = {}
    if len(series) >= 2 and series[-2]:
        out[f"{name}_growth_1y_pct"] = round((series[-1] / abs(series[-2]) - 1) * 100, 2)
    if len(series) >= 3 and series[-3]:
        out[f"{name}_growth_prev_1y_pct"] = round((series[-2] / abs(series[-3]) - 1) * 100, 2)
    return out


def _recency(d: dict) -> tuple[int, int]:
    """How current and how deep a parsed sheet is — the key both modes are compared on."""
    labs = d.get("fy_labels") or []
    year = 0
    if labs:
        m = re.search(r"(\d{4})", labs[-1])
        year = int(m.group(1)) if m else 0
    return (year, len(labs))


def fetch(symbol: str) -> dict | None:
    """The better of Screener's consolidated and standalone views, not merely the first that loads.

    GE Vernova T&D India publishes a consolidated page whose profit-and-loss table holds exactly
    one column, **Dec 2010**. Taking consolidated on sight scored that company 55 out of 100 off a
    sixteen-year-old sheet, with no flag and no gap, because every check I had asked whether a
    figure was present rather than whether it was current. So both views are parsed and the more
    recent, deeper one wins; if they tie, consolidated wins, which is the right default.
    """
    sym = quote(symbol, safe="")      # GVT&D, M&M: an unencoded "&" cuts the path short
    best: dict | None = None
    for mode in ("consolidated/", ""):
        r = http().get(SCREENER.format(sym=sym, mode=mode), ttl=timedelta(hours=24))
        if r is not None and not r.headers.get("X-From-Cache"):
            time.sleep(0.8)   # screener.in rate-limits bursts
        if r is None or r.status_code != 200 or "Market Cap" not in r.text:
            continue
        d = _parse(r.text)
        d["source"] = f"screener.in/{mode or 'standalone'}"
        if best is None or _recency(d) > _recency(best):
            if best is not None:
                d["mode_note"] = (f"read {d['source']} rather than {best['source']}: "
                                  f"the latter's last annual column is {(best.get('fy_labels') or ['—'])[-1]}")
            best = d
    return best


# A finding in this list does not get averaged away — it puts a ceiling on the score. That is the
# structural fix: Enviro Infra scored 92 with three consecutive years of negative operating cash
# flow, because every flaw was one term among nine and the good levels outvoted them. A company
# burning cash cannot be a 92 no matter how clean its balance sheet looks.
CAPS = "caps"

# How much each dimension of a company may move the score, at most, in each direction.
#
# The 92 and the 100 are the same defect seen from opposite ends. ROCE, ROE and operating margin
# are three readings of one fact — profitability — and awarding +12, +8 and a margin bonus counts
# that fact three times; a strong company therefore accumulated past 100 and clipped, while Enviro
# Infra's single genuine strength was similarly triple-counted against its one fatal weakness.
# Budgets stop the double counting: a dimension contributes what it is worth once, however many
# ratios happen to express it.
#
# The positive budgets sum to 40 against a base of 50, so **90 is the highest score this module can
# produce**. That is deliberate. A public ratio page cannot tell the 90th percentile from the 99th,
# and a number that claims it would be pretending. The last ten points are not available to any
# company, which is a more honest statement than handing out a 100.
BUDGET = {
    "returns":   (10, -8),    # ROCE, ROE
    "growth":    (8, -16),    # the CAGRs, last year, the deceleration, latest quarter
    "cash":      (8, -16),    # operating cash flow and its conversion
    "balance":   (5, -18),    # debt/equity, interest cover, borrowing trend
    "value":     (5, -10),    # P/E, PEG
    "ownership": (3, -10),    # promoter, pledge, institutions
    "size":      (1, -6),     # market cap
}
BASE = 50.0


def assess(f: dict | None) -> dict:
    """→ {score, why, flags, caps, coverage}. The full read; `score()` is the two-value wrapper.

    Levels tell you what a company *is*; trends and cash tell you where it is *going*, and the second
    is what a fundamentals number is usually asked for. This weighs both, and refuses to hide a
    red flag inside an average.
    """
    if not f:
        return {"score": 40, "why": ["no fundamentals data (neutral-low)"], "flags": [],
                "caps": [], "coverage": {"seen": [], "missing": ["everything"]}}

    out = score(f, _internal=True)
    return out


def score(f: dict | None, _internal: bool = False):
    """0–100 fundamentals score with a human-readable breakdown."""
    if not f:
        return ({"score": 40, "why": ["no fundamentals data (neutral-low)"], "flags": [], "caps": [],
                 "coverage": {"seen": [], "missing": ["everything"]}} if _internal
                else (40, ["no fundamentals data (neutral-low)"]))
    why: list[str] = []
    flags: list[str] = []
    caps: list[tuple[int, str]] = []
    got: dict[str, float] = {}
    cur = "returns"

    def flag(ceiling: int, reason: str):
        flags.append(reason)
        caps.append((ceiling, reason))

    def add(points, reason):
        got[cur] = got.get(cur, 0.0) + points
        why.append(f"{'+' if points >= 0 else ''}{points:g} {reason}")

    # A model that does not fit must decline, not produce a number anyway. Yes Bank came out of the
    # industrial scorer at 68 and Bajaj Finance at 45 — the latter capped for "operating cash flow
    # negative 12 years running", which for a lender is not a finding at all: disbursing a loan is
    # an operating outflow, so a growing NBFC's operating cash flow is negative by construction.
    # Capping the number was not enough, because the reason printed underneath it was false. There
    # is no honest way to run this scorer on a balance-sheet business, so it does not run.
    if f.get("model_misfit"):
        note = ("not rated: this scorer reads an operating company's accounts. "
                + f["model_misfit"])
        out = {"score": 50, "raw_score": 50, "why": [note], "flags": [note], "caps": [],
               "unrated": True, "coverage": {"missing": []}}
        return out if _internal else (50, [note])

    roe, roce, pe = f.get("roe"), f.get("roce"), f.get("pe")
    if roce is not None:
        add(12 if roce >= 20 else 6 if roce >= 15 else -4 if roce < 8 else 0, f"ROCE {roce:g}%")
    if roe is not None:
        add(8 if roe >= 18 else 4 if roe >= 12 else -4 if roe < 6 else 0, f"ROE {roe:g}%")
    cur = "value"
    if pe is not None:
        add(6 if 8 <= pe <= 25 else 2 if pe <= 40 else -6 if pe > 70 else -2, f"P/E {pe:g}")
    elif f.get("market_cap_cr"):
        add(-8, "loss-making (no P/E)")
    cur = "growth"
    pg3 = f.get("profit_growth_3_years")
    sg3 = f.get("sales_growth_3_years")
    if pg3 is not None:
        add(8 if pg3 >= 20 else 4 if pg3 >= 10 else -6 if pg3 < 0 else 0, f"3y profit CAGR {pg3:g}%")
    if sg3 is not None:
        add(6 if sg3 >= 15 else 3 if sg3 >= 8 else -4 if sg3 < 0 else 0, f"3y sales CAGR {sg3:g}%")
    cur = "balance"
    de = f.get("debt_to_equity")
    if de is not None:
        add(5 if de < 0.3 else 2 if de < 0.8 else -6 if de > 2 else -2, f"D/E {de:g}")
    cur = "ownership"
    pr = f.get("promoter_pct")
    if pr is not None:
        add(4 if pr >= 50 else 0 if pr >= 30 else -3, f"promoter {pr:g}%")
        chg = f.get("promoter_pct_chg_4q")
        if chg is not None and chg <= -2:
            add(-5, f"promoter stake down {chg:g}pp in 4q")
    if f.get("pledged_pct"):
        add(-8 if f["pledged_pct"] > 20 else -3, f"pledge {f['pledged_pct']:g}%")
    cur = "growth"
    npg = f.get("np_yoy_growth_pct")
    if npg is not None:
        add(4 if npg >= 15 else -5 if npg < -15 else 0, f"latest qtr PAT YoY {npg:g}%")
    cur = "size"
    mc = f.get("market_cap_cr")
    if mc is not None:
        add(4 if mc >= 50000 else 2 if mc >= 10000 else -6 if mc < 1000 else 0, f"mcap ₹{mc:,.0f} cr")

    # ---------------------------------------------------------------- does the profit become cash?
    cur = "cash"
    cfo, pat = f.get("cfo_cr"), f.get("np_latest_q")
    pat_fy = f.get("profit_fy_cr")
    conv = None
    if cfo is not None and (f.get("revenue_fy_cr") or 0):
        base = pat_fy or (f.get("revenue_fy_cr") or 0) * 0.1
        if base:
            conv = cfo / abs(base)
    if cfo is not None:
        if cfo < 0:
            add(-14, f"operating cash flow ₹{cfo:,.0f}cr — the business consumed cash last year")
        elif conv is not None and conv >= 0.8:
            add(8, f"operating cash flow ₹{cfo:,.0f}cr, {conv:.0%} of profit — profit is turning into cash")
        elif conv is not None and conv >= 0.4:
            add(3, f"operating cash flow ₹{cfo:,.0f}cr, only {conv:.0%} of profit")
        elif conv is not None:
            add(-6, f"operating cash flow ₹{cfo:,.0f}cr, just {conv:.0%} of profit")
    streak = f.get("cfo_negative_streak") or 0
    if streak >= 2:
        flag(45, f"operating cash flow has been negative {streak} years running")
    if cfo is not None and cfo < 0 and (f.get("borrowings_growth_pct") or 0) > 50:
        flag(40, f"borrowings up {f['borrowings_growth_pct']:.0f}% while the business burned cash — "
                 f"the growth is being funded, not earned")

    # ---------------------------------------------------------------- is the growth still happening?
    cur = "growth"
    for label, key in (("sales", "sales"), ("profit", "profit")):
        now = f.get(f"{key}_growth_1y_pct")
        before = f.get(f"{key}_growth_prev_1y_pct")
        if now is not None and before is not None and before > 25 and now < before / 3:
            add(-8, f"{label} growth has stalled: {now:.1f}% last year against {before:.1f}% the year "
                    f"before")
            break

    # a long CAGR that the latest year contradicts is describing a boom that has ended
    for label, cagr_key, now_key in (("profit", "profit_growth_3_years", "profit_growth_1y_pct"),
                                     ("sales", "sales_growth_3_years", "sales_growth_1y_pct")):
        cagr, now = f.get(cagr_key), f.get(now_key)
        if cagr and now is not None and cagr > 25 and now < 10:
            add(-5, f"the {label} 3-year CAGR of {cagr:g}% is history — last year was {now:.1f}%")

    # ---------------------------------------------------------------- can it carry its debt?
    cur = "balance"
    cover = f.get("interest_cover")
    if cover is not None:
        falling = f.get("interest_cover_falling")
        if cover < 3:
            add(-12, f"interest cover {cover:g}× — thin")
        elif cover < 6:
            add(-6 if falling else -3, f"interest cover {cover:g}×" + (" and falling" if falling else ""))
        elif cover >= 10:
            add(4, f"interest cover {cover:g}×")
        if falling and cover < 6:
            flag(55, f"interest cover has fallen every quarter to {cover:g}×")
    ig = f.get("interest_growth_yoy_pct")
    if ig is not None and ig > 40:
        add(-4, f"interest cost up {ig:.0f}% year on year")
    bg = f.get("borrowings_growth_pct")
    if bg is not None and bg > 50:
        add(-10 if bg > 100 else -6, f"borrowings up {bg:.0f}% year on year")

    # ---------------------------------------------------------------- will anyone else own it?
    cur = "ownership"
    inst = f.get("institutional_pct")
    if inst is not None and (mc or 0) >= 2000:
        if inst < 2:
            add(-5, f"institutions hold {inst:g}% — desks with their own analysts are staying out")
        elif inst >= 15:
            add(3, f"institutions hold {inst:g}%")

    # ---------------------------------------------------------------- price against growth
    cur = "value"
    peg = f.get("peg")
    if peg is None and f.get("pe") and f.get("profit_growth_1y_pct"):
        g = f["profit_growth_1y_pct"]
        peg = round(f["pe"] / g, 2) if g > 0 else None
    if peg is not None and peg > 4:
        add(-6, f"PEG {peg:g} — priced for growth it is not delivering")

    # ---------------------------------------------------------------- what could not be seen
    wanted = {"cfo_cr": "cash flow", "sales_growth_1y_pct": "last year's growth",
              "interest_cover": "interest cover", "borrowings_growth_pct": "borrowing trend"}
    if f.get("interest_immaterial"):
        # "this company has no debt to service" is knowledge, not a gap, and must not be charged
        # the partial-view ceiling: it capped Infosys, TCS and HAL at 75 for being debt-free.
        wanted.pop("interest_cover")
    missing = [name for key, name in wanted.items() if f.get(key) is None]
    if missing:
        # "I could not see the cash flow" is not the same as "the cash flow is fine"
        flag(75, "could not read " + ", ".join(missing) + " — this score is a partial view")

    # A model that does not fit must say so rather than produce a number anyway. Yes Bank came out
    # of the industrial scorer at 68 — computed from a debt/equity ratio that is meaningless for a
    # lender and an operating cash flow that is mostly deposit flows. 55 is not a verdict on the
    # bank; it is this module declining to pretend it can grade one.
    # A sheet that contradicts itself has been misread somewhere, and I do not know where. That is
    # worse than a gap, so the ceiling is lower than the one for missing data.
    for warning in (f.get("parse_warnings") or []):
        flag(60, f"the page did not read cleanly — {warning}")

    # Compose: each dimension's net contribution, clamped to what that dimension is allowed to be
    # worth. A clamp is reported, because "profitability was as good as profitability gets" is a
    # different statement from "profitability was worth twenty points".
    s = BASE
    for dim, total in got.items():
        hi, lo = BUDGET.get(dim, (99, -99))
        clamped = max(lo, min(hi, total))
        s += clamped
        if clamped != round(total, 2):
            why.append(f"  ({dim} counted {clamped:+g} of {total:+g} — its terms measure the same "
                       f"thing more than once, so it is worth {hi:+g} at most)")

    raw = int(max(0, min(100, round(s))))
    final = raw
    applied = []
    for ceiling, reason in sorted(caps):
        if final > ceiling:
            applied.append(f"capped at {ceiling}: {reason}")
            final = ceiling
    why += [f"⚑ {a}" for a in applied]

    if _internal:
        return {"score": final, "raw_score": raw, "why": why, "flags": flags,
                "caps": applied, "coverage": {"missing": missing}}
    return final, why
