"""Turn cluttered article / message text into candidate structured tips.

Two passes:

1. **Anchored patterns** — the recurring shapes Indian tip columns use. Each
   anchor pins a company name to a BUY/SELL verb, then a ~350-char window after
   the anchor is mined for target(s), stop-loss, entry range and duration.

       "Tata Steel : Buy at ₹ 188, target price of ₹ 198, stop loss of ₹ 182."          (Mint / Bagadia)
       "Buy: Acme Solar Holdings Ltd (current price: ₹ 418) ... Target price: ₹ 500 in two to three months Stop loss: ₹ 392"  (MarketSmith)
       "Buy Brigade Enterprises; target of Rs 900: Motilal Oswal"                        (Moneycontrol headline)
       "Motilal Oswal maintains buy on V-Mart Retail with a target price of Rs 950"      (ET Buy/Sell/Hold column)
       "HDFC Bank | Buy | LTP: 1,720 | Target: 1,850 | SL: 1,660 | Duration: 2 weeks"     (table-ish)

2. **Generic sentence pass** — any sentence with a buy/sell verb and a resolvable
   company name, flagged `needs_review`, so the Claude layer in the scheduled
   run can confirm or discard it. Boilerplate (WhatsApp-channel promos,
   disclaimers, "Top Trending Stocks" footers) is dropped before either pass.

Every tip records `extracted_by` so we can measure regex vs LLM extraction quality.
"""
from __future__ import annotations

import re

from ..data.symbols import master
from ..util import short_hash

BROKERAGES = {
    "motilal oswal": "motilal", "motilal": "motilal", "icici direct": "icicidirect", "icici securities": "icicisec", "hdfc securities": "hdfcsec",
    "axis securities": "axissec", "axis direct": "axissec", "kotak securities": "kotaksec", "kotak institutional": "kotakinst", "sharekhan": "sharekhan",
    "angel one": "angelone", "nuvama": "nuvama", "emkay": "emkay", "anand rathi": "anandrathi", "choice broking": "choice", "choice equities": "choice",
    "choice institutional": "choice", "jm financial": "jmfin", "prabhudas lilladher": "pl", "yes securities": "yessec", "geojit": "geojit", "religare": "religare",
    "sbi securities": "sbisec", "citi": "citi", "morgan stanley": "morganstanley", "goldman sachs": "goldman", "jefferies": "jefferies", "nomura": "nomura",
    "clsa": "clsa", "macquarie": "macquarie", "ubs": "ubs", "hsbc": "hsbc", "jp morgan": "jpmorgan", "jpmorgan": "jpmorgan", "bofa": "bofa", "bernstein": "bernstein",
    "elara": "elara", "antique": "antique", "systematix": "systematix", "ambit": "ambit", "iifl": "iifl", "5paisa": "5paisa", "mirae": "mirae",
    "centrum": "centrum", "dolat": "dolat", "equirus": "equirus", "investec": "investec", "incred": "incred", "phillipcapital": "phillipcap",
    "marketsmith": "marketsmith", "sumeet bagadia": "bagadia", "vaishali parekh": "parekh", "jigar patel": "jigarpatel", "ganesh dongre": "dongre",
    "mehul kothari": "kothari", "raja venkatraman": "venkatraman", "rajesh bhosale": "bhosale", "shiju koothupalakkal": "koothupalakkal", "riyank arora": "arora",
    "mandar bhojane": "bhojane", "pravesh gour": "gour", "vinay rajani": "rajani", "nilesh jain": "nileshjain", "ruchit jain": "ruchitjain", "rupak de": "rupakde",
    "osho krishan": "osho", "kunal bothra": "bothra", "sudeep shah": "sudeepshah", "hardik matalia": "matalia", "dhupesh dhameja": "dhameja", "anuj gupta": "anujgupta",
}
BROKERAGE_NAMES_LOWER = set(BROKERAGES)

NUM = r"(?:rs\.?|₹|inr)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"


def _num(group: str) -> str:
    return r"(?:rs\.?|₹|inr)?\s*(?P<" + group + r">[0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
