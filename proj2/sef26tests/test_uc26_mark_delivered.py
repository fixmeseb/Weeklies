"""UC26: Mark Order Delivered — tests.

Verified against Flask_app.py:1139-1174. POST /restaurant/orders/<id>/deliver.
Rules mirror UC25 but require status='Ready'.
"""
import pytest
from proj2.sef26tests.conftest import make_order


def _login_owner(client, seed_restaurant):
    client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    })


def test_delivered_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC26 main: Ready → Delivered."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ready")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/deliver", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Delivered"


def test_delivered_not_found(client, seed_restaurant):
    """UC26 ext 2a: missing order → 403."""
    _login_owner(client, seed_restaurant)
    resp = client.post("/restaurant/orders/999999/deliver")
    assert resp.status_code == 403


def test_delivered_wrong_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC26 ext 2b: another restaurant's order → 403."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("R6","r6-uc26@x.com",?,"open")',
            (generate_password_hash("pw"),))
        other_rid = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="r6-uc26@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], other_rid, status="Ready")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/deliver")
    assert resp.status_code == 403


def test_delivered_not_ready(client, seed_user, seed_restaurant, temp_db_path):
    """UC26 ext 3a: Ordered (not Ready) → 400."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/deliver")
    assert resp.status_code == 400


def test_delivered_analytics_fail(client, seed_user, seed_restaurant, temp_db_path, monkeypatch):
    """UC26 ext 5a: analytics failure → status still changes."""
    from proj2 import Flask_app
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")), raising=True)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ready")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/deliver", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Delivered"
