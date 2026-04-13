import sqlite3

# ... (your existing code to create connection and table) ...
conn = sqlite3.connect('database/db.sqlite3')
cursor = conn.cursor()

# 1. Execute the DELETE statement to remove all rows
cursor.execute("DELETE FROM portfolio;")
print("All rows deleted from the portfolio table.")

# 2. Commit the changes
conn.commit()

# 3. Reset the AUTOINCREMENT counter (optional)
# This ensures the next inserted row starts with id 1 again
cursor.execute("DELETE FROM sqlite_sequence WHERE name='portfolio';")
conn.commit()
print("AUTOINCREMENT sequence reset for portfolio table.")

# 4. Vacuum the database (optional)
cursor.execute("VACUUM;")
conn.commit()
print("Database vacuumed to reclaim space.")

# Close the connection
conn.close()
