import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import tempfile
import contextlib
import pytest
import sqlite3

# Import your app module
import proj2.Flask_app as Flask_app
from proj2.db_cli import apply_migrations

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


@pytest.fixture(scope="session")
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    with contextlib.suppress(OSError):
        os.remove(path)


@pytest.fixture(scope="session", autouse=True)
def app(temp_db_path):

    Flask_app.app.config["DATABASE"] = temp_db_path
    Flask_app.app.config["SECRET_KEY"] = "test-secret"
    Flask_app.app.config["TESTING"] = True

    # Same schema as production: built from proj2/migrations.
    conn = sqlite3.connect(temp_db_path)
    try:
        apply_migrations(conn)
    finally:
        conn.close()

    return Flask_app.app


@pytest.fixture(autouse=True)
def app_context(app):
    """
    Each test runs inside an app context, so helpers that use get_db() (for example
    record_analytics_snapshot) can be called directly. The connection is opened on
    first use, so it follows any app.config["DATABASE"] a fixture sets, and is closed
    when the test ends.
    """
    with app.app_context():
        yield


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

        # One order per lifecycle status, each with one item, spread over six days.
        import json

        statuses = ["Ordered", "Accepted", "Preparing", "Ready", "Delivered", "Cancelled"]
        for idx, status in enumerate(statuses):
            total = 15.00 + idx  # $15.00, $16.00, ...
            details = {
                "placed_at": (datetime.now() - timedelta(days=idx)).isoformat(),
                "items": [
                    {
                        "itm_id": item_ids[idx % len(item_ids)],
                        "name": "Item",
                        "qty": 1,
                        "unit_price": total,
                        "line_total": total,
                    }
                ],
                "charges": {"subtotal": total, "total": total},
            }
            execute_query(
                conn,
                'INSERT INTO "Order"(rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
                (rtr_id, usr_id, json.dumps(details), status),
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
