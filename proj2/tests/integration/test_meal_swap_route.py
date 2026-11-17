"""
Integration tests for POST /menu/swap (single-meal swaps).

Each test seeds its own user, restaurants and items in the shared temp DB so the
expected plan contents are known exactly.
"""

import json
import uuid

import pytest
from werkzeug.security import generate_password_hash

from proj2.Flask_app import parse_generated_menu
from proj2.sqlQueries import close_connection, create_connection, execute_query, fetch_one

## 2025-11-03 is a Monday
MONDAY = "2025-11-03"
TUESDAY = "2025-11-04"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ALL_DAY = json.dumps({d: [800, 2200] for d in DAYS})
DINNER_ONLY = json.dumps({d: [1700, 2200] for d in DAYS})


def _insert(conn, sql, params):
    execute_query(conn, sql, params)
    return fetch_one(conn, "SELECT last_insert_rowid()")[0]


@pytest.fixture()
def plan(temp_db_path):
    """Seed a user with a three-slot plan plus a set of candidate replacement items."""
    conn = create_connection(temp_db_path)
    try:
        open_rtr = _insert(
            conn,
            'INSERT INTO "Restaurant"(name,status,hours) VALUES (?,?,?)',
            ("Swap Open", "Open", ALL_DAY),
        )
        dinner_rtr = _insert(
            conn,
            'INSERT INTO "Restaurant"(name,status,hours) VALUES (?,?,?)',
            ("Swap Dinner", "Open", DINNER_ONLY),
        )
        closed_rtr = _insert(
            conn,
            'INSERT INTO "Restaurant"(name,status,hours) VALUES (?,?,?)',
            ("Swap Closed", "Closed", ALL_DAY),
        )

        def item(rtr_id, name, instock=1, allergens=""):
            return _insert(
                conn,
                'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens) '
                "VALUES (?,?,?,?,?,?,?)",
                (rtr_id, name, "", 1000, 500, instock, allergens),
            )

        ids = {
            "breakfast": item(open_rtr, "Oatmeal"),
            "lunch": item(open_rtr, "Sandwich"),
            "dinner": item(open_rtr, "Curry"),
            "tuesday": item(open_rtr, "Tacos"),
            "safe": item(open_rtr, "Rice Bowl", allergens="Soy"),
            "peanut": item(open_rtr, "Satay", allergens="Gluten, Peanuts"),
            "sold_out": item(open_rtr, "Sold Out Pie", instock=0),
            "dinner_only": item(dinner_rtr, "Steak"),
            "closed_rtr": item(closed_rtr, "Closed Soup"),
        }

        menu = (
            f"[{MONDAY},{ids['breakfast']},1],[{MONDAY},{ids['lunch']},2],"
            f"[{MONDAY},{ids['dinner']},3],[{TUESDAY},{ids['tuesday']},2]"
        )
        email = f"swap-{uuid.uuid4().hex[:8]}@test.com"
        usr_id = _insert(
            conn,
            'INSERT INTO "User"(first_name,last_name,email,phone,password_HS,wallet,preferences,allergies,generated_menu) '
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("Swap", "User", email, "5550001111", generate_password_hash("pw123456"), 0, "", "peanuts", menu),
        )
    finally:
        close_connection(conn)
    return {"email": email, "usr_id": usr_id, "menu": menu, "ids": ids}


@pytest.fixture()
def logged_in(client, plan):
    with client.session_transaction() as sess:
        sess["Username"] = "Swap User"
        sess["Email"] = plan["email"]
        sess["usr_id"] = plan["usr_id"]
    return client


def stored_menu(temp_db_path, usr_id):
    conn = create_connection(temp_db_path)
    try:
        return fetch_one(conn, 'SELECT generated_menu FROM "User" WHERE usr_id = ?', (usr_id,))[0]
    finally:
        close_connection(conn)


def swap(client, date, meal, itm_id):
    return client.post("/menu/swap", json={"date": date, "meal": meal, "itm_id": itm_id})


def test_swap_replaces_target_slot(logged_in, plan, temp_db_path):
    ids = plan["ids"]
    resp = swap(logged_in, MONDAY, 2, ids["safe"])
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["previous_itm_id"] == ids["lunch"]
    assert data["itm_id"] == ids["safe"]

    saved = stored_menu(temp_db_path, plan["usr_id"])
    assert data["generated_menu"] == saved
    assert {"itm_id": ids["safe"], "meal": 2} in parse_generated_menu(saved)[MONDAY]


