"""UC23: Reject Order — tests.

Verified against Flask_app.py:1031-1064. POST /restaurant/orders/<id>/reject.
- Missing/wrong restaurant: abort(403) (both cases hit the same branch)
- Status not in {Ordered, Accepted, Preparing}: 400
- Success: 302 redirect (HTML) → /restaurant/orders
"""
import pytest
from proj2.sef26tests.conftest import make_order


def _login_owner(client, seed_restaurant):
    client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    })


def test_reject_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC23 main: Ordered → Cancelled."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/reject", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Cancelled"


def test_reject_not_found(client, seed_restaurant):
    """UC23 ext 2a: missing order → 403 (same branch as wrong restaurant, see Flask_app.py:1045)."""
    _login_owner(client, seed_restaurant)
    resp = client.post("/restaurant/orders/999999/reject")
    assert resp.status_code == 403


def test_reject_wrong_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC23 ext 2b: order belongs to another restaurant → 403."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("R3","r3-uc23@x.com",?,"open")',
            (generate_password_hash("pw"),))
        other_rid = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="r3-uc23@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], other_rid, status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/reject")
    assert resp.status_code == 403


def test_reject_disallowed_state(client, seed_user, seed_restaurant, temp_db_path):
    """UC23 ext 3a: Delivered order cannot be cancelled → 400."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/reject")
    assert resp.status_code == 400


def test_reject_analytics_fail(client, seed_user, seed_restaurant, temp_db_path, monkeypatch):
    """UC23 ext 5a: analytics failure → order still Cancelled."""
    from proj2 import Flask_app
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")), raising=True)
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login_owner(client, seed_restaurant)
    resp = client.post(f"/restaurant/orders/{ord_id}/reject", follow_redirects=False)
    assert resp.status_code == 302
    from proj2.sqlQueries import create_connection, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Cancelled"
