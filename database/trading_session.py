import sqlite3

conn = sqlite3.connect('database/db.sqlite3')



conn.execute("""ALTER TABLE trading_session ADD COLUMN start_time REAL;""")

conn.commit()
conn.close()

print("Trading session table created")