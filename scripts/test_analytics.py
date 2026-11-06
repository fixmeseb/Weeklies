#!/usr/bin/env python
"""
Test script to verify analytics dashboard data population.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from proj2 import config

from proj2.sqlQueries import create_connection, close_connection, fetch_one, fetch_all, execute_query
from werkzeug.security import generate_password_hash

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db

def setup_restaurant_login():
    """Ensure a restaurant exists with known credentials for testing."""
    conn = create_connection(db_file)
    if not conn:
        print("Failed to connect to database")
        return False
    
    try:
        # Check if restaurant exists
        rtr = fetch_one(conn, "SELECT rtr_id, email FROM Restaurant WHERE name = 'Bida Manda'")
        
        if rtr:
            rtr_id = rtr[0]
            print(f"Found restaurant: Bida Manda (ID: {rtr_id})")
            
            # WEEKLIES_SEED_PASSWORD if set, otherwise a random password printed below
            password = config.seed_password()
            hashed = generate_password_hash(password)
            execute_query(conn, 
                "UPDATE Restaurant SET password_HS = ? WHERE rtr_id = ?",
                (hashed, rtr_id))
            print(f"Updated restaurant login password to: {password}")
            
            # Record a fresh analytics snapshot
            from proj2.Flask_app import record_analytics_snapshot
            result = record_analytics_snapshot(rtr_id)
            print(f"Recorded analytics snapshot: {result}")
            
            if result:
                # Display the snapshot
                analytics = fetch_one(conn,
                    "SELECT total_orders, total_revenue_cents, avg_order_value_cents, total_customers, order_completion_rate FROM Analytics WHERE rtr_id = ? ORDER BY analytics_id DESC LIMIT 1",
                    (rtr_id,))
                
                if analytics:
                    print("\nLatest Analytics Snapshot:")
                    print(f"  Total Orders: {analytics[0]}")
                    print(f"  Total Revenue: ${analytics[1]/100:.2f}")
                    print(f"  Avg Order Value: ${analytics[2]/100:.2f}")
                    print(f"  Total Customers: {analytics[3]}")
                    print(f"  Completion Rate: {analytics[4]:.1%}")
            
            return True
        else:
            print("Restaurant 'Bida Manda' not found")
            return False
    finally:
        close_connection(conn)

if __name__ == '__main__':
    setup_restaurant_login()
