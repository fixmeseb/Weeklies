"""
Unexpected input and actions that land at the same time: each test is a case that used to
answer 500, lose something, or undo a refund.
"""

import sqlite3
import uuid

import pytest
from werkzeug.security import generate_password_hash

import proj2.food.owner as owner
import proj2.food.reviews as reviews


def _run(path, sql, params=()):
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        conn.commit()
        return rows, cur.lastrowid
    finally:
        conn.close()


@pytest.fixture()
def errors_answered(app, monkeypatch):
    """Let the app answer unhandled errors with a 500, as it does outside the tests."""
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)


class Shop:
    """A customer with $100, and a restaurant of their own with one $10.00 dish."""

    def __init__(self, path):
        self.path = path
        self.email = f"edge-{uuid.uuid4().hex[:8]}@test.com"
        self.usr_id = self.insert(
            'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,'
            "allergies) VALUES ('Ed','Ge',?,'5550000',?,10000,'','')",
            self.email,
            generate_password_hash("secret123"),
        )
        self.rtr_id = self.insert(
            'INSERT INTO "Restaurant"(name,email,status) VALUES (?,?,?)',
            "Edge Cafe",
            f"cafe-{self.email}",
            "open",
        )
        self.itm_id = self.insert(
            'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
            "VALUES (?,'Ten Dollar Plate','',1000,500,1,'')",
            self.rtr_id,
        )

    def run(self, sql, *params):
        return _run(self.path, sql, params)[0]

    def insert(self, sql, *params):
        return _run(self.path, sql, params)[1]

    def one(self, sql, *params):
        return self.run(sql, *params)[0][0]

    def sign_in(self, client, password="secret123"):
        return client.post("/login", data={"email": self.email, "password": password})

    def as_owner(self, client):
        with client.session_transaction() as sess:
            sess["restaurant_mode"] = True
            sess["rtr_id"] = self.rtr_id

    def order(self, client):
        self.sign_in(client)
        body = {
            "restaurant_id": self.rtr_id,
            "delivery_type": "pickup",
            "items": [{"itm_id": self.itm_id, "qty": 1}],
        }
        return client.post("/order", json=body).get_json()["ord_id"]

    def review(self, ord_id, title, created_at):
        self.insert(
            'INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,ord_id,created_at) '
            "VALUES (?,?,?,5,'',?,?)",
            self.rtr_id,
            self.usr_id,
            title,
            ord_id,
            created_at,
        )


@pytest.fixture()
def shop(temp_db_path, seed_minimal_data):
    return Shop(temp_db_path)


# ---------------------------------------------------------------- orders


@pytest.mark.parametrize(
    "action, status",
    [("accept", "Ordered"), ("prepare", "Accepted"), ("ready", "Preparing"), ("deliver", "Ready")],
)
def test_an_order_cancelled_meanwhile_stays_cancelled(client, shop, monkeypatch, action, status):
    """The order is cancelled between an owner's page being drawn and their click landing."""
    ord_id = shop.order(client)
    shop.run('UPDATE "Order" SET status=? WHERE ord_id=?', status, ord_id)
    shop.as_owner(client)
    real = owner.set_status

    def cancelled_just_before(conn, *args, **kwargs):
        shop.run('UPDATE "Order" SET status=? WHERE ord_id=?', "Cancelled", ord_id)
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(owner, "set_status", cancelled_just_before)
    assert client.post(f"/restaurant/orders/{ord_id}/{action}").status_code == 400
    assert shop.one('SELECT status FROM "Order" WHERE ord_id=?', ord_id) == "Cancelled"


def test_a_refunded_order_is_not_accepted(app, client, shop, monkeypatch):
    ord_id = shop.order(client)
    shop.as_owner(client)
    real = owner.set_status

    def rejected_just_before(conn, ord_id_, status, *args, **kwargs):
        if status == "Accepted":
            other_tab = app.test_client()
            shop.as_owner(other_tab)
            with app.app_context():  # its own database connection
                assert other_tab.post(f"/restaurant/orders/{ord_id}/reject").status_code == 302
        return real(conn, ord_id_, status, *args, **kwargs)

    monkeypatch.setattr(owner, "set_status", rejected_just_before)
    assert client.post(f"/restaurant/orders/{ord_id}/accept").status_code == 400
    assert shop.one('SELECT status FROM "Order" WHERE ord_id=?', ord_id) == "Cancelled"
    assert shop.one('SELECT wallet FROM "User" WHERE usr_id=?', shop.usr_id) == 10000


