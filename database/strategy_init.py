import sqlite3

conn = sqlite3.connect('database/db.sqlite3')

strategies = [
    ("Moving Average Crossover", "Buy when short MA crosses above long MA"),
    ("RSI Strategy", "Buy when RSI < 30, Sell when RSI > 70"),
    ("Breakout Strategy", "Buy when price breaks resistance"),
    ("Volume Spike Strategy", "Trade when volume suddenly increases")
]

for name, logic in strategies:
    conn.execute(
        "INSERT INTO strategies (username, name, logic) VALUES (?, ?, ?)",
        (None, name, logic)
    )

conn.commit()
conn.close()