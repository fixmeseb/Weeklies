"""
Integration tests: the diets on a user's account are enforced by /menu/generate and /menu/swap.
"""

import json
import sqlite3
from unittest.mock import Mock

import pytest

from proj2.menu_generation import DAYS_OF_WEEK

MONDAY = "2026-10-05"


@pytest.fixture
def diet_catalog(app, temp_db_path, seed_minimal_data, login_session, monkeypatch):
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
    llm = Mock()
    monkeypatch.setattr("proj2.menu_generation.llm_toolkit.LLM", Mock(return_value=llm))
    yield {"veg": veg, "meat": meat, "llm": llm, "usr_id": seed_minimal_data["usr_id"]}
    with sqlite3.connect(temp_db_path) as conn:
        snapshot.backup(conn)
    snapshot.close()


def picks(llm, itm_id):
    llm.generate.return_value = f"<|start_of_role|>assistant<|end_of_role|>{itm_id}<|end_of_text|>"


def generate(client, **overrides):
    data = {"start_date": "2026-10-06", "meal_numbers": [3], "number_of_days": 1}
    data.update(overrides)
    return client.post("/menu/generate", json=data)


def test_request_preferences_cannot_drop_account_diet(client, diet_catalog):
    picks(diet_catalog["llm"], diet_catalog["veg"])
    response = generate(client, preferences="Spicy")
    assert response.status_code == 200, response.get_json()
    _, prompt = diet_catalog["llm"].generate.call_args.args
    assert "Veg Curry" in prompt
    assert "Beef Curry" not in prompt


def test_no_tagged_items_returns_clear_400(client, diet_catalog, temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute("UPDATE MenuItem SET diet_tags=NULL")
    response = generate(client)
    assert response.status_code == 400
    assert "vegetarian" in response.get_json()["error"]
    diet_catalog["llm"].generate.assert_not_called()


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
    picks(diet_catalog["llm"], diet_catalog["veg"])
    # The request names a different allergen; the account's peanut allergy must still apply.
    response = generate(client, allergens="Soy")
    assert response.status_code == 200, response.get_json()
    _, prompt = diet_catalog["llm"].generate.call_args.args
    assert "Veg Curry" in prompt
    assert "Beef Curry" not in prompt
