from proj2.sqlQueries import create_connection, close_connection, fetch_all


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


def test_orders_json_no_items_error_when_all_ids_nonpositive(
    client, temp_db_path, seed_minimal_data, login_session
):
    rtr_id = seed_minimal_data["rtr_id"]

    payload = {
        "restaurant_id": rtr_id,
        "items": [{"itm_id": 0, "qty": 1}],
    }
    resp = client.post("/order", json=payload)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body.get("error") == "no_items"


def test_orders_json_items_not_found_when_db_has_no_rows(
    client, temp_db_path, seed_minimal_data, login_session
):
    rtr_id = seed_minimal_data["rtr_id"]

    payload = {
        "restaurant_id": rtr_id,
        "items": [{"itm_id": 999999, "qty": 1}],
    }
    resp = client.post("/order", json=payload)
    assert resp.status_code == 404
    body = resp.get_json()
    assert body.get("error") == "items_not_found"


def test_orders_json_item_specific_not_found(
    client, temp_db_path, seed_minimal_data, login_session
):
    rtr_id = seed_minimal_data["rtr_id"]
    real_itm = _first_menu_item_id(temp_db_path, rtr_id)

    payload = {
        "restaurant_id": rtr_id,
        "items": [
            {"itm_id": real_itm, "qty": 1},
            {"itm_id": 999999, "qty": 1},
        ],
    }
    resp = client.post("/order", json=payload)
    assert resp.status_code == 404
    body = resp.get_json()
    assert body.get("error") == "item_999999_not_found"


def test_legacy_get_order_success_redirects_to_my_orders(
    client, temp_db_path, seed_minimal_data, login_session
):
    rtr_id = seed_minimal_data["rtr_id"]
    itm_id = _first_menu_item_id(temp_db_path, rtr_id)

    resp = client.get(
        f"/order?itm_id={itm_id}&qty=2&delivery=delivery&tip=1.50&eta=30&date=2025-11-10&meal=2",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    loc = resp.headers.get("Location", "")
    assert "/orders" in loc
    assert "ordered=" in loc
