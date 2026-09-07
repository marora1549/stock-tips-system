"""Lessons journal — state/lessons.md.

Two kinds of entries:
* machine lessons  — computed by the EOD run (e.g. "pattern breakout_60d_high_volume: 7/10 reached T1")
* analyst lessons  — written by the Claude layer after reviewing the day (free text, dated)

The morning run reads the latest lessons so the analyst persona actually
*uses* what the system has learned rather than just logging it.
"""
from __future__ import annotations

from collections import defaultdict

from ..util import STATE_DIR, today_str

PATH = STATE_DIR / "lessons.md"


def append(text: str, kind: str = "analyst") -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    header = not PATH.exists()
    with open(PATH, "a", encoding="utf-8") as f:
        if header:
            f.write("# Lessons journal\n\nAppended by every EOD run. Newest at the bottom. `[machine]` = computed from the ledger, `[analyst]` = Claude's review.\n\n")
        f.write(f"\n### {today_str()} [{kind}]\n{text.strip()}\n")


def tail(n_chars: int = 6000) -> str:
    if not PATH.exists():
        return ""
    txt = PATH.read_text(encoding="utf-8")
    return txt[-n_chars:]


def pattern_stats(closed_positions: list[dict]) -> str:
    """Which TA reasons / patterns / timeframes / buckets actually worked. Returns a markdown block."""
    if not closed_positions:
        return "No closed positions yet."
    buckets: dict[str, list[float]] = defaultdict(list)
    for p in closed_positions:
        ret = p.get("pnl_pct", 0.0)
        buckets[f"timeframe={p.get('timeframe')}"].append(ret)
        buckets[f"bucket={p.get('bucket')}"].append(ret)
        for pat in p.get("patterns", []):
            buckets[f"pattern={pat}"].append(ret)
        tc = p.get("ta_confidence", 0)
        buckets[f"ta_conf={'>=70' if tc >= 70 else '55-69' if tc >= 55 else '<55'}"].append(ret)
        fs = p.get("fund_score", 0)
        buckets[f"fund={'>=65' if fs >= 65 else '<65'}"].append(ret)
    lines = ["| factor | n | win% | avg ret% |", "|---|---|---|---|"]
    for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(v) < 2:
            continue
        wins = sum(1 for x in v if x > 0)
        lines.append(f"| {k} | {len(v)} | {wins / len(v) * 100:.0f} | {sum(v) / len(v):+.2f} |")
    return "\n".join(lines)
