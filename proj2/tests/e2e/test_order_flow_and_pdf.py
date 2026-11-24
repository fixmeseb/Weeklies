import datetime

# Orders for a day already past are refused, so the planned meal is two days ahead.
MEAL_DAY = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()


def test_order_post_and_receipt_pdf(client, seed_minimal_data, login_session, tmp_path):
    rtr_id = seed_minimal_data["rtr_id"]

    # Discover menu items
    # /orders page provides items, but for test we query DB directly:
    # (You could also hit /orders and parse HTML, but DB is simpler & faster here.)
    # We’ll just assume item IDs 1 and 2 exist from seed_minimal_data.
    items = [{"itm_id": 1, "qty": 2}, {"itm_id": 2, "qty": 1}]

    # Place single-order POST
    resp = client.post(
        "/order",
        json={
            "restaurant_id": rtr_id,
            "items": items,
            "delivery_type": "delivery",
            "tip": 1.23,
            "eta_minutes": 30,
            "date": MEAL_DAY,
            "meal": 3,
        },
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body and body.get("ok") is True and body.get("ord_id")

    ord_id = body["ord_id"]

    # Fetch the PDF (route enforces user ownership)
    pdf = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF-1.")  # from fake pdf in fixture


def test_db_view_pagination(client, seed_minimal_data, login_session):
    # default table=User, page defaults to 1
    r = client.get("/db")
    assert r.status_code == 200
    assert b"User" in r.data

    # invalid table should fallback to 'User'
    r = client.get("/db?t=NotATable")
    assert r.status_code == 200
    assert b"User" in r.data

    # page not int → treated as 1
    r = client.get("/db?page=abc")
    assert r.status_code == 200
