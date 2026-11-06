#!/usr/bin/env python
"""
Migration script to add Analytics table to the production database.

Usage:
    python migrate_add_analytics.py
    
This script will:
    1. Back up the existing database
    2. Add the Analytics table if it doesn't exist
    3. Verify the table was created successfully
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

# Repo root on sys.path so this works from any working directory.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from proj2 import config

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db

# Analytics table schema
ANALYTICS_SCHEMA = """
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

def main():
    if not os.path.exists(db_file):
        print(f"❌ Database file not found: {db_file}")
        return False
    
    # Create backup
    backup_file = f"{db_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(db_file, backup_file)
        print(f"✓ Backup created: {backup_file}")
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return False
    
    # Add Analytics table
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Analytics'")
        if cursor.fetchone():
            print("✓ Analytics table already exists")
        else:
            cursor.execute(ANALYTICS_SCHEMA)
            conn.commit()
            print("✓ Analytics table created successfully")
        
        # Verify table structure
        cursor.execute("PRAGMA table_info(Analytics)")
        columns = cursor.fetchall()
        print(f"✓ Analytics table has {len(columns)} columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to add Analytics table: {e}")
        print(f"📋 To restore, copy from backup: {backup_file}")
        return False

if __name__ == '__main__':
    success = main()
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
    exit(0 if success else 1)
