"""Corporate events out of news text — who, what happened, how big, how sure.

`extract.py` reads *recommendations*: buy X, target Y, stop Z. Corporate news has none of those.
"GE Vernova T&D India in focus as Power Grid secures 6,000 MW Barmer HVDC project" carries no target
price and does not even name a rupee value, yet it was worth 9% the next morning. What it carries is
an **event**, and this module reads that shape instead.

Three things make it harder than it looks:

**The named company is often not the tradable one.** The headline's subject is Power Grid — a utility
too large to move on its own capex. The name that moves supplies the equipment. `config/themes.yaml`
maps the event's vocabulary to the NSE names that actually trade on it, and `buyers` in that file
stops the awarding party being read as the beneficiary of its own spending.

**A story with a named winner is not a story about the whole theme.** When one theme play is named,
the others are demoted to sympathy weight rather than emitted as equals: GE Vernova won the bid,
Hitachi Energy did not, and a system that cannot tell the difference sends two emails and is wrong
about one of them.

**The size is often missing.** GE Vernova's announcement gave a capacity, not a value. Themes carry
a cost-per-unit rule, so 6,000 MW of HVDC terminal becomes an estimate of about ₹12,600cr — close
enough to Nomura's ₹12,980cr to make materiality computable. Estimates are always marked as such.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..data.symbols import master as symbol_master, resolve_offline
from ..util import CONFIG_DIR, load_yaml, short_hash
from .extract import BOILERPLATE, company_names_in

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ event taxonomy
# `sign` is the direction of the surprise; `certainty` is how firm the event is (an MoU is not an
# order). `prior` is the seed weight the catalyst scorer starts from — outcomes move it from there,
# so these are estimates on the record, not constants.
EVENT_CLASSES: dict[str, dict] = {
    "order_win": {
        "label": "Order win", "sign": 1, "certainty": 1.0, "prior": 30,
        "patterns": [r"\b(?:wins?|won|bags?|bagged|secures?|secured|receives?|received|awarded)\b[^.]{0,80}"
                     r"\b(?:order|contract|project|tender|loa|letter of award|work order)\b",
                     r"\b(?:order|contract)\b[^.]{0,40}\b(?:worth|valued at|of rs)\b"],
    },
    "l1_bidder": {
        "label": "L1 bidder", "sign": 1, "certainty": 0.8, "prior": 24,
        "patterns": [r"\bl1\b(?:\s+bidder)?", r"\blowest bidder\b", r"\bemerge[sd]? as (?:the )?l1\b",
                     r"\bdeclared l1\b", r"\bl-1 bidder\b"],
    },
    "regulatory_approval": {
        "label": "Approval", "sign": 1, "certainty": 0.95, "prior": 26,
        "patterns": [r"\b(?:usfda|us fda|cdsco|dcgi|ema)\b[^.]{0,60}\bapprov",
                     r"\bfinal approval\b", r"\btentative approval\b", r"\banda approval\b",
                     r"\breceives?\b[^.]{0,40}\bapproval\b", r"\bestablishment inspection report\b",
                     r"\bzero (?:483s?|observations?)\b", r"\bpatent granted\b"],
    },
    "index_inclusion": {
        "label": "Index inclusion", "sign": 1, "certainty": 1.0, "prior": 18,
        "patterns": [r"\b(?:included in|inclusion in|added to)\b[^.]{0,40}\b(?:nifty|sensex|msci|ftse)\b",
                     r"\bmsci\b[^.]{0,30}\b(?:inclusion|added)\b"],
    },
    "earnings_beat": {
        "label": "Earnings beat", "sign": 1, "certainty": 1.0, "prior": 22,
        "patterns": [r"\b(?:profit|pat|net profit)\b[^.]{0,40}\b(?:jump|surge|rise|up|double|beat)s?\b",
                     r"\bbeats? (?:street|estimates?|expectations?)\b",
                     r"\brevenue\b[^.]{0,30}\b(?:jump|surge)s?\b"],
    },
    "guidance_raise": {
        "label": "Guidance raised", "sign": 1, "certainty": 0.9, "prior": 20,
        "patterns": [r"\braises? (?:its )?(?:fy\d+ )?guidance\b", r"\bguidance (?:raised|upgraded)\b",
                     r"\braises? (?:revenue|margin) outlook\b"],
    },
    "capacity_expansion": {
        "label": "Capacity expansion", "sign": 1, "certainty": 0.85, "prior": 14,
        "patterns": [r"\b(?:commission(?:s|ed|ing)?|expands?|expansion|new plant|greenfield|brownfield)\b"
                     r"[^.]{0,60}\b(?:capacity|plant|facility|unit|line)\b",
                     r"\bcapex\b[^.]{0,40}\b(?:announce|approv|plan)"],
    },
    "jv_partnership": {
        "label": "JV / partnership", "sign": 1, "certainty": 0.6, "prior": 12,
        "patterns": [r"\b(?:joint venture|jv with|partners? with|partnership with|signs? (?:an? )?mou|"
                     r"memorandum of understanding|strategic (?:tie-?up|alliance))\b"],
    },
    "stake_buy": {
        "label": "Insider / promoter buying", "sign": 1, "certainty": 0.9, "prior": 14,
        "patterns": [r"\bpromoters? (?:buy|bought|raise[sd]?|increase[sd]?|hike[sd]?)\b[^.]{0,30}\bstake\b",
                     r"\bopen offer\b", r"\bbuyback\b[^.]{0,30}\bapprov"],
    },
    "analyst_upgrade": {
        "label": "Broker upgrade", "sign": 1, "certainty": 0.5, "prior": 10,
        "patterns": [r"\b(?:upgrades?|upgraded)\b[^.]{0,40}\b(?:to buy|to outperform|to overweight|rating)\b",
                     r"\b(?:raises?|hikes?) target price\b", r"\binitiates? coverage\b[^.]{0,40}\bbuy\b"],
    },
    "corporate_action": {
        "label": "Dividend / bonus / split", "sign": 1, "certainty": 1.0, "prior": 8,
        "patterns": [r"\bbonus (?:issue|shares)\b", r"\bstock split\b", r"\bspecial dividend\b",
                     r"\brecord date\b[^.]{0,40}\b(?:bonus|split|dividend)\b"],
    },
    # --------------- the ones that mean stay away, and sell if you hold it
    "order_cancellation": {
        "label": "Order cancelled", "sign": -1, "certainty": 1.0, "prior": -24,
        "patterns": [r"\border\b[^.]{0,30}\b(?:cancell?ed|terminated|withdrawn)\b",
                     r"\bcontract (?:cancell?ed|terminated)\b", r"\bloses? (?:the )?contract\b"],
    },
    "regulatory_action": {
        "label": "Regulatory action", "sign": -1, "certainty": 1.0, "prior": -22,
        "patterns": [r"\b(?:sebi|income tax|ed |enforcement directorate|cbi|gst)\b[^.]{0,60}"
                     r"\b(?:probe|investigat|raid|search|notice|penalt|show cause|summons)\b",
                     r"\bimport alert\b", r"\bform 483\b", r"\bwarning letter\b", r"\bofficial action indicated\b"],
    },
    "earnings_miss": {
        "label": "Earnings miss", "sign": -1, "certainty": 1.0, "prior": -20,
        "patterns": [r"\b(?:profit|pat|net profit)\b[^.]{0,40}\b(?:fall|drop|decline|slump|plunge|miss)e?s?\b",
                     r"\bmisses? (?:street|estimates?|expectations?)\b", r"\bslips? into (?:a )?loss\b"],
    },
    "pledge": {
        "label": "Promoter pledge / stake sale", "sign": -1, "certainty": 1.0, "prior": -18,
        "patterns": [r"\bpledge[sd]?\b[^.]{0,30}\bshares?\b",
                     r"\bpromoters? (?:sell|sold|offload|pare[sd]?|cut)\b[^.]{0,30}\bstake\b"],
    },
    "dilution": {
        "label": "Equity dilution", "sign": -1, "certainty": 0.9, "prior": -16,
        "patterns": [r"\bqip\b", r"\bqualified institutional placement\b", r"\bpreferential (?:issue|allotment)\b",
                     r"\brights issue\b", r"\bfpo\b", r"\bofs\b", r"\boffer for sale\b"],
    },
    "analyst_downgrade": {
        "label": "Broker downgrade", "sign": -1, "certainty": 0.5, "prior": -14,
        "patterns": [r"\b(?:downgrades?|downgraded)\b", r"\bcuts? target price\b",
                     r"\b(?:to sell|to underperform|to underweight)\b"],
    },
    "exec_exit": {
        "label": "Senior exit", "sign": -1, "certainty": 0.8, "prior": -12,
        "patterns": [r"\b(?:ceo|cfo|managing director|md &|chairman)\b[^.]{0,40}\b(?:resign|steps? down|quits?|exits?)\b",
                     r"\bauditor resign"],
    },
}

# ------------------------------------------------------------------ money and capacity
# Everything is normalised to crore of rupees, because that is the unit Indian filings use and the
# unit revenue comes back in, and materiality is a ratio of the two.
MONEY_MULT = {
    "lakh crore": 100_000.0, "lakh cr": 100_000.0, "trillion": 100_000.0,
    "thousand crore": 1_000.0,
    "crore": 1.0, "cr": 1.0, "cr.": 1.0,
    "billion": 100.0, "bn": 100.0,
    "million": 0.1, "mn": 0.1,
    "lakh": 0.01,
}
MONEY_RE = re.compile(
    r"(?P<cur>rs\.?|₹|inr|us\$|\$|usd)?\s*"
    r"(?P<n>\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>lakh crore|lakh cr|thousand crore|crore|cr\.?|billion|bn|million|mn|lakh|trillion)\b",
    re.I)
CAPACITY_RE = re.compile(
    r"(?P<n>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>gwh|mwh|gw|mw|kms|km|mtpa|ktpa)\b", re.I)
CAPACITY_TO_BASE = {"gw": ("MW", 1000.0), "mw": ("MW", 1.0), "gwh": ("MWh", 1000.0), "mwh": ("MWh", 1.0),
                    "km": ("km", 1.0), "kms": ("km", 1.0), "mtpa": ("MTPA", 1.0), "ktpa": ("MTPA", 0.001)}


def _f(s: str) -> float:
    return float(s.replace(",", ""))


# The biggest number in the article is usually the wrong one. GE Vernova's story carries both the
# ₹12,980cr contract value and the ₹26,000cr *project* capex; the supplier only books the first, and
# using the second overstates materiality by two times. So amounts are ranked by what they sit next
# to, not by size.
WANTED_NEAR = re.compile(r"(?:contract|order|deal|loa|letter of award|work order|worth|valued at|"
                         r"value of|bid|tender|award(?:ed)?|supply)", re.I)
UNWANTED_NEAR = re.compile(r"(?:capex|capital expenditure|project cost|total cost|outlay|investment|"
                           r"programme|program|scheme|market cap|revenue|turnover|profit|ebitda|"
                           r"net worth|debt|borrowing|order book|pipeline)", re.I)


def _context(text: str, start: int, end: int) -> str:
    """What the amount sits beside. The qualifier almost always precedes the number — "contract value
    of Rs X", "capex of Rs X" — so look back further than forward, stay inside the sentence, and when
    both kinds of wording are present let the nearer one decide."""
    left = text.rfind(".", 0, start) + 1
    right = text.find(".", end)
    right = len(text) if right == -1 else right
    before = text[max(left, start - 48):start]
    after = text[end:min(right, end + 18)]
    def nearest(rx):
        hits = [start - (max(left, start - 48) + m.end()) for m in rx.finditer(before)]
        hits += [len(before) + m.start() for m in rx.finditer(after)]
        return min(hits) if hits else None
    w, u = nearest(WANTED_NEAR), nearest(UNWANTED_NEAR)
    if w is not None and (u is None or w <= u):
        return "contract"
    return "other" if u is not None else "bare"


def money_in_crore(text: str, usd_inr: float = 88.0) -> list[dict]:
    """Every rupee (or dollar) amount, normalised to crore, ranked by context then size.

    `context` is `contract` when the amount sits beside order/contract/award language, `other` when
    it sits beside capex/revenue/market-cap language, and `bare` when neither is nearby.
    """
    text = text or ""
    out = []
    for m in MONEY_RE.finditer(text):
        unit = m.group("unit").lower().rstrip(".")
        mult = MONEY_MULT.get(unit) or MONEY_MULT.get(unit + ".")
        if mult is None:
            continue
        value = _f(m.group("n")) * mult
        cur = (m.group("cur") or "").lower()
        if cur in ("$", "us$", "usd"):
            value *= usd_inr
        context = _context(text, m.start(), m.end())
        out.append({"inr_cr": round(value, 2), "text": m.group(0).strip(), "at": m.start(),
                    "currency": "USD" if cur in ("$", "us$", "usd") else "INR", "context": context})
    rank = {"contract": 0, "bare": 1, "other": 2}
    out.sort(key=lambda d: (rank[d["context"]], -d["inr_cr"]))
    return out


def capacity_in(text: str) -> list[dict]:
    """Capacity figures, normalised (GW→MW). Largest first, so "6,000 MW" beats "2x3000 MW"."""
    out = []
    for m in CAPACITY_RE.finditer(text or ""):
        base, mult = CAPACITY_TO_BASE[m.group("unit").lower()]
        out.append({"value": round(_f(m.group("n")) * mult, 3), "unit": base, "text": m.group(0).strip()})
    out.sort(key=lambda d: -d["value"])
    return out


# ------------------------------------------------------------------ themes
_THEMES: list[dict] | None = None


def themes() -> list[dict]:
    global _THEMES
    if _THEMES is None:
        _THEMES = (load_yaml(CONFIG_DIR / "themes.yaml") or {}).get("themes") or []
    return _THEMES


def _kw_present(kw: str, low: str) -> bool:
    """Word-bounded search — a plain substring check lets "cable" fire on "applicable"."""
    return re.search(r"(?<!\w)" + re.escape(kw.strip()) + r"(?!\w)", low) is not None


def themes_in(text: str) -> list[dict]:
    """Which themes this story belongs to, with the keyword that put it there."""
    low = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    hits = []
    for t in themes():
        got = [k for k in t.get("match", []) if _kw_present(k, low)]
        if not got:
            continue
        need = t.get("require")
        if need and not any(_kw_present(k, low) for k in need):
            continue
        hits.append({**t, "matched": got})
    return hits


# Pearl Global Industries was AVOID-flagged as an "earnings miss" on 11 September 2026 off a preview
# article that had not yet reported: "If that rate ever normalises, reported net profit falls
# without anything changing in operations." The pattern is a true reading of the sentence and a false
# reading of the company — nothing has fallen, it is a hypothetical about a tax rate. classify() scans
# a 12,000-char blob with no notion of a sentence being conditional, so any preview/analysis piece can
# manufacture a "miss" or a "beat" out of a what-if. Skip a match whose immediate lead-in is
# conditional and take the next occurrence of the same pattern instead.
_CONDITIONAL_LEADIN = re.compile(r"\b(?:if|unless|hypothetical(?:ly)?|assuming|were (?:it|that|this)|"
                                  r"in case|suppose|what if)\b")
_CONDITIONAL_WINDOW = 60


def _conditional(low: str, start: int) -> bool:
    return bool(_CONDITIONAL_LEADIN.search(low[max(0, start - _CONDITIONAL_WINDOW):start]))


def classify(text: str) -> list[dict]:
    """Every event class the text matches, strongest prior magnitude first."""
    low = re.sub(r"\s+", " ", (text or "").lower())
    out = []
    for cid, spec in EVENT_CLASSES.items():
        for pat in spec["patterns"]:
            hit = None
            for m in re.finditer(pat, low, re.I):
                if not _conditional(low, m.start()):
                    hit = m
                    break
            if hit:
                out.append({"event": cid, "label": spec["label"], "sign": spec["sign"],
                            "certainty": spec["certainty"], "prior": spec["prior"],
                            "phrase": hit.group(0)[:120], "at": hit.start()})
                break
    out.sort(key=lambda d: (-abs(d["prior"]), d["at"]))
    return out


# ------------------------------------------------------------------ who trades on it
NAME_FLOOR = 0.86      # a news scan throws hundreds of capitalised phrases at the matcher; only a
                       # confident hit becomes a candidate, because a wrong symbol is a wrong trade
DIRECTNESS_FLOOR = 0.3   # below this the link to the news is too thin to email anyone about
MAX_BENEFICIARIES = 6    # one story, a handful of names — not a sector

# Something has to tie the story to this market before the theme map fans it out. "Babcock LGE
# secures contract for four new VLGCs" is a UK marine-engineering firm building gas carriers for a
# European operator; the shipping theme fired on it and produced Adani Ports and Cochin Shipyard as
# candidates. A theme play with nobody named is already one inference — inferring the country too is
# two, and the second one was simply wrong.
INDIA_ANCHOR = re.compile(r"(?<!\w)(?:india|indian|nse|bse|sebi|nifty|sensex|crore|lakh|rupee|rs\.?\s*\d|₹)",
                          re.I)


def _named_symbols(text: str, title: str) -> dict[str, dict]:
    """Companies the article actually names, resolved to NSE symbols — offline, never a lookup.

    `resolve_offline` rather than `SymbolMaster.resolve`: the latter falls through to Moneycontrol
    when its fuzzy match is weak, and one article yields dozens of near-miss phrases, so a scan
    would spend its whole budget on requests for names that are not companies at all.
    """
    m = symbol_master()
    found: dict[str, dict] = {}
    # the title carries the subject; body names still count but rank below it
    for in_body_only, chunk in ((False, title or ""), (True, text or "")):
        for name in company_names_in(chunk):
            hit = resolve_offline(name, m, floor=NAME_FLOOR)
            sym = hit["symbol"]
            if not sym:
                continue
            prev = found.get(sym)
            if prev is None or (prev["in_body_only"] and not in_body_only):
                found[sym] = {"symbol": sym, "company": m.name_of(sym), "as_written": name,
                              "in_body_only": in_body_only, "confidence": hit["confidence"],
                              "method": "name:" + hit["method"]}
    return found


def estimate_size(theme: dict, caps: list[dict]) -> dict | None:
    """Turn a capacity into a rupee estimate using the theme's cost-per-unit rule."""
    rule = theme.get("cost_per")
    if not rule or not caps:
        return None
    want = str(rule.get("unit", "")).lower()
    for c in caps:
        if c["unit"].lower() == want:
            return {"inr_cr": round(c["value"] * float(rule["inr_cr"]), 2), "estimated": True,
                    "basis": f"{c['text']} × ₹{rule['inr_cr']}cr/{rule['unit']} ({rule.get('note', 'theme rule')})"}
    return None


