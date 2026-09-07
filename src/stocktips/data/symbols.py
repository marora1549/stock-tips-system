"""NSE symbol master + company-name → symbol resolution.

Tips arrive as company names in prose ("Tata Motors", "HDFC Bank", "L&T Finance").
We resolve them against the official NSE EQUITY_L list (archives.nseindia.com,
refreshed weekly and cached in state/universe_cache.json) with fuzzy matching,
falling back to Moneycontrol's autosuggest which knows colloquial names and
returns the NSE symbol + Moneycontrol sc_id (needed for live quotes).
"""
from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import datetime, timedelta

from rapidfuzz import fuzz, process

from ..util import ROOT, STATE_DIR, http, read_json, write_json

log = logging.getLogger(__name__)

UNIVERSE_PATH = STATE_DIR / "universe_cache.json"
EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
MC_SUGGEST = "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"

# Manual overrides for names the fuzzy matcher gets wrong or that changed on
# corporate actions. Extend freely; this file is meant to grow.
ALIASES = {
    "tata motors": "TMCV",              # post-demerger (Nov 2025): CV business kept the name
    "tata motors passenger vehicles": "TMPV",
    "l&t": "LT", "larsen": "LT", "larsen & toubro": "LT", "larsen and toubro": "LT",
    "l&t finance": "LTF", "lt finance": "LTF",
    "m&m": "M&M", "mahindra": "M&M", "mahindra & mahindra": "M&M",
    "hdfc bank": "HDFCBANK", "icici bank": "ICICIBANK", "sbi": "SBIN", "state bank": "SBIN", "state bank of india": "SBIN",
    "reliance": "RELIANCE", "ril": "RELIANCE", "reliance industries": "RELIANCE",
    "infy": "INFY", "infosys": "INFY", "tcs": "TCS", "hcl tech": "HCLTECH", "hcl technologies": "HCLTECH",
    "bajaj finance": "BAJFINANCE", "bajaj finserv": "BAJAJFINSV",
    "airtel": "BHARTIARTL", "bharti airtel": "BHARTIARTL",
    "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "titan": "TITAN", "titan company": "TITAN",
    "kotak bank": "KOTAKBANK", "kotak mahindra bank": "KOTAKBANK",
    "axis bank": "AXISBANK", "indusind bank": "INDUSINDBK",
    "sun pharma": "SUNPHARMA", "dr reddy's": "DRREDDY", "dr reddys": "DRREDDY", "divis labs": "DIVISLAB", "divi's": "DIVISLAB",
    "ultratech": "ULTRACEMCO", "ultratech cement": "ULTRACEMCO",
    "adani ports": "ADANIPORTS", "adani enterprises": "ADANIENT", "adani green": "ADANIGREEN", "adani power": "ADANIPOWER",
    "ongc": "ONGC", "ntpc": "NTPC", "power grid": "POWERGRID", "coal india": "COALINDIA", "bhel": "BHEL", "bel": "BEL",
    "bharat electronics": "BEL", "hal": "HAL", "hindustan aeronautics": "HAL", "bdl": "BDL", "bharat dynamics": "BDL",
    "zomato": "ETERNAL", "eternal": "ETERNAL", "swiggy": "SWIGGY", "paytm": "PAYTM", "nykaa": "NYKAA", "policybazaar": "POLICYBZR",
    "jio financial": "JIOFIN", "jio fin": "JIOFIN",
    "indigo": "INDIGO", "interglobe aviation": "INDIGO",
    "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR", "itc": "ITC", "nestle": "NESTLEIND", "britannia": "BRITANNIA",
    "asian paints": "ASIANPAINT", "pidilite": "PIDILITIND", "havells": "HAVELLS", "voltas": "VOLTAS", "dixon": "DIXON",
    "trent": "TRENT", "dmart": "DMART", "avenue supermarts": "DMART", "v-mart": "VMART", "v mart retail": "VMART",
    "tata steel": "TATASTEEL", "jsw steel": "JSWSTEEL", "hindalco": "HINDALCO", "vedanta": "VEDL", "hindustan zinc": "HINDZINC", "nmdc": "NMDC",
    "tata power": "TATAPOWER", "tata consumer": "TATACONSUM", "tata elxsi": "TATAELXSI", "tata chemicals": "TATACHEM", "tata communications": "TATACOMM",
    "cg power": "CGPOWER", "siemens": "SIEMENS", "abb": "ABB", "cummins": "CUMMINSIND", "polycab": "POLYCAB", "kei": "KEI", "rr kabel": "RRKABEL", "r r kabel": "RRKABEL",
    "lic": "LICI", "sbi life": "SBILIFE", "hdfc life": "HDFCLIFE", "icici pru": "ICICIPRULI", "icici lombard": "ICICIGI",
    "max healthcare": "MAXHEALTH", "apollo hospitals": "APOLLOHOSP", "fortis": "FORTIS",
    "prestige": "PRESTIGE", "prestige estates": "PRESTIGE", "brigade": "BRIGADE", "brigade enterprises": "BRIGADE", "dlf": "DLF", "godrej properties": "GODREJPROP", "lodha": "LODHA", "macrotech": "LODHA", "oberoi realty": "OBEROIRLTY",
    "amber": "AMBER", "amber enterprises": "AMBER", "page industries": "PAGEIND", "gopal snacks": "GOPAL", "castrol": "CASTROLIND", "devyani": "DEVYANI",
    "hyundai": "HYUNDAI", "hyundai motor india": "HYUNDAI", "eicher": "EICHERMOT", "eicher motors": "EICHERMOT", "bajaj auto": "BAJAJ-AUTO", "hero moto": "HEROMOTOCO", "tvs motor": "TVSMOTOR",
    "upl": "UPL", "pi industries": "PIIND", "coromandel": "COROMANDEL",
    "physicswallah": "PHYSICSWAL", "physics wallah": "PHYSICSWAL",
    "manappuram": "MANAPPURAM", "bandhan bank": "BANDHANBNK", "bank of baroda": "BANKBARODA", "bob": "BANKBARODA", "pnb": "PNB", "canara bank": "CANBK",
    "vodafone idea": "IDEA", "vi": "IDEA", "idea": "IDEA",
    "tejas networks": "TEJASNET", "tejas network": "TEJASNET",
    "gujarat state petronet": "GSPL", "gspl": "GSPL", "psp projects": "PSPPROJECT",
    "esds software": "ESDS", "esds": "ESDS",
}

