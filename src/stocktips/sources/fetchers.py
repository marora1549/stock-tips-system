"""Fetchers for every `kind` in config/sources.yaml.

Each fetcher returns a list of *documents*: {url, title, published, text}.
Articles are only kept if published within `max_age_hours` (default 36h) so the
morning run sees last evening's + this morning's calls, not January's.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from ..util import CACHE_DIR, http, read_json, strip_html, write_json

log = logging.getLogger(__name__)

GNEWS = "https://news.google.com/rss/search"


def _recent(published: str | None, max_age_hours: float) -> bool:
    if not published:
        return True
    try:
        dt = parsedate_to_datetime(published)
    except Exception:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except Exception:
            return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt <= timedelta(hours=max_age_hours)


def _rss_items(xml: str) -> list[dict]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def g(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        out.append({"title": g("title"), "link": g("link") or g("guid"), "published": g("pubDate"), "description": strip_html(g("description"))})
    return out


_GNEWS_URL_CACHE = CACHE_DIR / "gnews_urls.json"


def resolve_gnews_url(link: str) -> str | None:
    """Decode a news.google.com/rss/articles/<id> link into the publisher URL.

    Google no longer redirects these server-side; the id must be exchanged via the
    DotsSplashUi batchexecute endpoint using a signature+timestamp embedded in the
    article splash page (same technique as the `googlenewsdecoder` package).
    Results are cached on disk — the mapping never changes.
    """
    m = re.search(r"/articles/([^?/]+)", link)
    if not m:
        return link
    aid = m.group(1)
    cache = read_json(_GNEWS_URL_CACHE, {})
    if aid in cache:
        return cache[aid]
    s = http().s
    try:
        r = s.get(f"https://news.google.com/rss/articles/{aid}?oc=5", timeout=20)
        sg = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if not (sg and ts):
            log.warning("gnews decode: no signature (HTTP %s) for %s", r.status_code, aid[:20])
            return None
        req = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{aid}",{ts.group(1)},"{sg.group(1)}"]']
        payload = "f.req=" + quote(json.dumps([[req]]))
        r2 = s.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=payload,
                    headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"}, timeout=20)
        parsed = json.loads(r2.text.split("\n\n")[1])
        url = json.loads(parsed[0][2])[1]
        cache[aid] = url
        write_json(_GNEWS_URL_CACHE, cache)
        time.sleep(0.4)
        return url
    except Exception as e:
        log.warning("gnews decode failed for %s: %s", aid[:20], e)
        return None


def article_text(url: str) -> str:
    """Fetch an article and return its readable text (title + paragraphs)."""
    if "news.google.com" in url:
        url = resolve_gnews_url(url) or ""
        if not url or re.search(r"/topic/|/videos?/|/slideshow/", url):
            return ""
    r = http().get(url, timeout=25)
    if r is None or r.status_code != 200:
        return ""
    # Publishers often omit charset in headers; requests then assumes ISO-8859-1 and ₹ becomes "â¹"
    raw = r.content
    if re.search(rb'charset=["\']?utf-?8', raw[:4000], re.I) or b"\xe2\x82\xb9" in raw:
        h = raw.decode("utf-8", errors="replace")
    else:
        h = r.text
    # Prefer article body containers
    body = ""
    for pat in (r'<article[^>]*>(.*?)</article>', r'class="artText[^"]*"[^>]*>(.*?)</div>\s*<div', r'class="[^"]*article[_-]?(?:body|content|text)[^"]*"[^>]*>(.*?)</div>\s*</div>',
                r'<div[^>]+class="[^"]*(?:content_wrapper|story-content|storyContent|contentSec|page-content)[^"]*"[^>]*>(.*?)</div>\s*</div>'):
        m = re.search(pat, h, re.S | re.I)
        if m and len(strip_html(m.group(1))) > 400:
            body = m.group(1)
            break
    if not body:
        paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)
        body = "\n".join(p for p in paras if len(strip_html(p)) > 40)
    text = strip_html(body)
    # JSON-LD description/articleBody is often the cleanest
    m = re.search(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"', h)
    if m and len(m.group(1)) > len(text):
        try:
            text = strip_html(json.loads('"' + m.group(1) + '"'))
        except Exception:
            pass
    return text[:20000]


def fetch_gnews(src: dict, max_age_hours: float = 36) -> list[dict]:
    q = src["query"]
    if src.get("publisher"):
        q += f" site:{src['publisher']}"
    q += " when:2d"
    r = http().get(GNEWS, params={"q": q, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}, ttl=timedelta(minutes=20))
    if r is None or r.status_code != 200:
        return []
    docs = []
    for it in _rss_items(r.text):
        if not _recent(it["published"], max_age_hours):
            continue
        title = re.sub(r"\s+-\s+[^-]+$", "", it["title"])  # strip " - The Economic Times"
        docs.append({"url": it["link"], "title": title, "published": it["published"], "text": ""})
    log.info("%s: %d fresh articles", src["id"], len(docs))
    return docs[:25]


def fetch_page(src: dict, max_age_hours: float = 36) -> list[dict]:
    r = http().get(src["url"], ttl=timedelta(minutes=20))
    if r is None or r.status_code != 200:
        return []
    links = re.findall(r'href=["\'](' + src["link_pattern"] + r')["\']', r.text)
    base = re.match(r"https?://[^/]+", src["url"]).group(0)
    seen, docs = set(), []
    for l in links:
        l = l if isinstance(l, str) else l[0]
        u = l if l.startswith("http") else base + l
        if u in seen or re.search(r"/(topic|tag|author|videos?|slideshow|photos?)/", u):
            continue
        seen.add(u)
        docs.append({"url": u, "title": "", "published": "", "text": ""})
        if len(docs) >= 20:
            break
    log.info("%s: %d article links", src["id"], len(docs))
    return docs


def fetch_rss(src: dict, max_age_hours: float = 36) -> list[dict]:
    r = http().get(src["url"], ttl=timedelta(minutes=20))
    if r is None or r.status_code != 200:
        return []
    return [{"url": it["link"], "title": it["title"], "published": it["published"], "text": it["description"]}
            for it in _rss_items(r.text) if _recent(it["published"], max_age_hours)][:25]


def fetch_chartink(src: dict, **_) -> list[dict]:
    """Run a Chartink scan clause. Returns one pseudo-document per matched stock."""
    s = http()
    page = s.get("https://chartink.com/screener/15-minute-stock-breakouts", use_cache=False)
    if page is None or page.status_code != 200:
        return []
    m = re.search(r'name="csrf-token" content="([^"]+)"', page.text)
    if not m:
        return []
    r = s.post("https://chartink.com/screener/process", {"scan_clause": src["clause"]},
               headers={"x-csrf-token": m.group(1), "x-requested-with": "XMLHttpRequest", "referer": "https://chartink.com/screener/15-minute-stock-breakouts"})
    if r is None or r.status_code != 200:
        log.warning("chartink %s: HTTP %s", src["id"], r.status_code if r is not None else None)
        return []
    try:
        rows = r.json().get("data", [])
    except Exception:
        return []
    docs = []
    for row in rows[:40]:
        docs.append({"url": f"https://chartink.com/stocks/{row['nsecode'].lower()}.html", "title": f"Chartink scan {src['id']}: {row['name']}",
                     "published": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
                     "text": f"Buy {row['name']} (NSE: {row['nsecode']}) LTP {row['close']} — matched scan '{src['name']}', "
                             f"day change {row.get('per_chg')}%, volume {row.get('volume')}.",
                     "symbol": row["nsecode"], "scan": True})
    log.info("%s: %d matches", src["id"], len(docs))
    return docs


def fetch_telegram(src: dict, max_age_hours: float = 36) -> list[dict]:
    r = http().get(f"https://t.me/s/{src['channel']}", ttl=timedelta(minutes=15))
    if r is None or r.status_code != 200:
        return []
    docs = []
    for blk in re.findall(r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|$)', r.text, re.S):
        t = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', blk, re.S)
        d = re.search(r'<time[^>]+datetime="([^"]+)"', blk)
        link = re.search(r'data-post="([^"]+)"', blk)
        if not t:
            continue
        pub = d.group(1) if d else ""
        if not _recent(pub, max_age_hours):
            continue
        docs.append({"url": f"https://t.me/{link.group(1)}" if link else f"https://t.me/s/{src['channel']}", "title": f"Telegram @{src['channel']}",
                     "published": pub, "text": strip_html(t.group(1))})
    log.info("%s: %d recent messages", src["id"], len(docs))
    return docs


FETCHERS = {"gnews": fetch_gnews, "page": fetch_page, "rss": fetch_rss, "chartink": fetch_chartink, "telegram": fetch_telegram}


def fetch_source(src: dict, max_age_hours: float = 36, limit: int | None = None) -> list[dict]:
    """Documents from one source, bodies hydrated.

    `limit` caps how many are hydrated. Hydration is the expensive half — an article fetch, and for
    a Google News link two more requests to decode it first — so a caller with a deadline (the
    pre-open run has to be finished before 09:15) can say how much it is willing to pay here.
    """
    fn = FETCHERS.get(src.get("kind"))
    if fn is None:
        log.info("%s: kind '%s' not implemented yet — skipped", src["id"], src.get("kind"))
        return []
    try:
        docs = fn(src, max_age_hours=max_age_hours)
    except Exception as e:  # a broken source must never kill the run
        log.exception("%s failed: %s", src["id"], e)
        return []
    if limit is not None:
        docs = docs[:max(0, limit)]
    # hydrate article bodies (and swap Google News links for the publisher URL)
    for d in docs:
        if not d.get("text") and d.get("url"):
            if "news.google.com" in d["url"]:
                real = resolve_gnews_url(d["url"])
                if not real:
                    continue
                d["url"] = real
            if re.search(r"/(topic|tag|author|videos?|slideshow|photos?|live-blog|liveblog)/", d["url"]) or d["url"].rstrip("/").count("/") <= 3:
                continue  # aggregation/topic pages, video, live blogs — not a recommendation article
            d["text"] = article_text(d["url"])
    return [d for d in docs if d.get("text")]
