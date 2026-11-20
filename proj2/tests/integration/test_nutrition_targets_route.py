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
        conn.execute(
            'UPDATE "User" SET generated_menu="" WHERE usr_id=?', (seed_minimal_data["usr_id"],)
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


def test_profile_form_offers_a_range_for_each_nutrient(client, login_session):
    page = client.get("/profile").get_data(as_text=True)
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


def test_profile_form_offers_strict_targets(client, login_session):
    assert 'name="strict_targets"' in client.get("/profile").get_data(as_text=True)