def test_submitting_a_review_twice_at_once_keeps_the_first(
    client, shop, monkeypatch, errors_answered
):
    ord_id = shop.order(client)
    shop.run('UPDATE "Order" SET status=? WHERE ord_id=?', "Delivered", ord_id)
    real, done = reviews.execute_query, []

    def first_one_wins(conn, *args):
        if not done:
            done.append(True)
            shop.review(ord_id, "The first one", "2026-01-01")
        return real(conn, *args)

    monkeypatch.setattr(reviews, "execute_query", first_one_wins)
    resp = client.post(f"/order/{ord_id}/review", data={"rating": "1", "title": "The second one"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/order/{ord_id}/review")
    assert "The first one" in client.get(resp.headers["Location"]).get_data(as_text=True)


# ---------------------------------------------------------------- sign-in and passwords


def test_an_account_without_a_password_cannot_sign_in(client, shop, errors_answered):
    shop.run('UPDATE "User" SET password_HS=NULL WHERE usr_id=?', shop.usr_id)
    resp = shop.sign_in(client, "x")
    assert resp.status_code == 200 and "Invalid credentials" in resp.get_data(as_text=True)


def test_a_restaurant_without_a_password_cannot_sign_in(client, shop, errors_answered):
    resp = client.post("/restaurant/login", data={"email": f"cafe-{shop.email}", "password": "x"})
    assert resp.status_code == 200 and "Invalid credentials" in resp.get_data(as_text=True)


def test_a_password_with_spaces_at_its_ends_can_be_changed(client, shop):
    shop.run(
        'UPDATE "User" SET password_HS=? WHERE usr_id=?',
        generate_password_hash(" secret 1 "),
        shop.usr_id,
    )
    shop.sign_in(client, " secret 1 ")
    change = {
        "current_password": " secret 1 ",
        "new_password": " secret 2 ",
        "confirm_password": " secret 2 ",
    }
    resp = client.post("/profile/change-password", data=change)
    assert "pw_updated=1" in resp.headers["Location"]
    client.get("/logout")
    assert shop.sign_in(client, " secret 2 ").status_code == 302


# ---------------------------------------------------------------- addresses


@pytest.mark.parametrize("path", ["/2026/13", "/2026/99", "/1/1", "/9999/12", "/10000/1"])
@pytest.mark.parametrize("page", ["", "/insights"])
def test_an_impossible_month_is_not_found(client, shop, errors_answered, page, path):
    shop.sign_in(client)
    assert client.get(page + path).status_code == 404


@pytest.mark.parametrize("page", ["abc", "", "-1", "0", "1.5", "9" * 30])
def test_a_bad_page_number_still_shows_the_reviews(client, shop, errors_answered, page):
    assert client.get(f"/restaurant/{shop.rtr_id}/reviews?page={page}").status_code == 200
    shop.as_owner(client)
    assert client.get(f"/restaurant/reviews?page={page}").status_code == 200


def test_a_page_past_the_end_shows_the_last_reviews(client, shop):
    for n in range(11):
        ord_id = shop.insert(
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            shop.rtr_id,
            shop.usr_id,
            "{}",
            "Delivered",
        )
        shop.review(ord_id, f"review-{n:02d}", f"2026-01-{n + 1:02d}")
    page = client.get(f"/restaurant/{shop.rtr_id}/reviews?page=50").get_data(as_text=True)
    assert "review-00" in page and "review-10" not in page


# ---------------------------------------------------------------- JSON and form bodies

JSON_ROUTES = [
    "/order",
    "/menu/generate",
    "/menu/remove",
    "/menu/clear",
    "/menu/order-plan",
    "/menu/swap",
]


@pytest.mark.parametrize("path", JSON_ROUTES)
@pytest.mark.parametrize("body", [[1], "text", 5])
def test_json_that_is_not_an_object_is_refused(client, shop, errors_answered, path, body):
    shop.sign_in(client)
    resp = client.post(path, json=body)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


@pytest.mark.parametrize("field", ["start_date", "preferences", "allergens"])
@pytest.mark.parametrize("value", [5, ["2026-01-01"], {"a": 1}])
def test_generate_refuses_text_fields_that_are_not_text(
    client, shop, errors_answered, field, value
):
    shop.sign_in(client)
    resp = client.post("/menu/generate", json={field: value})
    assert resp.status_code == 400 and field in resp.get_json()["error"]


@pytest.mark.parametrize("path", ["/menu/clear", "/menu/order-plan"])
@pytest.mark.parametrize("meals", [5, [None], [[1]], ["x"]])
def test_a_range_refuses_meals_that_are_not_meal_numbers(
    client, shop, errors_answered, path, meals
):
    shop.sign_in(client)
    assert client.post(path, json={"meal_numbers": meals}).status_code == 400


@pytest.mark.parametrize("path", ["/menu/clear", "/menu/order-plan", "/menu/generate"])
def test_a_range_past_the_last_date_is_refused(client, shop, errors_answered, path):
    shop.sign_in(client)
    body = {"start_date": "9999-12-31", "number_of_days": 7, "replace": True}
    assert client.post(path, json=body).status_code == 400


@pytest.mark.parametrize("day", ["20260105", "2026-W02-1"])
def test_other_ways_to_write_a_date_still_return_to_the_calendar(
    client, shop, errors_answered, day
):
    shop.sign_in(client)
    resp = client.post("/menu/remove", data={"date": day, "meal": "1"})
    assert resp.status_code == 302 and "/2026/1?week=2026-01-05" in resp.headers["Location"]