def beneficiaries(text: str, title: str, matched_themes: list[dict]) -> list[dict]:
    """The tradable names, each with how it got here and how directly the news touches it.

    `named` — the article names it and it is not the awarding party. `theme` — the map says this
    kind of news flows to it. `sympathy` — a theme peer, where the story already names a winner;
    peers do move, but less, and pretending otherwise emits a candidate that is simply wrong.
    """
    named = _named_symbols(text, title)
    buyers = {b for t in matched_themes for b in (t.get("buyers") or [])}
    out: dict[str, dict] = {}

    for sym, info in named.items():
        if sym in buyers:
            continue                                   # it is spending the money, not receiving it
        out[sym] = {**info, "weight": 0.85 if info["in_body_only"] else 1.0, "route": "named",
                    "theme": None, "why": "named in the story"}

    # Whether the story names a winner is a fact about the story, not about one theme. The Barmer
    # scheme also contains 1,000km of line, so the transmission-EPC names are real sympathy plays —
    # but GE Vernova won the bid and they did not, and emitting them at equal weight would be a
    # candidate that is simply wrong.
    winner_named = bool(out)
    for t in matched_themes:
        for p in (t.get("plays") or []):
            sym = p["symbol"]
            if sym in buyers:
                continue
            if sym in out and out[sym]["route"] == "named":
                out[sym]["theme"] = t["id"]            # keep the full weight, gain the explanation
                out[sym]["why"] = p["why"]
                continue
            weight = float(p["weight"]) * (0.4 if winner_named else 1.0)
            route = "sympathy" if winner_named else "theme"
            if sym in out and out[sym]["weight"] >= weight:
                continue
            m = symbol_master()
            out[sym] = {"symbol": sym, "company": m.name_of(sym), "as_written": None,
                        "in_body_only": True, "confidence": 1.0, "method": "theme",
                        "weight": round(weight, 3), "route": route, "theme": t["id"], "why": p["why"]}

    keep = [b for b in out.values() if b["weight"] >= DIRECTNESS_FLOOR]
    return sorted(keep, key=lambda d: (-d["weight"], d["symbol"]))[:MAX_BENEFICIARIES]


