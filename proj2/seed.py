"""
The one demo/test seed: two customers, two restaurants, seven menu items, four orders,
a review and two analytics snapshots, plus task-planner data for testuser (two projects,
six tasks, three tags, three plan entries). Used by `flask seed` and by Cypress
(scripts/cypress_seed.py). Seeding always recreates the database from the migrations.

Accounts (password for all: password123):
  customers: testuser@example.com, seconduser@example.com
  owners:    owner@tasteofitaly.com, owner@greengarden.com
"""

import json
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from proj2 import db
from proj2.db_cli import init_database
from proj2.tasks import store


def seed_database(path):
    """Delete ``path`` if it exists, recreate the schema, and insert the demo data."""
    init_database(path, force=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            _insert_demo_data(conn.cursor())
    finally:
        conn.close()
    conn = db.connect(path)
    try:
        with db.transaction(conn):
            _insert_demo_tasks(conn, usr_id=1)  # testuser@example.com
    finally:
        conn.close()


def _insert_demo_tasks(conn, usr_id):
    """Tasks go through proj2.tasks.store, so the seed obeys the same rules as the app."""
    today = date.today()
    day = lambda n: (today + timedelta(days=n)).isoformat()
    work = store.create_project(conn, usr_id, "CSC 510")
    home = store.create_project(conn, usr_id, "Home")
    report = store.create_task(
        conn,
        usr_id,
        "Write project report",
        project_id=work,
        due_date=day(3),
        est_minutes=120,
        priority=1,
        tags=["writing"],
    )
    slides = store.create_task(
        conn,
        usr_id,
        "Make demo slides",
        project_id=work,
        due_date=day(5),
        est_minutes=90,
        tags=["writing", "presentation"],
    )
    store.create_task(
        conn,
        usr_id,
        "Review teammate's pull request",
        project_id=work,
        due_date=day(1),
        est_minutes=30,
        priority=1,
    )
    groceries = store.create_task(
        conn,
        usr_id,
        "Buy groceries",
        project_id=home,
        est_minutes=45,
        priority=3,
        tags=["errand"],
    )
    laundry = store.create_task(conn, usr_id, "Laundry", project_id=home, est_minutes=60)
    store.create_task(conn, usr_id, "Call the dentist", notes="Ask about Friday", priority=2)
    store.set_status(conn, usr_id, laundry, "done")
    store.set_status(conn, usr_id, report, "in_progress")
    store.schedule_task(conn, usr_id, report, day(1), "morning")
    store.schedule_task(conn, usr_id, slides, day(2), "afternoon")
    store.schedule_task(conn, usr_id, groceries, day(0), "evening")


def _insert_demo_data(cursor):
    pw_hash = generate_password_hash("password123")

    # 1. Seed Users
    # Today and future dates for generated calendar menu
    today = date.today()
    d1 = (today + timedelta(days=1)).isoformat()
    d2 = (today + timedelta(days=2)).isoformat()
    d3 = (today + timedelta(days=3)).isoformat()
    gen_menu_str = f"[{d1},1,1][{d2},2,2][{d3},3,3]"

    users = [
        (
            "John",
            "Doe",
            "testuser@example.com",
            "9195550101",
            pw_hash,
            5000,
            "Vegetarian, Italian",
            "Peanuts",
            gen_menu_str,
        ),
        (
            "Jane",
            "Smith",
            "seconduser@example.com",
            "9195550102",
            pw_hash,
            2500,
            "Gluten-Free, Healthy",
            "Dairy",
            f"[{d1},5,2]",
        ),
    ]
    cursor.executemany(
        """
        INSERT INTO "User" (first_name, last_name, email, phone, password_HS, wallet, preferences, allergies, generated_menu)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        users,
    )

    # 2. Seed Restaurants
    restaurants = [
        (
            "Taste of Italy",
            "Authentic artisanal Italian cuisine crafted with fresh ingredients.",
            "9195550201",
            "owner@tasteofitaly.com",
            pw_hash,
            "100 Main Street",
            "Raleigh",
            "NC",
            "27601",
            "11:00 AM - 10:00 PM",
            "open",
        ),
        (
            "Green Garden Bistro",
            "Fresh farm-to-table salads, grain bowls, and cold-pressed juices.",
            "9195550202",
            "owner@greengarden.com",
            pw_hash,
            "200 Hillsborough Street",
            "Raleigh",
            "NC",
            "27603",
            "10:00 AM - 9:00 PM",
            "open",
        ),
    ]
    cursor.executemany(
        """
        INSERT INTO "Restaurant" (name, description, phone, email, password_HS, address, city, state, zip, hours, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        restaurants,
    )

    # 3. Seed Menu Items
    menu_items = [
        # Taste of Italy (rtr_id: 1)
        (
            1,
            "Margherita Pizza",
            "San Marzano tomatoes, fresh mozzarella, fresh basil, extra virgin olive oil",
            1499,
            750,
            1,
            "",
            "dairy, gluten",
        ),
        (
            1,
            "Penne Arrabbiata",
            "Spicy garlic tomato marinara with fresh herbs and parmesan",
            1299,
            550,
            1,
            "",
            "gluten, dairy",
        ),
        (
            1,
            "Classic Tiramisu",
            "Espresso-soaked ladyfingers with whipped mascarpone cream and cocoa",
            799,
            420,
            1,
            "",
            "dairy, eggs, gluten",
        ),
        (
            1,
            "Caprese Salad",
            "Heirloom tomatoes, sliced fresh mozzarella, balsamic glaze, sweet basil",
            999,
            320,
            1,
            "",
            "dairy",
        ),
        # Green Garden Bistro (rtr_id: 2)
        (
            2,
            "Avocado Quinoa Bowl",
            "Tri-color quinoa, sliced avocado, black beans, corn, lime vinaigrette",
            1350,
            480,
            1,
            "",
            "none",
        ),
        (
            2,
            "Mediterranean Wrap",
            "House hummus, kalamata olives, crisp greens, cucumber, tahini in spinach tortilla",
            1150,
            410,
            1,
            "",
            "gluten, sesame",
        ),
        (
            2,
            "Green Goddess Smoothie",
            "Baby kale, granny smith apple, cucumber, ginger, coconut water",
            699,
            180,
            1,
            "",
            "none",
        ),
    ]
    cursor.executemany(
        """
        INSERT INTO "MenuItem" (rtr_id, name, description, price, calories, instock, restock, allergens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        menu_items,
    )

    # 4. Seed Orders
    now_iso = datetime.now().isoformat()
    past_iso = (datetime.now() - timedelta(days=2)).isoformat()

    order_details_1 = {
        "placed_at": past_iso,
        "restaurant_id": 1,
        "items": [
            {
                "itm_id": 1,
                "name": "Margherita Pizza",
                "qty": 1,
                "unit_price": 14.99,
                "line_total": 14.99,
            },
            {
                "itm_id": 2,
                "name": "Penne Arrabbiata",
                "qty": 1,
                "unit_price": 12.99,
                "line_total": 12.99,
            },
        ],
        "charges": {
            "subtotal": 27.98,
            "tax": 2.03,
            "delivery_fee": 3.99,
            "service_fee": 1.49,
            "tip": 3.00,
            "total": 38.49,
        },
        "delivery_type": "delivery",
        "eta_minutes": 35,
        "date": d1,
        "meal": 3,
    }

    order_details_2 = {
        "placed_at": now_iso,
        "restaurant_id": 1,
        "items": [
            {
                "itm_id": 1,
                "name": "Margherita Pizza",
                "qty": 1,
                "unit_price": 14.99,
                "line_total": 14.99,
            }
        ],
        "charges": {
            "subtotal": 14.99,
            "tax": 1.09,
            "delivery_fee": 0.00,
            "service_fee": 1.49,
            "tip": 2.00,
            "total": 19.57,
        },
        "delivery_type": "pickup",
        "eta_minutes": 25,
        "date": d2,
        "meal": 2,
    }

    order_details_3 = {
        "placed_at": now_iso,
        "restaurant_id": 1,
        "items": [
            {
                "itm_id": 3,
                "name": "Classic Tiramisu",
                "qty": 2,
                "unit_price": 7.99,
                "line_total": 15.98,
            }
        ],
        "charges": {
            "subtotal": 15.98,
            "tax": 1.16,
            "delivery_fee": 3.99,
            "service_fee": 1.49,
            "tip": 2.50,
            "total": 25.12,
        },
        "delivery_type": "delivery",
        "eta_minutes": 40,
        "date": d3,
        "meal": 3,
    }

    # Order 4 is delivered and unreviewed (for testing review submission)
    order_details_4 = {
        "placed_at": past_iso,
        "restaurant_id": 1,
        "items": [
            {
                "itm_id": 4,
                "name": "Caprese Salad",
                "qty": 1,
                "unit_price": 9.99,
                "line_total": 9.99,
            }
        ],
        "charges": {
            "subtotal": 9.99,
            "tax": 0.72,
            "delivery_fee": 3.99,
            "service_fee": 1.49,
            "tip": 2.00,
            "total": 18.19,
        },
        "delivery_type": "delivery",
        "eta_minutes": 30,
        "date": d1,
        "meal": 1,
    }

    orders = [
        (1, 1, json.dumps(order_details_1), "Delivered"),
        (1, 1, json.dumps(order_details_2), "Ordered"),
        (1, 2, json.dumps(order_details_3), "Accepted"),
        (1, 1, json.dumps(order_details_4), "Delivered"),
    ]
    cursor.executemany(
        """
        INSERT INTO "Order" (rtr_id, usr_id, details, status)
        VALUES (?, ?, ?, ?)
        """,
        orders,
    )

    # 5. Seed Reviews (Order 1 is reviewed, Order 4 is not reviewed)
    reviews = [
        (
            1,
            1,
            "Outstanding Pizza and Pasta!",
            5,
            "The Margherita pizza crust had the perfect char and the Arrabbiata was delightfully spicy. Arrived piping hot!",
            1,
            past_iso,
        )
    ]
    cursor.executemany(
        """
        INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        reviews,
    )

    # 6. Seed Analytics snapshots for Restaurant 1
    analytics = [
        (
            1,
            (today - timedelta(days=2)).isoformat(),
            4,
            10137,
            2534,
            2,
            1,
            1.0,
            past_iso,
        ),
        (
            1,
            today.isoformat(),
            5,
            12671,
            2534,
            2,
            1,
            0.8,
            now_iso,
        ),
    ]
    cursor.executemany(
        """
        INSERT INTO "Analytics" (rtr_id, snapshot_date, total_orders, total_revenue_cents, avg_order_value_cents, total_customers, most_popular_item_id, order_completion_rate, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        analytics,
    )
