"""
Integration tests for the daily calorie target on /menu/generate: the JSON report, bad
input, and the calendar notice after a form submission
"""

import json
import sqlite3

import pytest

from proj2.menu_generation import DAYS_OF_WEEK


@pytest.fixture
def calorie_catalog(app, temp_db_path, seed_minimal_data):
    """One open restaurant with a single 700 kcal item in stock; restores the DB after."""
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
            'UPDATE MenuItem SET price=500, calories=700, instock=1, allergens="" WHERE itm_id=?',
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


def test_json_reports_each_day_against_the_target(client, login_session, calorie_catalog):
    response = client.post("/menu/generate", json=payload(calorie_min=600, calorie_max="800"))
    assert response.status_code == 200
    report = response.get_json()["calories"]
    assert report == {
        "target": {"min": 600, "max": 800},
        "days": [
            {"date": "2026-10-05", "calories": 700, "miss": 0.0},
            {"date": "2026-10-06", "calories": 700, "miss": 0.0},
        ],
        "days_outside": 0,
    }


def test_unreachable_target_still_saves_the_plan_and_reports_the_miss(
    client, login_session, calorie_catalog, temp_db_path
):
    response = client.post("/menu/generate", json=payload(calorie_min=2000))
    assert response.status_code == 200
    data = response.get_json()
    assert data["calories"]["days_outside"] == 2
    assert data["calories"]["days"][0]["miss"] == pytest.approx(0.65)
    assert saved_menu(temp_db_path) == data["generated_menu"]


def test_without_a_target_the_response_has_no_calorie_report(
    client, login_session, calorie_catalog
):
    response = client.post("/menu/generate", json=payload())
    assert response.status_code == 200
    assert response.get_json()["calories"] is None


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"calorie_min": "abc"}, "whole number from 1 to 10000"),
        ({"calorie_max": "0"}, "whole number from 1 to 10000"),
        ({"calorie_min": "2500", "calorie_max": "2000"}, "minimum cannot be more"),
    ],
)
def test_bad_target_is_rejected_without_changing_the_plan(
    client, login_session, calorie_catalog, temp_db_path, fields, message
):
    response = client.post("/menu/generate", json=payload(**fields))
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    assert saved_menu(temp_db_path) == ""


def test_form_submission_shows_the_miss_once_on_the_calendar(
    client, login_session, calorie_catalog
):
    form = {"start_date": "2026-10-05", "days": "2", "meal3": "on", "calorie_min": "2000"}
    response = client.post("/menu/generate", data=form)
    assert response.status_code in (302, 303)
    page = client.get("/").get_data(as_text=True)
    assert (
        "2 of 2 planned days fall outside your daily calorie target (at least 2,000 kcal)." in page
    )
    assert "outside your" not in client.get("/").get_data(as_text=True)  # shown once


def test_profile_form_offers_the_calorie_range(client, login_session):
    page = client.get("/profile").get_data(as_text=True)
    assert 'name="calorie_min"' in page and 'name="calorie_max"' in page
