"""UC24: Start Order Preparation — tests.

Verified against Flask_app.py:1067-1100. POST /restaurant/orders/<id>/prepare.
- Missing/wrong restaurant → 403 (Flask_app.py:1081)
- Status not 'Accepted' → 400
- Success → 302 redirect
"""
import pytest
from proj2.sef26tests.conftest import make_order


def _login_owner(client, seed_restaurant):
    client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    })


def test_prepare_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC24 main: Accepted → Preparing."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Accepted")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/prepare", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Preparing"


def test_prepare_not_found(client, seed_restaurant):
    """UC24 ext 2a: missing order → 403."""
    _login_owner(client, seed_restaurant)
    resp = client.post("/restaurant/orders/999999/prepare")
    assert resp.status_code == 403


def test_prepare_wrong_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC24 ext 2b: order belongs to another restaurant → 403."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("R4","r4-uc24@x.com",?,"open")',
            (generate_password_hash("pw"),))
        other_rid = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="r4-uc24@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], other_rid, status="Accepted")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/prepare")
    assert resp.status_code == 403


def test_prepare_not_accepted(client, seed_user, seed_restaurant, temp_db_path):
    """UC24 ext 3a: Order in Ordered (not Accepted) → 400."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/prepare")
    assert resp.status_code == 400


def test_prepare_analytics_fail(client, seed_user, seed_restaurant, temp_db_path, monkeypatch):
    """UC24 ext 5a: analytics failure → status still changes."""
    from proj2 import Flask_app
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")), raising=True)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Accepted")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/prepare", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Preparing"