# ------------------------------------------------------------------ one article → events
def _published_ts(published: str | None) -> datetime | None:
    if not published:
        return None
    try:
        return parsedate_to_datetime(published)
    except Exception:
        try:
            return datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except Exception:
            return None


# When two classes match the same story, which one is the story. These are *specificity* rules, not
# strength rules: "emerges as L1 bidder for the project Power Grid secured" matches both l1_bidder
# and order_win, and reading it as a signed order is the expensive mistake — it overstates both the
# certainty and the class prior. The qualified reading wins.
BEATS = {
    "l1_bidder": {"order_win"},                     # an L1 call is not a signed order
    "order_cancellation": {"order_win", "l1_bidder"},
    "regulatory_action": {"regulatory_approval"},   # a Form 483 is not an approval
    "earnings_miss": {"earnings_beat"},
    "analyst_downgrade": {"analyst_upgrade"},
    "pledge": {"stake_buy"},
}

# Newlines matter as much as full stops here. Headlines and ticker items carry no trailing period, so
# splitting on punctuation alone merges a company's name and an unrelated headline's rupee figure into
# one "sentence" — which is how a ₹24,700cr shipbuilding number ended up attached to a ₹97.66cr wagon
# order. `extract.clean` collapses all whitespace, so this module must not use it on the body.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def clean_blocks(text: str) -> str:
    """Tidy the text without destroying its line structure, and drop boilerplate lines."""
    lines = []
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r"[ \t\xa0]+", " ", raw).strip()
        if line and not BOILERPLATE.search(line):
            lines.append(line)
    return "\n".join(lines)


