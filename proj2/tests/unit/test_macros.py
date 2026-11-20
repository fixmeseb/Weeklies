"""
Unit tests for estimating menu-item nutrients from USDA FoodData Central foods
(proj2/nutrition.py estimate_macros, proj2/demo_nutrition.py, proj2/fndds_foods.py) and
for storing them (migration 005, proj2/seed.py)
"""

import sqlite3

import pytest

from proj2 import db, demo_menu, demo_nutrition, fndds_foods
from proj2.nutrition import MACRO_FIELDS, describe_source, estimate_macros
from proj2.seed import SeedDataError, menu_item_row, seed_database

## Two made-up foods, per 100 g
FOODS = {
    1: {"description": "Rice", "kcal": 130.0, "protein_g": 2.7, "carbs_g": 28.0,
        "fat_g": 0.3, "sodium_mg": 1.0},
    2: {"description": "Chicken", "kcal": 200.0, "protein_g": 30.0, "carbs_g": 0.0,
        "fat_g": 8.0, "sodium_mg": 80.0},
    3: {"description": "Water", "kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
        "fat_g": 0.0, "sodium_mg": 4.0},
}  # fmt: skip


class TestEstimate:
    def test_one_food_is_scaled_to_the_item_calories(self):
        # 260 kcal of rice is 200 g
        assert estimate_macros(260, [(1, 1.0)], FOODS) == {
            "protein_g": 5.4,
            "carbs_g": 56.0,
            "fat_g": 0.6,
            "sodium_mg": 2,
        }

    def test_a_blend_gives_each_food_its_share_of_the_calories(self):
        # 130 kcal of rice (100 g) and 200 kcal of chicken (100 g)
        blend = estimate_macros(330, [(1, 130 / 330), (2, 200 / 330)], FOODS)
        assert blend == {"protein_g": 32.7, "carbs_g": 28.0, "fat_g": 8.3, "sodium_mg": 81}

    def test_shares_must_add_up_to_one(self):
        with pytest.raises(ValueError, match="add up to 1"):
            estimate_macros(300, [(1, 0.5), (2, 0.4)], FOODS)

    def test_a_food_without_calories_cannot_be_scaled(self):
        with pytest.raises(ValueError, match="Water has no calories"):
            estimate_macros(100, [(3, 1.0)], FOODS)

    def test_source_names_each_food_and_its_share(self):
        text = describe_source([(1, 0.4), (2, 0.6)], FOODS, "2024-10-31")
        assert text == (
            "Estimated from USDA FoodData Central FNDDS 2024-10-31: "
            "Rice (FDC 1, 40%); Chicken (FDC 2, 60%)"
        )


class TestDemoMatches:
    def test_every_demo_item_has_a_match_and_nothing_else_does(self):
        names = [item["name"] for item in demo_menu.MENU_ITEMS]
        assert sorted(demo_nutrition.MATCHES) == sorted(names)

    @pytest.mark.parametrize("name", sorted(demo_nutrition.MATCHES))
    def test_each_match_uses_snapshot_foods_and_whole_shares(self, name):
        parts = demo_nutrition.MATCHES[name]
        assert sum(share for _, share in parts) == pytest.approx(1)
        assert all(0 < share <= 1 for _, share in parts)
        for fdc_id, _ in parts:
            food = fndds_foods.FOODS[fdc_id]
            assert food["kcal"] > 0
            assert set(MACRO_FIELDS) <= set(food)

    def test_snapshot_holds_only_foods_the_matches_use(self):
        used = {fdc_id for parts in demo_nutrition.MATCHES.values() for fdc_id, _ in parts}
        assert set(fndds_foods.FOODS) == used

    def test_estimates_keep_the_listed_calories(self):
        # Protein and carbs give about 4 kcal/g and fat 9 kcal/g. FNDDS energy uses
        # food-specific factors and counts little energy from fibre, so fibre-rich
        # vegetables (collards, corn) come out up to ~13% above their listed calories.
        for item in demo_menu.MENU_ITEMS:
            row = menu_item_row(item)
            from_macros = 4 * row["protein_g"] + 4 * row["carbs_g"] + 9 * row["fat_g"]
            assert from_macros == pytest.approx(item["calories"], rel=0.15, abs=15), item["name"]

    def test_an_item_without_a_match_is_refused(self, monkeypatch):
        monkeypatch.delitem(demo_nutrition.MATCHES, "Margherita Pizza")
        with pytest.raises(SeedDataError, match="Margherita Pizza: no USDA match"):
            menu_item_row(demo_menu.MENU_ITEMS[0])


def test_seed_stores_the_estimates_and_their_source(tmp_path):
    path = str(tmp_path / "seeded.db")
    seed_database(path)
    conn = db.connect(path)
    try:
        row = conn.execute(
            "SELECT calories, protein_g, carbs_g, fat_g, sodium_mg, nutrition_source "
            "FROM MenuItem WHERE name = 'Margherita Pizza'"
        ).fetchone()
        missing = conn.execute(
            "SELECT COUNT(*) FROM MenuItem WHERE protein_g IS NULL OR sodium_mg IS NULL"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute("UPDATE MenuItem SET protein_g = -1")
    finally:
        conn.close()
    assert tuple(row[:5]) == (750, 32.1, 94.0, 27.3, 1523)
    assert row[5].startswith("Estimated from USDA FoodData Central FNDDS 2024-10-31: Pizza")
    assert missing == 0
