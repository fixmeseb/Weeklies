"""
Integration tests for POST /menu/swap (single-meal swaps).

Each test seeds its own user, restaurants and items in the shared temp DB so the
expected plan contents are known exactly.
"""

import json
import re
import uuid
from datetime import date, timedelta

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
            (
                "Swap",
                "User",
                email,
                "5550001111",
                generate_password_hash("pw123456"),
                0,
                "",
                "peanuts",
                menu,
            ),
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
    assert [e for e in after[MONDAY] if e["meal"] != 2] == [
        e for e in before[MONDAY] if e["meal"] != 2
    ]
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
def test_rejected_swap_leaves_plan_unchanged(
    logged_in, plan, temp_db_path, key, meal, code, status
):
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
    resp = logged_in.post(
        "/menu/swap", data={"date": MONDAY, "meal": "3", "itm_id": str(ids["safe"])}
    )
    assert resp.status_code == 302
    assert "/2025/11" in resp.headers["Location"]
    assert "swapped=1" in resp.headers["Location"]
    assert "week=2025-11-03" in resp.headers["Location"]  # the Almanac style stays on the week
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
    # The generate form's error box is always there, but hidden until it has an error
    shown = [
        tag for tag in re.findall(r'<div[^>]*class="flash[^>]*>', html) if " hidden" not in tag
    ]
    assert shown == []


# ---- Variety ----


def test_options_are_ranked_by_variety(logged_in, plan):
    opts = options(logged_in, MONDAY, 2).get_json()["options"]
    scores = [o["variety"] for o in opts]
    assert scores == sorted(scores, reverse=True)
    # The rice bowl is not planned anywhere nearby; these repeat a neighbouring meal.
    order = [o["itm_id"] for o in opts]
    for repeat in ("breakfast", "dinner", "tuesday"):
        assert order.index(plan["ids"]["safe"]) < order.index(plan["ids"][repeat])


def test_insights_show_weekly_variety(logged_in, plan):
    html = logged_in.get("/insights/2025/11").get_data(as_text=True)
    card = html.split('aria-label="Plan variety"')[1].split("</section>")[0]
    assert "2025-11-03" in card
    # Four different dishes from one restaurant and no other tags. Only 5.0 of the
    # 19.5 total weight is comparable, so variety.distance shrinks the pair toward
    # NEUTRAL_DISTANCE: 53%, not the 60% an undescribed catalog used to be credited with.
    assert "53%" in card
    assert "Oatmeal (Mon breakfast) and Sandwich (Mon lunch): same restaurant" in card


