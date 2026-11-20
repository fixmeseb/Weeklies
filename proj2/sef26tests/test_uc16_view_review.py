"""UC16: View Submitted Review — tests.

One page per order, /order/<int:ord_id>/review (the old /review/view redirects there)
requires login, and the review must belong to the current user.
Missing/foreign review → redirect to /orders (My Orders).
"""
import pytest
from proj2.sef26tests.conftest import make_order
from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def _insert_review(temp_db_path, usr_id, rtr_id, ord_id, rating=5):
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,ord_id,created_at) '
            'VALUES (?,?,?,?,?,?,?)',
            (rtr_id, usr_id, "t", rating, "d", ord_id, "2025-01-01T00:00"))
    finally:
        close_connection(conn)


def test_view_review_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC16 main: owned review renders 200."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _insert_review(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], ord_id)
    _login(client, seed_user)
    resp = client.get(f"/order/{ord_id}/review")
    assert resp.status_code == 200
    assert b"Your Review" in resp.data


def test_view_review_not_found(client, seed_user):
    """UC16 ext 1a: no review for order → redirect to /profile."""
    _login(client, seed_user)
    resp = client.get("/order/999999/review", follow_redirects=False)
    assert resp.status_code == 302
    assert "/orders" in resp.headers["Location"]


def test_view_review_unauthorized(client, seed_user, seed_restaurant, temp_db_path):
    """UC16 ext 1b: review belongs to another user → redirect to /profile (not disclosed)."""
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "User"(first_name,last_name,email,phone,password_HS) '
            'VALUES ("Foreign","U","foreign-uc16@x.com","5550001111",?)',
            (generate_password_hash("x"),))
        other = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email="foreign-uc16@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, other, seed_restaurant["rtr_id"], status="Delivered")
    _insert_review(temp_db_path, other, seed_restaurant["rtr_id"], ord_id)
    _login(client, seed_user)
    resp = client.get(f"/order/{ord_id}/review", follow_redirects=False)
    assert resp.status_code == 302
    assert "/orders" in resp.headers["Location"]


def test_old_view_address_redirects_to_the_review_page(client, seed_user):
    """The separate /review/view page was merged into /order/<id>/review."""
    _login(client, seed_user)
    resp = client.get("/order/7/review/view", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/order/7/review")