NAME = r"(?P<name>(?-i:[A-Z][A-Za-z0-9&'’\.\-]*(?:\s+(?:[A-Z][A-Za-z0-9&'’\.\-]*|&|and|of|\([A-Z]+\))){0,4}))"
ANCHORS = [
    # "Tata Steel : Buy at ₹ 188, target price of ₹ 198, stop loss of ₹ 182"
    re.compile(NAME + r"\s*(?:\((?:NSE:)?\s*[A-Z&\-]+\))?\s*[:\-–|]\s*(?P<verb>Buy|Sell|Short)\s*(?:at|around|above|below|near|in the range of|between)?\s*[:\-–]?\s*" + _num("entry"), re.I),
    # "Buy: Acme Solar Holdings Ltd (current price: ₹ 418)"  /  "Buy Balaji Amines Limited (current price: ₹ 2,538)"
    re.compile(r"\b(?P<verb>Buy|Sell)\s*:?\s+" + NAME + r"\s*(?:Ltd|Limited)?\.?\s*\((?:current price|CMP|LTP)\s*:?\s*" + _num("entry") + r"\)", re.I),
    # "Buy Brigade Enterprises; target of Rs 900: Motilal Oswal"
    re.compile(r"\b(?P<verb>Buy|Sell|Accumulate|Neutral|Hold)\s+" + NAME + r"\s*(?:Ltd|Limited)?\.?\s*[;,:]?\s*(?:for the|with a|with|for a)?\s*target(?:\s*price)?\s*(?:of|at|:)?\s*" + _num("target"), re.I),
    # "Motilal Oswal maintains buy on V-Mart Retail with a target price of Rs 950" / "initiated coverage on X with a Buy rating and a ₹275 target"
    re.compile(r"(?:maintain\w*|reiterat\w*|recommend\w*|initiat\w+ coverage on|upgrad\w+|retain\w*|has a|assign\w*|gives?|keeps?)\s+(?:a\s+|an\s+|its\s+)?(?:'|‘|\")?(?P<verb>buy|sell|accumulate|add|overweight|outperform|reduce|underweight)(?:'|’|\")?(?:\s*(?:rating|call|recommendation))?\s+(?:on|for)\s+" + NAME, re.I),
    re.compile(r"(?:initiat\w+ coverage on|upgrad\w+|maintain\w*|reiterat\w*)\s+" + NAME + r"\s*(?:Ltd|Limited)?\.?\s+(?:with|to|at)\s+(?:a\s+|an\s+)?(?:'|‘|\")?(?P<verb>buy|sell|accumulate|add|overweight|outperform|reduce|underweight)", re.I),
    # table-ish "HDFC Bank | Buy | LTP: 1,720 | Target: 1,850 | SL: 1,660"
    re.compile(NAME + r"\s*\|\s*(?P<verb>Buy|Sell)\s*\|", re.I),
]
TARGET_RE = re.compile(r"(?:target(?:\s*price)?s?|tp|tgt|upside target|for a target)\s*(?:of|at|:|-|–|to|is|price|price of|price :)?\s*" + NUM + r"(?:\s*(?:/|,|and|-|–|then)\s*" + NUM + r")?(?:\s*(?:/|,|and|-|–|then)\s*" + NUM + r")?", re.I)
SL_RE = re.compile(r"(?:stop[\s-]*loss|sl|stoploss)\s*(?:of|at|:|-|–|below|is|placed at|should be|kept at|to be placed at)?\s*(?:₹|rs\.?)?\s*" + NUM, re.I)
ENTRY_RE = re.compile(r"(?:buy(?:ing)?\s*(?:range|zone|at|around|above|near|in the range of|between)|ltp|cmp|entry|current price|trading at)\s*(?:of|:|-|–)?\s*" + NUM + r"(?:\s*(?:-|–|to)\s*" + NUM + r")?", re.I)
UPSIDE_RE = re.compile(r"(?:up\s*to\s*|upside\s*(?:of|potential of)?\s*|return\s*of\s*|could\s*(?:give|deliver|gain|rise)\s*|implying (?:a |an )?)([0-9]{1,3})\s*(?:-|–|to)?\s*([0-9]{1,3})?\s*%", re.I)
DURATION_RE = re.compile(r"(?:duration|time\s*frame|timeframe|horizon|period|in|within|over|for)\s*:?\s*((?:\d+|one|two|three|four|six|twelve|a few|couple of|next)\s*(?:-|–|to)?\s*(?:\d+|three|four|six)?\s*(?:trading\s*)?(?:day|week|month|session|year)s?)", re.I)
GENERIC_ACTION_RE = re.compile(r"\b(buy|accumulate|overweight|outperform|sell|reduce|underweight|underperform|hold|neutral|book profits?|short)\b", re.I)

