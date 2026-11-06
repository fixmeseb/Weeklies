"""UC22: Accept Order — tests.

Verified against Flask_app.py:989-1028. POST /restaurant/orders/<id>/accept
requires owner session for the order's restaurant. Rules:
- Missing order: abort(404)
- Different restaurant: abort(403)
- Not in "Ordered" status: 400 JSON
- Success (HTML): 302 redirect to /restaurant/orders
- Success (XHR): 200 JSON {"ok": true, "new_status": "Accepted"}
"""
import pytest
from proj2.sef26tests.conftest import make_order


def _login_owner(client, seed_restaurant):
    client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    })


def test_accept_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC22 main: Ordered → Accepted; redirect to /restaurant/orders."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/accept", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Accepted"


def test_accept_not_found(client, seed_restaurant):
    """UC22 ext 2a: missing order → 404."""
    _login_owner(client, seed_restaurant)
    resp = client.post("/restaurant/orders/999999/accept")
    assert resp.status_code == 404


def test_accept_wrong_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC22 ext 2b: order belongs to another restaurant → 403."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("R2","r2-uc22@x.com",?,"open")',
            (generate_password_hash("pw"),))
        other_rid = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="r2-uc22@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], other_rid, status="Ordered")
    _login_owner(client, seed_restaurant)  # logged in as OUR restaurant, not other_rid
    resp = client.post(f"/restaurant/orders/{ord_id}/accept")
    assert resp.status_code == 403


def test_accept_not_pending(client, seed_user, seed_restaurant, temp_db_path):
    """UC22 ext 3a: order not in 'Ordered' status → 400."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/accept")
    assert resp.status_code == 400


def test_accept_analytics_fail(client, seed_user, seed_restaurant, temp_db_path, monkeypatch):
    """UC22 ext 5a: analytics update failure → order still Accepted."""
    from proj2 import Flask_app
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")), raising=True)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/accept", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Accepted"
