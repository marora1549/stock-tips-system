"""Markets Mojo calls, pasted straight out of the browser.

Two shapes come off that site and both arrive as one column of text once pasted:

**The table** — every call on the screen, fifteen fields a row in a fixed order, with the header
block above it and blank lines everywhere:

    Kennametal India / Buy / Monthly / Small Cap / Engineering / 4,658.40 / -0.79% /
    4,700.70 / 07-Sep-2026 / 5,168.90 / 4,385.73 / -0.90% / 1 day / 10.96% / Follow

**One call's detail panel** — label/value pairs, and the stock name may or may not come with it:

    Call / BUY · Call type / Positional - Monthly · Recommended Price / Rs 4,700.70 ·
    Target Price / Rs 5,168.90 · Stop Loss / Rs 4,385.73 · Recommended on / 07 Sep 2026

Both are read here into the same record. Their entry, target and stop are recorded as *claims* —
`src_entry`, `src_targets`, `src_stop` — never as levels; the desk reads the chart itself and grades
Mojo later on what its calls actually did.

The names are the hard part. Mojo truncates them to fit its column: `Motil.Oswal.Fin.`,
`Container Corpn.`, `Firstsour.Solu.`. Matching is done against the NSE master offline, and when two
companies fit equally well the row comes back **ambiguous with its candidates** rather than guessed —
a tip on the wrong symbol is worse than no tip.
"""
from __future__ import annotations

import re
from datetime import datetime

from ..data import symbols

# ------------------------------------------------------------------ field readers
CALL_WORDS = {"buy": "buy", "sell": "sell", "hold": "hold", "accumulate": "buy", "reduce": "sell"}
MCAPS = {"large cap", "mid cap", "small cap", "micro cap", "nano cap"}
NUM = re.compile(r"^-?(?:rs\.?\s*)?[\d,]+(?:\.\d+)?$", re.I)
PCT = re.compile(r"^-?[\d.]+\s*%$")
DAYS = re.compile(r"^(\d+)\s*(day|days|week|weeks|month|months)$", re.I)
DATE_FORMATS = ("%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d/%m/%Y", "%Y-%m-%d")


def _num(s: str) -> float | None:
    if s is None:
        return None
    t = re.sub(r"(?i)^rs\.?\s*", "", str(s)).replace(",", "").replace("₹", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _date(s: str) -> str | None:
    t = str(s or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _timeframe(call_type: str) -> str:
    t = (call_type or "").lower()
    if "intraday" in t or "day trad" in t:
        return "intraday"
    if "week" in t:
        return "weekly"
    if "month" in t or "positional" in t:
        return "monthly"
    if "long" in t or "year" in t:
        return "long"
    return "monthly"


# ------------------------------------------------------------------ the table paste
TABLE_FIELDS = ("mcap", "sector", "current_price", "days_change", "src_entry", "entry_date",
                "src_target", "src_stop", "performance", "days_since", "returns_till_target")


def parse_table(lines: list[str]) -> list[dict]:
    """Read the bulk table paste: a name, a Buy/Sell, then eleven fields, then Follow."""
    out: list[dict] = []
    i = 0
    while i < len(lines):
        word = CALL_WORDS.get(lines[i].strip().lower())
        # a call word with a plausible name above it and a call type below it starts a row
        if not word or i == 0 or i + 2 >= len(lines):
            i += 1
            continue
        name = lines[i - 1].strip()
        if not name or CALL_WORDS.get(name.lower()) or name.lower() in MCAPS or NUM.match(name):
            i += 1
            continue
        row: dict = {"company_raw": name, "action": word, "call_type": lines[i + 1].strip()}
        rest = lines[i + 2:i + 2 + len(TABLE_FIELDS)]
        if len(rest) < len(TABLE_FIELDS):
            i += 1
            continue
        for key, value in zip(TABLE_FIELDS, rest):
            row[key] = value.strip()
        # the shape has to hold, or this was not a row at all
        if row["mcap"].lower() not in MCAPS or not _num(row["src_entry"]) or not _num(row["src_target"]):
            i += 1
            continue
        out.append(_finish(row))
        i += 2 + len(TABLE_FIELDS)
    return out


# ------------------------------------------------------------------ the detail paste
LABELS = {
    "call": "action", "call type": "call_type", "recommended price": "src_entry",
    "target price": "src_target", "stop loss": "src_stop", "recommended on": "entry_date",
    "performance": "performance", "returns till target": "returns_till_target",
    "current price": "current_price", "cmp": "current_price", "probable success rate": "success_rate",
    "sector": "sector", "mcap": "mcap",
}


def parse_detail(lines: list[str]) -> list[dict]:
    """Read one call's detail panel: label lines followed by their value lines."""
    clean = [ln.strip() for ln in lines]
    row: dict = {}
    used: set[int] = set()                      # lines that are a label or a label's value
    for i, line in enumerate(clean):
        key = LABELS.get(re.sub(r"[:\s]+$", "", line).lower())
        if key is None:
            continue
        j = next((k for k in range(i + 1, min(i + 3, len(clean))) if clean[k]), None)
        if j is None or LABELS.get(clean[j].lower()):
            continue
        row[key] = clean[j]
        used.update({i, j})
    if "action" not in row or not _num(row.get("src_entry")) or not _num(row.get("src_target")):
        return []
    # whatever is left over and reads like a company name is the stock; the panel often omits it
    name = next((line for i, line in enumerate(clean)
                 if i not in used and re.search(r"[A-Za-z]{3}", line)
                 and not CALL_WORDS.get(line.lower()) and not NUM.match(line) and not PCT.match(line)), "")
    row["action"] = CALL_WORDS.get(str(row["action"]).strip().lower(), "buy")
    row["company_raw"] = name
    return [_finish(row)]


def _finish(row: dict) -> dict:
    """Normalise one raw row into the record the importer works with."""
    entry, target, stop = _num(row.get("src_entry")), _num(row.get("src_target")), _num(row.get("src_stop"))
    out = {
        "company_raw": row.get("company_raw", "").strip(),
        "action": row.get("action", "buy"),
        "call_type": row.get("call_type", ""),
        "timeframe": _timeframe(row.get("call_type", "")),
        "src_entry": entry, "src_targets": [target] if target else [], "src_stop": stop,
        "current_price": _num(row.get("current_price")),
        "entry_date": _date(row.get("entry_date")) or None,
        "sector": row.get("sector") or None,
        "mcap": row.get("mcap") or None,
        "performance_pct": _num(str(row.get("performance", "")).rstrip("%")),
        "returns_till_target_pct": _num(str(row.get("returns_till_target", "")).rstrip("%")),
        "days_since": row.get("days_since") or None,
    }
    # a Sell call has its target below the entry; that is a short, which this desk cannot take
    if entry and target:
        out["direction"] = "long" if target > entry else "short"
    else:
        out["direction"] = "long"
    if out["action"] == "buy" and out["direction"] == "short":
        out["action"] = "sell"          # trust the arithmetic over the label
    return out


def parse(text: str) -> list[dict]:
    """Read either paste shape. The table wins when both could apply, because it carries more."""
    lines = [ln for ln in (text or "").replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        return []
    rows = parse_table(lines)
    return rows if rows else parse_detail(lines)


# ------------------------------------------------------------------ name → NSE symbol
def resolve_name(name: str, master, floor: float = 0.72, margin: float = 0.06) -> dict:
    """Mojo's truncated names against the NSE master. See `data.symbols.resolve_offline`."""
    return symbols.resolve_offline(name, master, floor=floor, margin=margin)