NAME_RE = re.compile(r"\b((?:[A-Z][A-Za-z&'’\.\-]+|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z&'’\.\-]+|&|and|of|[A-Z]{2,})){0,3})\b")
BOILERPLATE = re.compile(r"Add as a Reliable|WhatsApp channel|Top Trending Stocks|does not hold any financial interest|Disclaimer|More Topics|Also Read|View full Image|"
                         r"Subscribe|Download the app|Follow us|Catch all the|Live Mint|ETMarkets\.com|Read more at|Log in|Sign up|All rights reserved|"
                         r"views expressed|are their own|outdated browser|upgrade your browser|Start -->|Quotes Mutual Funds|Instant Loans|should consult|do their own research|Copyright|newsletter|Share Price\s*,|Stock Market Today:|Stock market news", re.I)
STOP_WORDS = {"Buy", "Sell", "Hold", "Target", "Stop", "Loss", "Rs", "INR", "NSE", "BSE", "Nifty", "Sensex", "Bank Nifty", "Stock", "Stocks", "Market", "Markets",
              "The", "This", "That", "These", "Here", "Why", "How", "What", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
              "September", "October", "November", "December", "January", "February", "March", "April", "May", "June", "July", "August", "India", "Indian",
              "Economic Times", "Moneycontrol", "Mint", "Business Standard", "Financial Express", "Reuters", "Bloomberg", "PTI", "ET", "Q1", "Q2", "Q3", "Q4",
              "FY", "YoY", "QoQ", "CEO", "MD", "Ltd", "Limited", "Sebi", "SEBI", "RBI", "Fed", "US", "China", "FII", "DII", "Dalal Street", "D-Street", "Street",
              "Trade", "Trading", "Guide", "Spotlight", "Analyst", "Analysts", "Brokerage", "Brokerages", "Research", "Report", "Shares", "Share", "Price", "Live",
              "Budget", "GST", "IPO", "SIP", "MF", "Mutual Fund", "Gold", "Silver", "Crude", "Rupee", "Dollar", "Wall Street", "Asia", "Europe", "Nikkei", "Dow",
              "Tech", "Tech view", "News", "Jane Street", "Gift Nifty", "Bank", "Banks", "Pharma", "Auto", "Metal", "Metals", "Realty", "Energy", "Power", "Oil",
              "Stocks To Buy", "Stocks to buy", "Buy Sell", "Buy Or Sell", "Stock Market", "Weekly", "Daily", "Today", "Also", "Read", "Image", "Add", "Nifty Bank"}


