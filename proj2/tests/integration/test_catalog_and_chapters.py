"""The Restaurants page as a catalog (index, catalog page, order slip) and the Profile
page as chapters (Particulars, Diet, Wallet, Password)."""

import json
import re
import uuid
from datetime import datetime

from werkzeug.security import generate_password_hash

from proj2.Flask_app import diet_summary, open_now
from proj2.sqlQueries import close_connection, create_connection, execute_query, fetch_one


def _db(path, sql, params=()):
    conn = create_connection(path)
    try:
        execute_query(conn, sql, params)
        return fetch_one(conn, "SELECT last_insert_rowid()")[0]
    finally:
        close_connection(conn)


def _fresh_user(client, path, allergies="", preferences=""):
    """A new user, logged in (the shared test database holds other tests' users and orders)."""
    email = f"cat-{uuid.uuid4().hex[:8]}@test.com"
    usr_id = _db(
        path,
        'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies) '
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "Ada",
            "Page",
            email,
            "5550101",
            generate_password_hash("secret123"),
            1234,
            preferences,
            allergies,
        ),
    )
    resp = client.post("/login", data={"email": email, "password": "secret123"})
    assert resp.status_code in (302, 303)
    return usr_id


def _page_json(html, name):
    return json.loads(re.search(rf"window\.{name} = (.*?);\n", html).group(1))


# ---------------------------------------------------------------- open_now


def test_open_now_reads_the_hours():
    hours = json.dumps({"Mon": [1100, 2200]})
    monday_noon = datetime(2026, 11, 16, 12, 0)
    monday_late = datetime(2026, 11, 16, 23, 0)
    assert open_now(hours, "open", monday_noon) is True
    assert open_now(hours, "open", monday_late) is False
    assert open_now(hours, "open", datetime(2026, 11, 17, 12, 0)) is False  # no Tuesday hours


def test_open_now_closed_status_and_unknown_hours():
    assert open_now(json.dumps({"Mon": [0, 2359]}), "Closed", datetime(2026, 11, 16, 12)) is False
    assert open_now("11am to 10pm", "open", datetime(2026, 11, 16, 12)) is None
    assert open_now(None, "open", datetime(2026, 11, 16, 12)) is None


# ---------------------------------------------------------------- Restaurants: catalog


def test_restaurants_page_flags_dishes_against_my_allergies(
    client, temp_db_path, seed_minimal_data
):
    # seed_minimal_data first: it adopts the first restaurant in the shared database as "Cafe One"
    rtr_id = _db(
        temp_db_path,
        'INSERT INTO "Restaurant"(name,city,status,hours) VALUES (?,?,?,?)',
        ("Catalog Kitchen", "Raleigh", "open", json.dumps({"Mon": [0, 2359]})),
    )
    risky = _db(
        temp_db_path,
        'INSERT INTO "MenuItem"(rtr_id,name,price,calories,instock,allergens) VALUES (?,?,?,?,?,?)',
        (rtr_id, "Pollen Pie", 500, 300, 1, "ZZPollen, wheat"),
    )
    safe = _db(
        temp_db_path,
        'INSERT INTO "MenuItem"(rtr_id,name,price,calories,instock,allergens) VALUES (?,?,?,?,?,?)',
        (rtr_id, "Plain Toast", 300, 200, 1, "wheat"),
    )
    usr_id = _fresh_user(client, temp_db_path, allergies="zzpollen, ZZDust")
    _db(
        temp_db_path,
        'INSERT INTO "Review"(rtr_id,usr_id,title,rating,description,created_at) VALUES (?,?,?,?,?,?)',
        (rtr_id, usr_id, "t", 4, "d", "2026-11-01"),
    )
    html = client.get("/restaurants").get_data(as_text=True)

    items = {it["itm_id"]: it for it in _page_json(html, "__ITEMS__")}
    assert items[risky]["conflicts"] == ["zzpollen"]
    assert items[safe]["conflicts"] == []
    rest = next(r for r in _page_json(html, "__RESTS__") if r["rtr_id"] == rtr_id)
    assert rest["review_count"] == 1 and rest["rating"] == 4.0
    assert rest["open_now"] in (True, False)  # JSON hours: the page can tell
    assert _page_json(html, "__MY_ALLERGIES__") == ["zzpollen", "ZZDust"]


def test_restaurants_page_has_index_catalog_and_slip(client, login_session):
    html = client.get("/restaurants").get_data(as_text=True)
    for marker in (
        'id="restList"',
        'id="catalogPage"',
        'id="cartSection"',
        'id="cartGroups"',
        'id="clearCartBtn"',
        'id="fOpen"',
        'id="fSafe"',
        'id="fLight"',
        "Order Slip",
    ):
        assert marker in html, marker
    assert "accordion" not in html  # the old accordion list is gone


def test_allergen_filter_is_off_without_allergies(client, temp_db_path):
    _fresh_user(client, temp_db_path, allergies="")
    html = client.get("/restaurants").get_data(as_text=True)
    box = html.split('id="fSafe"')[1].split(">")[0]
    assert "disabled" in box and "checked" not in box


# ---------------------------------------------------------------- Profile: chapters