INDEX_WORDS = {"nifty", "sensex", "bank nifty", "banknifty", "midcap", "smallcap", "index", "fii", "dii", "rbi", "sebi", "fed", "market"}


class SymbolMaster:
    def __init__(self):
        self.rows: list[dict] = []
        self.by_symbol: dict[str, dict] = {}
        self.names: list[str] = []
        self._load()

    def _load(self):
        cache = read_json(UNIVERSE_PATH, None)
        fresh = cache and datetime.fromisoformat(cache["fetched"]) > datetime.now() - timedelta(days=7)
        if not fresh:
            text = None
            for attempt in range(3):   # archives.nseindia.com intermittently 403s, then serves fine
                r = http().get(EQUITY_L_URL, use_cache=False, retries=1)
                if r is not None and r.status_code == 200 and len(r.content) > 50_000:
                    text = r.text
                    break
                time.sleep(2)
            if text is None:
                seed = ROOT / "data" / "EQUITY_L.csv"
                if seed.exists() and cache is None:
                    text = seed.read_text(encoding="utf-8")
                    log.warning("Using bundled EQUITY_L.csv seed (live fetch failed)")
            if text is not None:
                rdr = csv.DictReader(io.StringIO(text))
                rows = []
                for row in rdr:
                    row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                    if row.get("SERIES") not in ("EQ", "BE", "BZ"):
                        continue
                    if re.search(r"\b(ETF|Bees|Liquid|Gold|Silver|Nifty|Sensex|Index Fund|Mutual Fund|FOF)\b", row["NAME OF COMPANY"], re.I):
                        continue  # exchange-traded funds are not tips
                    rows.append({"symbol": row["SYMBOL"], "name": row["NAME OF COMPANY"], "isin": row.get("ISIN NUMBER"), "series": row["SERIES"]})
                cache = {"fetched": datetime.now().isoformat(), "rows": rows}
                write_json(UNIVERSE_PATH, cache)
                log.info("NSE symbol master refreshed: %d symbols", len(rows))
            elif cache is not None:
                log.warning("EQUITY_L refresh failed — using cached master from %s", cache["fetched"][:10])
            else:
                log.error("Could not fetch EQUITY_L.csv and no cache — symbol resolution degraded")
                cache = {"fetched": "1970-01-01T00:00:00", "rows": []}
        self.rows = cache["rows"]
        self.by_symbol = {r["symbol"]: r for r in self.rows}
        self.names = [self._norm(r["name"]) for r in self.rows]

    @staticmethod
    def _norm(name: str) -> str:
        n = name.lower()
        n = re.sub(r"\b(limited|ltd\.?|india|inds\.?|industries|company|co\.?|corporation|corp\.?|the|&amp;)\b", " ", n)
        n = re.sub(r"[^a-z0-9& ]+", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    def resolve(self, name_or_symbol: str) -> tuple[str | None, float, str]:
        """→ (symbol, confidence 0-1, method)."""
        if not name_or_symbol:
            return None, 0.0, "empty"
        q = name_or_symbol.strip()
        if q.lower() in INDEX_WORDS:
            return None, 0.0, "index"
        if q.upper() in self.by_symbol and (q.isupper() or len(q) <= 5):
            return q.upper(), 1.0, "symbol"
        ql = re.sub(r"\s+", " ", q.lower().replace("’", "'")).strip()
        ql_clean = re.sub(r"\b(ltd|limited|shares?|stock)\b\.?", "", ql).strip()
        for cand in (ql, ql_clean):
            if cand in ALIASES and ALIASES[cand] in self.by_symbol:
                return ALIASES[cand], 0.98, "alias"
        if not self.names:
            return None, 0.0, "no-master"
        if len(ql_clean) < 5 and ql_clean not in ALIASES:
            return None, 0.0, "too-short"
        nq = self._norm(q)
        # exact normalised name
        for i, n in enumerate(self.names):
            if n == nq:
                return self.rows[i]["symbol"], 0.95, "exact"
        best = process.extractOne(nq, self.names, scorer=fuzz.token_set_ratio)
        first_ok = best and nq.split()[0] == self.names[best[2]].split()[0] if best and nq and self.names[best[2]] else False
        if best and best[1] >= 90 and first_ok:
            return self.rows[best[2]]["symbol"], best[1] / 100 * 0.9, "fuzzy"
        # Moneycontrol autosuggest knows colloquial names — but validate: its top hit for
        # junk like "The Indian" is a real company, so demand real similarity to the query.
        sym = mc_suggest(q)
        if sym and sym[0] in self.by_symbol:
            mc_name = self._norm(self.by_symbol[sym[0]]["name"])
            sim = max(fuzz.token_set_ratio(nq, mc_name), fuzz.partial_ratio(nq, mc_name))
            if sim >= 75 and len(nq) >= 4:
                return sym[0], 0.85, "moneycontrol"
        if best and best[1] >= 88 and len(nq) >= 6 and first_ok:
            return self.rows[best[2]]["symbol"], best[1] / 100 * 0.7, "fuzzy-weak"
        return None, 0.0, "unresolved"

    def name_of(self, symbol: str) -> str:
        return self.by_symbol.get(symbol, {}).get("name", symbol)


_MC_CACHE: dict[str, tuple[str, str] | None] = {}


def mc_suggest(query: str) -> tuple[str, str] | None:
    """→ (NSE symbol, moneycontrol sc_id) or None."""
    key = query.lower()
    if key in _MC_CACHE:
        return _MC_CACHE[key]
    r = http().get(MC_SUGGEST, params={"classic": "true", "query": query, "type": 1, "format": "json"})
    out = None
    if r is not None and r.status_code == 200:
        try:
            for item in r.json():
                disp = item.get("pdt_dis_nm", "")
                m = re.search(r"<span>[^,]*,\s*([A-Z0-9&\-]+)\s*,", disp)
                if m:
                    out = (m.group(1), item["sc_id"])
                    break
        except Exception:
            pass
    _MC_CACHE[key] = out
    return out


_master: SymbolMaster | None = None


def master() -> SymbolMaster:
    global _master
    if _master is None:
        _master = SymbolMaster()
    return _master
