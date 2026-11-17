"""UC06: Generate Meal Plan — tests.

Planning is rule-based and deterministic (proj2/menu_generation.py), so these go
through POST /menu/generate. Each test plans from its own small catalog: the shared
database is snapshotted, every other item is taken out of stock, and the snapshot is
restored afterwards so other UC tests see the original data.
"""

import json
import re
import sqlite3
from datetime import date

import pytest

from proj2.Flask_app import parse_generated_menu
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator
from proj2.sef26tests.conftest import login_as_user

## 2025-11-05 is a Wednesday
DAY = "2025-11-05"
ALL_DAY = json.dumps({d: [0, 2359] for d in DAYS_OF_WEEK})


@pytest.fixture()
def plan_world(temp_db_path, seed_user, client):
    snapshot = sqlite3.connect(":memory:")
    with sqlite3.connect(temp_db_path) as conn:
        conn.backup(snapshot)
        conn.execute("UPDATE MenuItem SET instock=0")
        conn.execute(
            'UPDATE "User" SET preferences="", allergies="", generated_menu="" WHERE usr_id=?',
            (seed_user["usr_id"],),
        )

        def restaurant(name, hours):
            return conn.execute(
                'INSERT INTO "Restaurant"(name,status,hours) VALUES (?,?,?)', (name, "Open", hours)
            ).lastrowid

        def item(rtr_id, name, allergens="", protein=None, cuisine=None):
            return conn.execute(
                'INSERT INTO "MenuItem"(rtr_id,name,description,price,calories,instock,allergens,'
                "protein,cuisine) VALUES (?,?,'',900,500,1,?,?,?)",
                (rtr_id, name, allergens, protein, cuisine),
            ).lastrowid

        bistro = restaurant("UC06 Bistro", ALL_DAY)
        broken = restaurant("UC06 Broken Hours", "open whenever")
        ids = {
            "curry": item(bistro, "Curry", "Peanuts", "chicken", "indian"),
            "tacos": item(bistro, "Tacos", "Wheat", "beef", "mexican"),
            "salad": item(bistro, "Salad", "Peanuts, Wheat", "tofu", "mediterranean"),
            "broken": item(broken, "Mystery Stew"),
        }
    login_as_user(client, seed_user)
    yield {"ids": ids, "usr_id": seed_user["usr_id"], "path": temp_db_path}
    with sqlite3.connect(temp_db_path) as conn:
        snapshot.backup(conn)
    snapshot.close()


def generate(client, **data):
    return client.post("/menu/generate", json=data)


def entries(menu):
    return [(d, int(i), int(m)) for d, i, m in re.findall(r"\[([^,\]]+),(\d+),(\d)\]", menu)]


def saved_menu(world):
    with sqlite3.connect(world["path"]) as conn:
        return conn.execute(
            'SELECT generated_menu FROM "User" WHERE usr_id=?', (world["usr_id"],)
        ).fetchone()[0]


def test_generate_meal_plan_valid(client, plan_world):
    """UC06 main: plans every requested slot from eligible items and saves the plan."""
    response = generate(client, start_date=DAY, meal_numbers=[1, 2, 3], number_of_days=2)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    planned = entries(body["generated_menu"])
    assert [(d, m) for d, _, m in planned] == [
        (DAY, 1),
        (DAY, 2),
        (DAY, 3),
        ("2025-11-06", 1),
        ("2025-11-06", 2),
        ("2025-11-06", 3),
    ]
    assert {i for _, i, _ in planned} <= set(plan_world["ids"].values()) - {
        plan_world["ids"]["broken"]
    }
    # Three different dishes are available, so no meal repeats the one just before it.
    assert all(a[1] != b[1] for a, b in zip(planned, planned[1:]))
    assert 0 < body["variety"]["score"] <= 1
    assert saved_menu(plan_world) == body["generated_menu"]


def test_generate_meal_plan_is_repeatable(client, plan_world):
    """The same request on the same catalog gives the same plan."""
    first = generate(client, start_date=DAY, number_of_days=3).get_json()["generated_menu"]
    with sqlite3.connect(plan_world["path"]) as conn:
        conn.execute('UPDATE "User" SET generated_menu="" WHERE usr_id=?', (plan_world["usr_id"],))
    assert generate(client, start_date=DAY, number_of_days=3).get_json()["generated_menu"] == first


