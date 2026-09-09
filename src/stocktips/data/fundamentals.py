"""Fundamentals from Screener.in (public company page, consolidated → standalone fallback).

Produces a 0–100 fundamentals score. The score is deliberately simple and
transparent — every component is listed in `breakdown` so a run's report can
say *why* a company is "hold-worthy" rather than a hot potato.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import timedelta
from urllib.parse import quote

from ..util import http

log = logging.getLogger(__name__)

SCREENER = "https://www.screener.in/company/{sym}/{mode}"


def _num(s: str) -> float | None:
    s = html.unescape(s).replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _row_values(block: str, row_name: str) -> list[float]:
    """Values of a table row whose first cell *contains* row_name (cells may wrap the label in a <button>)."""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not cells:
            continue
        label = re.sub(r"<[^>]+>", " ", cells[0])
        label = re.sub(r"\s+", " ", html.unescape(label)).replace("+", "").strip()
        if label.lower() == row_name.lower():
            vals = []
            for c in cells[1:]:
                v = _num(re.sub(r"<[^>]+>", " ", c))
                if v is not None:
                    vals.append(v)
            return vals
    return []


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
            vals = _row_values(blk, who)
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
        vals = _row_values(qs.group(0), "Net Profit")
        if True:
            if len(vals) >= 5:
                d["np_latest_q"], d["np_yoy_q"] = vals[-1], vals[-5]
                d["np_yoy_growth_pct"] = round((vals[-1] / abs(vals[-5]) - 1) * 100, 1) if vals[-5] else None
        # Trailing twelve months of sales — the denominator for "is this order material?". The last
        # four quarters beat the last annual column, which can be nine months stale by Q3.
        sales_q = _row_values(qs.group(0), "Sales") or _row_values(qs.group(0), "Revenue")
        if len(sales_q) >= 4:
            d["revenue_ttm_cr"] = round(sum(sales_q[-4:]), 2)
            d["revenue_basis"] = "trailing 4 quarters"

    # Annual sales, as the fallback and for the growth read
    pl = re.search(r'id="profit-loss".*?</section>', h, re.S)
    if pl:
        blk = pl.group(0)
        sales_y = _row_values(blk, "Sales") or _row_values(blk, "Revenue")
        if sales_y:
            d["revenue_fy_cr"] = sales_y[-1]
            d.setdefault("revenue_ttm_cr", sales_y[-1])
            d.setdefault("revenue_basis", "last reported financial year")
        # Last year against the year before it. A three-year CAGR averages a boom with the bust
        # that follows it: Enviro Infra's sales CAGR was 50% while the latest year grew 7.5%, and the
        # CAGR is what the score was reading.
        d.update(_pair_growth(sales_y, "sales"))
        d.update(_pair_growth(_row_values(blk, "Net Profit"), "profit"))
        d.update(_pair_growth(_row_values(blk, "Operating Profit"), "opm_abs"))
        opm = _row_values(blk, "OPM %")
        if len(opm) >= 2:
            d["opm_pct"], d["opm_pct_prev"] = opm[-1], opm[-2]

    # Cash flow. The most important section in the file and it was not being read at all.
    cf = re.search(r'id="cash-flow".*?</section>', h, re.S)
    if cf:
        ops = (_row_values(cf.group(0), "Cash from Operating Activity")
               or _row_values(cf.group(0), "Cash from Operating Activity +")
               or _row_values(cf.group(0), "Net Cash Flow from Operating Activities"))
        if ops:
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
        bor_series = _row_values(bs.group(0), "Borrowings")
        if len(bor_series) >= 2 and bor_series[-2]:
            d["borrowings_cr"] = bor_series[-1]
            d["borrowings_growth_pct"] = round((bor_series[-1] / abs(bor_series[-2]) - 1) * 100, 1)

    # Quarterly interest and operating profit, for the coverage trend
    if qs:
        blk = qs.group(0)
        interest = _row_values(blk, "Interest")
        op = _row_values(blk, "Operating Profit")
        if interest and op and len(interest) == len(op):
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
    return d


def _pair_growth(series: list[float], name: str) -> dict:
    """Latest year's growth and the year before's, so deceleration is visible."""
    out: dict = {}
    if len(series) >= 2 and series[-2]:
        out[f"{name}_growth_1y_pct"] = round((series[-1] / abs(series[-2]) - 1) * 100, 2)
    if len(series) >= 3 and series[-3]:
        out[f"{name}_growth_prev_1y_pct"] = round((series[-2] / abs(series[-3]) - 1) * 100, 2)
    return out


def fetch(symbol: str) -> dict | None:
    sym = quote(symbol, safe="")      # GVT&D, M&M: an unencoded "&" cuts the path short
    for mode in ("consolidated/", ""):
        r = http().get(SCREENER.format(sym=sym, mode=mode), ttl=timedelta(hours=24))
        if r is not None and not r.headers.get("X-From-Cache"):
            time.sleep(0.8)   # screener.in rate-limits bursts
        if r is not None and r.status_code == 200 and "Market Cap" in r.text:
            d = _parse(r.text)
            d["source"] = f"screener.in/{mode or 'standalone'}"
            return d
    return None


# A finding in this list does not get averaged away — it puts a ceiling on the score. That is the
# structural fix: Enviro Infra scored 92 with three consecutive years of negative operating cash
# flow, because every flaw was one term among nine and the good levels outvoted them. A company
# burning cash cannot be a 92 no matter how clean its balance sheet looks.
CAPS = "caps"


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
    s, why = 50.0, []
    flags: list[str] = []
    caps: list[tuple[int, str]] = []

    def flag(ceiling: int, reason: str):
        flags.append(reason)
        caps.append((ceiling, reason))

    def add(points, reason):
        nonlocal s
        s += points
        why.append(f"{'+' if points >= 0 else ''}{points:g} {reason}")

    roe, roce, pe = f.get("roe"), f.get("roce"), f.get("pe")
    if roce is not None:
        add(12 if roce >= 20 else 6 if roce >= 15 else -4 if roce < 8 else 0, f"ROCE {roce:g}%")
    if roe is not None:
        add(8 if roe >= 18 else 4 if roe >= 12 else -4 if roe < 6 else 0, f"ROE {roe:g}%")
    if pe is not None:
        add(6 if 8 <= pe <= 25 else 2 if pe <= 40 else -6 if pe > 70 else -2, f"P/E {pe:g}")
    elif f.get("market_cap_cr"):
        add(-8, "loss-making (no P/E)")
    pg3 = f.get("profit_growth_3_years")
    sg3 = f.get("sales_growth_3_years")
    if pg3 is not None:
        add(8 if pg3 >= 20 else 4 if pg3 >= 10 else -6 if pg3 < 0 else 0, f"3y profit CAGR {pg3:g}%")
    if sg3 is not None:
        add(6 if sg3 >= 15 else 3 if sg3 >= 8 else -4 if sg3 < 0 else 0, f"3y sales CAGR {sg3:g}%")
    de = f.get("debt_to_equity")
    if de is not None:
        add(5 if de < 0.3 else 2 if de < 0.8 else -6 if de > 2 else -2, f"D/E {de:g}")
    pr = f.get("promoter_pct")
    if pr is not None:
        add(4 if pr >= 50 else 0 if pr >= 30 else -3, f"promoter {pr:g}%")
        chg = f.get("promoter_pct_chg_4q")
        if chg is not None and chg <= -2:
            add(-5, f"promoter stake down {chg:g}pp in 4q")
    if f.get("pledged_pct"):
        add(-8 if f["pledged_pct"] > 20 else -3, f"pledge {f['pledged_pct']:g}%")
    npg = f.get("np_yoy_growth_pct")
    if npg is not None:
        add(4 if npg >= 15 else -5 if npg < -15 else 0, f"latest qtr PAT YoY {npg:g}%")
    mc = f.get("market_cap_cr")
    if mc is not None:
        add(4 if mc >= 50000 else 2 if mc >= 10000 else -6 if mc < 1000 else 0, f"mcap ₹{mc:,.0f} cr")

    # ---------------------------------------------------------------- does the profit become cash?
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
    inst = f.get("institutional_pct")
    if inst is not None and (mc or 0) >= 2000:
        if inst < 2:
            add(-5, f"institutions hold {inst:g}% — desks with their own analysts are staying out")
        elif inst >= 15:
            add(3, f"institutions hold {inst:g}%")

    # ---------------------------------------------------------------- price against growth
    peg = f.get("peg")
    if peg is None and f.get("pe") and f.get("profit_growth_1y_pct"):
        g = f["profit_growth_1y_pct"]
        peg = round(f["pe"] / g, 2) if g > 0 else None
    if peg is not None and peg > 4:
        add(-6, f"PEG {peg:g} — priced for growth it is not delivering")

    # ---------------------------------------------------------------- what could not be seen
    wanted = {"cfo_cr": "cash flow", "sales_growth_1y_pct": "last year's growth",
              "interest_cover": "interest cover", "borrowings_growth_pct": "borrowing trend"}
    missing = [name for key, name in wanted.items() if f.get(key) is None]
    if missing:
        # "I could not see the cash flow" is not the same as "the cash flow is fine"
        flag(75, "could not read " + ", ".join(missing) + " — this score is a partial view")

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
