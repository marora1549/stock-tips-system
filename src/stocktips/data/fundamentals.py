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
        sales_y = _row_values(pl.group(0), "Sales") or _row_values(pl.group(0), "Revenue")
        if sales_y:
            d["revenue_fy_cr"] = sales_y[-1]
            d.setdefault("revenue_ttm_cr", sales_y[-1])
            d.setdefault("revenue_basis", "last reported financial year")
    return d


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


def score(f: dict | None) -> tuple[int, list[str]]:
    """0–100 fundamentals score with a human-readable breakdown."""
    if not f:
        return 40, ["no fundamentals data (neutral-low)"]
    s, why = 50.0, []

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
    return int(max(0, min(100, round(s)))), why
