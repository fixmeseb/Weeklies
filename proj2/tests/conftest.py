import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import tempfile
import contextlib
import pytest
import sqlite3
import platform

# Import your app module
import proj2.Flask_app as Flask_app

# Import your DB helpers
from proj2.sqlQueries import (
    create_connection,
    close_connection,
    execute_query,
    fetch_one,
    fetch_all,
)

from typing import Any, Optional, Sequence


def expect_one(row: Optional[Sequence[Any]], err: str) -> Any:
    """Assert there is exactly one row and return first column; helpful for type checkers."""
    if row is None:
        raise AssertionError(err)
    return row[0]


# ---- SCHEMA (from your __main__ docstring) ----
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
  instock INTEGER, restock TEXT, allergens TEXT, diet_tags TEXT
);

CREATE TABLE IF NOT EXISTS "Order" (
  ord_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, usr_id INTEGER, details TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS "OrderItems" (
  oi_id INTEGER PRIMARY KEY AUTOINCREMENT,
  o_id INTEGER, itm_id INTEGER, quantity INTEGER, unit_price_cents INTEGER
);

CREATE TABLE IF NOT EXISTS "Review" (
  rev_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id INTEGER, usr_id INTEGER, title TEXT, rating INTEGER, description TEXT,
  ord_id INTEGER, created_at TEXT
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


@pytest.fixture(scope="session")
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    with contextlib.suppress(OSError):
        os.remove(path)


@pytest.fixture(scope="session", autouse=True)
def app(temp_db_path):

    Flask_app.db_file = temp_db_path
    Flask_app.app.config["SECRET_KEY"] = "test-secret"
    Flask_app.app.config["TESTING"] = True

    # Build schema (supports multiple statements)
    conn = create_connection(temp_db_path)
    if conn is None:  # <-- guard for type checker + safety
        conn = sqlite3.connect(temp_db_path)
    try:
        conn.executescript(SCHEMA_SQL)  # <-- executes all CREATE TABLEs
        conn.commit()
    finally:
        close_connection(conn)

    return Flask_app.app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


# ---------- Seeding helpers ----------


def _hash_pw(raw="password"):
    # re-use werkzeug imported inside Flask_app
    from werkzeug.security import generate_password_hash

    return generate_password_hash(raw)


@pytest.fixture()
def seed_minimal_data(temp_db_path):
    """Create one restaurant, two items in stock, and one user. Idempotent across tests."""
    conn = create_connection(temp_db_path)
    try:
        # --- Restaurant (insert if none exists) ---
        rtr_row = fetch_one(conn, "SELECT rtr_id FROM Restaurant LIMIT 1")
        if rtr_row is None:
            execute_query(
                conn,
                """
              INSERT INTO "Restaurant"(name,address,city,state,zip,status)
              VALUES ("Cafe One","123 Main","Raleigh","NC","27606","open")
            """,
            )
            rtr_row = fetch_one(conn, "SELECT rtr_id FROM Restaurant LIMIT 1")
        rtr_id = expect_one(rtr_row, "Expected at least one Restaurant row after seeding")

        # --- Menu items (ensure two exist for that restaurant) ---
        count_row = fetch_one(conn, 'SELECT COUNT(*) FROM "MenuItem" WHERE rtr_id=?', (rtr_id,))
        count = (count_row[0] if count_row else 0) or 0
        if count < 2:
            # Insert only the missing ones
            execute_query(
                conn,
                """
              INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens)
              VALUES (?, "Pasta", "Delicious", 1299, 600, 1, "wheat")
            """,
                (rtr_id,),
            )
            execute_query(
                conn,
                """
              INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens)
              VALUES (?, "Salad", "Fresh", 899, 250, 1, "nuts")
            """,
                (rtr_id,),
            )

        # --- User (upsert: create if missing; else ensure known password) ---
        email = "test@x.com"
        usr_row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email=?', (email,))
        if usr_row is None:
            execute_query(
                conn,
                """
              INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies,generated_menu)
              VALUES ("Test","User",?, "5551234", ?, 0, "", "", "[2025-11-02,1,3]")
            """,
                (email, _hash_pw("secret123")),
            )
            usr_row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email=?', (email,))
        else:
            # make sure password matches what tests use
            execute_query(
                conn,
                'UPDATE "User" SET password_HS=? WHERE email=?',
                (_hash_pw("secret123"), email),
            )

        usr_id = expect_one(usr_row, "Expected seeded user 'test@x.com'")

    finally:
        close_connection(conn)

    return {"usr_email": "test@x.com", "usr_id": usr_id, "rtr_id": rtr_id}


@pytest.fixture()
def login_session(client, seed_minimal_data):
    """Log in the seeded user by simulating POST /login."""
    resp = client.post(
        "/login", data={"email": "test@x.com", "password": "secret123"}, follow_redirects=False
    )
    assert resp.status_code in (302, 303)
    return True


@pytest.fixture()
def seed_orders_for_analytics(temp_db_path, seed_minimal_data):
    """Seed multiple orders with different statuses for analytics testing."""
    from datetime import datetime, timedelta

    conn = create_connection(temp_db_path)
    try:
        rtr_id = seed_minimal_data["rtr_id"]
        usr_id = seed_minimal_data["usr_id"]

        # Get MenuItem IDs
        items = fetch_all(conn, "SELECT itm_id FROM MenuItem WHERE rtr_id=?", (rtr_id,))
        item_ids = [row[0] for row in items] if items else []

        if len(item_ids) < 2:
            pytest.skip("Not enough menu items seeded")

        # Create Orders with different statuses
        statuses = ["pending", "confirmed", "preparing", "completed", "delivered", "cancelled"]

        for idx, status in enumerate(statuses):
            # Order table expects: rtr_id, usr_id, details, status
            order_date = datetime.now() - timedelta(days=idx)
            total_cents = 1500 + (idx * 100)  # $15.00, $16.00, etc.

            execute_query(
                conn,
                """
              INSERT INTO "Orders"(rtr_id, usr_id, order_date, total_amount_cents, status)
              VALUES (?, ?, ?, ?, ?)
            """,
                (rtr_id, usr_id, order_date.isoformat(), total_cents, status),
            )

            # Get the order ID just inserted
            o_row = fetch_one(
                conn,
                "SELECT o_id FROM Orders WHERE rtr_id=? AND status=? ORDER BY o_id DESC LIMIT 1",
                (rtr_id, status),
            )

            if o_row:
                ord_id = o_row[0]
                # Add order items
                execute_query(
                    conn,
                    """
                  INSERT INTO "OrderItems"(o_id, itm_id, quantity, unit_price_cents)
                  VALUES (?, ?, 1, ?)
                """,
                    (ord_id, item_ids[idx % len(item_ids)], total_cents),
                )
    finally:
        close_connection(conn)

    return seed_minimal_data


@pytest.fixture(autouse=True)
def monkeypatch_pdf(monkeypatch):
    """Avoid calling real PDF generator; return dummy bytes."""

    def fake_pdf(db_path, ord_id):
        return b"%PDF-1.4\n%fake\n"

    monkeypatch.setattr("proj2.Flask_app.generate_order_receipt_pdf", fake_pdf, raising=True)


def pytest_collection_modifyitems(config, items):
    """Skip LLM generator tests on Windows due to transformers library access violation issues.

    Note: test_llm.py and test_helpers.py do not require model generation and should pass.
    The issue is in the transformers library when running model.generate() on Windows CPU.
    This is a known limitation and may be resolved in future transformers releases.
    See: https://github.com/huggingface/transformers/issues/...
    """
    if platform.system() == "Windows":
        skip_llm = pytest.mark.skip(
            reason="LLM generator tests skipped on Windows due to PyTorch/transformers access violation"
        )
        for item in items:
            # Only skip tests that use the MenuGenerator (which calls model.generate())
            if "test_generator.py" in str(item.fspath):
                item.add_marker(skip_llm)

@pytest.fixture()
def login_session(client, seed_minimal_data):
    """Log in the seeded user by simulating POST /login."""
    resp = client.post(
        "/login", data={"email": "test@x.com", "password": "secret123"}, follow_redirects=False
    )
    assert resp.status_code in (302, 303)
    return True


@pytest.fixture()
def seed_orders_for_analytics(temp_db_path, seed_minimal_data):
    """Seed multiple orders with different statuses for analytics testing."""
    from datetime import datetime, timedelta

    conn = create_connection(temp_db_path)
    try:
        rtr_id = seed_minimal_data["rtr_id"]
        usr_id = seed_minimal_data["usr_id"]

        # Get MenuItem IDs
        items = fetch_all(conn, "SELECT itm_id FROM MenuItem WHERE rtr_id=?", (rtr_id,))
        item_ids = [row[0] for row in items] if items else []

        if len(item_ids) < 2:
            pytest.skip("Not enough menu items seeded")

        # Create Orders with different statuses
        statuses = ["pending", "confirmed", "preparing", "completed", "delivered", "cancelled"]

        for idx, status in enumerate(statuses):
            # Order table expects: rtr_id, usr_id, details, status
            order_date = datetime.now() - timedelta(days=idx)
            total_cents = 1500 + (idx * 100)  # $15.00, $16.00, etc.

            execute_query(
                conn,
                """
              INSERT INTO "Orders"(rtr_id, usr_id, order_date, total_amount_cents, status)
              VALUES (?, ?, ?, ?, ?)
            """,
                (rtr_id, usr_id, order_date.isoformat(), total_cents, status),
            )

            # Get the order ID just inserted
            o_row = fetch_one(
                conn,
                "SELECT o_id FROM Orders WHERE rtr_id=? AND status=? ORDER BY o_id DESC LIMIT 1",
                (rtr_id, status),
            )

            if o_row:
                ord_id = o_row[0]
                # Add order items
                execute_query(
                    conn,
                    """
                  INSERT INTO "OrderItems"(o_id, itm_id, quantity, unit_price_cents)
                  VALUES (?, ?, 1, ?)
                """,
                    (ord_id, item_ids[idx % len(item_ids)], total_cents),
                )
    finally:
        close_connection(conn)

    return seed_minimal_data


@pytest.fixture(autouse=True)
def monkeypatch_pdf(monkeypatch):
    """Avoid calling real PDF generator; return dummy bytes."""

    def fake_pdf(db_path, ord_id):
        return b"%PDF-1.4\n%fake\n"

    monkeypatch.setattr("proj2.Flask_app.generate_order_receipt_pdf", fake_pdf, raising=True)


def pytest_collection_modifyitems(config, items):
    """Skip LLM generator tests on Windows due to transformers library access violation issues.

    Note: test_llm.py and test_helpers.py do not require model generation and should pass.
    The issue is in the transformers library when running model.generate() on Windows CPU.
    This is a known limitation and may be resolved in future transformers releases.
    See: https://github.com/huggingface/transformers/issues/...
    """
    if platform.system() == "Windows":
        skip_llm = pytest.mark.skip(
            reason="LLM generator tests skipped on Windows due to PyTorch/transformers access violation"
        )
        for item in items:
            # Only skip tests that use the MenuGenerator (which calls model.generate())
            if "test_generator.py" in str(item.fspath):
                item.add_marker(skip_llm)
