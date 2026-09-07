"""Shared helpers: paths, settings, IST time, HTTP session with retry/cache, JSON state IO."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

log = logging.getLogger("stocktips")

IST = timezone(timedelta(hours=5, minutes=30))

# Repo root = two levels above this file's package dir (src/stocktips/util.py)
ROOT = Path(os.environ.get("STOCKTIPS_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
REPORTS_DIR = ROOT / "reports"
CACHE_DIR = ROOT / ".cache"


def now_ist() -> datetime:
    return datetime.now(IST)


def today_str() -> str:
    return now_ist().strftime("%Y-%m-%d")


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_settings: dict | None = None


def settings() -> dict:
    global _settings
    if _settings is None:
        _settings = load_yaml(CONFIG_DIR / "settings.yaml")
    return _settings


def sources_config() -> list[dict]:
    return load_yaml(CONFIG_DIR / "sources.yaml").get("sources", [])


# ----------------------------------------------------------------- JSON state
def read_json(path: Path, default: Any):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            log.error("Corrupt JSON at %s — using default", path)
            return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60]


def short_hash(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


# ----------------------------------------------------------------- HTTP
class Http:
    """requests.Session with browser UA, retries with backoff, and an on-disk cache.

    The cache is keyed on URL+method+body and honours a TTL so that repeated
    runs inside a session don't hammer Yahoo (which 429s aggressively).
    """

    def __init__(self, ttl_minutes: float | None = None):
        cfg = settings().get("data", {})
        self.ttl = timedelta(minutes=ttl_minutes if ttl_minutes is not None else cfg.get("cache_ttl_minutes", 30))
        self.s = requests.Session()
        self.s.headers.update(
            {
                "User-Agent": cfg.get("user_agent", "Mozilla/5.0"),
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            }
        )
        CACHE_DIR.mkdir(exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / (short_hash(key, 24) + ".bin")

    def get(self, url: str, *, params: dict | None = None, timeout: int = 20, retries: int = 3,
            use_cache: bool = True, headers: dict | None = None, ttl: timedelta | None = None) -> requests.Response | None:
        key = f"GET {url} {json.dumps(params, sort_keys=True) if params else ''}"
        cp = self._cache_path(key)
        ttl = ttl or self.ttl
        if use_cache and cp.exists() and datetime.now() - datetime.fromtimestamp(cp.stat().st_mtime) < ttl:
            r = requests.Response()
            r.status_code = 200
            r._content = cp.read_bytes()
            r.url = url
            r.headers["X-From-Cache"] = "1"
            return r
        delay = 2.0
        for attempt in range(retries):
            try:
                r = self.s.get(url, params=params, timeout=timeout, headers=headers)
                if r.status_code == 200:
                    if use_cache:
                        cp.write_bytes(r.content)
                    return r
                if r.status_code in (429, 500, 502, 503, 504):
                    log.warning("HTTP %s from %s (attempt %d) — backing off %.0fs", r.status_code, url[:80], attempt + 1, delay)
                    time.sleep(delay)
                    delay *= 2.5
                    continue
                log.info("HTTP %s from %s", r.status_code, url[:100])
                return r
            except requests.RequestException as e:
                log.warning("request error %s (attempt %d): %s", url[:80], attempt + 1, e)
                time.sleep(delay)
                delay *= 2
        return None

    def post(self, url: str, data: dict, *, timeout: int = 25, headers: dict | None = None) -> requests.Response | None:
        try:
            return self.s.post(url, data=data, timeout=timeout, headers=headers)
        except requests.RequestException as e:
            log.warning("POST error %s: %s", url[:80], e)
            return None


_http: Http | None = None


def http() -> Http:
    global _http
    if _http is None:
        _http = Http()
    return _http


def strip_html(s: str) -> str:
    import html as _html
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def fmt_inr(x: float) -> str:
    return f"₹{x:,.2f}"


def pct(a: float, b: float) -> float:
    """percent change from b to a"""
    return (a / b - 1.0) * 100.0 if b else 0.0
