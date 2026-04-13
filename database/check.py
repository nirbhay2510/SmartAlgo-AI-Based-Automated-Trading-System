import sqlite3

conn = sqlite3.connect("DB_PATH")
cursor = conn.execute("PRAGMA table_info(trades);")

for row in cursor:
    print(row)

conn.close()