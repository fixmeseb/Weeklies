"""Routes for editing a plan, ordering planned days, meal times, the delivery address,
the ordering rules and the order status history."""

import datetime
import json

import pytest

from proj2.sqlQueries import (
    close_connection,
    create_connection,
    execute_query,
    fetch_all,
    fetch_one,
)

TOMORROW = datetime.date.today() + datetime.timedelta(days=1)
DAY1 = TOMORROW.isoformat()
DAY2 = (TOMORROW + datetime.timedelta(days=1)).isoformat()
DAY3 = (TOMORROW + datetime.timedelta(days=2)).isoformat()


def _db(path, sql, params=(), one=False):
    conn = create_connection(path)
    try:
        if sql.lstrip().upper().startswith("SELECT"):
            return fetch_one(conn, sql, params) if one else fetch_all(conn, sql, params)
        execute_query(conn, sql, params)
    finally:
        close_connection(conn)


@pytest.fixture()
def items(temp_db_path, seed_minimal_data):
    rows = _db(
        temp_db_path,
        'SELECT itm_id FROM "MenuItem" WHERE rtr_id = ? ORDER BY itm_id',
        (seed_minimal_data["rtr_id"],),
    )
    return [r[0] for r in rows[:2]]


@pytest.fixture()
def planned(temp_db_path, seed_minimal_data, login_session, items):
    """The user has a three-day plan, no orders, the fixture address and no allergies."""
    a, b = items
    menu = f"[{DAY1},{a},2],[{DAY1},{b},3],[{DAY2},{a},3],[{DAY3},{b},3]"
    usr = seed_minimal_data["usr_id"]
    _db(
        temp_db_path,
        'UPDATE "User" SET generated_menu = ?, allergies = "", address = "1 Test Way", '
        'city = "Raleigh", state = "NC", zip = "27606", breakfast_time = NULL, '
        "lunch_time = NULL, dinner_time = NULL WHERE usr_id = ?",
        (menu, usr),
    )
    _db(temp_db_path, 'DELETE FROM "Order" WHERE usr_id = ?', (usr,))
    _db(
        temp_db_path,
        'UPDATE "MenuItem" SET instock = 1 WHERE rtr_id = ?',
        (seed_minimal_data["rtr_id"],),
    )
    _db(
        temp_db_path,
        'UPDATE "Restaurant" SET status = "open", hours = NULL WHERE rtr_id = ?',
        (seed_minimal_data["rtr_id"],),
    )
    return {"usr_id": usr, "a": a, "b": b, "rtr_id": seed_minimal_data["rtr_id"]}


def _menu(temp_db_path, usr_id):
    return _db(temp_db_path, 'SELECT generated_menu FROM "User" WHERE usr_id = ?', (usr_id,), True)[
        0
    ]


# ---------------------------------------------------------------- plan editing


def test_remove_one_meal(client, temp_db_path, planned):
    resp = client.post("/menu/remove", json={"date": DAY1, "meal": 3})
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    menu = _menu(temp_db_path, planned["usr_id"])
    assert f"[{DAY1},{planned['b']},3]" not in menu
    assert f"[{DAY1},{planned['a']},2]" in menu and DAY3 in menu


def test_remove_empty_slot_is_404(client, planned):
    resp = client.post("/menu/remove", json={"date": DAY1, "meal": 1})
    assert resp.status_code == 404 and resp.get_json()["ok"] is False


def test_remove_from_a_form_redirects_with_a_notice(client, planned):
    resp = client.post("/menu/remove", data={"date": DAY2, "meal": "3"})
    assert resp.status_code in (302, 303)
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "removed from your plan" in page


def test_clear_a_range_of_days(client, temp_db_path, planned):
    resp = client.post(
        "/menu/clear", json={"start_date": DAY1, "number_of_days": 2, "meal_numbers": [3]}
    )
    body = resp.get_json()
    assert body["ok"] is True and body["removed"] == 2
    menu = _menu(temp_db_path, planned["usr_id"])
    assert f"[{DAY1},{planned['a']},2]" in menu  # lunch was not chosen
    assert f"[{DAY3},{planned['b']},3]" in menu  # outside the range
    assert f"{DAY2}," not in menu


def test_generate_with_replace_clears_the_days_first(client, temp_db_path, planned, monkeypatch):
    from proj2 import Flask_app

    seen = {}

    class FakeGenerator:
        def __init__(self, *a, **k):
            pass

        def update_menu(self, menu, *a, **k):
            seen["menu"] = menu
            seen["meal_times"] = k.get("meal_times")
            return menu

    monkeypatch.setattr(Flask_app, "MenuGenerator", FakeGenerator)
    client.post(
        "/menu/generate",
        data={"start_date": DAY1, "days": "2", "meal3": "on", "replace": "on"},
    )
    assert f"{DAY2}," not in seen["menu"] and f"[{DAY1},{planned['b']},3]" not in seen["menu"]
    assert f"[{DAY1},{planned['a']},2]" in seen["menu"]
    assert seen["meal_times"] == {1: 1000, 2: 1400, 3: 2000}


