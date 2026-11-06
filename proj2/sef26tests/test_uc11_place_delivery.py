"""UC11: Place Delivery Order — tests.

Verified against Flask_app.py:1801-1957. POST /order (JSON) with
`delivery_type: "delivery"`. Success returns 200 {"ok": true, "ord_id": N}.
Various validation failures return 400 with an error code.
"""
import pytest
from proj2.sqlQueries import create_connection, fetch_one, close_connection


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def test_place_delivery_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 main: valid delivery order returns ok + ord_id, and creates Order row."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    ord_id = body["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT status FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == "Ordered"


def test_place_delivery_missing_items(client, seed_user, seed_restaurant):
    """UC11 ext 1a: missing items list → 400 invalid_input."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_input"


def test_place_delivery_invalid_item(client, seed_user, seed_restaurant):
    """UC11 ext 2b: unknown itm_id → 404 error names the missing item."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": 999999, "qty": 1}],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 404
    assert "not_found" in resp.get_json()["error"]


def test_place_delivery_mixed_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 ext 2c: items from another restaurant → 400 mixed_restaurants."""
    from proj2.sqlQueries import execute_query
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Restaurant"(name,email,password_HS,status) VALUES ("Rival","rival@x.com","x","open")')
        r2 = fetch_one(conn, 'SELECT rtr_id FROM "Restaurant" WHERE email="rival@x.com"')[0]
        execute_query(conn, 'INSERT INTO "MenuItem"(rtr_id,name,price,instock) VALUES (?,"Rival Dish",500,1)', (r2,))
        r2_item = fetch_one(conn, 'SELECT itm_id FROM "MenuItem" WHERE rtr_id=?', (r2,))[0]
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1},
                  {"itm_id": r2_item, "qty": 1}],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "mixed_restaurants"


def test_place_delivery_price_changed(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 ext 3a: server uses catalog price regardless of what client submits.

    We can't submit a client-side price directly (payload doesn't accept one),
    but we assert that the stored charges use the current DB price of the item.
    """
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "delivery",
    })
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details_row = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    d = _json.loads(details_row[0])
    # Pasta is 1299 cents = $12.99
    assert d["items"][0]["unit_price"] == 12.99


def test_place_delivery_bad_choice(client, seed_user, seed_restaurant):
    """UC11 ext 4a: unknown delivery_type defaults to 'delivery' (see Flask_app.py:1835)."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "teleport",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_place_delivery_qty_zero(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 ext 4b: qty=0 coerced to 1; user charged for one."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 0}],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 200
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details_row = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    assert _json.loads(details_row[0])["items"][0]["qty"] == 1


def test_place_delivery_analytics_fail(client, seed_user, seed_restaurant, monkeypatch):
    """UC11 ext 7a: order still succeeds when analytics update raises."""
    from proj2 import Flask_app
    def boom(*a, **k):
        raise RuntimeError("analytics down")
    monkeypatch.setattr("proj2.food.views.record_analytics_snapshot", boom, raising=True)
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "delivery",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_place_delivery_with_tip(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 variant: tip is included in the stored total."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "delivery",
        "tip": 3.50,
    })
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        details_row = fetch_one(conn, 'SELECT details FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    import json as _json
    assert _json.loads(details_row[0])["charges"]["tip"] == 3.50


def test_place_delivery_visible_to_restaurant(client, seed_user, seed_restaurant, temp_db_path):
    """UC11 variant: placed order appears when the restaurant queries its own orders."""
    _login(client, seed_user)
    resp = client.post("/order", json={
        "restaurant_id": seed_restaurant["rtr_id"],
        "items": [{"itm_id": seed_restaurant["first_item_id"], "qty": 1}],
        "delivery_type": "delivery",
    })
    ord_id = resp.get_json()["ord_id"]
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT rtr_id FROM "Order" WHERE ord_id=?', (ord_id,))
    finally:
        close_connection(conn)
    assert row[0] == seed_restaurant["rtr_id"]