def sentences_about(blob: str, name: str | None) -> list[str]:
    """The article's sentences that actually mention this company."""
    if not name:
        return []
    low = name.lower()
    return [x for x in SENTENCE_SPLIT.split(blob) if low in x.lower()]


def class_for(blob: str, classes: list[dict], who: dict) -> dict | None:
    """Which of the story's events belongs to *this* company — or None when none of them do.

    Returning None is the important case. A "stocks to watch" column names a dozen companies and
    says something eventful about one of them: without this, Bharat Electronics' ₹2,100cr defence
    order was filed against Cipla, Reliance and Titan as well, at full directness, because they were
    named in the same article. Three false candidates from one column, on one of the wires this desk
    reads every morning.

    So for a company the article names, only the classes whose wording appears in a sentence that
    also mentions that company are eligible — and if none do, the article mentions the company
    without reporting an event about it, which is not a trade. `BEATS` then decides between what is
    left, and a negative class always wins, because "wins an order and pledges promoter shares" is
    not a story to buy.

    Nearest-phrase attribution was tried first and rejected: in the GE Vernova piece "as Power Grid
    secures the project" sits ten characters closer to the company's name than "emerged as the L1
    bidder" does, so proximity filed a bid as a signed contract. Grammar is not distance.
    """
    pool = classes
    if who.get("route") == "named":
        sents = sentences_about(blob, who.get("as_written"))
        joined = " ".join(x.lower() for x in sents)
        pool = [c for c in classes if c["phrase"].lower()[:40] in joined]
        if not pool:
            # A company in the headline is normally what the story is about, even when the eventful
            # sentence refers to it only by pronoun — so it keeps the story's event. But a headline
            # that lists five companies is a roundup, and appearing in that list says nothing at
            # all: "Stocks to watch: Reliance, Tata Motors, Bharat Electronics, Cipla, Titan" was
            # handing BEL's ₹2,100cr defence order to the other four.
            if who.get("in_body_only") or who.get("title_is_roundup"):
                return None
            pool = classes

    negatives = [c for c in pool if c["sign"] < 0]
    pool = negatives or pool
    ids = {c["event"] for c in pool}
    survivors = [c for c in pool if not (BEATS_INVERSE.get(c["event"], set()) & ids)]
    pool = survivors or pool
    return max(pool, key=lambda c: (abs(c["prior"]), -c["at"]))


