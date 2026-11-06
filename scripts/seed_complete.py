#!/usr/bin/env python
"""Complete seed script for Bida Manda restaurant with menu items and analytics data."""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
import json
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from proj2 import config
from proj2.sqlQueries import create_connection, close_connection, fetch_one, execute_query
from werkzeug.security import generate_password_hash

db_file = config.db_path()  # WEEKLIES_DB_PATH, else proj2/CSC510_DB.db

def seed_menu_items():
    """Seed Bida Manda with menu items."""
    conn = create_connection(db_file)
    if not conn:
        print("❌ Failed to connect to database")
        return False
    
    try:
        # Get Bida Manda ID
        rtr = fetch_one(conn, "SELECT rtr_id FROM Restaurant WHERE name = 'Bida Manda'")
        if not rtr:
            print("❌ Restaurant Bida Manda not found")
            return False
        
        rtr_id = rtr[0]
        print(f"✓ Found Bida Manda (ID: {rtr_id})")
        
        # Check if items already exist
        items = fetch_one(conn, "SELECT COUNT(*) FROM MenuItem WHERE rtr_id = ?", (rtr_id,))
        if items and items[0] > 0:
            print(f"✓ Menu items already exist ({items[0]} items)")
            return True
        
        # Add sample Laotian menu items
        menu_items = [
            (rtr_id, "Drunken Noodles", "Spicy stir-fried noodles with basil", 1600, 450, 1, None, "Gluten, Soy"),
            (rtr_id, "Green Papaya Salad", "Fresh green papaya with lime dressing", 1400, 250, 1, None, "Fish, Peanuts"),
            (rtr_id, "Larb", "Spicy ground meat salad with herbs", 1500, 380, 1, None, "Fish"),
            (rtr_id, "Sticky Rice", "Traditional steamed sticky rice", 300, 200, 1, None, None),
            (rtr_id, "Pad Thai", "Thai stir-fried noodles with shrimp", 1550, 420, 1, None, "Peanuts, Shellfish"),
            (rtr_id, "Tom Yum Soup", "Hot and sour soup with coconut", 1200, 280, 1, None, "Shellfish"),
            (rtr_id, "Satay Skewers", "Grilled meat skewers with peanut sauce", 1800, 380, 1, None, "Peanuts"),
            (rtr_id, "Mango Sticky Rice", "Sweet dessert with fresh mango", 800, 350, 1, None, None),
        ]
        
        for item in menu_items:
            execute_query(conn, '''
                INSERT INTO MenuItem 
                (rtr_id, name, description, price, calories, instock, restock, allergens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', item)
        
        print(f"✓ Added {len(menu_items)} menu items")
        return True
        
    finally:
        close_connection(conn)

def seed_orders_and_analytics():
    """Seed orders for analytics dashboard."""
    conn = create_connection(db_file)
    if not conn:
        print("❌ Failed to connect to database")
        return False
    
    try:
        # Get restaurant
        rtr = fetch_one(conn, "SELECT rtr_id FROM Restaurant WHERE name = 'Bida Manda'")
        if not rtr:
            print("❌ Restaurant not found")
            return False
        
        rtr_id = rtr[0]
        
        # Create a test user if it doesn't exist
        user = fetch_one(conn, "SELECT usr_id FROM User LIMIT 1")
        if not user:
            password = config.seed_password()  # WEEKLIES_SEED_PASSWORD, else random
            hashed_pw = generate_password_hash(password)
            print(f"✓ Created test@example.com with password: {password}")
            execute_query(conn, '''
                INSERT INTO User 
                (first_name, last_name, email, phone, password_HS, wallet, preferences, allergies, generated_menu)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('Test', 'Customer', 'test@example.com', '555-0001', hashed_pw, 10000, '', '', ''))
            user = fetch_one(conn, "SELECT usr_id FROM User WHERE email = 'test@example.com'")
        
        usr_id = user[0]
        print(f"✓ Using user ID: {usr_id}")
        
        # Clear existing orders
        print("🗑️  Clearing existing orders...")
        execute_query(conn, 'DELETE FROM "Order"')
        execute_query(conn, 'DELETE FROM OrderItems')
        execute_query(conn, 'DELETE FROM Orders')
        execute_query(conn, 'DELETE FROM Analytics')
        
        # Get menu items
        items_result = fetch_one(conn, 'SELECT COUNT(*) FROM MenuItem WHERE rtr_id = ?', (rtr_id,))
        item_count = items_result[0] if items_result else 0
        
        if item_count == 0:
            print("❌ No menu items found")
            return False
        
        print(f"✓ Found {item_count} menu items")
        
        # Create sample orders with different statuses
        statuses = ['Ordered', 'Accepted', 'Preparing', 'Ready', 'Delivered', 'Cancelled']
        now = datetime.now()
        
        print(f"\n📝 Creating {len(statuses)} sample orders...")
        
        for idx, status in enumerate(statuses):
            # Create order with varied timestamps
            order_time = now - timedelta(hours=idx*2)
            
            details = {
                'placed_at': order_time.isoformat(),
                'restaurant_id': rtr_id,
                'items': [
                    {'itm_id': 1, 'name': 'Drunken Noodles', 'qty': 1, 'unit_price': 16.00, 'line_total': 16.00},
                    {'itm_id': 2, 'name': 'Green Papaya Salad', 'qty': 1, 'unit_price': 14.00, 'line_total': 14.00}
                ],
                'charges': {
                    'subtotal': 30.00,
                    'tax': 2.18,
                    'delivery_fee': 2.99,
                    'service_fee': 1.29,
                    'tip': 4.00,
                    'total': 40.46
                },
                'delivery_type': 'delivery',
                'eta_minutes': 35,
                'notes': 'No peanuts'
            }
            
            execute_query(conn, '''
                INSERT INTO "Order" (rtr_id, usr_id, details, status)
                VALUES (?, ?, ?, ?)
            ''', (rtr_id, usr_id, json.dumps(details), status))
            
            print(f"  ✓ Order {idx+1}: {status}")
        
        print(f"\n✅ Successfully seeded {len(statuses)} orders!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_connection(conn)

if __name__ == '__main__':
    print("🍽️  Seeding Bida Manda restaurant data...\n")
    
    if not seed_menu_items():
        print("❌ Failed to seed menu items")
        sys.exit(1)
    
    print()
    
    if not seed_orders_and_analytics():
        print("❌ Failed to seed orders")
        sys.exit(1)
    
    print("\n✅ All data seeded successfully!")
