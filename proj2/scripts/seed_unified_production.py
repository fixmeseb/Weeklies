"""
Unified Seed Script for Restaurant Analytics Database

This script ensures the CSC510_DB.db contains all production data with full historical analytics.

APPROACH:
- Production database (backup) is the authoritative data source
- Contains 19 restaurants, 269 menu items, 334 orders, 103 users, and 50 reviews
- Analytics snapshots computed from order data using production schema
- Schema uses "Order" table (not "Orders") with JSON details field
- Analytics table has columns: rtr_id, snapshot_date, total_orders, total_revenue_cents,
  avg_order_value_cents, total_customers, most_popular_item_id, order_completion_rate, created_at

DATABASE COPY COMMAND:
If needed to reset database to production baseline, run:
  cp CSC510_DB.db.backup.20251119_183208 CSC510_DB.db

VERIFICATION:
After running this script, verify with:
  python verify_production_db.py
  python -m pytest tests/e2e/test_analytics_dashboard.py -v
  python -m pytest tests/ -v

TABLES INCLUDED:
- Restaurant (19 records)
- MenuItem (269 records)
- Order (334 records with JSON details field)
- User (103 records)
- Review (50 records)
- Analytics (snapshots from orders, regenerated on demand)

NOTES:
- The analytics snapshots in the database may be from previous dates
- Fresh snapshots are generated when /restaurant/analytics route is accessed
- Each call to record_analytics_snapshot() creates a new snapshot for the current date
"""

import sqlite3
import os
import sys
from pathlib import Path

# Repo root on sys.path so `proj2` imports when run as `python scripts/<name>.py`.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from proj2 import config

# Get database path (WEEKLIES_DB_PATH, else proj2/CSC510_DB.db); the backup sits beside it
db_file = Path(config.db_path())
db_dir = db_file.parent
backup_file = db_dir / "CSC510_DB.db.backup.20251119_183208"


def verify_production_data():
    """Verify the production database has all required data."""
    if not db_file.exists():
        print(f"❌ Database not found: {db_file}")
        return False

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Check all required tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required_tables = {
            "Restaurant",
            "MenuItem",
            "Order",
            "User",
            "Review",
            "Analytics",
        }

        if not required_tables.issubset(tables):
            print(
                f"❌ Missing tables. Found: {tables}, Required: {required_tables}"
            )
            conn.close()
            return False

        # Verify record counts
        counts = {}
        for table in ["Restaurant", "MenuItem", "User", "Review"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            counts[table] = count
        
        # Order table has special name with quotes
        cursor.execute('SELECT COUNT(*) FROM "Order"')
        counts["Order"] = cursor.fetchone()[0]

        print("\n📊 Database Contents:")
        print(f"   Restaurants: {counts['Restaurant']}")
        print(f"   Menu Items: {counts['MenuItem']}")
        print(f"   Orders: {counts['Order']}")
        print(f"   Users: {counts['User']}")
        print(f"   Reviews: {counts['Review']}")

        # Verify Analytics table has production schema
        cursor.execute("PRAGMA table_info(Analytics)")
        columns = {row[1] for row in cursor.fetchall()}
        required_columns = {
            "rtr_id",
            "snapshot_date",
            "total_orders",
            "total_revenue_cents",
            "avg_order_value_cents",
            "total_customers",
            "most_popular_item_id",
            "order_completion_rate",
            "created_at",
        }

        if not required_columns.issubset(columns):
            print(
                f"❌ Analytics table missing columns. Found: {columns}, Required: {required_columns}"
            )
            conn.close()
            return False

        cursor.execute("SELECT COUNT(*) FROM Analytics")
        analytics_count = cursor.fetchone()[0]
        print(f"   Analytics Snapshots: {analytics_count}")

        conn.close()

        if counts["Restaurant"] > 0 and counts["Order"] > 0:
            print(
                "\n✅ Production database verified successfully with all required data!"
            )
            return True
        else:
            print("\n⚠️  Database exists but has minimal data")
            return False

    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False


def restore_from_backup():
    """Restore production database from backup if needed."""
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return False

    try:
        import shutil

        print(f"\n📦 Restoring from backup: {backup_file}")
        shutil.copy(backup_file, db_file)
        print(f"✅ Restored to: {db_file}")
        return True
    except Exception as e:
        print(f"❌ Error restoring from backup: {e}")
        return False


def main():
    """Main seed function."""
    print("=" * 70)
    print("UNIFIED PRODUCTION DATABASE SEED")
    print("=" * 70)

    # Check if database exists and has data
    if db_file.exists():
        print(f"\n📂 Database found: {db_file}")
        if verify_production_data():
            print(
                "\n✅ Database is properly seeded with production data!"
            )
            return True

    # If verification failed or database doesn't exist, try restore
    print("\n⚙️  Attempting to restore production database from backup...")
    if restore_from_backup():
        if verify_production_data():
            return True

    print(
        "\n❌ Could not establish production database. Manual steps required:"
    )
    print(f"1. Ensure backup exists at: {backup_file}")
    print(f"2. Run: cp {backup_file} {db_file}")
    print("3. Re-run this script to verify")
    return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
