"""Technical analysis on daily OHLCV.

Pure numpy/pandas — no TA library dependency, so every number is auditable.
Outputs a flat dict of indicators + detected patterns + support/resistance levels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = atr(df, n)
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def swing_points(df: pd.DataFrame, w: int = 5) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Fractal swing highs/lows: bar i is a swing high if high[i] is the max of high[i-w..i+w]."""
    h, l = df["high"].values, df["low"].values
    highs, lows = [], []
    for i in range(w, len(df) - w):
        seg_h = h[i - w:i + w + 1]
        seg_l = l[i - w:i + w + 1]
        if h[i] == seg_h.max() and (seg_h == h[i]).sum() == 1:
            highs.append((i, float(h[i])))
        if l[i] == seg_l.min() and (seg_l == l[i]).sum() == 1:
            lows.append((i, float(l[i])))
    return highs, lows


def cluster_levels(levels: list[float], tol_pct: float = 1.5) -> list[dict]:
    """Merge nearby price levels; strength = number of touches."""
    out: list[dict] = []
    for p in sorted(levels):
        if out and abs(p - out[-1]["price"]) / out[-1]["price"] * 100 <= tol_pct:
            c = out[-1]
            c["price"] = (c["price"] * c["touches"] + p) / (c["touches"] + 1)
            c["touches"] += 1
        else:
            out.append({"price": p, "touches": 1})
    for c in out:
        c["price"] = round(c["price"], 2)
    return out


