import sqlite3

conn = sqlite3.connect('database/db.sqlite3')

# Users table
conn.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    dob DATE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    mobile TEXT NOT NULL,
    email TEXT,
    mobile_verified INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 0
);
''')

# Portfolio table
conn.execute('''
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    stock TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    buy_price REAL NOT NULL,
    buy_time TEXT NOT NULL
);
''')

# Strategies table
conn.execute('''
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    name TEXT NOT NULL,
    logic TEXT
);
''')

conn.commit()
conn.close()
print("Database setup completed!")