def test_generate_meal_plan_no_periods(client, plan_world):
    """UC06 ext 1a: no meals selected defaults to breakfast, lunch and dinner."""
    body = generate(client, start_date=DAY).get_json()
    assert body["meal_numbers"] == [1, 2, 3]
    assert [m for _, _, m in entries(body["generated_menu"])] == [1, 2, 3]


def test_generate_meal_plan_invalid_date(client, plan_world):
    """UC06 ext 1b: an invalid start date falls back to today."""
    body = generate(client, start_date="not-a-date", meal_numbers=[3]).get_json()
    assert body["start_date"] == date.today().isoformat()
    assert entries(body["generated_menu"])[0][0] == date.today().isoformat()


def test_generate_meal_plan_duration_too_short(client, plan_world):
    """UC06 ext 1c: a duration under one day is raised to one."""
    body = generate(client, start_date=DAY, meal_numbers=[3], number_of_days=0).get_json()
    assert body["number_of_days"] == 1
    assert len(entries(body["generated_menu"])) == 1


def test_generate_meal_plan_duration_too_long(client, plan_world):
    """UC06 ext 1d: a duration over 14 days is capped at 14."""
    body = generate(client, start_date=DAY, meal_numbers=[3], number_of_days=30).get_json()
    assert body["number_of_days"] == 14
    assert len(entries(body["generated_menu"])) == 14


def test_generate_meal_plan_malformed_hours(client, plan_world):
    """UC06 ext 3a: items from a restaurant with unreadable hours are never planned."""
    body = generate(client, start_date=DAY, number_of_days=7).get_json()
    assert plan_world["ids"]["broken"] not in {i for _, i, _ in entries(body["generated_menu"])}


def test_generate_meal_plan_allergies_respected(client, plan_world):
    """UC06 ext 3b (part): an allergy removes items but planning continues with the rest."""
    body = generate(client, start_date=DAY, number_of_days=2, allergens="Peanuts").get_json()
    assert {i for _, i, _ in entries(body["generated_menu"])} == {plan_world["ids"]["tacos"]}


def test_generate_meal_plan_allergies_all(client, plan_world):
    """UC06 ext 3b: allergies that rule out every item give a clear error and save nothing."""
    response = generate(client, start_date=DAY, allergens="Peanuts, Wheat")
    assert response.status_code == 400
    assert "every item that fits contains one of your allergens" in response.get_json()["error"]
    assert saved_menu(plan_world) == ""


def test_generate_meal_plan_invalid_selection():
    """UC06 ext 4a: the plan parser drops entries that don't match the format."""
    assert parse_generated_menu("[bad-date,not-an-id]") == {}


def test_generate_meal_plan_planner_failure(client, plan_world, monkeypatch):
    """UC06 ext 4c: an unexpected planner failure returns a generic 500 and saves nothing."""

    def broken(*args, **kwargs):
        raise RuntimeError("internal detail")

    monkeypatch.setattr(MenuGenerator, "update_menu", broken)
    response = generate(client, start_date=DAY)
    assert response.status_code == 500
    assert "internal detail" not in response.get_json()["error"]
    assert saved_menu(plan_world) == ""


def test_generate_meal_plan_preserves_existing(client, plan_world):
    """UC06 ext 5a: meals already planned stay, and only the empty slots are filled."""
    existing = f"[{DAY},{plan_world['ids']['salad']},2]"
    with sqlite3.connect(plan_world["path"]) as conn:
        conn.execute(
            'UPDATE "User" SET generated_menu=? WHERE usr_id=?', (existing, plan_world["usr_id"])
        )
    menu = generate(client, start_date=DAY).get_json()["generated_menu"]
    assert menu.startswith(existing)
    assert sorted(m for d, _, m in entries(menu) if d == DAY) == [1, 2, 3]


def test_parse_keeps_multiple_entries_for_the_same_day():
    """parse_generated_menu keeps every meal of one day."""
    result = parse_generated_menu("[2025-11-05,1,1][2025-11-05,2,2]")
    assert len(result["2025-11-05"]) == 2