def _f(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def brokerages_in(text: str) -> list[str]:
    t = text.lower()
    return sorted({slug for name, slug in BROKERAGES.items() if name in t})


def nearest_brokerage(body: str, start: int, end: int) -> list[str]:
    """Brokerage(s) attributable to the anchor at body[start:end]: same sentence first, else nearest within 150 chars."""
    sb = max(body.rfind(". ", 0, start), body.rfind("; ", 0, start), body.rfind("| ", 0, start), -2) + 2
    se_candidates = [i for i in (body.find(". ", end), body.find("; ", end), body.find(" | ", end)) if i != -1]
    se = min(se_candidates) if se_candidates else len(body)
    same = brokerages_in(body[sb:se])
    if len(same) == 1:
        return same
    low = body.lower()
    best, best_d = None, 10 ** 9
    for name, slug in BROKERAGES.items():
        i = low.find(name, max(0, start - 150), end + 150)
        while i != -1:
            d = min(abs(i - start), abs(i - end))
            if d < best_d:
                best, best_d = slug, d
            i = low.find(name, i + 1, end + 150)
    return [best] if best and best_d <= 150 else same


def _is_brokerage_name(name: str) -> bool:
    n = name.lower()
    return any(b in n or n in b for b in BROKERAGE_NAMES_LOWER if len(b) > 3)


LEAD_JUNK = re.compile(r"^(?:Buy|Sell|Hold|Neutral|Accumulate|Reduce|Stocks?|Top|The|These|Also|Read|News|Markets?|Weekly|Daily|Today|Why|How|Tech|View|Image|Nifty|Sensex|Bank Nifty|Gift Nifty)\s+", re.I)


def company_names_in(text: str) -> list[str]:
    out, seen = [], set()
    for m in NAME_RE.finditer(text):
        s = m.group(1).strip(" .,'’")
        while LEAD_JUNK.match(s):
            s = LEAD_JUNK.sub("", s, count=1)
        if s in STOP_WORDS or len(s) < 3 or _is_brokerage_name(s):
            continue
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def _resolve(name: str):
    name = re.sub(r"\s*\((?:NSE:)?\s*[A-Z&\-]+\)\s*$", "", name).strip()
    name = re.sub(r"\b(Ltd|Limited)\.?$", "", name).strip(" .,:;-–")
    while LEAD_JUNK.match(name):
        name = LEAD_JUNK.sub("", name, count=1)
    if not name or not name[:1].isupper() or _is_brokerage_name(name) or name in STOP_WORDS or name.lower() in ("the stock", "stock", "shares", "the company"):
        return None, 0.0, "skip"
    return master().resolve(name)


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    # drop boilerplate sentences
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z₹\"'])", text)
    return " ".join(p for p in parts if not BOILERPLATE.search(p))


def _window_fields(win: str) -> dict:
    tgt = TARGET_RE.search(win)
    slm = SL_RE.search(win)
    em = ENTRY_RE.search(win)
    um = UPSIDE_RE.search(win)
    dm = DURATION_RE.search(win)
    return {
        "targets": [x for x in (_f(tgt.group(1)), _f(tgt.group(2)), _f(tgt.group(3))) if x] if tgt else [],
        "stop": _f(slm.group(1)) if slm else None,
        "entry": _f(em.group(1)) if em else None,
        "entry_hi": _f(em.group(2)) if em and em.lastindex and em.lastindex >= 2 else None,
        "upside": _f(um.group(2) or um.group(1)) if um else None,
        "duration": dm.group(1) if dm else None,
    }


def _norm_verb(v: str) -> str:
    v = v.lower()
    if v in ("accumulate", "add", "overweight", "outperform", "buy"):
        return "buy"
    if v in ("reduce", "underweight", "underperform", "short", "sell", "book profit", "book profits"):
        return "sell"
    return "hold"


def _mk(source_id, url, title, published, default_tf, *, name, sym, conf, how, action, fields, sentence, by, xconf, review, brokers):
    key = f"{source_id}|{sym}|{action}|{fields.get('targets', [None])[0] if fields.get('targets') else ''}"
    return {
        "id": short_hash(key + url), "source_id": source_id,
        "brokerage": brokers[0] if len(brokers) == 1 else (brokers or None),
        "url": url, "title": title, "published": published,
        "company": name, "symbol": sym, "symbol_confidence": round(conf, 2), "symbol_method": how,
        "action": action,
        "src_entry": fields.get("entry"), "src_entry_hi": fields.get("entry_hi"), "src_targets": fields.get("targets", []), "src_stop": fields.get("stop"),
        "src_upside_pct": fields.get("upside"), "src_duration": fields.get("duration"),
        "default_timeframe": default_tf, "sentence": sentence[:400], "extracted_by": by,
        "extraction_confidence": xconf, "needs_review": review,
    }