def test_diet_summary_counts_the_dishes_set_aside(temp_db_path, seed_minimal_data):
    rtr_id = seed_minimal_data["rtr_id"]
    _db(
        temp_db_path,
        'INSERT INTO "MenuItem"(rtr_id,name,price,instock,allergens) VALUES (?,?,?,?,?)',
        (rtr_id, "Odd Dish", 100, 1, "ZZMoss"),
    )
    _db(
        temp_db_path,
        'INSERT INTO "MenuItem"(rtr_id,name,price,instock,allergens) VALUES (?,?,?,?,?)',
        (rtr_id, "Gone Dish", 100, 0, "ZZMoss"),  # out of stock: not on offer
    )
    conn = create_connection(temp_db_path)
    try:
        d = diet_summary(conn, "zzmoss, ", " Vegan ,Spicy")
        on_offer = fetch_one(
            conn, 'SELECT COUNT(*) FROM "MenuItem" WHERE instock IS NULL OR instock = 1'
        )[0]
    finally:
        close_connection(conn)
    assert d == {
        "allergies": ["zzmoss"],
        "preferences": ["Vegan", "Spicy"],
        "set_aside": 1,
        "dishes": on_offer,
    }


def test_profile_has_four_chapters_and_contents(client, temp_db_path):
    _fresh_user(client, temp_db_path)
    html = client.get("/profile").get_data(as_text=True)
    for anchor in ("particulars", "diet", "wallet", "password"):
        assert f'id="{anchor}"' in html and f'href="#{anchor}"' in html
    assert "Ada Page" in html and "5550101" in html
    assert "$12.34" in html  # wallet, stored in cents


def test_profile_diet_sentence(client, temp_db_path):
    _fresh_user(client, temp_db_path, allergies="Peanuts,Soy", preferences="Vegan")
    html = client.get("/profile").get_data(as_text=True)
    diet = html.split('id="dietSummary"')[1].split("</p>")[0]
    assert "Allergic to <strong>Peanuts</strong> and <strong>Soy</strong>, which sets aside" in diet
    assert re.search(r"sets aside \d+ of the \d+ dishes on offer", diet)
    assert "Required diets include <strong>Vegan</strong>." in diet


def test_profile_diet_sentence_without_choices(client, temp_db_path):
    _fresh_user(client, temp_db_path)
    diet = (
        client.get("/profile").get_data(as_text=True).split('id="dietSummary"')[1].split("</p>")[0]
    )
    assert "No allergies recorded" in diet and "Required diets include" not in diet


def test_profile_wallet_names_the_last_order(client, temp_db_path, seed_minimal_data):
    usr_id = _fresh_user(client, temp_db_path)
    html = client.get("/profile").get_data(as_text=True)
    assert "No orders yet." in html and 'href="/restaurants"' in html.split('id="wallet"')[1]
    details = {"placed_at": "2026-11-10T12:30:00", "charges": {"total": 9.5}, "items": []}
    _db(
        temp_db_path,
        'INSERT INTO "Order"(rtr_id,usr_id,details,status) VALUES (?,?,?,?)',
        (seed_minimal_data["rtr_id"], usr_id, json.dumps(details), "Delivered"),
    )
    wallet = (
        client.get("/profile").get_data(as_text=True).split('id="wallet"')[1].split("</section>")[0]
    )
    assert "Last order on 2026-11-10" in wallet and "(delivered)" in wallet
    assert 'href="/orders"' in wallet


def test_password_form_sits_on_the_page(client, temp_db_path):
    _fresh_user(client, temp_db_path)
    html = client.get("/profile").get_data(as_text=True)
    chapter = html.split('id="password"')[1].split("</section>")[0]
    assert 'action="/profile/change-password"' in chapter
    for field in ("pwCurrent", "pwNew", "pwConfirm", "submitPwBtn"):
        assert f'id="{field}"' in chapter
    assert "pwModal" not in html and "openChangePwBtn" not in html


def test_phone_change_opens_the_edit_pop_up(client, temp_db_path):
    _fresh_user(client, temp_db_path)
    html = client.get("/profile").get_data(as_text=True)
    particulars = html.split('id="particulars"')[1].split("</section>")[0]
    assert "js-open-edit" in particulars
    phone_form = html.split('id="editProfileForm"')[1].split("</form>")[0]
    assert 'name="phone"' in phone_form
    assert 'name="allergies[]"' not in phone_form


def test_diet_chapter_contains_one_form_for_constraints_and_sliders(client, temp_db_path):
    _fresh_user(client, temp_db_path)
    html = client.get("/profile").get_data(as_text=True)
    chapter = html.split('id="diet"')[1].split("</section>")[0]
    assert 'id="dietProfileForm"' in chapter
    assert 'name="allergies[]"' in chapter
    assert 'name="diets[]"' in chapter
    assert 'name="weekly_cap"' in chapter
    assert 'id="optimization-preferences"' in chapter
    assert chapter.count("<form") == 1
    assert 'name="variety_weight" type="range" min="0" max="100"' in chapter


def test_dishes_are_numbered_per_restaurant(client, login_session):
    html = client.get("/restaurants").get_data(as_text=True)
    assert "No. ${dishNo.get(it.itm_id)}" in html  # numbered within the restaurant
    assert "No. ${it.itm_id}" not in html  # not by the database id


def test_diet_paragraph_has_no_drop_cap(client, temp_db_path):
    _fresh_user(client, temp_db_path, allergies="Soy")
    html = client.get("/profile").get_data(as_text=True)
    assert '<p id="dietSummary">' in html and "first-letter" not in html
