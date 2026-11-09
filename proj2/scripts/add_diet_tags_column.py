"""
Adds the MenuItem.diet_tags column to an existing database (safe to run more than once).

Usage: python proj2/scripts/add_diet_tags_column.py [path/to/db]
Defaults to WEEKLIES_DB_PATH or proj2/CSC510_DB.db. Items stay untagged until someone
fills diet_tags in, so users with a diet in their preferences get no meals from them.
"""

import os
import sqlite3
import sys

# Repo root on sys.path so `proj2` imports when run as `python scripts/<name>.py`.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from proj2 import config
from proj2.dietary import ensure_diet_tags_column


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = os.path.abspath(argv[0]) if argv else config.db_path()
    if not os.path.exists(path):
        print(f"No database at {path}")
        return 1
    conn = sqlite3.connect(path)
    try:
        added = ensure_diet_tags_column(conn)
    finally:
        conn.close()
    print(f"{'Added' if added else 'Already had'} MenuItem.diet_tags in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