def test_swap_keeps_other_slots_intact(logged_in, plan, temp_db_path):
    ids = plan["ids"]
    before = parse_generated_menu(plan["menu"])
    assert swap(logged_in, MONDAY, 2, ids["safe"]).status_code == 200
    after = parse_generated_menu(stored_menu(temp_db_path, plan["usr_id"]))

    assert after[TUESDAY] == before[TUESDAY]
    assert [e for e in after[MONDAY] if e["meal"] != 2] == [e for e in before[MONDAY] if e["meal"] != 2]
    assert len(after[MONDAY]) == len(before[MONDAY])


def test_swap_updates_session(logged_in, plan):
    swap(logged_in, MONDAY, 1, plan["ids"]["safe"])
    with logged_in.session_transaction() as sess:
        assert f"[{MONDAY},{plan['ids']['safe']},1]" in sess["GeneratedMenu"]


def test_swap_twice_on_different_slots(logged_in, plan, temp_db_path):
    ids = plan["ids"]
    assert swap(logged_in, MONDAY, 1, ids["safe"]).status_code == 200
    assert swap(logged_in, MONDAY, 3, ids["dinner_only"]).status_code == 200
    assert stored_menu(temp_db_path, plan["usr_id"]) == (
        f"[{MONDAY},{ids['safe']},1],[{MONDAY},{ids['lunch']},2],"
        f"[{MONDAY},{ids['dinner_only']},3],[{TUESDAY},{ids['tuesday']},2]"
    )


@pytest.mark.parametrize(
    "key,meal,code,status",
    [
        ("peanut", 2, "allergen", 409),
        ("sold_out", 2, "out_of_stock", 409),
        ("closed_rtr", 2, "restaurant_unavailable", 409),
        ("dinner_only", 2, "restaurant_closed", 409),
        ("lunch", 2, "same_item", 400),
    ],
)
def test_rejected_swap_leaves_plan_unchanged(logged_in, plan, temp_db_path, key, meal, code, status):
    resp = swap(logged_in, MONDAY, meal, plan["ids"][key])
    assert resp.status_code == status
    assert resp.get_json()["error"] == code
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


def test_allergen_check_uses_stored_allergies(logged_in, plan, temp_db_path):
    """Client-supplied allergen fields are ignored; the account's allergies are enforced."""
    resp = logged_in.post(
        "/menu/swap",
        json={"date": MONDAY, "meal": 2, "itm_id": plan["ids"]["peanut"], "allergens": ""},
    )
    assert resp.status_code == 409
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


def test_unknown_item(logged_in, plan, temp_db_path):
    resp = swap(logged_in, MONDAY, 2, 999999)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "item_not_found"
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


def test_empty_slot(logged_in, plan, temp_db_path):
    resp = swap(logged_in, TUESDAY, 1, plan["ids"]["safe"])
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "slot_not_found"
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


