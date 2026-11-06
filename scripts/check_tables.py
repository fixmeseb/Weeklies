import sqlite3
import sys
import os

# Repo root on sys.path so this works from any working directory.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from proj2 import config

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db


def check_database_tables():
    """Check and display database tables and their schemas."""
    if not os.path.exists(db_file):
        print(f"Database file not found: {db_file}")
        sys.exit(1)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    print("Tables in database:")
    for table in tables:
        print(f"  - {table[0]}")

    # Get schema for each table
    print("\nTable schemas:")
    for table in tables:
        table_name = table[0]
        # Quote table name in case it's a reserved word
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = cursor.fetchall()
        print(f"\n{table_name}:")
        for col in columns:
            print(f"  - {col[1]}: {col[2]}")

    conn.close()


if __name__ == '__main__':
    check_database_tables()
