"""
Integration tests: the diets on a user's account are enforced by /menu/generate and /menu/swap.
"""

import json
import re
import sqlite3

import pytest

from proj2.menu_generation import DAYS_OF_WEEK

MONDAY = "2026-10-05"


@pytest.fixture
def diet_catalog(app, temp_db_path, seed_minimal_data, login_session):
    """A vegetarian user and two open items: one tagged vegetarian, one untagged."""
    snapshot = sqlite3.connect(":memory:")
    with sqlite3.connect(temp_db_path) as conn:
        conn.backup(snapshot)
        restaurant = seed_minimal_data["rtr_id"]
        conn.execute(
            'UPDATE Restaurant SET hours=?, status="Open" WHERE rtr_id=?',
            (json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK}), restaurant),
        )
        conn.execute("UPDATE MenuItem SET instock=0")
        insert = (
            "INSERT INTO MenuItem(rtr_id,name,description,price,calories,instock,allergens,diet_tags) "
            "VALUES (?,?,'',500,500,1,'',?)"
        )
        veg = conn.execute(insert, (restaurant, "Veg Curry", "vegetarian")).lastrowid
        meat = conn.execute(insert, (restaurant, "Beef Curry", None)).lastrowid
        conn.execute(
            'UPDATE "User" SET preferences="Vegetarian, Indian", generated_menu=? WHERE usr_id=?',
            (f"[{MONDAY},{veg},3]", seed_minimal_data["usr_id"]),
        )
    yield {"veg": veg, "meat": meat, "usr_id": seed_minimal_data["usr_id"]}
    with sqlite3.connect(temp_db_path) as conn:
        snapshot.backup(conn)
    snapshot.close()


def planned_ids(response):
    return {int(itm_id) for itm_id in re.findall(r",(\d+),", response.get_json()["generated_menu"])}


def generate(client, **overrides):
    data = {"start_date": "2026-10-06", "meal_numbers": [3], "number_of_days": 1}
    data.update(overrides)
    return client.post("/menu/generate", json=data)


def test_request_preferences_cannot_drop_account_diet(client, diet_catalog):
    response = generate(client, preferences="Spicy", number_of_days=3)
    assert response.status_code == 200, response.get_json()
    assert diet_catalog["veg"] in planned_ids(response)
    assert diet_catalog["meat"] not in planned_ids(response)


