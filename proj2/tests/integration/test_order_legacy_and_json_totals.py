# tests/integration/test_order_legacy_and_json_totals.py
import datetime

import proj2.Flask_app as Flask_app  # noqa: F401 (ensures module loads)
from proj2.sqlQueries import (
    create_connection,
    close_connection,
    execute_query,
    fetch_all,
)


def _first_menu_item_id(db_path, rtr_id):
    conn = create_connection(db_path)
    try:
        rows = fetch_all(
            conn,
            'SELECT itm_id FROM "MenuItem" WHERE rtr_id=? ORDER BY itm_id',
            (rtr_id,),
        )
        return rows[0][0]
    finally:
        close_connection(conn)


def test_orders_json_missing_items_400(client, temp_db_path, seed_minimal_data, login_session):
    rtr_id = seed_minimal_data["rtr_id"]
    payload = {"restaurant_id": rtr_id, "items": []}
    resp = client.post("/order", json=payload)
    assert resp.status_code == 400
    assert resp.is_json
    body = resp.get_json()
    assert body.get("error") == "invalid_input"


def test_orders_json_invalid_restaurant_400(client, seed_minimal_data, login_session):
    payload = {"restaurant_id": 0, "items": [{"itm_id": 1, "qty": 1}]}
    resp = client.post("/order", json=payload)
    assert resp.status_code == 400


def test_orders_json_mixed_restaurants_400(client, temp_db_path, seed_minimal_data, login_session):
    data = seed_minimal_data
    rtr_a = data["rtr_id"]

    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            """
            INSERT INTO "Restaurant"(name,address,city,state,zip,status)
            VALUES ("Second Rtr","456 Other","Durham","NC","27701","open")
            """,
        )
        rows = fetch_all(
            conn,
            'SELECT rtr_id FROM "Restaurant" WHERE name="Second Rtr"',
        )
        rtr_b = rows[0][0]

        execute_query(
            conn,
            """
            INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,restock,allergens)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (rtr_b, "MixedRtrItem", "Should not mix", 1000, 100, 1, "", ""),
        )
        conn.commit()

        rows = fetch_all(conn, 'SELECT itm_id, rtr_id FROM "MenuItem" ORDER BY itm_id')
        itm_a = rows[0][0]
        itm_b = rows[-1][0]
    finally:
        close_connection(conn)

    payload = {
        "restaurant_id": rtr_a,
        "items": [
            {"itm_id": itm_a, "qty": 1},
            {"itm_id": itm_b, "qty": 1},
        ],
    }
    resp = client.post("/order", json=payload)
    assert resp.status_code == 400
    assert resp.is_json
    body = resp.get_json()
    assert body.get("error") == "mixed_restaurants"


def test_orders_json_success_with_weird_delivery_type(
    client, temp_db_path, seed_minimal_data, login_session
):
    rtr_id = seed_minimal_data["rtr_id"]
    itm_id = _first_menu_item_id(temp_db_path, rtr_id)

    payload = {
        "restaurant_id": rtr_id,
        "items": [{"itm_id": itm_id, "qty": 2}],
        "delivery_type": "WEIRD",
        "tip": 0.0,
        "eta_minutes": 10,
        "date": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
        "meal": 1,
    }
    resp = client.post("/order", json=payload)
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert body.get("ok") is True
    assert isinstance(body.get("ord_id"), int)


def test_order_legacy_missing_item_redirects(client, login_session):
    resp = client.get("/order")
    assert resp.status_code in (302, 303)


def test_order_legacy_bad_item_redirects(client, login_session):
    resp = client.get("/order?itm_id=999999")
    assert resp.status_code in (302, 303)
