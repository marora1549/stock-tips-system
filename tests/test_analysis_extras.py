"""Velocity, target ETAs, derived tags, and the manual tip path — the numbers behind the portal."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("STOCKTIPS_ROOT", str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stocktips import cli, pipeline  # noqa: E402
from stocktips.analysis import plan as planmod, scoring, ta  # noqa: E402
from stocktips.learning import confidence  # noqa: E402


def series(vals):
    return pd.Series(vals, index=pd.bdate_range("2026-06-01", periods=len(vals), tz="Asia/Kolkata"))


# ------------------------------------------------------------------ velocity
def test_velocity_separates_a_trend_from_chop_of_the_same_amplitude():
    trend = series(100 * np.cumprod(1 + np.r_[np.zeros(20), np.full(21, 0.008)]))
    chop = series(100 * np.cumprod(1 + np.r_[np.zeros(20), np.tile([0.02, -0.02], 10), [0.0]]))

    t, c = ta.velocity(trend), ta.velocity(chop)
    # the chopper moves further every day but arrives nowhere
    assert c["amplitude_pct_day"] > t["amplitude_pct_day"]
    assert t["efficiency"] == pytest.approx(1.0, abs=0.01) and c["efficiency"] < 0.15
    assert t["drift_pct_day"] > 0.7 and abs(c["drift_pct_day"]) < 0.2
    assert t["up_day_share"] == 1.0


def test_velocity_is_signed_and_degrades_without_enough_bars():
    down = series(100 * np.cumprod(1 - np.r_[np.zeros(20), np.full(21, 0.006)]))
    assert ta.velocity(down)["drift_pct_day"] < 0
    assert ta.velocity(series([100, 101, 102]))["drift_pct_day"] is None


# ------------------------------------------------------------------ ETA
def test_eta_turns_distance_and_pace_into_sessions():
    e = planmod.eta_days([2.0, 5.0, 8.0], 0.5, time_stop=10)
    assert e["eta_days"] == [4, 10, 16] and e["t1_inside_clock"] is True

    slow = planmod.eta_days([2.0, 5.0, 8.0], 0.08, time_stop=10)
    assert slow["eta_days"][0] == 25 and slow["t1_inside_clock"] is False   # right way, wrong clock

    assert planmod.eta_days([2.0], None, 10)["eta_days"] == [None]
    assert planmod.eta_days([2.0], -0.4, 10)["eta_days"] == [None]          # drifting away from the target


def test_eta_is_capped_at_three_clocks_rather_than_promising_a_year():
    e = planmod.eta_days([40.0], 0.05, time_stop=10)
    assert e["eta_days"] == [30]


def test_plan_scores_the_clock_and_publishes_the_pace(monkeypatch):
    """A fast idea and a stalled one, identical but for their velocity."""
    def snap(drift, mom):
        return {"close": 100.0, "atr": 2.0, "atr_pct": 2.0, "rsi": 58.0, "adx": 26.0, "trend": "strong_up",
                "macd_hist": 0.4, "macd_hist_rising": True, "vol_ratio": 1.4, "avg_turnover_cr": 50.0,
                "patterns": [], "resistances": [], "supports": [], "high_52w": 130.0, "low_52w": 70.0,
                "dist_52w_high_pct": -23.0, "dist_ema20_pct": 1.0, "dist_ema50_pct": 3.0,
                "dist_ema200_pct": 9.0, "ema20": 99.0, "ema50": 97.0, "ema200": 91.0, "bars": 300,
                "recent_swing_low": 96.5, "recent_swing_high": 108.0,
                "chg_1d_pct": 0.4, "chg_5d_pct": 1.2, "chg_20d_pct": 5.0, "bb_squeeze": False,
                "drift_pct_day": drift, "momentum_score": mom, "efficiency": 0.7, "amplitude_pct_day": 1.0}

    fast = planmod.build_plan(snap(0.9, 85), "weekly")
    slow = planmod.build_plan(snap(0.05, 8), "weekly")
    assert fast["eta_days"][0] < slow["eta_days"][0]
    assert fast["momentum_score"] == 85 and fast["pace_pct_day"] == 0.9
    assert fast["t1_inside_clock"] and not slow["t1_inside_clock"]
    # pace is scored, so the same chart at two speeds does not score the same
    assert fast["ta_confidence"] > slow["ta_confidence"]
    assert any("clock" in r for r in slow["reasons"])


# ------------------------------------------------------------------ tags
def test_tags_name_why_an_idea_is_worth_taking():
    plan = {"ta_confidence": 84, "eta_days": [4, 10, 16], "time_stop_days": 30, "pace_pct_day": 0.5,
            "reward_risk_t2": 3.2, "stop_loss_pct": 2.4}
    keys = {t["key"]: t for t in scoring.tags(plan, {"momentum_score": 78, "trend": "strong_up"}, 91, 5, 1)}
    assert keys["fundamentals"]["tone"] == "good" and "91" in keys["fundamentals"]["why"]
    assert keys["technicals"]["tone"] == "good"
    assert keys["momentum"]["label"] == "Fast mover" and "4 sessions" in keys["momentum"]["why"]
    assert keys["asymmetric"]["tone"] == "good" and keys["tight-stop"]["tone"] == "good"
    assert keys["corroborated"]["label"] == "5 sources"
    assert keys["trend"]["label"] == "Strong uptrend"
    assert "hot-potato" not in keys                       # fundamentals 91 is hold-capable


def test_tags_call_out_the_bad_ones_too():
    plan = {"ta_confidence": 62, "eta_days": [38, 60, 90], "time_stop_days": 10, "pace_pct_day": 0.05,
            "reward_risk_t2": 1.6, "stop_loss_pct": 7.4}
    keys = {t["key"]: t for t in scoring.tags(plan, {"momentum_score": 11, "trend": "sideways"}, 38)}
    assert keys["weak-fundamentals"]["tone"] == "bad"
    assert keys["sluggish"]["tone"] == "warn"
    assert keys["slow-clock"]["tone"] == "warn" and "10-session" in keys["slow-clock"]["why"]
    assert keys["hot-potato"]["tone"] == "warn"
    assert "technicals" not in keys and "tight-stop" not in keys
    assert all(t["why"] for t in scoring.tags(plan, {"momentum_score": 11}, 38))    # never decorative


# ------------------------------------------------------------------ add-tip
class TipArgs:
    def __init__(self, **kw):
        self.source = kw.get("source", "manual:mohan")
        self.symbol = kw.get("symbol", "TATASTEEL")
        self.company = kw.get("company")
        self.text = kw.get("text")
        self.url = kw.get("url")
        self.entry = kw.get("entry")
        self.target = kw.get("target")
        self.stop = kw.get("stop")
        self.timeframe = kw.get("timeframe", "weekly")
        self.action = kw.get("action", "buy")


@pytest.fixture
def paper(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(confidence, "PATH", tmp_path / "conf.json")
    return tmp_path


def test_add_tip_writes_the_pipeline_schema_and_registers_the_source(paper, capsys):
    cli.cmd_add_tip(TipArgs(target="195, 210", stop=168.0, timeframe="monthly",
                            text="Tata Steel strong above 180, target 195 then 210, SL 168"))
    out = capsys.readouterr().out
    day = sorted((paper / "reports").iterdir())[-1]
    raw = json.loads((day / "tips_raw.json").read_text(encoding="utf-8"))
    assert set(raw) == {"date", "sources", "tips", "docs"}
    tip = raw["tips"][0]
    assert tip["symbol"] == "TATASTEEL" and tip["company"] == "Tata Steel Limited"
    assert tip["src_targets"] == [195.0, 210.0] and tip["src_stop"] == 168.0
    assert tip["extracted_by"] == "manual" and tip["extraction_confidence"] == 0.9
    assert tip["needs_review"] is False and tip["action"] == "buy"
    assert tip["default_timeframe"] == "monthly" and tip["src_duration"] == "monthly"
    assert raw["sources"] == {"manual:mohan": 1}
    assert tip["id"] in out
    # a manual source starts neutral like every other source — no bonus for being mine
    assert confidence.load()["manual:mohan"]["score"] == 0.0


def test_add_tip_resolves_a_company_name_and_refuses_to_guess(paper, capsys):
    cli.cmd_add_tip(TipArgs(symbol="Reliance Industries"))
    day = sorted((paper / "reports").iterdir())[-1]
    assert json.loads((day / "tips_raw.json").read_text(encoding="utf-8"))["tips"][0]["symbol"] == "RELIANCE"
    assert "resolved" in capsys.readouterr().out

    with pytest.raises(SystemExit, match="Not guessing"):
        cli.cmd_add_tip(TipArgs(symbol="Definitely Not A Listed Company Pvt"))


def test_add_tip_appends_and_counts_per_source(paper):
    cli.cmd_add_tip(TipArgs(symbol="TATASTEEL"))
    cli.cmd_add_tip(TipArgs(symbol="INFY", source="manual:tg_friend", target="1900"))
    cli.cmd_add_tip(TipArgs(symbol="WIPRO", source="manual:tg_friend"))
    day = sorted((paper / "reports").iterdir())[-1]
    raw = json.loads((day / "tips_raw.json").read_text(encoding="utf-8"))
    assert [t["symbol"] for t in raw["tips"]] == ["TATASTEEL", "INFY", "WIPRO"]
    assert raw["sources"] == {"manual:mohan": 1, "manual:tg_friend": 2}
    assert set(confidence.load()) == {"manual:mohan", "manual:tg_friend"}
