"""
Known database bugs, pinned as strict xfail tests (Phase 0 of the DB cleanup plan,
docs/Weeklies_DB_Cleanup_Plan.pdf).

Each test asserts the CORRECT behaviour. Tests still marked xfail fail today; because
the marker is strict, a fix makes the test XPASS, which pytest reports as a failure:
remove the xfail marker in the same commit as the fix. Tests without a marker are
fixed bugs, kept as regression tests.

Every test runs against its own throwaway database so it cannot disturb, or be
disturbed by, the shared session database used by the rest of the suite.
"""

import json
import os
import sqlite3
import tempfile

import pytest
from werkzeug.security import generate_password_hash

import proj2.Flask_app as Flask_app
from proj2.menu_generation import MenuGenerator

PASSWORD = "secret123"
EMAIL = "bugs@x.com"
ALL_DAY = json.dumps({d: [0, 2359] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]})


def _known_bug(phase, reason):
    return pytest.mark.xfail(strict=True, reason=f"Known bug, fixed in Phase {phase}: {reason}")


def _rows(path, sql, params=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@pytest.fixture()
def bug_db(temp_db_path, monkeypatch):
    """
    A fresh DB with the suite's schema (copied from the session DB, not redefined here):
    one user with an allergy, one restaurant stored with lowercase status 'open' (as
    cypress_seed.py and conftest.py store it), one in-stock and one out-of-stock item.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    src = sqlite3.connect(temp_db_path)
    try:
        ddl = [
            r[0]
            for r in src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
    finally:
        src.close()

    conn = sqlite3.connect(path)
    try:
        for stmt in ddl:
            conn.execute(stmt)
        conn.execute(
            'INSERT INTO "Restaurant"(name,email,address,city,state,zip,hours,status) '
            "VALUES ('Cafe Bug','owner@bug.com','1 Main','Raleigh','NC','27606',?,'open')",
            (ALL_DAY,),
        )
        rtr_id = conn.execute("SELECT rtr_id FROM Restaurant").fetchone()[0]
        conn.execute(
            'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
            "VALUES (?, 'In Stock Soup', 'Hot', 500, 300, 1, '')",
            (rtr_id,),
        )
        conn.execute(
            'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
            "VALUES (?, 'Sold Out Pie', 'Gone', 700, 400, 0, '')",
            (rtr_id,),
        )
        conn.execute(
            'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,'
            "preferences,allergies,generated_menu) VALUES ('Bug','Hunter',?,'5550000',?,0,"
            "'spicy','Peanut','')",
            (EMAIL, generate_password_hash(PASSWORD)),
        )
        conn.commit()
        ids = {
            "rtr_id": rtr_id,
            "usr_id": conn.execute('SELECT usr_id FROM "User"').fetchone()[0],
            "in_stock": conn.execute("SELECT itm_id FROM MenuItem WHERE instock=1").fetchone()[0],
            "out_of_stock": conn.execute("SELECT itm_id FROM MenuItem WHERE instock=0").fetchone()[0],
        }
    finally:
        conn.close()

    monkeypatch.setitem(Flask_app.app.config, "DATABASE", path)
    yield {"path": path, **ids}
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture()
def user_client(app, bug_db):
    with app.test_client() as c:
        resp = c.post("/login", data={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code in (302, 303), "login against bug_db failed"
        yield c


def _order_count(bug_db):
    return _rows(bug_db["path"], 'SELECT COUNT(*) FROM "Order"')[0][0]


def _insert_order(bug_db, status, total):
    details = {"items": [{"itm_id": bug_db["in_stock"], "name": "Soup", "qty": 1}],
               "charges": {"total": total}}
    conn = sqlite3.connect(bug_db["path"])
    try:
        cur = conn.execute(
            'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
            (bug_db["rtr_id"], bug_db["usr_id"], json.dumps(details), status),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------- profile


@_known_bug(3, "an empty form field falls back to the old value (Flask_app.py:1525-1527)")
def test_profile_edit_can_clear_allergies(user_client, bug_db):
    user_client.post(
        "/profile/edit", data={"phone": "5550000", "preferences": "", "allergies": ""}
    )
    assert _rows(bug_db["path"], 'SELECT allergies FROM "User"')[0][0] == ""


# ---------------------------------------------------------------- ordering


@_known_bug(3, "negative tips are accepted and produce a negative total")
def test_order_rejects_negative_tip(user_client, bug_db):
    resp = user_client.post(
        "/order",
        json={"restaurant_id": bug_db["rtr_id"],
              "items": [{"itm_id": bug_db["in_stock"], "qty": 1}], "tip": -50},
    )
    assert resp.status_code == 400
    assert _order_count(bug_db) == 0


@_known_bug(3, "ordering does not check stock (swaps do)")
def test_order_rejects_out_of_stock_item(user_client, bug_db):
    resp = user_client.post(
        "/order",
        json={"restaurant_id": bug_db["rtr_id"],
              "items": [{"itm_id": bug_db["out_of_stock"], "qty": 1}]},
    )
    assert resp.status_code in (400, 409)
    assert _order_count(bug_db) == 0


@_known_bug(3, "the legacy GET /order path writes an order (Flask_app.py:2078-2176)")
def test_get_request_does_not_create_order(user_client, bug_db):
    user_client.get(f"/order?itm_id={bug_db['in_stock']}")
    assert _order_count(bug_db) == 0


# ---------------------------------------------------------------- analytics


@pytest.fixture()
def restaurant_client(app, bug_db):
    conn = sqlite3.connect(bug_db["path"])
    try:
        conn.execute(
            "UPDATE Restaurant SET password_HS=? WHERE rtr_id=?",
            (generate_password_hash(PASSWORD), bug_db["rtr_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    with app.test_client() as c:
        resp = c.post("/restaurant/login", data={"email": "owner@bug.com", "password": PASSWORD})
        assert resp.status_code in (302, 303), "restaurant login against bug_db failed"
        yield c


@_known_bug(3, "every analytics page view inserts a new snapshot row")
def test_analytics_views_do_not_multiply_snapshots(restaurant_client, bug_db):
    restaurant_client.get("/restaurant/analytics")
    after_one = _rows(bug_db["path"], "SELECT COUNT(*) FROM Analytics")[0][0]
    for _ in range(3):
        restaurant_client.get("/restaurant/analytics")
    assert _rows(bug_db["path"], "SELECT COUNT(*) FROM Analytics")[0][0] == after_one


@_known_bug(3, "revenue includes cancelled orders (Flask_app.py:209-226)")
def test_analytics_revenue_excludes_cancelled_orders(bug_db):
    _insert_order(bug_db, "Delivered", 10.00)
    _insert_order(bug_db, "Cancelled", 20.00)
    assert Flask_app.record_analytics_snapshot(bug_db["rtr_id"]) is True
    revenue = _rows(
        bug_db["path"],
        "SELECT total_revenue_cents FROM Analytics ORDER BY analytics_id DESC LIMIT 1",
    )[0][0]
    assert revenue == 1000


# ---------------------------------------------------------------- schema


def test_schema_rejects_duplicate_review_for_same_order(bug_db):
    ord_id = _insert_order(bug_db, "Delivered", 10.00)
    conn = sqlite3.connect(bug_db["path"])
    try:
        insert = ('INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,ord_id,created_at) '
                  "VALUES (?,?,?,?,?,?,?)")
        row = (bug_db["rtr_id"], bug_db["usr_id"], "t", 5, "d", ord_id, "2026-11-02T12:00:00")
        conn.execute(insert, row)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, row)
    finally:
        conn.close()


# ---------------------------------------------------------------- missing database


@pytest.mark.parametrize("create_file", [True, False], ids=["empty-file", "no-file"])
def test_missing_database_fails_loudly(app, monkeypatch, tmp_path, create_file):
    path = tmp_path / "missing.db"
    if create_file:
        path.touch()
    monkeypatch.setitem(Flask_app.app.config, "DATABASE", str(path))
    with app.test_client() as c:
        resp = c.post("/login", data={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 500
    assert b"Database not initialised" in resp.data
    assert b"Invalid credentials" not in resp.data
    # and opening it must not have created a database file as a side effect
    assert path.exists() == create_file


# ---------------------------------------------------------------- meal generation


def test_meal_generation_sees_lowercase_open_restaurants(bug_db):
    gen = MenuGenerator(database_path=bug_db["path"])
    assert bug_db["rtr_id"] in set(gen.restaurants["rtr_id"])


@pytest.mark.parametrize("status", ["Open", "OPEN", " open "])
def test_meal_generation_matches_open_status_like_plan_rules(bug_db, status):
    conn = sqlite3.connect(bug_db["path"])
    conn.execute("UPDATE Restaurant SET status = ? WHERE rtr_id = ?", (status, bug_db["rtr_id"]))
    conn.commit()
    conn.close()
    gen = MenuGenerator(database_path=bug_db["path"])
    assert bug_db["rtr_id"] in set(gen.restaurants["rtr_id"])


@pytest.mark.parametrize("status", ["closed", "Closed", "", None, "opening soon"])
def test_meal_generation_excludes_restaurants_not_open(bug_db, status):
    conn = sqlite3.connect(bug_db["path"])
    conn.execute("UPDATE Restaurant SET status = ? WHERE rtr_id = ?", (status, bug_db["rtr_id"]))
    conn.commit()
    conn.close()
    gen = MenuGenerator(database_path=bug_db["path"])
    assert bug_db["rtr_id"] not in set(gen.restaurants["rtr_id"])