def test_no_tagged_items_returns_clear_400(client, diet_catalog, temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute("UPDATE MenuItem SET diet_tags=NULL")
    response = generate(client)
    assert response.status_code == 400
    assert "vegetarian" in response.get_json()["error"]


def test_swap_to_untagged_item_is_rejected(client, diet_catalog):
    response = client.post(
        "/menu/swap", json={"date": MONDAY, "meal": 3, "itm_id": diet_catalog["meat"]}
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "diet"


def test_swap_options_hide_untagged_items(client, diet_catalog, temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        other = conn.execute(
            "INSERT INTO MenuItem(rtr_id,name,description,price,calories,instock,allergens,diet_tags) "
            "SELECT rtr_id,'Paneer','',500,500,1,'','vegan' FROM MenuItem WHERE itm_id=?",
            (diet_catalog["veg"],),
        ).lastrowid
    response = client.get(f"/menu/swap/options?date={MONDAY}&meal=3")
    assert response.status_code == 200
    ids = [option["itm_id"] for option in response.get_json()["options"]]
    assert other in ids
    assert diet_catalog["meat"] not in ids


def test_request_allergens_cannot_drop_account_allergies(client, diet_catalog, temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute(
            'UPDATE "User" SET preferences="", allergies="Peanuts" WHERE usr_id=?',
            (diet_catalog["usr_id"],),
        )
        conn.execute(
            'UPDATE MenuItem SET allergens="Peanuts" WHERE itm_id=?', (diet_catalog["meat"],)
        )
    # The request names a different allergen; the account's peanut allergy must still apply.
    response = generate(client, allergens="Soy", number_of_days=3)
    assert response.status_code == 200, response.get_json()
    assert diet_catalog["veg"] in planned_ids(response)
    assert diet_catalog["meat"] not in planned_ids(response)


def test_profile_saves_hard_limits_and_soft_priorities_together(client, diet_catalog, temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        affordable = conn.execute(
            """INSERT INTO MenuItem (rtr_id, name, price, instock, allergens, diet_tags, spice_level)
               SELECT rtr_id, 'Mild vegan dinner', 300, 1, '', 'vegan', 0
               FROM MenuItem WHERE itm_id=?""",
            (diet_catalog["veg"],),
        ).lastrowid
        hot = conn.execute(
            """INSERT INTO MenuItem (rtr_id, name, price, instock, allergens, diet_tags, spice_level)
               SELECT rtr_id, 'Hot vegan dinner', 250, 1, '', 'vegan', 3
               FROM MenuItem WHERE itm_id=?""",
            (diet_catalog["veg"],),
        ).lastrowid
        conn.execute("UPDATE MenuItem SET diet_tags='vegan' WHERE itm_id=?", (diet_catalog["veg"],))
        conn.execute(
            "UPDATE MenuItem SET diet_tags='vegan', allergens='Soy' WHERE itm_id=?",
            (diet_catalog["meat"],),
        )

    response = client.post(
        "/profile/edit",
        data={
            "diet_constraints": "1",
            "allergies[]": "Soy",
            "diets[]": "vegan",
            "weekly_cap": "8.00",
            "mildness_weight": "100",
        },
        follow_redirects=True,
    )
    assert b"Diet settings saved." in response.data
    assert b'value="8.00"' in response.data

    options = client.get(f"/menu/swap/options?date={MONDAY}&meal=3").json["options"]
    assert [item["itm_id"] for item in options] == [affordable, hot]

    response = generate(client, weekly_cap="100.00", allergens="Milk", preferences="Italian")
    assert response.status_code == 200, response.json
    assert response.json["weekly_cap_cents"] == 800
    assert response.json["optimization"]["average_spice"] == 0
    assert response.json["optimization"]["constraints"] == {
        "diets": ["vegan"],
        "allergies": ["dairy", "soy"],
        "weekly_cap_cents": 800,
    }
    assert f"[2026-10-06,{affordable},3]" in response.json["generated_menu"]

    response = client.post(
        "/menu/swap", json={"date": "2026-10-06", "meal": 3, "itm_id": diet_catalog["veg"]}
    )
    assert response.status_code == 409
    assert response.json["error"] == "weekly_cap"

    response = generate(client, start_date="2026-10-07", weekly_cap="")
    assert response.status_code == 422


def test_invalid_diet_save_is_atomic_and_zero_disables_food_matching(client, diet_catalog):
    initial = {
        "diet_constraints": "1",
        "diets[]": "vegetarian",
        "allergies[]": "Soy",
        "weekly_cap": "10.00",
        "food_matches": "Indian",
        "preference_weight": "0",
    }
    client.post("/profile/edit", data=initial)

    bad = client.post(
        "/profile/edit",
        data={**initial, "allergies[]": "Milk", "weekly_cap": "", "preference_weight": "101"},
        follow_redirects=True,
    )
    assert b"Use whole-number weights from 0 to 100." in bad.data
    assert b'value="Soy" checked' in bad.data
    assert b'value="Milk" checked' not in bad.data
    assert b'value="10.00"' in bad.data

    response = generate(client)
    assert response.status_code == 200, response.json
    assert response.json["weekly_cap_cents"] == 1000
    assert response.json["optimization"] is None

    cleared = client.post("/profile/edit", data={"diet_constraints": "1"}, follow_redirects=True)
    assert b'value="Soy" checked' not in cleared.data
    assert b'value="vegetarian" checked' not in cleared.data
    response = generate(client, start_date="2026-10-07")
    assert response.status_code == 200, response.json
    assert response.json["weekly_cap_cents"] is None


def test_generation_cannot_save_against_a_stale_account_cap(
    client, diet_catalog, temp_db_path, monkeypatch
):
    from proj2.menu_generation import MenuGenerator

    generate_plan = MenuGenerator.update_menu

    def change_cap_during_generation(self, **kwargs):
        plan = generate_plan(self, **kwargs)
        with sqlite3.connect(temp_db_path) as conn:
            conn.execute(
                'UPDATE "User" SET weekly_cap_cents=0 WHERE usr_id=?', (diet_catalog["usr_id"],)
            )
        return plan

    monkeypatch.setattr(MenuGenerator, "update_menu", change_cap_during_generation)
    response = generate(client)
    assert response.status_code == 409
    with sqlite3.connect(temp_db_path) as conn:
        plan = conn.execute(
            'SELECT generated_menu FROM "User" WHERE usr_id=?', (diet_catalog["usr_id"],)
        ).fetchone()[0]
    assert plan == f"[{MONDAY},{diet_catalog['veg']},3]"
