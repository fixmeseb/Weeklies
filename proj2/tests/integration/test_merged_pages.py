"""The merged pages: ordering on Restaurants, order history on My Orders, the Profile
edit pop-up with the shared allergy/preference editor, Today's Menu buttons and the
restaurant owners' tabbed banner."""

import json
import uuid
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from proj2.sqlQueries import close_connection, create_connection, execute_query, fetch_one


def _db(path, sql, params=()):
    conn = create_connection(path)
    try:
        execute_query(conn, sql, params)
        return fetch_one(conn, "SELECT last_insert_rowid()")[0]
    finally:
        close_connection(conn)


def _login(client):
    resp = client.post("/login", data={"email": "test@x.com", "password": "secret123"})
    assert resp.status_code in (302, 303)


def _order(path, seed, status="Delivered"):
    details = {"placed_at": "2026-11-10T12:30:00", "charges": {"total": 14.5}, "items": []}
    return _db(
        path,
        'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
        (seed["rtr_id"], seed["usr_id"], json.dumps(details), status),
    )


# ---------------------------------------------------------------- customer nav


def test_customer_nav_has_one_ordering_tab(client, login_session):
    html = client.get("/").get_data(as_text=True)
    nav = html.split("<nav>")[1].split("</nav>")[0]
    order = [
        nav.index(f'href="{p}"') for p in ("/", "/insights", "/restaurants", "/orders", "/profile")
    ]
    assert order == sorted(order)
    assert ">My Orders</a>" in nav and ">Order</a>" not in nav


# ---------------------------------------------------------------- My Orders


def test_my_orders_lists_orders_and_links_their_review_page(
    client, seed_minimal_data, temp_db_path
):
    ord_id = _order(temp_db_path, seed_minimal_data)
    _login(client)
    html = client.get("/orders").get_data(as_text=True)
    assert "My Orders" in html
    assert 'id="restaurantSelect"' not in html  # the dropdown order builder is gone
    assert "Cafe One" in html and "$14.50" in html
    assert f'href="/order/{ord_id}/review"' in html
    assert f'href="/orders/{ord_id}/receipt.pdf"' in html


def test_my_orders_without_orders_points_to_restaurants(client, temp_db_path):
    # a fresh user: the shared test database holds other tests' orders for test@x.com
    email = f"new-{uuid.uuid4().hex[:8]}@test.com"
    _db(
        temp_db_path,
        'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies) '
        "VALUES (?,?,?,?,?,?,?,?)",
        ("New", "User", email, "5550000", generate_password_hash("secret123"), 0, "", ""),
    )
    client.post("/login", data={"email": email, "password": "secret123"})
    html = client.get("/orders").get_data(as_text=True)
    assert "No orders yet." in html and 'href="/restaurants"' in html


def test_my_orders_confirms_a_just_placed_order(client, login_session):
    assert "Order #42 placed." in client.get("/orders?ordered=42").get_data(as_text=True)
    assert "placed." not in client.get("/orders?ordered=<b>").get_data(as_text=True)


def test_profile_no_longer_lists_orders(client, seed_minimal_data, temp_db_path):
    _order(temp_db_path, seed_minimal_data)
    _login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Order Tracking" not in html and "stepper" not in html


def test_my_orders_needs_login(client):
    resp = client.get("/orders", follow_redirects=False)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


# ---------------------------------------------------------------- Restaurants is the cart page


def test_restaurants_page_takes_item_notes_and_escapes_them(client, login_session):
    html = client.get("/restaurants").get_data(as_text=True)
    assert 'class="note-input"' in html
    assert "Note: ${esc(l.notes)}" in html
    assert 'window.location.href = "/orders"' in html  # after ordering: My Orders


# ---------------------------------------------------------------- reviews


def test_review_page_shows_the_form_then_the_review(client, seed_minimal_data, temp_db_path):
    ord_id = _order(temp_db_path, seed_minimal_data)
    _login(client)
    page = client.get(f"/order/{ord_id}/review").get_data(as_text=True)
    assert "Write a Review" in page and 'id="reviewForm"' in page
    resp = client.post(
        f"/order/{ord_id}/review", data={"rating": "4", "title": "Tasty", "description": "Good"}
    )
    assert resp.headers["Location"].endswith(f"/order/{ord_id}/review")
    page = client.get(f"/order/{ord_id}/review").get_data(as_text=True)
    assert "Your Review" in page and "Tasty" in page and 'id="reviewForm"' not in page
    assert 'href="/orders"' in page  # back to My Orders


