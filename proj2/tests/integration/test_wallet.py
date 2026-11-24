"""
Orders are paid from the customer's wallet: charged when placed, refused when the wallet
is short, refunded when the restaurant cancels.

Each test signs in its own new customer, because the test database is shared across the
session and the usual test@x.com wallet is spent by other tests.
"""

import json
import sqlite3
import uuid

import pytest
from werkzeug.security import generate_password_hash

from proj2 import config, wallet

PASSWORD = "secret123"
# The one-item pickup orders below: a $10.00 dish, 7.25% tax and the service fee
TOTAL_CENTS = 1000 + 73 + 149


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
def shop(temp_db_path, seed_minimal_data):
    """
    A customer (not signed in), a restaurant of their own with one $10.00 dish, and helpers
    to read what is stored. The restaurant has no hours, so nothing else plans from it.
    """
    email = f"wallet-{uuid.uuid4().hex[:8]}@test.com"
    _, usr_id = _run(
        temp_db_path,
        'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies) '
        "VALUES ('Wal','Let',?,'5550000',?,0,'','')",
        (email, generate_password_hash(PASSWORD)),
    )
    _, rtr = _run(
        temp_db_path,
        'INSERT INTO "Restaurant"(name,email,status) VALUES (?,?,?)',
        ("Wallet Cafe", f"cafe-{email}", "closed"),
    )
    _, itm_id = _run(
        temp_db_path,
        'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
        "VALUES (?,'Ten Dollar Plate','',1000,500,1,'')",
        (rtr,),
    )

    class Shop:
        rtr_id = rtr

        def set_balance(self, cents):
            _run(temp_db_path, 'UPDATE "User" SET wallet=? WHERE usr_id=?', (cents, usr_id))

        def balance(self):
            return _run(temp_db_path, 'SELECT wallet FROM "User" WHERE usr_id=?', (usr_id,))[0][0][
                0
            ]

        def orders(self):
            return _run(
                temp_db_path,
                'SELECT ord_id, details, status FROM "Order" WHERE usr_id=?',
                (usr_id,),
            )[0]

        def add_order(self, status, **details):
            return _run(
                temp_db_path,
                'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
                (self.rtr_id, usr_id, json.dumps(details), status),
            )[1]

        def sign_in(self, client):
            client.post("/login", data={"email": email, "password": PASSWORD})

        def place(self, client, **extra):
            body = {
                "restaurant_id": self.rtr_id,
                "items": [{"itm_id": itm_id, "qty": 1}],
                "delivery_type": "pickup",
            }
            return client.post("/order", json={**body, **extra})

        def legacy(self, client, query=""):
            return client.get(f"/order?itm_id={itm_id}&delivery=pickup{query}")

        def as_owner(self, client):
            with client.session_transaction() as sess:
                sess["restaurant_mode"] = True
                sess["rtr_id"] = self.rtr_id

    return Shop()


# ---------------------------------------------------------------- charging


def test_an_order_charges_the_wallet(client, shop):
    shop.set_balance(5000)
    shop.sign_in(client)
    assert shop.place(client).get_json()["ok"] is True
    assert shop.balance() == 5000 - TOTAL_CENTS
    ((_, details, status),) = shop.orders()
    assert json.loads(details)["wallet_cents"] == TOTAL_CENTS and status == "Ordered"


def test_an_order_for_exactly_the_balance_is_placed(client, shop):
    shop.set_balance(TOTAL_CENTS)
    shop.sign_in(client)
    assert shop.place(client).status_code == 200
    assert shop.balance() == 0


@pytest.mark.parametrize("balance", [0, TOTAL_CENTS - 1])
def test_an_order_the_wallet_cannot_cover_is_refused(client, shop, balance):
    shop.set_balance(balance)
    shop.sign_in(client)
    response = shop.place(client)
    assert response.status_code == 402
    assert response.get_json() == {
        "ok": False,
        "error": "insufficient_funds",
        "balance_cents": balance,
        "total_cents": TOTAL_CENTS,
    }
    assert shop.balance() == balance and shop.orders() == []


def test_the_second_order_is_refused_once_the_first_spent_the_balance(client, shop):
    shop.set_balance(TOTAL_CENTS + 1)
    shop.sign_in(client)
    assert shop.place(client).status_code == 200
    assert shop.place(client).status_code == 402
    assert shop.balance() == 1 and len(shop.orders()) == 1


