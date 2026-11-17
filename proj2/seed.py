"""
The one demo/test seed: two customers, eleven restaurants, 76 menu items (listed in
proj2/demo_menu.py), four orders, a review and two analytics snapshots. Used by
`flask seed` and by Cypress (scripts/cypress_seed.py). Seeding always recreates the
database from the migrations.

Accounts (customers testuser@example.com, seconduser@example.com; one owner per
restaurant, e.g. owner@tasteofitaly.com, owner@greengarden.com) all get one password: Cypress uses the
default, password123, which its fixtures expect; `flask seed` passes
config.seed_password(), so a seeded development database has no guessable login.
"""

import json
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from proj2 import demo_menu
from proj2.db_cli import init_database
from proj2.menu_tags_io import TAG_COLUMNS, canonical_cell, contradictions
from proj2.meal_tags import tag_clashes

CYPRESS_PASSWORD = "password123"


def seed_database(path, password=CYPRESS_PASSWORD):
    """Delete ``path`` if it exists, recreate the schema, and insert the demo data."""
    init_database(path, force=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            _insert_demo_data(conn.cursor(), password)
    finally:
        conn.close()


class SeedDataError(ValueError):
    """An item in proj2/demo_menu.py has an invalid or contradictory tag."""


_RESTAURANT_COLUMNS = (
    "name", "description", "phone", "email", "address", "city", "state", "zip", "hours", "status"
)
_ITEM_COLUMNS = ("rtr_id", "name", "description", "price", "calories", "allergens")


def menu_item_row(item: dict) -> dict:
    """
    Checks one demo menu item and returns it with every tag in canonical form

    Args:
        item (dict): An entry of demo_menu.MENU_ITEMS

    Returns:
        dict: The item's columns, ready to insert (instock 1, restock "")

    Raises:
        SeedDataError: if a tag is missing, unknown, or contradicts the item's diets,
            allergens or other tags
    """
    row = {column: item[column] for column in _ITEM_COLUMNS}
    problems = []
    for column in TAG_COLUMNS:
        if column not in item:
            problems.append(f"no {column}")
            continue
        value, cell_problems = canonical_cell(column, item[column])
        problems += cell_problems
        row[column] = None if value == "" else value
    if not problems:
        problems += contradictions(
            row["diet_tags"], row["allergens"], row["protein"], row["contains"]
        )
        problems += tag_clashes(row)
    if problems:
        raise SeedDataError(f"{item['name']}: {'; '.join(problems)}")
    row.update(instock=1, restock="")
    return row


def _insert_menu(cursor, pw_hash):
    """Insert demo_menu's restaurants (one owner login each) and its tagged menu items."""
    cursor.executemany(
        f"""
        INSERT INTO "Restaurant" ({", ".join(_RESTAURANT_COLUMNS)}, password_HS)
        VALUES ({", ".join("?" * (len(_RESTAURANT_COLUMNS) + 1))})
        """,
        [
            [restaurant[column] for column in _RESTAURANT_COLUMNS] + [pw_hash]
            for restaurant in demo_menu.RESTAURANTS
        ],
    )
    rows = [menu_item_row(item) for item in demo_menu.MENU_ITEMS]
    columns = list(rows[0])
    cursor.executemany(
        f'INSERT INTO "MenuItem" ({", ".join(columns)}) VALUES ({", ".join("?" * len(columns))})',
        [[row[column] for column in columns] for row in rows],
    )


def _insert_demo_data(cursor, password):
    pw_hash = generate_password_hash(password)

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

    # 2-3. Restaurants and menu items (proj2/demo_menu.py)
    _insert_menu(cursor, pw_hash)

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
