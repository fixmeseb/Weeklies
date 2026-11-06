#!/usr/bin/env python
"""Initialize the database schema if it doesn't exist."""

import sqlite3
import os
import sys

# Repo root on sys.path so this works from any working directory.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from proj2 import config

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS "User" (
  usr_id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name TEXT, last_name TEXT, email TEXT UNIQUE, phone TEXT,
  password_HS TEXT, wallet INTEGER, preferences TEXT, allergies TEXT, generated_menu TEXT
);

CREATE TABLE IF NOT EXISTS "Restaurant" (
  rtr_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, description TEXT, phone TEXT, email TEXT, password_HS TEXT,
  address TEXT, city TEXT, state TEXT, zip TEXT, hours TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS "MenuItem" (
  itm_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, name TEXT, description TEXT, price INTEGER, calories INTEGER,
  instock INTEGER, restock TEXT, allergens TEXT
);

CREATE TABLE IF NOT EXISTS "Order" (
  ord_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, usr_id INTEGER, details TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS "OrderItems" (
  oi_id INTEGER PRIMARY KEY AUTOINCREMENT,
  o_id INTEGER, itm_id INTEGER, quantity INTEGER, unit_price_cents INTEGER
);

CREATE TABLE IF NOT EXISTS "Orders" (
  o_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, usr_id INTEGER, order_date TEXT, total_amount_cents INTEGER, status TEXT
);

CREATE TABLE IF NOT EXISTS "Review" (
  rev_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, usr_id INTEGER, title TEXT, rating INTEGER, description TEXT
);

CREATE TABLE IF NOT EXISTS "Analytics" (
  analytics_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER NOT NULL,
  snapshot_date TEXT NOT NULL,
  total_orders INTEGER DEFAULT 0,
  total_revenue_cents INTEGER DEFAULT 0,
  avg_order_value_cents INTEGER DEFAULT 0,
  total_customers INTEGER DEFAULT 0,
  most_popular_item_id INTEGER,
  order_completion_rate REAL DEFAULT 0.0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(rtr_id) REFERENCES Restaurant(rtr_id),
  FOREIGN KEY(most_popular_item_id) REFERENCES MenuItem(itm_id)
);
"""

def init_database():
    """Initialize the database with schema."""
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"✅ Database initialized at {db_file}")
        print("\nTables created:")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_database()
