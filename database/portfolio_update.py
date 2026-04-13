import sqlite3

conn = sqlite3.connect('database/db.sqlite3')

# Add new columns
conn.execute("ALTER TABLE portfolio ADD COLUMN strategy TEXT")
conn.execute("ALTER TABLE portfolio ADD COLUMN ai_model TEXT")

conn.commit()
conn.close()