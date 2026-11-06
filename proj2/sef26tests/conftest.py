"""Shared fixtures for sef26tests — CSC510 Project 1a tests for Weeklies.

Uses a temp SQLite DB seeded with a known user (customer) and restaurant (owner),
and provides helpers to log in as customer or owner via Flask's test client.
"""
import os
import sys
import tempfile
import contextlib
import sqlite3
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import proj2.Flask_app as Flask_app
from proj2.db_cli import apply_migrations
from proj2.sqlQueries import create_connection, close_connection, execute_query, fetch_one
from werkzeug.security import generate_password_hash


@pytest.fixture(scope="session")
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    with contextlib.suppress(OSError):
        os.remove(path)


@pytest.fixture(scope="session")
def app(temp_db_path):
    Flask_app.app.config["DATABASE"] = temp_db_path
    Flask_app.app.config["SECRET_KEY"] = "sef26-test-secret"
    Flask_app.app.config["TESTING"] = True

    conn = sqlite3.connect(temp_db_path)
    try:
        apply_migrations(conn)  # same schema as production (proj2/migrations)
    finally:
        conn.close()
    return Flask_app.app


@pytest.fixture(autouse=True)
def app_context(app):
    """Run each test in an app context so helpers using get_db() can be called directly."""
    with app.app_context():
        yield


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


# ---- Seeded actors ----

USER_EMAIL = "sef26user@test.com"
USER_PASSWORD = "secret123"
REST_EMAIL = "sef26rest@test.com"
REST_PASSWORD = "restpass1"


@pytest.fixture()
def seed_user(temp_db_path):
    """Ensure our known customer exists with a known password."""
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email=?', (USER_EMAIL,))
        pw_hash = generate_password_hash(USER_PASSWORD)
        if row is None:
            execute_query(
                conn,
                'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies,generated_menu) '
                'VALUES ("SEF","User",?,"5551234567",?,0,"","","")',
                (USER_EMAIL, pw_hash),
            )
            row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email=?', (USER_EMAIL,))
        else:
            # Reset password so tests are deterministic
            execute_query(conn, 'UPDATE "User" SET password_HS=? WHERE email=?', (pw_hash, USER_EMAIL))
    finally:
        close_connection(conn)
    return {"email": USER_EMAIL, "usr_id": row[0], "password": USER_PASSWORD}


@pytest.fixture()
def seed_restaurant(temp_db_path):
    """Ensure our known restaurant exists with email/password for owner login and two menu items."""
    conn = create_connection(temp_db_path)
    try:
        pw_hash = generate_password_hash(REST_PASSWORD)
        row = fetch_one(conn, "SELECT rtr_id FROM Restaurant WHERE email=?", (REST_EMAIL,))
        if row is None:
            execute_query(
                conn,
                'INSERT INTO "Restaurant"(name,description,phone,email,password_HS,address,city,state,zip,hours,status) '
                'VALUES ("SEF Cafe","Test cafe","5559998888",?,?,"1 Main","Raleigh","NC","27606","9-21","open")',
                (REST_EMAIL, pw_hash),
            )
            row = fetch_one(conn, "SELECT rtr_id FROM Restaurant WHERE email=?", (REST_EMAIL,))
        else:
            execute_query(conn, "UPDATE Restaurant SET password_HS=?, status='open' WHERE email=?", (pw_hash, REST_EMAIL))
        rtr_id = row[0]

        cnt = fetch_one(conn, 'SELECT COUNT(*) FROM "MenuItem" WHERE rtr_id=?', (rtr_id,))
        if not cnt or cnt[0] < 2:
            execute_query(
                conn,
                'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
                'VALUES (?,"Pasta","Yum",1299,600,1,"wheat")',
                (rtr_id,),
            )
            execute_query(
                conn,
                'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
                'VALUES (?,"Salad","Fresh",899,250,1,"nuts")',
                (rtr_id,),
            )
        items = fetch_one(conn, 'SELECT itm_id FROM "MenuItem" WHERE rtr_id=? ORDER BY itm_id LIMIT 1', (rtr_id,))
    finally:
        close_connection(conn)
    return {
        "rtr_id": rtr_id,
        "email": REST_EMAIL,
        "password": REST_PASSWORD,
        "first_item_id": items[0] if items else None,
    }


# ---- Login helpers ----

def login_as_user(client, seed_user):
    """POST to /login to establish a customer session with all required keys."""
    return client.post("/login", data={
        "email": seed_user["email"], "password": seed_user["password"],
    }, follow_redirects=False)


def login_as_owner(client, seed_restaurant):
    """POST to /restaurant/login to establish an owner session."""
    return client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    }, follow_redirects=False)


# ---- Order factory ----

def make_order(temp_db_path, usr_id, rtr_id, status="Ordered", details=None):
    """Insert an order directly into the DB and return its ord_id."""
    import json as _json
    if details is None:
        details = {
            "placed_at": "2025-11-05T13:45:00",
            "restaurant_id": rtr_id,
            "items": [{"itm_id": 1, "name": "Pasta", "qty": 1, "unit_price": 12.99, "line_total": 12.99}],
            "charges": {"subtotal": 12.99, "tax": 0.94, "delivery_fee": 3.99, "service_fee": 1.49, "tip": 0.0, "total": 19.41},
            "delivery_type": "delivery",
            "eta_minutes": 40,
            "date": "2025-11-05",
            "meal": 3,
        }
    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            (rtr_id, usr_id, _json.dumps(details), status),
        )
        row = fetch_one(conn, "SELECT last_insert_rowid()")
    finally:
        close_connection(conn)
    return row[0] if row else None