# ---------------------------------------------------------------- Today's Menu


def test_todays_menu_has_order_and_swap_buttons(client, seed_minimal_data, temp_db_path):
    today = date.today().isoformat()
    item = fetch_one_item(temp_db_path, seed_minimal_data["rtr_id"])
    _db(
        temp_db_path,
        'UPDATE "User" SET generated_menu=? WHERE usr_id=?',
        (f"[{today},{item},2]", seed_minimal_data["usr_id"]),
    )
    _login(client)
    html = client.get("/").get_data(as_text=True)
    card = html.split("Today’s Menu")[1].split("<!-- Calendar -->")[0]
    assert 'class="order-btn"' in card and 'class="swap-btn"' in card
    assert f'data-itm-id="{item}"' in card and f'data-date="{today}"' in card
    assert 'data-meal="2"' in card


def fetch_one_item(path, rtr_id):
    conn = create_connection(path)
    try:
        return fetch_one(
            conn, 'SELECT itm_id FROM "MenuItem" WHERE rtr_id=? ORDER BY itm_id LIMIT 1', (rtr_id,)
        )[0]
    finally:
        close_connection(conn)


# ---------------------------------------------------------------- Profile edit pop-up


def test_profile_pop_up_starts_from_saved_choices(client, seed_minimal_data, temp_db_path):
    _db(
        temp_db_path,
        'UPDATE "User" SET allergies=?, preferences=? WHERE usr_id=?',
        ("Peanuts, Milk", "Spicy,Vegan", seed_minimal_data["usr_id"]),
    )
    _login(client)
    html = client.get("/profile").get_data(as_text=True)
    form = html.split('id="dietProfileForm"')[1].split("</form>")[0]
    assert 'value="Peanuts" checked' in form and 'value="Milk" checked' in form
    assert 'value="Eggs">' in form  # not chosen
    assert 'value="vegan" checked' in form
    assert 'name="food_matches" value="Spicy"' in form
    assert 'for="preference-priority">15</output>' in form
    assert 'action="/profile/edit"' in html.split('id="dietProfileForm"')[0].rsplit("<form", 1)[1]


def test_register_uses_the_shared_editor(client):
    html = client.get("/register").get_data(as_text=True)
    assert html.count('class="diet-editor"') == 1
    assert 'name="allergies[]"' in html and 'name="diets[]"' in html
    assert 'name="food_matches"' not in html


# ---------------------------------------------------------------- restaurant owners


@pytest.fixture()
def owner(client, seed_minimal_data, temp_db_path):
    """A fresh restaurant (the shared test database holds other tests' orders and reviews)."""
    email = f"owner-{uuid.uuid4().hex[:8]}@test.com"
    rtr_id = _db(
        temp_db_path,
        'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES (?,?,?,?)',
        ("Tab Kitchen", email, generate_password_hash("ownerpw1"), "Open"),
    )
    resp = client.post("/restaurant/login", data={"email": email, "password": "ownerpw1"})
    assert resp.headers["Location"].endswith("/restaurant/orders")
    return {**seed_minimal_data, "rtr_id": rtr_id}


@pytest.mark.parametrize(
    "path", ["/restaurant/orders", "/restaurant/analytics", "/restaurant/reviews"]
)
def test_every_owner_page_has_the_tabs(client, owner, path):
    html = client.get(path).get_data(as_text=True)
    tabs = html.split('aria-label="Restaurant pages"')[1].split("</nav>")[0]
    for href in (
        "/restaurant/orders",
        "/restaurant/analytics",
        "/restaurant/reviews",
        "/restaurant/logout",
    ):
        assert f'href="{href}"' in tabs
    current = tabs.split('aria-current="page"')[0].rsplit("<a ", 1)[1]
    assert f'href="{path}"' in current
    assert "Back to Dashboard" not in html


def test_owner_tabs_count_active_orders_and_rating(client, owner, temp_db_path):
    for status in ("Ordered", "Preparing", "Delivered", "Cancelled"):
        _order(temp_db_path, owner, status)
    _db(
        temp_db_path,
        'INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,ord_id,created_at) VALUES (?,?,?,?,?,?,?)',
        (owner["rtr_id"], owner["usr_id"], "t", 4, "d", None, "2026-11-01"),
    )
    tabs = (
        client.get("/restaurant/orders")
        .get_data(as_text=True)
        .split('aria-label="Restaurant pages"')[1]
    )
    assert "2 active" in tabs
    assert "4.0 · 1 Review<" in tabs
