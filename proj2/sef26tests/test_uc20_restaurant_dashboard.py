"""UC20: View Restaurant Dashboard — tests.

The owner's home is the Orders page, /restaurant/orders (the separate dashboard
page was merged into it). It is protected by @restaurant_required and shows the
order-status counts, with the active-order count and review summary on the
banner's tabs. /restaurant/dashboard still redirects there for old links.
"""
import pytest


def _login_owner(client, seed_restaurant):
    client.post("/restaurant/login", data={
        "email": seed_restaurant["email"], "password": seed_restaurant["password"],
    })


def test_dashboard_valid(client, seed_restaurant):
    """UC20 main: authenticated owner sees dashboard."""
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/orders")
    assert resp.status_code == 200


def test_dashboard_no_auth(client):
    """UC20 ext 1a: no session → redirect to /restaurant/login."""
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/restaurant/orders", follow_redirects=False)
    assert resp.status_code == 302
    assert "/restaurant/login" in resp.headers["Location"]


def test_dashboard_no_orders(client, seed_restaurant, temp_db_path):
    """UC20 ext 2a: dashboard renders with zero counts when no orders exist."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "Order" WHERE rtr_id=?', (seed_restaurant["rtr_id"],))
    finally:
        close_connection(conn)
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/orders")
    assert resp.status_code == 200


def test_dashboard_no_reviews(client, seed_restaurant, temp_db_path):
    """UC20 ext 3a: dashboard renders with zero review state when no reviews exist."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "Review" WHERE rtr_id=?', (seed_restaurant["rtr_id"],))
    finally:
        close_connection(conn)
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/orders")
    assert resp.status_code == 200


def test_dashboard_own_restaurant(client, seed_restaurant):
    """UC20 variant: dashboard uses session rtr_id only."""
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/orders")
    assert resp.status_code == 200
    # RestaurantName from session appears in template
    assert b"SEF Cafe" in resp.data


def test_dashboard_tabs_show_counts_and_rating(client, seed_restaurant):
    """UC20: the banner tabs carry the active-order count and the review summary."""
    _login_owner(client, seed_restaurant)
    html = client.get("/restaurant/orders").get_data(as_text=True)
    assert 'aria-label="Restaurant pages"' in html
    assert "active</span>" in html
    assert "Reviews</span>" in html  # "0 Reviews" or "4.0 · 3 Reviews"
    assert 'href="/restaurant/analytics"' in html and 'href="/restaurant/reviews"' in html


def test_old_dashboard_address_redirects_to_orders(client, seed_restaurant):
    """UC20: /restaurant/dashboard is kept for old links and forwards to the Orders page."""
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/restaurant/orders")
    client.get("/restaurant/logout")
    resp = client.get("/restaurant/dashboard", follow_redirects=False)
    assert "/restaurant/login" in resp.headers["Location"]