BEATS_INVERSE: dict[str, set[str]] = {}
for _winner, _losers in BEATS.items():
    for _l in _losers:
        BEATS_INVERSE.setdefault(_l, set()).add(_winner)


def scan(doc: dict, source_id: str, usd_inr: float = 88.0) -> list[dict]:
    """One article → one event record per tradable name it implicates. [] when it implicates none."""
    title = doc.get("title") or ""
    body = clean_blocks(doc.get("text") or "")
    blob = (title + "\n" + body)[:12000]
    # A body recovered by scraping every paragraph on the page — no article container, no JSON-LD —
    # is an aggregator or an unparseable layout, and its text is not evidence about who did what.
    trusted_body = doc.get("body_how") in (None, "", "container", "jsonld")

    classes = classify(blob)
    if not classes:
        return []
    matched_themes = themes_in(blob)

    monies = [m for m in money_in_crore(blob, usd_inr) if m["context"] != "other"]
    caps = capacity_in(blob)
    size = ({"inr_cr": monies[0]["inr_cr"], "estimated": False,
             "basis": monies[0]["text"] + ("" if monies[0]["context"] == "contract" else " (no order wording nearby)")}
            if monies else None)
    if size is None:
        for t in matched_themes:
            size = estimate_size(t, caps)
            if size:
                break

    ts = _published_ts(doc.get("published"))
    people = beneficiaries(blob, title, matched_themes)
    # With a single named subject the article's figure is legitimately about it; with several, a
    # figure has to be found beside the company it belongs to or not used at all.
    n_named = sum(1 for b in people if b["route"] == "named")
    if people and all(b["route"] != "named" for b in people) and not INDIA_ANCHOR.search(blob):
        return []                # a theme fan-out onto a story that never mentions this market
    if not trusted_body:
        # Only what the headline itself says survives: a company named in the title is what the page
        # is about, and a theme play inferred from untrusted text is two guesses stacked.
        titled = set(_named_symbols("", title))
        people = [b for b in people if b["route"] == "named" and b["symbol"] in titled]
        if not people:
            return []
    # A headline naming three or more companies is a roundup, not a story about any of them.
    roundup = len(_named_symbols("", title)) >= 3

    out = []
    for who in people:
        top = class_for(blob, classes, {**who, "title_is_roundup": roundup})
        if top is None:
            continue          # named in the article, but the article reports no event about it
        mine = size
        # Only a company the article names can claim the order as its own. Everything reached
        # through the theme map — sympathy peer or full theme play — is an inference about who
        # benefits, not a record of who was awarded. Dividing the winner's order by an inferred
        # beneficiary's revenue produced "HAL · 0.6× revenue" off Tata's ₹20,000cr tank bid, which
        # reads as a fact about HAL and is not one. The deal size is still worth showing; the ratio
        # is not, and that holds even when the winner is unlisted and the peers are the only way to
        # trade it.
        own_order = who["route"] == "named"
        if who["route"] == "named":
            own = sentences_about(blob, who.get("as_written"))
            local = [m for m in money_in_crore("\n".join(own), usd_inr) if m["context"] == "contract"]
            if local:
                mine = {"inr_cr": local[0]["inr_cr"], "estimated": False, "basis": local[0]["text"]}
            elif n_named > 1:
                # The article names this company and gives no figure for it. Handing it the
                # article's biggest number is how "Vishnu Chemicals commissions new plant" acquired
                # the ₹404.88cr from a railway bid two lines away. Unknown is the honest answer, and
                # the catalyst score already says so out loud.
                mine = None
        out.append({
            "id": short_hash(f"{who['symbol']}|{top['event']}|{title[:80]}"),
            "symbol": who["symbol"], "company": who["company"],
            "event": top["event"], "event_label": top["label"], "sign": top["sign"],
            "certainty": top["certainty"], "event_prior": top["prior"], "phrase": top["phrase"],
            "also_matched": [c["event"] for c in classes if c["event"] != top["event"]][:3],
            "route": who["route"], "directness": who["weight"], "why_this_name": who["why"],
            "theme": who["theme"], "themes_matched": [t["id"] for t in matched_themes],
            "size_inr_cr": (mine or {}).get("inr_cr"), "size_estimated": (mine or {}).get("estimated", False),
            "size_basis": (mine or {}).get("basis"), "size_is_own_order": own_order,
            "capacity": caps[0] if caps else None,
            "source_id": source_id, "url": doc.get("url", ""), "title": title[:200],
            "published": doc.get("published", ""),
            "published_utc": ts.astimezone(timezone.utc).isoformat() if ts else None,
            "sentence": top["phrase"],
        })
    return out