@pytest.mark.parametrize(
    "body,code",
    [
        ({"date": "2025-02-30", "meal": 1, "itm_id": 1}, "invalid_slot"),
        ({"date": "", "meal": 1, "itm_id": 1}, "invalid_slot"),
        ({"date": MONDAY, "meal": 4, "itm_id": 1}, "invalid_slot"),
        ({"date": MONDAY, "meal": "x", "itm_id": 1}, "invalid_slot"),
        ({"date": MONDAY, "meal": 1}, "invalid_item"),
        ({"date": MONDAY, "meal": 1, "itm_id": "abc"}, "invalid_item"),
    ],
)
def test_invalid_input(logged_in, plan, temp_db_path, body, code):
    resp = logged_in.post("/menu/swap", json=body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == code
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


def test_requires_login_json(client):
    resp = client.post("/menu/swap", json={"date": MONDAY, "meal": 1, "itm_id": 1})
    assert resp.status_code == 401


def test_requires_login_form(client):
    resp = client.post("/menu/swap", data={"date": MONDAY, "meal": "1", "itm_id": "1"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_form_swap_redirects_to_slot_month(logged_in, plan, temp_db_path):
    ids = plan["ids"]
    resp = logged_in.post("/menu/swap", data={"date": MONDAY, "meal": "3", "itm_id": str(ids["safe"])})
    assert resp.status_code == 302
    assert "/2025/11" in resp.headers["Location"]
    assert "swapped=1" in resp.headers["Location"]
    assert f"[{MONDAY},{ids['safe']},3]" in stored_menu(temp_db_path, plan["usr_id"])


def test_form_rejection_redirects_with_error(logged_in, plan, temp_db_path):
    resp = logged_in.post(
        "/menu/swap", data={"date": MONDAY, "meal": "2", "itm_id": str(plan["ids"]["peanut"])}
    )
    assert resp.status_code == 302
    assert "swap_error=allergen" in resp.headers["Location"]
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


# ---- GET /menu/swap/options ----


def options(client, date, meal):
    return client.get(f"/menu/swap/options?date={date}&meal={meal}")


def test_options_only_list_eligible_items(logged_in, plan):
    ids = plan["ids"]
    resp = options(logged_in, MONDAY, 2)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["current_itm_id"] == ids["lunch"]
    listed = {o["itm_id"] for o in data["options"]}

    assert ids["safe"] in listed
    assert ids["breakfast"] in listed
    for blocked in ("lunch", "peanut", "sold_out", "closed_rtr", "dinner_only"):
        assert ids[blocked] not in listed


def test_options_depend_on_meal_time(logged_in, plan):
    listed = {o["itm_id"] for o in options(logged_in, MONDAY, 3).get_json()["options"]}
    assert plan["ids"]["dinner_only"] in listed


def test_options_include_display_fields(logged_in, plan):
    opts = options(logged_in, MONDAY, 2).get_json()["options"]
    safe = next(o for o in opts if o["itm_id"] == plan["ids"]["safe"])
    assert safe["name"] == "Rice Bowl"
    assert safe["restaurant_name"] == "Swap Open"
    assert safe["price"] == 1000


def test_every_listed_option_can_be_swapped_in(logged_in, plan):
    opts = options(logged_in, MONDAY, 2).get_json()["options"]
    assert opts
    assert swap(logged_in, MONDAY, 2, opts[0]["itm_id"]).status_code == 200


def test_options_listing_does_not_modify_plan(logged_in, plan, temp_db_path):
    options(logged_in, MONDAY, 2)
    assert stored_menu(temp_db_path, plan["usr_id"]) == plan["menu"]


def test_options_empty_slot(logged_in, plan):
    resp = options(logged_in, TUESDAY, 3)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "slot_not_found"


@pytest.mark.parametrize("date,meal", [("bad", 1), (MONDAY, 0), (MONDAY, "")])
def test_options_invalid_slot(logged_in, plan, date, meal):
    assert options(logged_in, date, meal).status_code == 400


def test_options_requires_login(client):
    assert options(client, MONDAY, 1).status_code == 401


# ---- Calendar banner and controls ----


def test_calendar_shows_swap_buttons(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert html.count('class="swap-btn"') == 4
    assert 'data-date="2025-11-03"' in html
    assert 'id="swapModal"' in html


def test_calendar_success_banner(logged_in, plan):
    html = logged_in.get("/2025/11?swapped=1").get_data(as_text=True)
    assert "Meal swapped" in html


def test_calendar_error_banner(logged_in, plan):
    html = logged_in.get("/2025/11?swap_error=allergen").get_data(as_text=True)
    assert "contains one of your allergens" in html


def test_calendar_unknown_error_code_is_generic(logged_in, plan):
    html = logged_in.get("/2025/11?swap_error=<script>").get_data(as_text=True)
    assert "That meal could not be swapped." in html
    assert "<script>" not in html.split('class="flash')[1].split("</div>")[0]


def test_calendar_without_swap_params_has_no_banner(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert 'class="flash' not in html


# ---- Variety ----


def test_options_are_ranked_by_variety(logged_in, plan):
    opts = options(logged_in, MONDAY, 2).get_json()["options"]
    scores = [o["variety"] for o in opts]
    assert scores == sorted(scores, reverse=True)
    # The rice bowl is not planned anywhere nearby; these repeat a neighbouring meal.
    order = [o["itm_id"] for o in opts]
    for repeat in ("breakfast", "dinner", "tuesday"):
        assert order.index(plan["ids"]["safe"]) < order.index(plan["ids"][repeat])


def test_calendar_shows_weekly_variety(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    card = html.split('aria-label="Plan variety"')[1].split("</section>")[0]
    assert "2025-11-03" in card
    # Four different dishes from one restaurant, with no other tags: 60% varied
    assert "60%" in card
    assert "Oatmeal (Mon breakfast) and Sandwich (Mon lunch): same restaurant" in card


def test_calendar_shows_readable_hours(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert "Daily 8 am–10 pm" in html
    assert '{"Mon"' not in html
