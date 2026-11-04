#!/usr/bin/env python3
"""Place the averaging-down GTT ladder on Zerodha Kite. Runs on YOUR machine, not in the cloud.

It has to run locally. The app's redirect URL is http://localhost:5001/api/login/callback, so the
request_token comes back to a port on the machine running the browser. A cloud container can never
receive it — and that is the right shape anyway: the api_secret and the access_token stay on your
disk, and the finger on an eight-lakh order placement stays yours.

    export KITE_API_KEY=...        # from developers.kite.trade
    export KITE_API_SECRET=...     # regenerate it if it has ever been pasted anywhere
    python3 tools/place_gtts.py              # DRY RUN — prints what it would place, places nothing
    python3 tools/place_gtts.py --live       # places them, after you type the confirmation

Dry run is the default and --live is the only way past it, because this is real money and a typo
here is thirty-four wrong orders rather than one.

What it does:
  1. opens the Kite login page, catches the redirect on localhost:5001
  2. exchanges request_token for an access_token (SHA-256 of api_key + request_token + api_secret)
  3. reads each symbol's last price, which the GTT API requires at placement
  4. places one single-leg BUY LIMIT CNC GTT per rung
  5. writes placed_gtts.json — every trigger_id, so you can audit or delete the batch later

Nothing is modified or cancelled. It only creates. To undo, use the trigger_ids it records.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime

API = "https://api.kite.trade"
PORT = 5001
CALLBACK_PATH = "/api/login/callback"

# symbol -> [(trigger, limit, qty), ...]   the ladder, exactly as agreed
LADDER: dict[str, list[tuple[float, float, int]]] = {
    "PCJEWELLER": [(12.56, 12.62, 796), (11.81, 11.87, 1693), (9.98, 10.03, 4008)],
    "BSOFT":      [(306.65, 308.18, 32), (295.05, 296.53, 67), (287.25, 288.69, 139)],
    "GROWW":      [(190.00, 190.95, 52), (184.68, 185.60, 108), (178.50, 179.39, 224)],
    "FORCEMOT":   [(17718.00, 17806.59, 1), (17017.33, 17102.42, 2), (16520.00, 16602.60, 4)],
    "RELIANCE":   [(1284.14, 1290.56, 7), (1251.50, 1257.76, 15), (1152.20, 1157.96, 34)],
    "CUPID":      [(302.30, 303.81, 33), (265.98, 267.31, 75), (246.00, 247.23, 162)],
    "MANAPPURAM": [(311.15, 312.71, 32), (303.35, 304.87, 65), (292.05, 293.51, 136)],
    "RBLBANK":    [(354.70, 356.47, 28), (347.85, 349.59, 57), (338.55, 340.24, 118)],
    "TMPV":       [(272.60, 273.96, 36), (259.10, 260.40, 77)],
    "OLAELEC":    [(34.43, 34.60, 290), (33.55, 33.72, 596), (32.11, 32.27, 1245)],
    "JIOFIN":     [(208.50, 209.54, 47), (202.51, 203.52, 98)],
    "YESBANK":    [(14.39, 14.46, 694), (13.18, 13.25, 1517), (11.97, 12.03, 3341)],
}
EXCHANGE, PRODUCT = "NSE", "CNC"
TICK = 0.05  # NSE rejects any price that is not a multiple of this


def tick_down(p: float) -> float:
    """Triggers round DOWN to a valid tick — never buy higher than the level we chose."""
    return round(int(p / TICK) * TICK, 2)


def tick_up(p: float) -> float:
    """Limits round UP to a valid tick — keeps the limit above its trigger so it can fill."""
    return round(-(-p // TICK) * TICK, 2)


def _req(method: str, path: str, token: str | None = None, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    r = urllib.request.Request(API + path, data=body, method=method)
    r.add_header("X-Kite-Version", "3")
    if token:
        r.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"Kite said {e.code} on {method} {path}:\n{detail}")


def login(api_key: str, api_secret: str) -> str:
    """Browser login, catch the redirect on localhost:5001, swap request_token for access_token."""
    got: dict[str, str] = {}
    ready = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                   # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if urllib.parse.urlparse(self.path).path == CALLBACK_PATH and "request_token" in q:
                got["t"] = q["request_token"][0]
                self.send_response(200); self.end_headers()
                self.wfile.write(b"<h2>Logged in. You can close this tab and return to the terminal.</h2>")
                ready.set()
            else:
                self.send_response(404); self.end_headers()

        def log_message(self, *a):                          # keep the terminal clean
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    print(f"Opening your browser to log in.\nIf it does not open, visit:\n  {url}\n")
    webbrowser.open(url)
    if not ready.wait(timeout=300):
        srv.shutdown(); raise SystemExit("No login callback within 5 minutes — aborted.")
    srv.shutdown()

    checksum = hashlib.sha256((api_key + got["t"] + api_secret).encode()).hexdigest()
    out = _req("POST", "/session/token", token=None,
               data={"api_key": api_key, "request_token": got["t"], "checksum": checksum})
    d = out["data"]
    print(f"Authenticated as {d.get('user_name')} ({d.get('user_id')})\n")
    return f"{api_key}:{d['access_token']}"


def last_prices(token: str, symbols: list[str]) -> dict[str, float]:
    """GTT placement requires the instrument's last price, so fetch them in one call."""
    q = "&".join("i=" + urllib.parse.quote(f"{EXCHANGE}:{s}") for s in symbols)
    out = _req("GET", f"/quote/ltp?{q}", token=token)
    return {k.split(":", 1)[1]: v["last_price"] for k, v in out["data"].items()}


