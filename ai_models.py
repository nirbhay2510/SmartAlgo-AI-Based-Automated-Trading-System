"""
ai_models.py — ML signal generation for intraday trading.

Key fixes vs previous version:
  1. Lower threshold (0.05% not 0.15%) → more BUY/SELL labels, less HOLD bias
  2. Train on older data, predict on recent bars (proper train/test split)
  3. Walk-forward: use last 20 bars as "test", train on bars before that
  4. Voting: return the most common signal across 3 recent predictions
  5. Full guard against None/NaN everywhere
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


def _flatten(df):
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
    return df


def _rsi(s, p=14):
    s = pd.to_numeric(s, errors='coerce')
    d = s.diff()
    g = d.clip(lower=0).rolling(p, min_periods=1).mean()
    l = (-d.clip(upper=0)).rolling(p, min_periods=1).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _build_features(df):
    """
    Returns (X, y, feat_df).
    Labels use 0.05% threshold → more BUY/SELL training examples.
    Raises ValueError if not enough clean data.
    """
    df = _flatten(df)
    if df.empty or 'Close' not in df.columns:
        raise ValueError("No Close column")
    df = df.dropna(subset=['Close']).copy()
    if len(df) < 40:
        raise ValueError(f"Only {len(df)} rows — need ≥40")

    c = df['Close'].astype(float)
    v = df['Volume'].astype(float) if 'Volume' in df.columns \
        else pd.Series(1.0, index=df.index)

    # Fast indicators — use short windows so they're ready quickly
    df['sma3']     = c.rolling(3, min_periods=1).mean()
    df['sma7']     = c.rolling(7, min_periods=1).mean()
    df['rsi']      = _rsi(c, p=9)        # shorter RSI for intraday
    ema8           = c.ewm(span=8,  adjust=False).mean()
    ema21          = c.ewm(span=21, adjust=False).mean()
    df['macd']     = ema8 - ema21
    df['macd_sig'] = df['macd'].ewm(span=5, adjust=False).mean()
    df['macd_hist']= df['macd'] - df['macd_sig']
    roll10         = c.rolling(10, min_periods=3)
    df['bb_up']    = roll10.mean() + 2 * roll10.std()
    df['bb_lo']    = roll10.mean() - 2 * roll10.std()
    df['bb_pct']   = (c - df['bb_lo']) / (df['bb_up'] - df['bb_lo']).replace(0, np.nan)
    avg_vol        = v.rolling(10, min_periods=3).mean()
    df['vol_ratio']= v / avg_vol.replace(0, np.nan)
    df['ret1']     = c.pct_change(1)
    df['ret3']     = c.pct_change(3)
    df['momentum'] = c - c.shift(5)      # 5-bar price momentum

    # Lower threshold → more actionable labels
    future_ret = c.pct_change(1).shift(-1)
    threshold  = 0.0005                  # 0.05% — fires much more often
    df['label'] = 0
    df.loc[future_ret >  threshold, 'label'] =  1
    df.loc[future_ret < -threshold, 'label'] = -1

    feat_cols = ['sma3','sma7','rsi','macd','macd_sig','macd_hist',
                 'bb_pct','vol_ratio','ret1','ret3','momentum']

    df = df.dropna(subset=feat_cols + ['label'])
    if len(df) < 35:
        raise ValueError(f"Only {len(df)} clean rows")

    X = df[feat_cols].values.astype(float)
    y = df['label'].values.astype(int)
    return X, y, df[feat_cols]


def _signal_str(pred):
    return {1: "BUY", -1: "SELL", 0: "HOLD"}.get(int(pred), "HOLD")


def _build_rf():
    return Pipeline([
        ('sc',  StandardScaler()),
        ('clf', RandomForestClassifier(
            n_estimators=80, max_depth=5,
            class_weight='balanced', random_state=42, n_jobs=-1))
    ])

def _build_svm():
    return Pipeline([
        ('sc',  StandardScaler()),
        ('clf', SVC(kernel='rbf', C=1.5, gamma='scale',
                    class_weight='balanced', random_state=42,
                    probability=True))   # enable probability for confidence
    ])

def _build_gb():
    return Pipeline([
        ('sc',  StandardScaler()),
        ('clf', GradientBoostingClassifier(
            n_estimators=80, max_depth=4,
            learning_rate=0.08, random_state=42))
    ])

MODEL_BUILDERS = {
    "Random Forest":  _build_rf,
    "SVM":            _build_svm,
    "Gradient Boost": _build_gb,
}


def get_ai_signal(data: pd.DataFrame, model_name: str) -> dict:
    """
    Walk-forward approach:
      - Train on [0 : -20] rows
      - Predict on last 5 rows, take majority vote
      - Return the most confident signal
    Never raises — returns safe HOLD dict on any failure.
    """
    default = {
        "signal": "HOLD", "confidence": 0,
        "model": model_name, "accuracy": 0,
        "features": {}, "note": ""
    }

    try:
        X, y, feat_df = _build_features(data)
    except Exception as e:
        default["note"] = str(e)
        return default

    # Need at least 2 classes in training portion
    TEST_ROWS  = min(10, len(X) // 5)   # last 10% as test
    TRAIN_END  = len(X) - TEST_ROWS

    if TRAIN_END < 30:
        default["note"] = "Not enough training rows"
        return default

    X_train = X[:TRAIN_END]
    y_train = y[:TRAIN_END]
    X_test  = X[TRAIN_END:]
    y_test  = y[TRAIN_END:]

    unique_train = np.unique(y_train)
    if len(unique_train) < 2:
        default["note"] = "Only one class in training data"
        return default

    builder = MODEL_BUILDERS.get(model_name, _build_rf)

    try:
        model = builder()
        model.fit(X_train, y_train)

        # Predict on test rows → majority vote
        preds   = model.predict(X_test)
        counts  = {1: 0, -1: 0, 0: 0}
        for p in preds:
            counts[int(p)] = counts.get(int(p), 0) + 1

        # Best signal = class with most votes (excluding HOLD if tied)
        best_pred = max(counts, key=lambda k: (counts[k], abs(k)))

        # Confidence from probabilities
        try:
            probas     = model.predict_proba(X_test)
            confidence = round(float(probas[:, model.classes_.tolist().index(best_pred)].mean()) * 100, 1)
        except Exception:
            confidence = round(float(counts[best_pred] / len(preds)) * 100, 1)

        # Train accuracy
        train_preds = model.predict(X_train)
        accuracy    = round(float((train_preds == y_train).mean()) * 100, 1)

        # Test accuracy
        if len(y_test) > 0:
            test_acc = round(float((preds == y_test).mean()) * 100, 1)
        else:
            test_acc = accuracy

        # Last-bar features for display
        row = feat_df.iloc[-1]
        features = {
            "RSI":       round(float(row['rsi']),       2),
            "MACD":      round(float(row['macd']),      4),
            "SMA3":      round(float(row['sma3']),      2),
            "SMA7":      round(float(row['sma7']),      2),
            "Vol Ratio": round(float(row['vol_ratio']), 2),
        }

        return {
            "signal":     _signal_str(best_pred),
            "confidence": confidence,
            "model":      model_name,
            "accuracy":   test_acc,
            "features":   features,
            "note":       f"votes: BUY={counts[1]} SELL={counts[-1]} HOLD={counts[0]}",
        }

    except Exception as e:
        default["note"] = f"Model error: {e}"
        return default