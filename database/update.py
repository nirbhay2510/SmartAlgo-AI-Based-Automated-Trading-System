"""
Run once to create / migrate the database.
Safe to re-run — uses CREATE TABLE IF NOT EXISTS.
"""
import sqlite3

conn = sqlite3.connect('database/db.sqlite3')

conn.executescript('''
-- Users
CREATE TABLE users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name       TEXT    NOT NULL,
    last_name        TEXT    NOT NULL,
    dob              DATE    NOT NULL,
    username         TEXT    UNIQUE NOT NULL,
    password         TEXT    NOT NULL,
    mobile           TEXT    NOT NULL,
    email            TEXT,
    mobile_verified  INTEGER DEFAULT 0,
    email_verified   INTEGER DEFAULT 0
);

-- Active holdings
CREATE TABLE portfolio (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT    NOT NULL,
    stock     TEXT    NOT NULL,
    quantity  INTEGER NOT NULL,
    buy_price REAL    NOT NULL,
    buy_time  TEXT    NOT NULL,
    strategy  TEXT,
    ai_model  TEXT
);

-- Completed trades
CREATE TABLE trade_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT,
    stock      TEXT,
    quantity   INTEGER,
    buy_price  REAL,
    sell_price REAL,
    profit     REAL,
    buy_time   TEXT,
    sell_time  TEXT,
    strategy   TEXT,
    ai_model   TEXT
);

-- Strategies
CREATE TABLE strategies (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    name     TEXT NOT NULL,
    logic    TEXT
);

-- Auto-trading sessions
CREATE TABLE trading_session (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT,
    stock     TEXT,
    capital   REAL,
    is_active INTEGER DEFAULT 0
);
''')

# Seed built-in strategies if not present
existing = conn.execute("SELECT name FROM strategies WHERE username IS NULL").fetchall()
existing_names = {r[0] for r in existing}

builtins = [
    ("Moving Average Crossover", "Buy when SMA5 crosses above SMA10; sell on cross-below"),
    ("RSI Strategy",             "Buy when RSI < 30 (oversold); sell when RSI > 70 (overbought)"),
    ("Breakout Strategy",        "Buy when price breaks 20-bar resistance; sell below support"),
    ("Volume Spike Strategy",    "Buy on bullish volume spike (>2× avg); sell on bearish spike"),
]

for name, logic in builtins:
    if name not in existing_names:
        conn.execute(
            "INSERT INTO strategies (username, name, logic) VALUES (NULL, ?, ?)",
            (name, logic)
        )

conn.commit()
conn.close()
print("✅  Database ready.")