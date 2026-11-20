"""
Integration tests for daily nutrition targets on /menu/generate: the JSON report, bad
input, and the calendar notice after a form submission
"""

import json
import sqlite3

import pytest

from proj2.menu_generation import DAYS_OF_WEEK


@pytest.fixture
def nutrition_catalog(app, temp_db_path, seed_minimal_data):
    """One open restaurant with a single 700 kcal, 40 g protein item in stock; restores the DB."""
    snapshot = sqlite3.connect(":memory:")
    with sqlite3.connect(temp_db_path) as conn:
        conn.backup(snapshot)
        restaurant = seed_minimal_data["rtr_id"]
        conn.execute(
            'UPDATE Restaurant SET hours=?, status="Open" WHERE rtr_id=?',
            (json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK}), restaurant),
        )
        # Other tests can leave the shared user with a diet, allergies or saved targets
        conn.execute(
            'UPDATE "User" SET generated_menu="", preferences="", allergies="",'
            ' nutrition_targets="", strict_targets=0 WHERE usr_id=?',
            (seed_minimal_data["usr_id"],),
        )
        item = conn.execute(
            "SELECT itm_id FROM MenuItem WHERE rtr_id=? ORDER BY itm_id LIMIT 1", (restaurant,)
        ).fetchone()[0]
        conn.execute("UPDATE MenuItem SET instock=0")
        conn.execute(
            "UPDATE MenuItem SET price=500, calories=700, protein_g=40, sodium_mg=900, instock=1,"
            ' allergens="" WHERE itm_id=?',
            (item,),
        )
    yield item
    with sqlite3.connect(temp_db_path) as conn:
        snapshot.backup(conn)
    snapshot.close()


def payload(**overrides):
    data = {"start_date": "2026-10-05", "meal_numbers": [3], "number_of_days": 2}
    data.update(overrides)
    return data


def saved_menu(temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        return conn.execute(
            'SELECT generated_menu FROM "User" WHERE email="test@x.com"'
        ).fetchone()[0]


def test_json_reports_each_day_against_the_targets(client, login_session, nutrition_catalog):
    response = client.post(
        "/menu/generate", json=payload(calorie_min=600, calorie_max="800", protein_min=30)
    )
    assert response.status_code == 200
    report = response.get_json()["nutrition"]
    day = {
        "totals": {"calories": 700.0, "protein_g": 40.0},
        "miss": {"calories": 0.0, "protein_g": 0.0},
    }
    assert report == {
        "targets": {"calories": {"min": 600, "max": 800}, "protein_g": {"min": 30, "max": None}},
        "days": [dict(day, date="2026-10-05"), dict(day, date="2026-10-06")],
        "days_outside": 0,
        "outside_by_nutrient": {"calories": 0, "protein_g": 0},
    }


def test_unreachable_target_still_saves_the_plan_and_reports_the_miss(
    client, login_session, nutrition_catalog, temp_db_path
):
    response = client.post("/menu/generate", json=payload(protein_min=50, sodium_max=1000))
    assert response.status_code == 200
    data = response.get_json()
    assert data["nutrition"]["days_outside"] == 2
    assert data["nutrition"]["outside_by_nutrient"] == {"protein_g": 2, "sodium_mg": 0}
    assert data["nutrition"]["days"][0]["miss"]["protein_g"] == pytest.approx(0.2)
    assert saved_menu(temp_db_path) == data["generated_menu"]


def test_without_targets_the_response_has_no_nutrition_report(
    client, login_session, nutrition_catalog
):
    response = client.post("/menu/generate", json=payload())
    assert response.status_code == 200
    assert response.get_json()["nutrition"] is None


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"calorie_min": "abc"}, "calories minimum must be a whole number from 1 to 10,000 kcal"),
        ({"protein_max": "0"}, "protein maximum must be a whole number from 1 to 1,000 g"),
        ({"fat_min": "90", "fat_max": "60"}, "fat minimum cannot be more than the maximum"),
    ],
)
def test_bad_target_is_rejected_without_changing_the_plan(
    client, login_session, nutrition_catalog, temp_db_path, fields, message
):
    response = client.post("/menu/generate", json=payload(**fields))
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    assert saved_menu(temp_db_path) == ""


def test_form_submission_shows_the_miss_once_on_the_calendar(
    client, login_session, nutrition_catalog
):
    form = {"start_date": "2026-10-05", "days": "2", "meal3": "on", "calorie_min": "2000"}
    response = client.post("/menu/generate", data=form)
    assert response.status_code in (302, 303)
    page = client.get("/").get_data(as_text=True)
    assert (
        "2 of 2 planned days miss your daily targets (calories at least 2,000 kcal on 2 days)."
        in page
    )
    assert "miss your daily targets" not in client.get("/").get_data(as_text=True)  # shown once


def test_plan_form_offers_a_range_for_each_nutrient(client, login_session):
    page = client.get("/").get_data(as_text=True)
    for field in ("calorie", "protein", "carbs", "fat", "sodium"):
        assert f'name="{field}_min"' in page and f'name="{field}_max"' in page


@pytest.mark.parametrize("flag", [True, "on", "1"])
def test_strict_target_out_of_reach_is_refused_without_changing_the_plan(
    client, login_session, nutrition_catalog, temp_db_path, flag
):
    response = client.post("/menu/generate", json=payload(protein_min=50, strict_targets=flag))
    assert response.status_code == 422
    assert "can meet your daily target of protein at least 50 g" in response.get_json()["error"]
    assert saved_menu(temp_db_path) == ""