@pytest.mark.parametrize("tip", [-0.01, -50, "lots", "nan", "inf", [5]])
def test_a_tip_that_is_not_an_amount_is_refused(client, shop, tip):
    """A negative tip would otherwise lower the charge, or pay the customer."""
    shop.set_balance(5000)
    shop.sign_in(client)
    assert shop.place(client, tip=tip).status_code == 400
    assert shop.balance() == 5000 and shop.orders() == []


def test_a_failed_insert_takes_nothing(client, shop, monkeypatch):
    import proj2.Flask_app as Flask_app

    shop.set_balance(5000)
    shop.sign_in(client)

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(Flask_app, "execute_query", fail)
    monkeypatch.setitem(Flask_app.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setitem(Flask_app.app.config, "TESTING", False)
    assert shop.place(client).status_code == 500
    assert shop.balance() == 5000 and shop.orders() == []


def test_the_legacy_link_charges_too(client, shop):
    shop.set_balance(TOTAL_CENTS)
    shop.sign_in(client)
    assert "ordered=" in shop.legacy(client, "&tip=-50").headers["Location"]
    assert shop.balance() == 0


def test_the_legacy_link_is_refused_when_the_wallet_is_short(client, shop):
    shop.set_balance(1)
    shop.sign_in(client)
    response = shop.legacy(client)
    assert response.headers["Location"].endswith("/orders?unpaid=1")
    assert shop.balance() == 1 and shop.orders() == []
    html = client.get("/orders?unpaid=1").get_data(as_text=True)
    assert "That order was not placed" in html and "$0.01" in html


def test_the_order_slip_shows_the_balance(client, shop):
    shop.set_balance(1234)
    shop.sign_in(client)
    assert "Paid from your wallet ($12.34)" in client.get("/restaurants").get_data(as_text=True)


# ---------------------------------------------------------------- refunds


def test_cancelling_refunds_once(client, shop):
    shop.set_balance(5000)
    shop.sign_in(client)
    ord_id = shop.place(client).get_json()["ord_id"]
    shop.as_owner(client)
    assert client.post(f"/restaurant/orders/{ord_id}/reject").status_code in (302, 303)
    assert shop.balance() == 5000
    assert client.post(f"/restaurant/orders/{ord_id}/reject").status_code == 400
    assert shop.balance() == 5000


@pytest.mark.parametrize("status", ["Ready", "Delivered", "Cancelled"])
def test_an_order_past_cancelling_is_not_refunded(client, shop, status):
    ord_id = shop.add_order(status, wallet_cents=500)
    shop.as_owner(client)
    assert client.post(f"/restaurant/orders/{ord_id}/reject").status_code == 400
    assert shop.balance() == 0


def test_an_order_from_before_wallets_were_charged_refunds_nothing(client, shop):
    ord_id = shop.add_order("Ordered", charges={"total": 25.0})
    shop.as_owner(client)
    client.post(f"/restaurant/orders/{ord_id}/reject")
    assert shop.balance() == 0 and shop.orders()[0][2] == "Cancelled"


@pytest.mark.parametrize("details", [None, "", "not json", "[]", '{"wallet_cents": -5}'])
def test_unreadable_details_refund_nothing(details):
    assert wallet.refund_order(None, 1, details) == 0


def test_a_negative_charge_is_refused():
    with pytest.raises(ValueError):
        wallet.charge(None, 1, -1)


# ---------------------------------------------------------------- starting balance


def test_a_new_account_can_order(client, shop, temp_db_path):
    email = f"new-{uuid.uuid4().hex[:8]}@test.com"
    client.post(
        "/register",
        data={
            "fname": "New",
            "lname": "User",
            "email": email,
            "phone": "9195550100",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    rows, _ = _run(temp_db_path, 'SELECT wallet FROM "User" WHERE email=?', (email,))
    assert rows == [(config.DEFAULT_STARTING_WALLET_CENTS,)]
    client.post("/login", data={"email": email, "password": PASSWORD})
    assert shop.place(client).status_code == 200


@pytest.mark.parametrize(
    "text, cents", [("", 10_000), ("  ", 10_000), ("0", 0), ("25", 2500), ("12.345", 1235)]
)
def test_starting_wallet_setting(text, cents):
    assert config.starting_wallet_cents({config.STARTING_WALLET_ENV: text}) == cents
    assert config.starting_wallet_cents({}) == 10_000


@pytest.mark.parametrize("text", ["-1", "lots", "nan", "inf"])
def test_starting_wallet_must_be_an_amount(text):
    with pytest.raises(ValueError):
        config.starting_wallet_cents({config.STARTING_WALLET_ENV: text})
