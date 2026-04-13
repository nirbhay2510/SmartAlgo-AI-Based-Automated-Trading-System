import sqlite3

conn = sqlite3.connect('database/db.sqlite3')
cursor = conn.cursor()

# Get the names of all user-defined tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = cursor.fetchall()

# Drop each table
for table_name in tables:
    cursor.execute(f'DROP TABLE IF EXISTS "{table_name[0]}"')


conn.commit()
conn.close()