def test_strict_target_within_reach_plans_normally(client, login_session, nutrition_catalog):
    response = client.post("/menu/generate", json=payload(protein_min=30, strict_targets=True))
    assert response.status_code == 200
    assert response.get_json()["nutrition"]["days_outside"] == 0


def test_plan_form_offers_strict_targets(client, login_session):
    assert 'name="strict_targets"' in client.get("/").get_data(as_text=True)


# ---------------------------------------------------------------- saved targets


def saved_targets(temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        text, strict = conn.execute(
            'SELECT nutrition_targets, strict_targets FROM "User" WHERE email="test@x.com"'
        ).fetchone()
    return (json.loads(text) if text else {}), strict


FORM = {"start_date": "2026-10-05", "days": "2", "meal3": "on"}


def test_form_saves_its_targets_and_the_plan_form_opens_with_them(
    client, login_session, nutrition_catalog, temp_db_path
):
    form = dict(FORM, calorie_min="600", calorie_max="800", sodium_max="2300", protein_min="")
    assert client.post("/menu/generate", data=form).status_code in (302, 303)
    assert saved_targets(temp_db_path) == (
        {"calories": {"min": 600, "max": 800}, "sodium_mg": {"min": None, "max": 2300}},
        0,
    )
    page = client.get("/").get_data(as_text=True)
    assert 'name="calorie_min" min="1"' in page  # sanity: the field is there
    assert 'value="600"' in page and 'value="800"' in page and 'value="2300"' in page
    assert "checked" not in page.split('id="strict_targets"')[1].split(">")[0]


def test_the_forms_own_fetch_saves_too(client, login_session, nutrition_catalog, temp_db_path):
    # profile.html's script posts the form data asking for JSON
    form = dict(FORM, protein_min="30", strict_targets="on")
    response = client.post("/menu/generate", data=form, headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert saved_targets(temp_db_path) == ({"protein_g": {"min": 30, "max": None}}, 1)
    page = client.get("/").get_data(as_text=True)
    assert 'value="30"' in page
    assert "checked" in page.split('id="strict_targets"')[1].split(">")[0]


def test_clearing_the_form_clears_the_saved_targets(
    client, login_session, nutrition_catalog, temp_db_path
):
    client.post("/menu/generate", data=dict(FORM, calorie_min="600"))
    client.post("/menu/generate", data=FORM)
    assert saved_targets(temp_db_path) == ({}, 0)


def test_a_refused_strict_plan_still_remembers_what_was_asked(
    client, login_session, nutrition_catalog, temp_db_path
):
    form = dict(FORM, protein_min="50", strict_targets="on")
    response = client.post("/menu/generate", data=form, headers={"Accept": "application/json"})
    assert response.status_code == 422
    assert saved_menu(temp_db_path) == ""
    assert saved_targets(temp_db_path) == ({"protein_g": {"min": 50, "max": None}}, 1)


def test_a_bad_target_is_not_saved(client, login_session, nutrition_catalog, temp_db_path):
    client.post("/menu/generate", data=dict(FORM, calorie_min="600"))
    client.post("/menu/generate", data=dict(FORM, calorie_min="lots"))
    assert saved_targets(temp_db_path) == ({"calories": {"min": 600, "max": None}}, 0)


def test_json_clients_change_saved_targets_only_when_asked(
    client, login_session, nutrition_catalog, temp_db_path
):
    client.post("/menu/generate", json=payload(protein_min=30))
    assert saved_targets(temp_db_path) == ({}, 0)
    client.post("/menu/generate", json=payload(protein_min=30, save_targets=True))
    assert saved_targets(temp_db_path) == ({"protein_g": {"min": 30, "max": None}}, 0)


def test_the_forms_fetch_gets_the_calendar_notice(client, login_session, nutrition_catalog):
    form = dict(FORM, calorie_min="2000")
    response = client.post("/menu/generate", data=form, headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert "miss your daily targets" in client.get("/").get_data(as_text=True)


def test_json_clients_get_no_calendar_notice(client, login_session, nutrition_catalog):
    client.post("/menu/generate", json=payload(calorie_min=2000))
    assert "miss your daily targets" not in client.get("/").get_data(as_text=True)


def test_profile_cost_priority_preserves_strict_nutrition(
    client, login_session, nutrition_catalog, temp_db_path
):
    with sqlite3.connect(temp_db_path) as conn:
        (restaurant,) = conn.execute(
            'SELECT rtr_id FROM "MenuItem" WHERE itm_id = ?', (nutrition_catalog,)
        ).fetchone()
        conn.execute(
            'INSERT INTO "MenuItem" (rtr_id, name, price, calories, protein_g, instock) '
            "VALUES (?, 'Cheaper dinner', 300, 250, 10, 1)",
            (restaurant,),
        )
    client.post("/profile/optimization", data={"cost_weight": "100"})
    response = client.post(
        "/menu/generate",
        json=payload(number_of_days=1, calorie_min=600, strict_targets=True),
    )
    assert response.status_code == 200
    assert response.json["nutrition"]["days_outside"] == 0
    assert response.json["optimization"]["item_cost_cents"] == 500
