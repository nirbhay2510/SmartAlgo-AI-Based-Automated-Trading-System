import sqlite3

conn = sqlite3.connect('database/db.sqlite3')

# Portfolio (ONLY ACTIVE)
conn.execute("""
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    stock TEXT,
    quantity INTEGER,
    buy_price REAL,
    buy_time TEXT,
    strategy TEXT,
    ai_model TEXT
)
""")

# Trade History (COMPLETED)
conn.execute("""
CREATE TABLE IF NOT EXISTS trade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    stock TEXT,
    quantity INTEGER,
    buy_price REAL,
    sell_price REAL,
    profit REAL,
    buy_time TEXT,
    sell_time TEXT,
    strategy TEXT,
    ai_model TEXT
)
""")




conn.commit()
conn.close()

print("Tables ready")