# ---------------------------------------------------------------- ordering planned days


def test_order_these_days_places_one_order_per_meal(client, temp_db_path, planned):
    resp = client.post(
        "/menu/order-plan",
        json={"start_date": DAY1, "number_of_days": 2, "delivery_type": "delivery"},
    )
    body = resp.get_json()
    assert body["ok"] is True and len(body["ord_ids"]) == 3, body
    rows = _db(temp_db_path, 'SELECT details FROM "Order" WHERE usr_id = ?', (planned["usr_id"],))
    details = [json.loads(r[0]) for r in rows]
    assert sorted((d["date"], d["meal"]) for d in details) == [(DAY1, 2), (DAY1, 3), (DAY2, 3)]
    lunch = next(d for d in details if d["meal"] == 2)
    assert lunch["due_at"] == f"{DAY1}T14:00" and lunch["asap"] is False
    assert lunch["deliver_to"] == "1 Test Way, Raleigh, NC 27606"

    # Ordering again places nothing: those meals are ordered already.
    again = client.post("/menu/order-plan", json={"start_date": DAY1, "number_of_days": 2})
    assert again.status_code == 200 and again.get_json()["ok"] is False

    # The calendar marks them as ordered.
    page = client.get(f"/?year={TOMORROW.year}&month={TOMORROW.month}").get_data(as_text=True)
    assert "Ordered" in page


def test_order_these_days_skips_meals_that_break_the_rules(client, temp_db_path, planned):
    _db(temp_db_path, 'UPDATE "MenuItem" SET instock = 0 WHERE itm_id = ?', (planned["b"],))
    body = client.post(
        "/menu/order-plan", json={"start_date": DAY1, "number_of_days": 3}
    ).get_json()
    assert len(body["ord_ids"]) == 2
    assert {s["error"] for s in body["skipped"]} == {"out_of_stock"}
    assert "Not ordered" in body["message"]