def main() -> None:
    live = "--live" in sys.argv
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        raise SystemExit("Set KITE_API_KEY and KITE_API_SECRET in your environment first.")

    # Snap every price to a valid NSE tick before anything else looks at it, so the
    # dry run shows exactly the numbers that would be sent.
    for _sym, _legs in list(LADDER.items()):
        LADDER[_sym] = [(tick_down(t), tick_up(l), q) for t, l, q in _legs]

    total = sum(t * q for legs in LADDER.values() for t, _, q in legs)
    n = sum(len(v) for v in LADDER.values())
    print(f"{n} GTT orders across {len(LADDER)} stocks · "
          f"Rs {total:,.0f} if every rung fills\n"
          f"mode: {'LIVE — these will be real orders' if live else 'DRY RUN — nothing will be placed'}\n")

    if not live:
        for sym, legs in LADDER.items():
            for i, (trig, lim, qty) in enumerate(legs, 1):
                print(f"  {sym:<11} rung {i}  trigger {trig:>10,.2f}  limit {lim:>10,.2f}  "
                      f"qty {qty:>5}  = Rs {trig*qty:>9,.0f}")
        print("\nPrices shown are snapped to the NSE 0.05 tick (triggers down, limits up).")
        print("Dry run only. Re-run with --live to place these.")
        return

    token = login(api_key, api_secret)
    ltp = last_prices(token, list(LADDER))
    print("last traded prices:", {k: f"{v:,.2f}" for k, v in ltp.items()}, "\n")

    for sym, legs in LADDER.items():
        for trig, _lim, _q in legs:
            if trig >= ltp[sym]:
                print(f"  !  {sym} rung at {trig:,.2f} is AT OR ABOVE the last price "
                      f"{ltp[sym]:,.2f} — Kite will reject a buy trigger above market.")

    print(f"\nAbout to place {n} REAL GTT orders worth Rs {total:,.0f} on account RU5448.")
    if input('Type "PLACE" to continue, anything else aborts: ').strip() != "PLACE":
        raise SystemExit("Aborted. Nothing was placed.")

    placed, failed = [], []
    for sym, legs in LADDER.items():
        for i, (trig, lim, qty) in enumerate(legs, 1):
            condition = {"exchange": EXCHANGE, "tradingsymbol": sym,
                         "trigger_values": [trig], "last_price": ltp[sym]}
            orders = [{"exchange": EXCHANGE, "tradingsymbol": sym, "transaction_type": "BUY",
                       "quantity": qty, "order_type": "LIMIT", "product": PRODUCT, "price": lim}]
            try:
                out = _req("POST", "/gtt/triggers", token=token,
                           data={"type": "single", "condition": json.dumps(condition),
                                 "orders": json.dumps(orders)})
                tid = out["data"]["trigger_id"]
                placed.append({"symbol": sym, "rung": i, "trigger": trig, "limit": lim,
                               "qty": qty, "trigger_id": tid})
                print(f"  ok   {sym:<11} rung {i}  trigger {trig:>10,.2f}  qty {qty:>5}  id {tid}")
            except SystemExit as e:                      # one bad order must not kill the batch
                failed.append({"symbol": sym, "rung": i, "error": str(e)})
                print(f"  FAIL {sym:<11} rung {i}: {e}")

    out_path = f"placed_gtts_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(out_path, "w") as fh:
        json.dump({"placed": placed, "failed": failed}, fh, indent=2)
    print(f"\n{len(placed)} placed, {len(failed)} failed. Trigger ids written to {out_path}")
    print("Delete any of them with:  DELETE /gtt/triggers/<trigger_id>")


if __name__ == "__main__":
    main()