def merge(events: list[dict]) -> list[dict]:
    """One event per (symbol, class); repeat coverage becomes corroboration, not duplicates.

    A Kothari Industrial rally story on 10 Sep 2026 mentioned, deep in a paragraph about school
    breakfast contracts, that it once won a small LoA "from Indian Railways' Integral Coach Factory"
    — one theme keyword, enough to fan the "railway orders" theme out onto TEXRAIL, TITAGARH, IRCON,
    RVNL and JWL as sympathy plays. TEXRAIL also had its own real, separately-named order win that
    morning, and the two landed on the same (symbol, event) key: the sympathy mention became
    "reported independently by 1 other source", with the Kothari URL cited as if it corroborated
    Texmaco Rail — a story that never names Texmaco Rail is not a second witness to its order. A
    "named" report and a "sympathy" fan-out are different kinds of claim about different underlying
    stories; only same-route reports corroborate each other.
    """
    by_key: dict[tuple, dict] = {}
    for e in sorted(events, key=lambda x: (-abs(x["event_prior"]), -(x["directness"]))):
        key = (e["symbol"], e["event"])
        keep = by_key.get(key)
        if keep is None:
            by_key[key] = {**e, "corroborating_sources": [], "urls": [e["url"]] if e["url"] else [],
                           "n_reports": 1}
            continue
        if e["route"] != keep["route"]:
            continue          # a sympathy/theme echo is not a witness to the named story
        keep["n_reports"] += 1
        if e["source_id"] != keep["source_id"] and e["source_id"] not in keep["corroborating_sources"]:
            keep["corroborating_sources"].append(e["source_id"])
        if e["url"] and e["url"] not in keep["urls"]:
            keep["urls"].append(e["url"])
        # a later report often carries the number the first one lacked
        if keep["size_inr_cr"] is None and e["size_inr_cr"] is not None:
            keep.update(size_inr_cr=e["size_inr_cr"], size_estimated=e["size_estimated"],
                        size_basis=e["size_basis"])
        elif e["size_inr_cr"] is not None and not e["size_estimated"] and keep["size_estimated"]:
            keep.update(size_inr_cr=e["size_inr_cr"], size_estimated=False, size_basis=e["size_basis"])
    return sorted(by_key.values(), key=lambda e: (-abs(e["event_prior"]) * e["directness"], e["symbol"]))
