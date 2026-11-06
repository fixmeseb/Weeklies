"""UC14: Download Order Receipt — tests.

Verified against Flask_app.py:2217-2255. GET /orders/<int:ord_id>/receipt.pdf
requires login, verifies usr_id owns the order, and streams PDF bytes.
"""
import pytest
from proj2.sef26tests.conftest import make_order


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


@pytest.fixture(autouse=True)
def _stub_pdf(monkeypatch):
    """PDF generation calls reportlab — stub it with fake bytes so tests are fast."""
    monkeypatch.setattr("proj2.food.views.generate_order_receipt_pdf",
                        lambda db, oid: b"%PDF-1.4\n%fake\n", raising=True)


def test_receipt_valid(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 main: owner of order gets a PDF response."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"])
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"


def test_receipt_order_not_found(client, seed_user):
    """UC14 ext 1a: unknown order → 404."""
    _login(client, seed_user)
    resp = client.get("/orders/999999/receipt.pdf")
    assert resp.status_code == 404


def test_receipt_unauthorized(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 ext 1b: order owned by a different user → 403."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    from werkzeug.security import generate_password_hash
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "User"(first_name,last_name,email,phone,password_HS) '
            'VALUES ("Other","User","other-uc14@x.com","5551112222",?)',
            (generate_password_hash("x"),))
        other_id = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email="other-uc14@x.com"')[0]
    finally:
        close_connection(conn)
    ord_id = make_order(temp_db_path, other_id, seed_restaurant["rtr_id"])
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 403


def test_receipt_missing_fields(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 ext 2a: order details with missing optional fields still return PDF (stub)."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"],
                        details={"items": [], "charges": {}})
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 200


def test_receipt_malformed_data(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 ext 2b: malformed JSON in details — stub still returns bytes."""
    from proj2.sqlQueries import create_connection, execute_query, fetch_one, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn,
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            (seed_restaurant["rtr_id"], seed_user["usr_id"], "{not json", "Delivered"))
        ord_id = fetch_one(conn, "SELECT last_insert_rowid()")[0]
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 200


def test_receipt_many_items(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 ext 3a: many items in details — stubbed PDF still returns 200."""
    many = {"items": [{"itm_id": 1, "name": f"Item{i}", "qty": 1, "unit_price": 1.0, "line_total": 1.0}
                      for i in range(30)],
            "charges": {"subtotal": 30.0, "tax": 2.0, "delivery_fee": 3.99, "service_fee": 1.49, "tip": 0, "total": 37.48}}
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], details=many)
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 200


def test_receipt_cancelled_order(client, seed_user, seed_restaurant, temp_db_path):
    """UC14 ext 3b: cancelled order still returns PDF (marking is inside the PDF renderer)."""
    ord_id = make_order(temp_db_path, seed_user["usr_id"], seed_restaurant["rtr_id"], status="Cancelled")
    _login(client, seed_user)
    resp = client.get(f"/orders/{ord_id}/receipt.pdf")
    assert resp.status_code == 200