def scan_tip(doc: dict, source_id: str, default_timeframe: str | None) -> dict:
    """A screener/scan match is already structured — one BUY candidate per symbol, no source targets."""
    sym = doc["symbol"]
    return _mk(source_id, doc.get("url", ""), doc.get("title", ""), doc.get("published", ""), default_timeframe or "weekly",
               name=master().name_of(sym), sym=sym, conf=1.0, how="scan", action="buy", fields={}, sentence=doc.get("text", ""),
               by="scan", xconf=1.0, review=False, brokers=[])


def extract(text: str, *, source_id: str, url: str = "", title: str = "", published: str = "", default_timeframe: str | None = None) -> list[dict]:
    """→ list of candidate tips (structured where possible, else flagged for review)."""
    body = clean((title + ". " + text) if title else text)
    tips: list[dict] = []
    seen: set[tuple] = set()
    covered: list[tuple[int, int]] = []

    # ---- pass 1: anchored patterns
    for rx in ANCHORS:
        for m in rx.finditer(body):
            name = m.group("name")
            sym, conf, how = _resolve(name)
            if not sym or conf < 0.7:
                continue
            action = _norm_verb(m.group("verb"))
            win = body[m.start(): m.end() + 350]
            fields = _window_fields(win)
            gd = m.groupdict()
            if gd.get("entry") and not fields["entry"]:
                fields["entry"] = _f(gd["entry"])
            if gd.get("target") and not fields["targets"]:
                fields["targets"] = [_f(gd["target"])]
            # sanity: targets must sit on the right side of entry for the action
            e = fields["entry"]
            if e and fields["targets"]:
                fields["targets"] = [t for t in fields["targets"] if (t > e * 1.002 if action == "buy" else t < e * 0.998) and abs(t / e - 1) < 1.5]
            if e and fields["stop"] and not (fields["stop"] < e if action == "buy" else fields["stop"] > e):
                fields["stop"] = None
            k = (sym, action)
            if k in seen:
                continue
            seen.add(k)
            covered.append((m.start(), m.end() + 350))
            brokers = nearest_brokerage(body, m.start(), m.end())
            xconf = 0.9 if (fields["targets"] or fields["stop"]) else 0.7
            tips.append(_mk(source_id, url, title, published, default_timeframe, name=name, sym=sym, conf=conf, how=how, action=action,
                            fields=fields, sentence=win[:300], by="anchor", xconf=xconf, review=not (fields["targets"] or fields["stop"] or fields["upside"]),
                            brokers=brokers))

    # ---- pass 2: generic sentences not already covered
    pos = 0
    for sent in re.split(r"(?<=[\.\!\?;])\s+(?=[A-Z₹\"'])|\s*\|\s*", body):
        start = body.find(sent, pos)
        pos = start + len(sent) if start >= 0 else pos
        if len(sent) < 20 or any(a <= start <= b for a, b in covered):
            continue
        act = GENERIC_ACTION_RE.search(sent)
        if not act:
            continue
        names = company_names_in(sent)
        if len(names) > 3:
            continue  # enumerations / ticker soup — leave to the LLM pass
        resolved = [(nm, *_resolve(nm)) for nm in names]
        resolved = [r for r in resolved if r[1] and r[2] >= 0.85]
        if not resolved:
            continue
        action = _norm_verb(act.group(1))
        fields = _window_fields(sent)
        brokers = brokerages_in(sent)
        multi = len(resolved) > 1
        for nm, sym, conf, how in resolved:
            k = (sym, action)
            if k in seen:
                continue
            seen.add(k)
            f = fields if not multi else {}
            tips.append(_mk(source_id, url, title, published, default_timeframe, name=nm, sym=sym, conf=conf, how=how, action=action,
                            fields=f, sentence=sent, by="regex", xconf=0.6 if (f.get("targets") or f.get("stop")) else 0.35,
                            review=True, brokers=brokers))
    return tips