def test_calendar_shows_readable_hours(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert "Daily 8 am–10 pm" in html
    assert '{"Mon"' not in html


def test_insights_tab_holds_the_weekly_cards(logged_in, plan):
    html = logged_in.get("/insights/2025/11").get_data(as_text=True)
    assert "Plan Insights" in html
    assert 'aria-label="Weekly item totals"' in html and 'aria-label="Plan variety"' in html
    assert "<td>2025-11-03</td><td>$40.00</td>" in html
    assert 'href="/insights/2025/10"' in html and 'href="/insights/2025/12"' in html
    assert 'href="/2025/11"' in html  # back to the same month on the calendar


def test_calendar_no_longer_shows_the_weekly_cards(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert 'aria-label="Weekly item totals"' not in html
    assert 'aria-label="Plan variety"' not in html
    assert '<a href="/insights">Insights</a>' in html


def test_generate_form_sits_below_the_calendar(logged_in, plan):
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert html.index('class="cal-grid std-only"') < html.index('id="new-plan"')
    assert html.index('class="almanac-only"') < html.index('id="new-plan"')
    form = html.split('id="new-plan"')[1]
    assert 'action="/menu/generate"' in form and 'name="weekly_cap"' in form
    profile = logged_in.get("/profile").get_data(as_text=True)
    assert 'action="/menu/generate"' not in profile
    assert "Generate Meal Plan" not in profile


def test_insights_needs_login_and_a_real_month(client, logged_in, plan):
    assert logged_in.get("/insights/2025/13").status_code == 404
    assert logged_in.get("/insights").status_code == 200
    logged_in.get("/logout")
    response = client.get("/insights")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_calendar_has_the_almanac_style(logged_in, plan):
    """The Seed Catalog & Almanac style: the same week drawn as an almanac page."""
    html = logged_in.get("/2025/11").get_data(as_text=True)
    page = html.split('<article class="al" aria-label="Week of 2025-11-03">')[1].split(
        "</article>"
    )[0]
    assert "Vol. MMXXV · No. 45" in page
    assert "Week of the 3rd to the 9th of November, 2025" in page
    assert "4 meals from 1 kitchen, set out by the day" in page
    # Entries open the same swap dialog as the month grid, and can be ordered
    assert 'class="al-e swap-btn" data-meal="1" data-date="2025-11-03"' in page
    assert 'class="al-order order-btn"' in page
    assert "Fallow" in page  # empty slots later in the week
    assert "53 parts in 100" in page and "Monotonous." in page
    assert "4 different dishes among 4." in page
    assert "Oatmeal (Mon breakfast) and Sandwich (Mon lunch): same restaurant." in page
    # Only one layout shows at a time; theme.js picks which
    assert 'class="cal-grid std-only"' in html
    assert 'class="almanac-only"' in html


def test_almanac_style_for_a_month_with_no_plan(logged_in, plan):
    html = logged_in.get("/2025/1").get_data(as_text=True)
    assert "Nothing is sown for the 30th of December, 2024 to the 5th of January, 2025 yet." in html
    assert '<article class="al"' not in html


def _week_nav(html):
    return html.split('id="weekNav"')[1].split('<div class="almanac-only">')[0]


def test_almanac_style_moves_by_week(logged_in, plan):
    """Prev and Next go to the weeks either side, planned or not, across months."""
    nav = _week_nav(logged_in.get("/2025/11").get_data(as_text=True))
    assert "Week of the 3rd to the 9th of November, 2025" in nav
    assert 'href="/?week=2025-10-27"' in nav and 'href="/?week=2025-11-10"' in nav

    html = logged_in.get("/?week=2025-10-27").get_data(as_text=True)
    assert "Nothing is sown for the 27th of October to the 2nd of November, 2025 yet." in html
    assert 'href="/?week=2025-11-03"' in _week_nav(html)

    html = logged_in.get("/?week=2025-11-05").get_data(as_text=True)  # any day of the week
    assert html.count('<article class="al"') == 1
    assert 'aria-label="Week of 2025-11-03"' in html


def test_almanac_style_draws_one_week_of_the_month(logged_in, plan, temp_db_path):
    later = f"{plan['menu']},[2025-11-12,{plan['ids']['dinner']},3]"
    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn, 'UPDATE "User" SET generated_menu=? WHERE usr_id=?', (later, plan["usr_id"])
        )
    finally:
        close_connection(conn)
    html = logged_in.get("/2025/11").get_data(as_text=True)
    assert 'aria-label="Week of 2025-11-03"' in html  # the first one planned
    assert 'aria-label="Week of 2025-11-10"' not in html
    html = logged_in.get("/?week=2025-11-10").get_data(as_text=True)
    assert 'aria-label="Week of 2025-11-10"' in html


def test_month_buttons_still_move_by_month(logged_in, plan):
    html = logged_in.get("/?week=2025-11-10").get_data(as_text=True)
    toolbar = html.split('class="calendar-toolbar std-only"')[1].split('id="weekNav"')[0]
    assert "November 2025" in toolbar
    assert 'href="/2025/10"' in toolbar and 'href="/2025/12"' in toolbar


@pytest.mark.parametrize("week", ["", "nonsense", "2025-02-30", "0001-01-01", "9999-12-31"])
def test_an_unusable_week_shows_this_week(logged_in, plan, week):
    response = logged_in.get("/", query_string={"week": week})
    today = date.today()
    assert response.status_code == 200
    monday = today - timedelta(days=today.weekday())
    assert f'href="/?week={monday + timedelta(days=7)}"' in response.get_data(as_text=True)
