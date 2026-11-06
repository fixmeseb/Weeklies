"""UC12: Place Pickup Order — tests.

Same POST /order endpoint as UC11, but with `delivery_type: "pickup"`.
Server sets delivery_fee=0 for pickup orders (Flask_app.py:1913).
"""
import pytest
from proj2.sqlQueries import create_connection, fetch_one, close_connection


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def test_place_pickup_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC12 main: valid pickup order creates 'Ordered' row with delivery_fee=0."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "pickup",
    })
    assert resp.status_code == 200
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    d = _json.loads(details[0])
    assert d["charges"]["delivery_fee"] == 0.0
    assert d["delivery_type"] == "pickup"


def test_place_pickup_missing_content(client, seed_user):
    """UC12 ext 1a: missing restaurant_id/items → 400 invalid_input."""
    _login(client, seed_user)
    resp = client.post("/order", json={"delivery_type": "pickup"})
    assert resp.status_code == 400


def test_place_pickup_missing_item(client, seed_user, seed_restaurant):
    """UC12 ext 2a: unknown itm_id in pickup order → 404 not_found."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": 999999, "qty": 1}],
        "delivery_type": "pickup",
    })
    assert resp.status_code == 404


def test_place_pickup_wrong_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC12 ext 2b: pickup order mixing restaurants → 400 mixed_restaurants."""
    from proj2.sqlQueries import execute_query
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("PickRival","prival@x.com","x","open")')
        r2 = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="prival@x.com"')[0]
        execute_query(conn, 'INSERT INTO "MenuItem"(rtr_id,name,price,instock) VALUES (?,"PR Dish",500,1)', (r2,))
        r2_item = fetch_one(conn, 'SELECT itm_id FROM "MenuItem" WHERE rtr_id=?', (r2,))[0]
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1},
                  {"itm_id": r2_item, "qty": 1}],
        "delivery_type": "pickup",
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "mixed_restaurants"


def test_place_pickup_price_check(client, seed_user, seed_restaurant, temp_db_path):
    """UC12 ext 3a: stored unit_price matches DB catalog."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "pickup",
    })
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    assert _json.loads(details[0])["items"][0]["unit_price"] == 12.99


def test_place_pickup_no_delivery_fee(client, seed_user, seed_restaurant, temp_db_path):
    """UC12 variant: delivery_fee = 0 for pickup."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "pickup",
    })
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    assert _json.loads(details[0])["charges"]["delivery_fee"] == 0.0


def test_place_pickup_analytics_fail(client, seed_user, seed_restaurant, monkeypatch):
    """UC12 ext 7a: analytics failure doesn't break pickup order."""
    from proj2 import Flask_app
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")), raising=True)
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "pickup",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
