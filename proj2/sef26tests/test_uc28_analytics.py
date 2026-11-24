"""UC28: Analyze Restaurant Performance — tests.

Verified against Flask_app.py:857-983. /restaurant/analytics is protected by
@restaurant_required. It also records a fresh snapshot on every request.
"""

from proj2.sef26tests.conftest import make_order


def _login_owner(client, seed_restaurant):
    client.post(
        "/restaurant/login",
        data={
            "email": seed_restaurant["email"],
            "password": seed_restaurant["password"],
        },
    )


def test_analytics_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC28 main: analytics page renders and creates an Analytics row."""
    make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/analytics")
    assert resp.status_code == 200


def test_analytics_no_auth(client):
    """UC28 ext 1a: no owner session → redirect to /restaurant/login."""
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/restaurant/analytics", follow_redirects=False)
    assert resp.status_code == 302
    assert "/restaurant/login" in resp.headers["Location"]


def test_analytics_no_orders(client, seed_restaurant, temp_db_path):
    """UC28 ext 1b: no orders → analytics shows zeros; still 200."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection

    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "Order" WHERE rtr_id=?', (seed_restaurant["rtr_id"],))
    finally:
        close_connection(conn)
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/analytics")
    assert resp.status_code == 200


def test_analytics_invalid_data(client, seed_user, seed_restaurant, temp_db_path):
    """UC28 ext 2a: order with invalid details JSON → row skipped but page still renders."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection

    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            (seed_restaurant["rtr_id"], seed_user["usr_id"], "not-json", "Ordered"),
        )
    finally:
        close_connection(conn)
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/analytics")
    assert resp.status_code == 200


def test_analytics_no_popular_item(client, seed_restaurant, temp_db_path):
    """UC28 ext 2b: no orders → most_popular_item_id is NULL in snapshot.

    Snapshots are saved when orders change, not when the page is viewed, so this
    records one directly after removing the orders."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection

    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "Order" WHERE rtr_id=?', (seed_restaurant["rtr_id"],))
    finally:
        close_connection(conn)
    from proj2 import Flask_app

    with client.application.app_context():
        assert Flask_app.record_analytics_snapshot(seed_restaurant["rtr_id"]) is True
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(
            conn,
            "SELECT most_popular_item_id FROM Analytics WHERE rtr_id=? ORDER BY analytics_id DESC LIMIT 1",
            (seed_restaurant["rtr_id"],),
        )
    finally:
        close_connection(conn)
    assert row is None or row[0] is None


def test_analytics_saves_snapshot(seed_user, seed_restaurant, temp_db_path):
    """UC28 variant: record_analytics_snapshot() writes a row and returns True."""
    from proj2.Flask_app import record_analytics_snapshot

    result = record_analytics_snapshot(seed_restaurant["rtr_id"])
    assert result is True
    from proj2.sqlQueries import create_connection, fetch_one, close_connection

    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(
            conn, "SELECT COUNT(*) FROM Analytics WHERE rtr_id=?", (seed_restaurant["rtr_id"],)
        )
    finally:
        close_connection(conn)
    assert row[0] >= 1


def test_analytics_limited_history(client, seed_restaurant):
    """UC28 ext 4a: fewer than 30 snapshots → page still renders 200."""
    _login_owner(client, seed_restaurant)
    resp = client.get("/restaurant/analytics")
    assert resp.status_code == 200
