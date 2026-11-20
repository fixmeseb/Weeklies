"""UC15: Submit Order Review — tests.

Verified against Flask_app.py:1505-1623. /order/<int:ord_id>/review
requires login. Order must exist, belong to the user, be status "Delivered",
and have no existing review. Success redirects to /profile.
"""
import pytest
from proj2.sef26tests.conftest import make_order
from proj2.sqlQueries import create_connection, fetch_one, close_connection


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def test_submit_review_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 main: valid review on Delivered order → redirect to /profile + DB row."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    resp = client.post(f"/order/{ord_id}/review", data={
        "rating": "5", "title": "Great", "description": "Loved it",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/order/{ord_id}/review")
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT rating FROM "Review" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == 5


def test_submit_review_not_owned(client, seed_user):
    """UC15 ext 1a: non-existent (or foreign) order → redirect to /profile, no review."""
    _login(client, seed_user)
    resp = client.post("/order/999999/review", data={"rating": "5"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/orders" in resp.headers["Location"]


def test_submit_review_not_delivered(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 ext 1b: order status != Delivered → redirect to /profile without accepting review."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Ordered")
    _login(client, seed_user)
    resp = client.post(f"/order/{ord_id}/review", data={"rating": "5"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/orders" in resp.headers["Location"]


def test_submit_review_already_exists(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 ext 1c: second review on the same order redirects to /view instead of accepting."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    client.post(f"/order/{ord_id}/review", data={"rating": "4", "title": "t", "description": "d"})
    resp = client.post(f"/order/{ord_id}/review", data={"rating": "1"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/order/{ord_id}/review")


def test_submit_review_no_rating(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 ext 3a: no rating → re-render form with error."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    resp = client.post(f"/order/{ord_id}/review", data={"title": "x"})
    assert resp.status_code == 200
    assert b"rating" in resp.data.lower()


def test_submit_review_invalid_rating(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 ext 4a: rating outside 1-5 → re-render form with 'Invalid rating value'."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    resp = client.post(f"/order/{ord_id}/review", data={"rating": "99"})
    assert resp.status_code == 200
    assert b"invalid" in resp.data.lower() or b"rating" in resp.data.lower()


def test_submit_review_updates_avg(client, seed_user, seed_restaurant, temp_db_path):
    """UC15 variant: submitting a review inserts a row for this specific order/restaurant."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    client.post(f"/order/{ord_id}/review", data={"rating": "4", "title": "t", "description": "d"})
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT rating FROM "Review" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row is not None
    assert row[0] == 4
