"""
strategy_logic.py
Intraday signal generation for 5-minute bars.
Uses relaxed thresholds that actually fire during a normal trading session.
"""
import pandas as pd
import numpy as np


def _safe(df):
    """Flatten MultiIndex, coerce to numeric, drop NaN close rows."""
    if df is None or (hasattr(df, 'empty') and df.empty):
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]) if c[0] is not None else '' for c in df.columns]
    else:
        df.columns = [str(c) if c is not None else '' for c in df.columns]
    df = df.loc[:, df.columns != '']
    for col in ['Open','High','Low','Close','Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Close' not in df.columns:
        return pd.DataFrame()
    return df.dropna(subset=['Close'])


def _rsi(s, p=14):
    s = pd.to_numeric(s, errors='coerce')
    d = s.diff()
    g = d.clip(lower=0).rolling(p, min_periods=1).mean()
    l = (-d.clip(upper=0)).rolling(p, min_periods=1).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ── SMA CROSSOVER ─────────────────────────────────────────────────
# Uses short windows (3 / 7) so crossovers actually happen intraday
def sma_strategy(data):
    d = _safe(data)
    if d.empty or len(d) < 10: return 0.0
    d = d.copy()
    d['s3'] = d['Close'].rolling(3).mean()
    d['s7'] = d['Close'].rolling(7).mean()
    pos = 0; bp = 0.0; pnl = 0.0
    for i in range(len(d)):
        s3, s7 = d['s3'].iloc[i], d['s7'].iloc[i]
        if pd.isna(s3) or pd.isna(s7): continue
        p = float(d['Close'].iloc[i])
        if s3 > s7 and pos == 0: pos = 1; bp = p
        elif s3 < s7 and pos == 1: pnl += p - bp; pos = 0
    return round(pnl, 2)


def sma_signal(data):
    d = _safe(data)
    if d.empty or len(d) < 10: return "HOLD"
    d = d.copy()
    d['s3'] = d['Close'].rolling(3).mean()
    d['s7'] = d['Close'].rolling(7).mean()
    # Use last 2 bars to detect crossover direction
    s3_now, s7_now = d['s3'].iloc[-1], d['s7'].iloc[-1]
    s3_prev, s7_prev = d['s3'].iloc[-2], d['s7'].iloc[-2]
    if any(pd.isna(x) for x in [s3_now, s7_now, s3_prev, s7_prev]):
        return "HOLD"
    # Crossover: fast crossed above slow → BUY
    if s3_prev <= s7_prev and s3_now > s7_now:
        return "BUY"
    # Crossover: fast crossed below slow → SELL
    if s3_prev >= s7_prev and s3_now < s7_now:
        return "SELL"
    # Trend-following (no crossover, just direction)
    if s3_now > s7_now:
        return "BUY"
    if s3_now < s7_now:
        return "SELL"
    return "HOLD"


# ── RSI ───────────────────────────────────────────────────────────
# Relaxed thresholds: <45 = oversold signal, >55 = overbought signal
def rsi_strategy(data):
    d = _safe(data)
    if d.empty or len(d) < 20: return 0.0
    d = d.copy(); d['rsi'] = _rsi(d['Close'])
    pos = 0; bp = 0.0; pnl = 0.0
    for i in range(len(d)):
        r = d['rsi'].iloc[i]
        if pd.isna(r): continue
        p = float(d['Close'].iloc[i])
        if r < 45 and pos == 0: pos = 1; bp = p
        elif r > 55 and pos == 1: pnl += p - bp; pos = 0
    return round(pnl, 2)


def rsi_signal(data):
    d = _safe(data)
    if d.empty or len(d) < 15: return "HOLD"
    d = d.copy(); d['rsi'] = _rsi(d['Close'])
    # Use last 3 values to confirm RSI direction
    recent = d['rsi'].dropna().iloc[-3:]
    if len(recent) < 2: return "HOLD"
    r = float(recent.iloc[-1])
    if pd.isna(r): return "HOLD"
    if r < 45: return "BUY"
    if r > 55: return "SELL"
    return "HOLD"


# ── MACD (replaces Breakout which needs 20-bar history) ───────────
# MACD crossover signal — fires reliably on 5-min intraday data
def macd_strategy(data):
    d = _safe(data)
    if d.empty or len(d) < 30: return 0.0
    d = d.copy()
    c = d['Close']
    d['macd']     = c.ewm(span=8, adjust=False).mean() - c.ewm(span=21, adjust=False).mean()
    d['signal']   = d['macd'].ewm(span=5, adjust=False).mean()
    d['hist']     = d['macd'] - d['signal']
    pos = 0; bp = 0.0; pnl = 0.0
    for i in range(1, len(d)):
        h_now  = d['hist'].iloc[i]
        h_prev = d['hist'].iloc[i-1]
        if pd.isna(h_now) or pd.isna(h_prev): continue
        p = float(d['Close'].iloc[i])
        if h_prev < 0 and h_now >= 0 and pos == 0: pos = 1; bp = p   # cross above zero
        elif h_prev > 0 and h_now <= 0 and pos == 1: pnl += p - bp; pos = 0  # cross below
    return round(pnl, 2)


def macd_signal(data):
    d = _safe(data)
    if d.empty or len(d) < 30: return "HOLD"
    d = d.copy()
    c = d['Close']
    d['macd']   = c.ewm(span=8, adjust=False).mean() - c.ewm(span=21, adjust=False).mean()
    d['signal'] = d['macd'].ewm(span=5, adjust=False).mean()
    d['hist']   = d['macd'] - d['signal']
    h_now  = float(d['hist'].iloc[-1])
    h_prev = float(d['hist'].iloc[-2]) if len(d) >= 2 else h_now
    if pd.isna(h_now) or pd.isna(h_prev): return "HOLD"
    # Crossover
    if h_prev < 0 and h_now >= 0: return "BUY"
    if h_prev > 0 and h_now <= 0: return "SELL"
    # Histogram direction
    if h_now > 0: return "BUY"
    if h_now < 0: return "SELL"
    return "HOLD"


# ── VOLUME SPIKE ──────────────────────────────────────────────────
def vol_strategy(data):
    d = _safe(data)
    if d.empty or len(d) < 12 or 'Volume' not in d.columns or 'Open' not in d.columns:
        return 0.0
    d = d.copy(); d['avg'] = d['Volume'].rolling(10).mean().shift(1)
    pos = 0; bp = 0.0; pnl = 0.0
    for i in range(len(d)):
        v = float(d['Volume'].iloc[i]); a = d['avg'].iloc[i]
        p = float(d['Close'].iloc[i]);  o = float(d['Open'].iloc[i])
        if pd.isna(a) or a == 0: continue
        if v > 1.5 * a and p > o and pos == 0: pos = 1; bp = p
        elif v > 1.5 * a and p < o and pos == 1: pnl += p - bp; pos = 0
    return round(pnl, 2)


def vol_signal(data):
    d = _safe(data)
    if d.empty or len(d) < 12 or 'Volume' not in d.columns or 'Open' not in d.columns:
        return "HOLD"
    d = d.copy(); d['avg'] = d['Volume'].rolling(10).mean().shift(1)
    v = float(d['Volume'].iloc[-1]); a = d['avg'].iloc[-1]
    p = float(d['Close'].iloc[-1]);  o = float(d['Open'].iloc[-1])
    if pd.isna(a) or a == 0: return "HOLD"
    if v > 1.5 * a:
        return "BUY" if p > o else "SELL"
    return "HOLD"


# ── MAPS ──────────────────────────────────────────────────────────
strategy_map = {
    "Moving Average Crossover": sma_strategy,
    "RSI Strategy":             rsi_strategy,
    "MACD Strategy":            macd_strategy,
    "Volume Spike Strategy":    vol_strategy,
}

signal_map = {
    "Moving Average Crossover": sma_signal,
    "RSI Strategy":             rsi_signal,
    "MACD Strategy":            macd_signal,
    "Volume Spike Strategy":    vol_signal,
}