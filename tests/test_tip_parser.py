"""The dashboard's paste-a-tip parser, exercised against messages of the kind people actually send.

The parser only fills a form the analyst then checks, so a miss is survivable and a wrong number is
not. These cases pin the shapes that must work and the traps that must not fire.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def parse_many(messages):
    """Pull parseTip out of the page and run the real function under node."""
    src = HTML.read_text(encoding="utf-8")
    body = "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S))
    m = re.search(r"^function parseTip\(text\)\{.*?^\}", body, re.S | re.M)
    assert m, "parseTip is no longer a top-level function in docs/index.html"
    script = m.group(0) + "\nconsole.log(JSON.stringify(" + json.dumps(messages) + ".map(parseTip)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_reads_a_plain_whatsapp_tip():
    got = parse_many(["Buy TATASTEEL above 180, target 195 / 210, SL 168, 1 month view"])[0]
    assert got["symbol"] == "TATASTEEL"
    assert got["target"] == "195, 210"
    assert got["stop"] == 168
    assert got["entry"] == 180
    assert got["timeframe"] == "monthly"


def test_reads_the_shapes_tipsters_actually_use():
    msgs = [
        "RELIANCE cmp 1420 tgt 1520 sl 1380",
        "ACCUMULATE INFY at 1560, TP 1700, stoploss 1495",
        "buy HAL 4850 target 5100 stop loss 4700 intraday",
        "LT — target price 4200 (SL: 3820)",
    ]
    got = parse_many(msgs)
    assert got[0]["symbol"] == "RELIANCE" and got[0]["entry"] == 1420 and got[0]["target"] == "1520" and got[0]["stop"] == 1380
    assert got[1]["symbol"] == "INFY" and got[1]["entry"] == 1560 and got[1]["target"] == "1700" and got[1]["stop"] == 1495
    assert got[2]["symbol"] == "HAL" and got[2]["stop"] == 4700 and got[2]["timeframe"] == "intraday"
    assert got[3]["symbol"] == "LT" and got[3]["target"] == "4200" and got[3]["stop"] == 3820


def test_takes_up_to_three_targets_and_keeps_their_order():
    got = parse_many(["CGPOWER targets 977 / 1013 / 1080 and beyond, sl 856"])[0]
    assert got["target"] == "977, 1013, 1080" and got["stop"] == 856


def test_does_not_mistake_order_words_for_the_symbol():
    for msg, sym in [("BUY SBIN tgt 900", "SBIN"), ("SL 340 for IDEA", "IDEA"),
                     ("CMP 250 NSE ITC target 280", "ITC"), ("GTT TATAMOTORS 720", "TATAMOTORS")]:
        assert parse_many([msg])[0].get("symbol") == sym, msg


def test_horizon_words_map_to_the_mandate_timeframes():
    got = parse_many([
        "ONGC swing trade target 280",
        "HDFCBANK long term investment target 2400",
        "NIFTY intraday 24500",
        "WIPRO target 300",
    ])
    assert got[0]["timeframe"] == "monthly"
    assert got[1]["timeframe"] == "long"
    assert got[2]["timeframe"] == "intraday"
    assert "timeframe" not in got[3]          # unstated stays unstated, the form's default applies


def test_survives_junk_without_inventing_numbers():
    for msg in ["", "good morning ji", "🚀🚀🚀", "market looks weak today, stay in cash"]:
        got = parse_many([msg])[0]
        assert "target" not in got and "stop" not in got, msg


def test_rupee_symbols_and_thousands_separators_do_not_break_it():
    got = parse_many(["Buy BAJAJ-AUTO around ₹11,750 target ₹12,470 SL ₹11,300"])[0]
    assert got["symbol"] == "BAJAJ-AUTO" and got["entry"] == 11750
    assert got["target"] == "12470" and got["stop"] == 11300
