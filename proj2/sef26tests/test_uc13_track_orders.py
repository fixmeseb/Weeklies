"""UC13: Track Order History — tests.

The order history is shown on /orders, My Orders (user_orders in Flask_app.py), which
queries the user's orders sorted newest-first with review-status flags.
"""

import re

import pytest
from proj2.sef26tests.conftest import make_order


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def test_track_orders_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC13 main: /orders lists the user's orders."""
    make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"])
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_none(client, seed_user, temp_db_path):
    """UC13 ext 1a: user with no orders still gets /orders 200."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection

    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "Order" WHERE usr_id=?', (seed_user["usr_id"],))
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_invalid_details(client, seed_user, seed_restaurant, temp_db_path):
    """UC13 ext 2a: order with invalid JSON details still renders (parser catches errors)."""
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
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_missing_restaurant(client, seed_user, temp_db_path):
    """UC13 ext 4a: order references restaurant that no longer exists.

    Current query INNER JOINs Restaurant, so an orphan order will not appear —
    /orders still renders 200 (documents behavior)."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection

    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            (999999, seed_user["usr_id"], "{}", "Ordered"),
        )
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_can_review(client, seed_user, seed_restaurant, temp_db_path):
    """UC13 ext 5a: delivered order with no review is flagged has_review=False."""
    make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_review_exists(client, seed_user, seed_restaurant, temp_db_path):
    """UC13 ext 5b: delivered order with review present is flagged has_review=True."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection

    ord_id = make_order(
        temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered"
    )
    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            'INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,ord_id,created_at) '
            "VALUES (?,?,?,?,?,?,?)",
            (
                seed_restaurant["rtr_id"],
                seed_user["usr_id"],
                "t",
                5,
                "d",
                ord_id,
                "2025-01-01T00:00",
            ),
        )
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_track_orders_filter_status(client, seed_user, seed_restaurant, temp_db_path):
    """UC13 variant: /orders currently returns all statuses (no server-side filter),
    but response is still 200. Documents current behavior."""
    make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Delivered")
    make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Cancelled")
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200


# ---- UC13 extension: progress stepper rendering on /profile ----
# The temp DB is session-scoped, so other tests' orders are on the page too;
# each test isolates its own order's block by data-order-id.


LIFECYCLE = ["Ordered", "Accepted", "Preparing", "Ready", "Delivered"]


def _progress_block(html, ord_id):
    """Return (data-status, inner HTML) for one order's progress block."""
    m = re.search(
        r'<div class="order-progress" data-order-id="%d" data-status="([^"]*)">(.*?)</div>'
        % ord_id,
        html,
        re.S,
    )
    assert m, f"no progress block for order {ord_id}"
    return m.group(1), m.group(2)


def _render(client, seed_user, temp_db_path, seed_restaurant, status):
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status=status)
    _login(client, seed_user)
    resp = client.get("/orders")
    assert resp.status_code == 200
    return _progress_block(resp.get_data(as_text=True), ord_id)


@pytest.mark.parametrize("index,status", list(enumerate(LIFECYCLE)))
def test_progress_badge_per_status(client, seed_user, seed_restaurant, temp_db_path, index, status):
    """Each lifecycle status renders its own styled badge (Accepted/Ready were unstyled before)."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, status)
    assert key == status.lower()
    assert f'<span class="status-bubble status-{key}">{status}</span>' in block


@pytest.mark.parametrize("index,status", list(enumerate(LIFECYCLE)))
def test_progress_current_step(client, seed_user, seed_restaurant, temp_db_path, index, status):
    """Exactly one step is current, and it is the order's stage."""
    _, block = _render(client, seed_user, temp_db_path, seed_restaurant, status)
    current = re.findall(r'data-step="(\w+)" data-state="current" aria-current="step"', block)
    assert current == [status.lower()]


@pytest.mark.parametrize("index,status", list(enumerate(LIFECYCLE)))
def test_progress_done_and_upcoming(
    client, seed_user, seed_restaurant, temp_db_path, index, status
):
    """Stages before the current one are done, stages after it are upcoming."""
    _, block = _render(client, seed_user, temp_db_path, seed_restaurant, status)
    states = re.findall(r'data-state="(\w+)"', block)
    assert states == ["done"] * index + ["current"] + ["upcoming"] * (len(LIFECYCLE) - index - 1)


def test_progress_cancelled(client, seed_user, seed_restaurant, temp_db_path):
    """Cancelled: red badge, greyed stepper, no stage claimed as reached."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, "Cancelled")
    assert key == "cancelled"
    assert '<span class="status-bubble status-cancelled">Cancelled</span>' in block
    assert 'class="stepper stepper-cancelled"' in block
    assert set(re.findall(r'data-state="(\w+)"', block)) == {"cancelled"}
    assert "aria-current" not in block


def test_progress_all_six_statuses_distinct(client, seed_user, seed_restaurant, temp_db_path):
    """All six real statuses on one page get six different badge classes."""
    statuses = LIFECYCLE + ["Cancelled"]
    ids = [
        make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status=s)
        for s in statuses
    ]
    _login(client, seed_user)
    html = client.get("/orders").get_data(as_text=True)
    classes = set()
    for ord_id in ids:
        _, block = _progress_block(html, ord_id)
        classes.update(re.findall(r"status-bubble (status-\w+)", block))
    assert classes == {f"status-{s.lower()}" for s in statuses}


@pytest.mark.parametrize(
    "key", ["ordered", "accepted", "preparing", "ready", "delivered", "cancelled", "unknown"]
)
def test_progress_badge_has_css(client, seed_user, key):
    """Every status class the template can emit has a colour defined (statuses are
    coloured words, so the colour is the text colour)."""
    _login(client, seed_user)
    html = client.get("/orders").get_data(as_text=True)
    assert re.search(r"\.status-%s\s*\{[^}]*(?<![-\w])color\s*:\s*var\(--" % key, html)


def test_progress_lowercase_status_from_db(client, seed_user, seed_restaurant, temp_db_path):
    """A hand-edited lowercase value still maps to the right stage."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, "ready")
    assert key == "ready"
    assert ">Ready</span>" in block


# ---- Failure cases: bad status values must not 500 the page ----


def test_progress_unknown_status(client, seed_user, seed_restaurant, temp_db_path):
    """A status outside the lifecycle shows a grey badge with the raw value and no stepper."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, "Shipped")
    assert key == "unknown"
    assert '<span class="status-bubble status-unknown">Shipped</span>' in block
    assert "stepper" not in block


@pytest.mark.parametrize("status", [None, "", "   "])
def test_progress_missing_status(client, seed_user, seed_restaurant, temp_db_path, status):
    """NULL/blank status renders an 'Unknown' badge instead of crashing."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, status)
    assert key == "unknown"
    assert '<span class="status-bubble status-unknown">Unknown</span>' in block
    assert "stepper" not in block


def test_progress_status_markup_is_escaped(client, seed_user, seed_restaurant, temp_db_path):
    """A status containing HTML is shown as text, not injected into the page."""
    key, block = _render(
        client, seed_user, temp_db_path, seed_restaurant, "<script>alert(1)</script>"
    )
    assert key == "unknown"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in block
    assert "<script>" not in block


def test_progress_numeric_status(client, seed_user, seed_restaurant, temp_db_path):
    """SQLite is loosely typed: an integer in the status column still renders."""
    key, block = _render(client, seed_user, temp_db_path, seed_restaurant, 3)
    assert key == "unknown"
    assert ">3</span>" in block