def test_order_these_days_needs_an_address_for_delivery(client, temp_db_path, planned):
    _db(temp_db_path, 'UPDATE "User" SET address = "" WHERE usr_id = ?', (planned["usr_id"],))
    resp = client.post(
        "/menu/order-plan",
        json={"start_date": DAY1, "number_of_days": 1, "delivery_type": "delivery"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["skipped"][0]["error"] == "no_address"
    pickup = client.post(
        "/menu/order-plan",
        json={"start_date": DAY1, "number_of_days": 1, "delivery_type": "pickup"},
    )
    assert len(pickup.get_json()["ord_ids"]) == 2


def test_restaurant_sees_what_the_order_is_for(client, temp_db_path, planned):
    client.post("/menu/order-plan", json={"start_date": DAY2, "number_of_days": 1})
    rtr = _db(
        temp_db_path,
        "SELECT email FROM Restaurant WHERE rtr_id = ?",
        (planned["rtr_id"],),
        True,
    )
    client.get("/logout")
    with client.session_transaction() as s:
        s["restaurant_mode"] = True
        s["rtr_id"] = planned["rtr_id"]
        s["RestaurantName"] = "Cafe One"
        s["RestaurantEmail"] = rtr[0]
    page = client.get("/restaurant/orders").get_data(as_text=True)
    assert f"For {TOMORROW + datetime.timedelta(days=1):%a %b}" in page
    assert "Deliver to: 1 Test Way, Raleigh, NC 27606" in page


# ---------------------------------------------------------------- the ordering rules


def _order(client, itm_id, rtr_id, **over):
    body = {
        "restaurant_id": rtr_id,
        "items": [{"itm_id": itm_id, "qty": 1}],
        "delivery_type": "pickup",
        "date": DAY1,
        "meal": 3,
    }
    body.update(over)
    return client.post("/order", json=body)


def test_order_refuses_an_allergen_on_the_account(client, temp_db_path, planned):
    _db(temp_db_path, 'UPDATE "User" SET allergies = "nuts" WHERE usr_id = ?', (planned["usr_id"],))
    salad = _db(temp_db_path, 'SELECT itm_id FROM "MenuItem" WHERE name = "Salad"', one=True)[0]
    resp = _order(client, salad, planned["rtr_id"])
    assert resp.status_code == 409 and resp.get_json()["error"] == "allergen"


def test_order_refuses_a_closed_restaurant_and_closed_hours(client, temp_db_path, planned):
    _db(
        temp_db_path,
        'UPDATE "Restaurant" SET status = "closed" WHERE rtr_id = ?',
        (planned["rtr_id"],),
    )
    assert _order(client, planned["a"], planned["rtr_id"]).get_json()["error"] == (
        "restaurant_unavailable"
    )
    lunch_only = json.dumps({d: [1100, 1500] for d in "Mon Tue Wed Thu Fri Sat Sun".split()})
    _db(
        temp_db_path,
        'UPDATE "Restaurant" SET status = "open", hours = ? WHERE rtr_id = ?',
        (lunch_only, planned["rtr_id"]),
    )
    assert (
        _order(client, planned["a"], planned["rtr_id"]).get_json()["error"] == "restaurant_closed"
    )
    assert _order(client, planned["a"], planned["rtr_id"], meal=2).get_json()["ok"] is True


def test_order_refuses_past_days(client, planned):
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    resp = _order(client, planned["a"], planned["rtr_id"], date=yesterday)
    assert resp.status_code == 400 and resp.get_json()["error"] == "past_date"


def test_delivery_without_an_address_is_refused(client, temp_db_path, planned):
    _db(temp_db_path, 'UPDATE "User" SET address = NULL WHERE usr_id = ?', (planned["usr_id"],))
    resp = _order(client, planned["a"], planned["rtr_id"], delivery_type="delivery")
    assert resp.get_json()["error"] == "no_address"


# ---------------------------------------------------------------- profile: address, meal times


def test_profile_saves_and_clears_the_address(client, temp_db_path, planned):
    client.post(
        "/profile/edit",
        data={"phone": "555", "address": "9 Oak St", "city": "Cary", "state": "NC", "zip": "27511"},
    )
    page = client.get("/profile").get_data(as_text=True)
    assert "9 Oak St, Cary, NC 27511" in page
    client.post("/profile/edit", data={"address": ""})
    row = _db(
        temp_db_path,
        'SELECT address, city FROM "User" WHERE usr_id = ?',
        (planned["usr_id"],),
        True,
    )
    assert row[0] == "" and row[1] == "Cary"


def test_meal_times_are_saved_and_used(client, temp_db_path, planned):
    resp = client.post(
        "/profile/meal-times",
        data={"breakfast_time": "07:30", "lunch_time": "12:15", "dinner_time": "18:45"},
    )
    assert resp.status_code in (302, 303) and "times_saved=1" in resp.headers["Location"]
    row = _db(
        temp_db_path,
        'SELECT breakfast_time, lunch_time, dinner_time FROM "User" WHERE usr_id = ?',
        (planned["usr_id"],),
        True,
    )
    assert tuple(row) == (730, 1215, 1845)
    assert 'value="18:45"' in client.get("/profile").get_data(as_text=True)
    _order(client, planned["a"], planned["rtr_id"])
    details = json.loads(
        _db(
            temp_db_path, 'SELECT details FROM "Order" WHERE usr_id = ?', (planned["usr_id"],), True
        )[0]
    )
    assert details["due_at"] == f"{DAY1}T18:45"


@pytest.mark.parametrize(
    "form",
    [
        {"breakfast_time": "13:00", "lunch_time": "12:00", "dinner_time": "18:00"},
        {"breakfast_time": "nope", "lunch_time": "12:00", "dinner_time": "18:00"},
    ],
)
def test_bad_meal_times_are_refused(client, temp_db_path, planned, form):
    client.post("/profile/meal-times", data=form)
    row = _db(
        temp_db_path, 'SELECT lunch_time FROM "User" WHERE usr_id = ?', (planned["usr_id"],), True
    )
    assert row[0] is None
    assert 'id="timesError"' in client.get("/profile").get_data(as_text=True)


# ---------------------------------------------------------------- status history


def test_status_history_is_shown_on_my_orders(client, temp_db_path, planned):
    ord_id = _order(client, planned["a"], planned["rtr_id"]).get_json()["ord_id"]
    rtr = _db(
        temp_db_path, "SELECT email FROM Restaurant WHERE rtr_id = ?", (planned["rtr_id"],), True
    )
    with client.session_transaction() as s:
        s["restaurant_mode"] = True
        s["rtr_id"] = planned["rtr_id"]
        s["RestaurantEmail"] = rtr[0]
    client.post(f"/restaurant/orders/{ord_id}/accept")
    client.post(f"/restaurant/orders/{ord_id}/reject")
    history = _db(
        temp_db_path,
        "SELECT status FROM OrderStatus WHERE ord_id = ? ORDER BY ost_id",
        (ord_id,),
    )
    assert [h[0] for h in history] == ["Ordered", "Accepted", "Cancelled"]
    page = client.get("/orders").get_data(as_text=True)
    assert "Cancelled " in page and 'class="step-at' in page


def test_another_dish_ordered_at_that_time_does_not_count_as_the_planned_meal(
    client, temp_db_path, planned
):
    # An order for the same day and meal, but of a dish that is not the planned one
    resp = _order(client, planned["b"], planned["rtr_id"], date=DAY1, meal=2)
    assert resp.get_json()["ok"] is True
    body = client.post(
        "/menu/order-plan", json={"start_date": DAY1, "number_of_days": 1, "meal_numbers": [2]}
    ).get_json()
    assert len(body["ord_ids"]) == 1  # the planned lunch is still ordered