def analyze(df: pd.DataFrame) -> dict:
    """Full TA snapshot from daily bars (needs >= 60 rows; 250+ preferred)."""
    df = df.copy()
    c = df["close"]
    n = len(df)
    out: dict = {"bars": n}

    df["ema20"], df["ema50"], df["ema200"] = ema(c, 20), ema(c, 50), ema(c, 200 if n >= 200 else max(50, n // 2))
    df["rsi"] = rsi(c)
    df["atr"] = atr(df)
    df["adx"] = adx(df)
    macd = ema(c, 12) - ema(c, 26)
    sig = ema(macd, 9)
    df["macd_hist"] = macd - sig
    df["vol_sma20"] = df["volume"].rolling(20).mean()
    bb_mid = c.rolling(20).mean()
    bb_sd = c.rolling(20).std()
    df["bb_width"] = (bb_mid + 2 * bb_sd - (bb_mid - 2 * bb_sd)) / bb_mid

    last = df.iloc[-1]
    prev = df.iloc[-2]
    px = float(last["close"])
    out.update(
        close=px, ema20=round(float(last["ema20"]), 2), ema50=round(float(last["ema50"]), 2), ema200=round(float(last["ema200"]), 2),
        rsi=round(float(last["rsi"]), 1), atr=round(float(last["atr"]), 2), atr_pct=round(float(last["atr"]) / px * 100, 2),
        adx=round(float(last["adx"]), 1) if not np.isnan(last["adx"]) else None,
        macd_hist=round(float(last["macd_hist"]), 3), macd_hist_rising=bool(last["macd_hist"] > prev["macd_hist"]),
        vol_ratio=round(float(last["volume"] / last["vol_sma20"]), 2) if last["vol_sma20"] else None,
        avg_turnover_cr=round(float((df["close"] * df["volume"]).tail(20).mean()) / 1e7, 2),
        chg_1d_pct=round((px / float(prev["close"]) - 1) * 100, 2),
        chg_5d_pct=round((px / float(df["close"].iloc[-6]) - 1) * 100, 2) if n > 6 else None,
        chg_20d_pct=round((px / float(df["close"].iloc[-21]) - 1) * 100, 2) if n > 21 else None,
        high_52w=round(float(df["high"].tail(250).max()), 2), low_52w=round(float(df["low"].tail(250).min()), 2),
        last_bar_date=str(df.index[-1].date()),
    )
    out["dist_52w_high_pct"] = round((px / out["high_52w"] - 1) * 100, 2)
    out["dist_ema20_pct"] = round((px / out["ema20"] - 1) * 100, 2)
    out["dist_ema50_pct"] = round((px / out["ema50"] - 1) * 100, 2)
    out["dist_ema200_pct"] = round((px / out["ema200"] - 1) * 100, 2)

    # ---- trend regime
    if out["ema20"] > out["ema50"] > out["ema200"] and px > out["ema20"]:
        trend = "strong_up"
    elif px > out["ema50"] and out["ema50"] > out["ema200"]:
        trend = "up"
    elif px < out["ema50"] < out["ema200"] and out["ema20"] < out["ema50"]:
        trend = "strong_down"
    elif px < out["ema200"]:
        trend = "down"
    else:
        trend = "sideways"
    out["trend"] = trend

    # ---- support / resistance from swing points (last ~150 bars) + 52w high + round numbers
    look = df.tail(160)
    offset = n - len(look)
    highs, lows = swing_points(look, 5)
    res_levels = [p for _, p in highs if p > px * 1.003]
    sup_levels = [p for _, p in lows if p < px * 0.997]
    if out["high_52w"] > px * 1.003:
        res_levels.append(out["high_52w"])
    out["resistances"] = [c_ for c_ in cluster_levels(res_levels) if c_["price"] > px][:6]
    out["supports"] = sorted([c_ for c_ in cluster_levels(sup_levels) if c_["price"] < px], key=lambda x: -x["price"])[:6]
    out["recent_swing_low"] = round(min([p for i, p in lows if i >= len(look) - 25] or [float(look["low"].tail(10).min())]), 2)
    out["recent_swing_high"] = round(max([p for i, p in highs if i >= len(look) - 25] or [float(look["high"].tail(10).max())]), 2)

    # ---- patterns
    pats: list[str] = []
    hi60 = float(df["high"].iloc[-61:-1].max()) if n > 61 else float(df["high"].iloc[:-1].max())
    if px > hi60 and (out["vol_ratio"] or 0) >= 1.5:
        pats.append("breakout_60d_high_volume")
    elif px > hi60:
        pats.append("breakout_60d_low_volume")
    if trend in ("strong_up", "up") and abs(out["dist_ema20_pct"]) <= 2.0 and 40 <= out["rsi"] <= 58:
        pats.append("pullback_to_ema20_in_uptrend")
    if trend in ("strong_up", "up") and -6 <= out["dist_ema50_pct"] <= 1.5 and out["rsi"] < 50:
        pats.append("pullback_to_ema50_in_uptrend")
    bbw = df["bb_width"].dropna()
    if len(bbw) > 120 and float(bbw.iloc[-1]) <= float(bbw.tail(120).quantile(0.2)):
        pats.append("bollinger_squeeze")
    # double bottom: two swing lows within 3% of each other, 10-60 bars apart, price above the interim high (neckline)
    lows_abs = [(i + offset, p) for i, p in lows]
    for a in range(len(lows_abs)):
        for b in range(a + 1, len(lows_abs)):
            (ia, pa), (ib, pb) = lows_abs[a], lows_abs[b]
            if 10 <= ib - ia <= 60 and abs(pa - pb) / pa <= 0.03 and ib >= n - 40:
                neck = float(df["high"].iloc[ia:ib].max())
                if px > neck and px < neck * 1.06:
                    pats.append("double_bottom_confirmed")
    if out["rsi"] >= 75 or out["dist_ema20_pct"] >= 10:
        pats.append("overextended")
    if out["rsi"] <= 30 and trend in ("down", "strong_down"):
        pats.append("oversold_in_downtrend")
    if px >= out["high_52w"] * 0.995:
        pats.append("at_52w_high")
    if out["chg_1d_pct"] >= 8:
        pats.append("gap_or_spike_today")
    if (out["vol_ratio"] or 0) >= 2.5:
        pats.append("volume_spike")
    if 45 <= out["rsi"] <= 65 and out["macd_hist"] > 0 and out["macd_hist_rising"] and trend in ("strong_up", "up"):
        pats.append("momentum_aligned")
    out["patterns"] = sorted(set(pats))
    return out
