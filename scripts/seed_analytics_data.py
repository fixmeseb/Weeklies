#!/usr/bin/env python
"""
Seed script to populate the Order table with dummy data for testing the analytics dashboard.

Usage:
    python seed_analytics_data.py
    
This script will:
    1. Clear all existing orders from the Order table
    2. Connect to the production database
    3. Insert orders at different stages (PENDING, CONFIRMED, PREPARING, READY, COMPLETED, CANCELLED)
    4. Generate realistic revenue and customer data with JSON details
    5. Verify data was inserted successfully
"""

import os
import sqlite3
from datetime import datetime, timedelta
import random
import sys
import json

# Database file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from proj2 import config
from proj2.sqlQueries import create_connection, close_connection, fetch_all, fetch_one, execute_query

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db

def seed_analytics_data():
    """
    Seed Order table with realistic dummy data for analytics testing.
    Uses the actual production database schema with JSON details.
    
    Stages:
    - PENDING: New orders just placed (last 1 hour)
    - CONFIRMED: Orders confirmed and in queue (1-3 hours ago)
    - PREPARING: Orders currently being prepared (3-6 hours ago)
    - READY: Orders ready for pickup/delivery (6-12 hours ago)
    - COMPLETED: Orders delivered/picked up (12+ hours ago)
    - CANCELLED: Cancelled orders (random times)
    """
    conn = create_connection(db_file)
    if conn is None:
        print("❌ Failed to connect to database")
        return False
    
    try:
        # Clear existing orders first
        print("🗑️  Clearing existing orders...")
        execute_query(conn, 'DELETE FROM "Order"')
        print("✓ Orders cleared\n")
        
        # Get a restaurant to use for testing
        rtr_result = fetch_one(conn, "SELECT rtr_id, name FROM Restaurant LIMIT 1")
        if not rtr_result:
            print("❌ No restaurants found in database. Please add a restaurant first.")
            return False
        
        rtr_id, rtr_name = rtr_result
        print(f"✓ Using restaurant: {rtr_name} (ID: {rtr_id})")
        
        # Get available menu items
        items_result = fetch_all(conn, "SELECT itm_id, name, price FROM MenuItem WHERE rtr_id = ?", (rtr_id,))
        if not items_result:
            print(f"❌ No menu items found for restaurant {rtr_id}. Please add menu items first.")
            return False
        
        items = items_result
        print(f"✓ Found {len(items)} menu items")
        
        # Get available users (customers)
        users_result = fetch_all(conn, "SELECT usr_id FROM User LIMIT 10")
        if not users_result:
            print("❌ No users found in database. Please add users first.")
            return False
        
        user_ids = [row[0] for row in users_result]
        print(f"✓ Found {len(user_ids)} users to assign to orders\n")
        
        # Define order stages with their statuses and time offsets
        # Orders spread across 30 days to show trends in analytics graph
        stages = [
            {
                "name": "PENDING",
                "status": "Ordered",
                "count": 8,
                "time_offset_minutes": lambda: random.randint(0, 60)  # Today
            },
            {
                "name": "CONFIRMED",
                "status": "Confirmed",
                "count": 6,
                "time_offset_minutes": lambda: random.randint(1440, 2880)  # 1-2 days ago
            },
            {
                "name": "PREPARING",
                "status": "Preparing",
                "count": 4,
                "time_offset_minutes": lambda: random.randint(4320, 5760)  # 3-4 days ago
            },
            {
                "name": "READY",
                "status": "Ready",
                "count": 5,
                "time_offset_minutes": lambda: random.randint(7200, 8640)  # 5-6 days ago
            },
            {
                "name": "COMPLETED",
                "status": random.choice(['Completed', 'Delivered']),
                "count": 80,  # Increased to get more days of data
                "time_offset_minutes": lambda: random.randint(10080, 43200)  # 7-30 days ago
            },
            {
                "name": "CANCELLED",
                "status": "Cancelled",
                "count": 5,
                "time_offset_minutes": lambda: random.randint(1440, 43200)  # 1-30 days ago
            }
        ]
        
        orders_created = 0
        
        print("📝 Creating orders by stage:\n")
        for stage in stages:
            stage_name = stage["name"]
            status = stage["status"]
            count = stage["count"]
            
            print(f"  Creating {count} {stage_name} orders...")
            
            for _ in range(count):
                # Calculate order time
                offset_minutes = stage["time_offset_minutes"]()
                order_date = datetime.now() - timedelta(minutes=offset_minutes)
                
                # Random customer
                usr_id = random.choice(user_ids)
                
                # Random number of items (1-4)
                num_items = random.randint(1, 4)
                item_indices = random.sample(range(len(items)), min(num_items, len(items)))
                selected_items = [items[i] for i in item_indices]
                
                # Build order details JSON
                detail_items = []
                subtotal = 0.0
                for itm_id, name, price in selected_items:
                    qty = random.randint(1, 3)
                    price_dollars = price / 100.0  # Assuming price is in cents
                    line_total = qty * price_dollars
                    subtotal += line_total
                    detail_items.append({
                        "itm_id": itm_id,
                        "name": name,
                        "qty": qty,
                        "unit_price": price_dollars,
                        "line_total": round(line_total, 2)
                    })
                
                # Calculate charges
                tax = round(subtotal * 0.0725, 2)
                delivery_fee = 3.99 if random.random() < 0.7 else 0.00
                service_fee = 1.49
                tip = round(random.uniform(0, 10), 2)
                total = round(subtotal + tax + delivery_fee + service_fee + tip, 2)
                
                # Create order details JSON
                details = {
                    "placed_at": order_date.astimezone().isoformat(),
                    "restaurant_id": int(rtr_id),
                    "items": detail_items,
                    "charges": {
                        "subtotal": round(subtotal, 2),
                        "tax": tax,
                        "delivery_fee": delivery_fee,
                        "service_fee": service_fee,
                        "tip": tip,
                        "total": total
                    },
                    "delivery_type": random.choice(['delivery', 'pickup']),
                    "eta_minutes": random.randint(20, 60)
                }
                
                # Insert order
                try:
                    execute_query(conn, '''
                        INSERT INTO "Order" (rtr_id, usr_id, details, status)
                        VALUES (?, ?, ?, ?)
                    ''', (rtr_id, usr_id, json.dumps(details), status))
                    orders_created += 1
                except Exception as e:
                    print(f"      Warning: Could not insert order: {e}")
                    continue
            
            print(f"    ✓ Created {count} {stage_name} orders")
        
        print(f"\n✓ Created {orders_created} total orders")
        
        # Display summary
        print("\n📊 Data Summary:")
        order_summary = fetch_one(conn, '''
            SELECT 
                COUNT(*) as total_orders,
                COUNT(DISTINCT usr_id) as unique_customers
            FROM "Order" WHERE rtr_id = ?
        ''', (rtr_id,))
        
        if order_summary:
            print(f"  - Total orders for restaurant: {order_summary[0]}")
            print(f"  - Unique customers: {order_summary[1]}")
        
        status_summary = fetch_all(conn, '''
            SELECT status, COUNT(*) as count
            FROM "Order"
            WHERE rtr_id = ?
            GROUP BY status
            ORDER BY count DESC
        ''', (rtr_id,))
        
        if status_summary:
            print("  - Orders by status:")
            for status, count in status_summary:
                print(f"    • {status}: {count}")
        
        # Calculate metrics that would be in analytics
        metrics = fetch_one(conn, '''
            SELECT
                COUNT(*) as total_orders,
                COUNT(DISTINCT usr_id) as unique_customers,
                COUNT(CASE WHEN status IN ('Completed', 'Delivered') THEN 1 END) as completed_orders
            FROM "Order"
            WHERE rtr_id = ?
        ''', (rtr_id,))
        
        if metrics:
            total, customers, completed = metrics
            completion_rate = (completed / total * 100) if total > 0 else 0
            print(f"  - Completion rate: {completion_rate:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_connection(conn)

if __name__ == '__main__':
    if not os.path.exists(db_file):
        print(f"❌ Database file not found: {db_file}")
        exit(1)
    
    success = seed_analytics_data()
    if success:
        print("\n✅ Analytics data seeded successfully!")
        print("   You can now test the analytics dashboard with /restaurant/analytics")
    else:
        print("\n❌ Failed to seed analytics data!")
    exit(0 if success else 1)
