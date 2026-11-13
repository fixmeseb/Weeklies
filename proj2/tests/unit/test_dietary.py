"""
Unit tests for the hard dietary rules in proj2/dietary.py and where generation and swaps apply them
"""

import json
import sqlite3

import pandas as pd
import pytest

from proj2.dietary import (
    DietaryConstraintError,
    ensure_diet_tags_column,
    filter_diets,
    has_diet_tags_column,
    missing_diets,
    normalize_tag,
    required_diets,
    satisfied_diets,
    with_account_allergies,
    with_account_diets,
)
from proj2.meal_budget import BudgetExceededError, plan_entries
from proj2.meal_swap import list_swap_options, load_swap_item, swap_rejection
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator

## 2025-11-03 is a Monday
MONDAY = "2025-11-03"
ALL_WEEK = json.dumps({d: [0, 2359] for d in DAYS_OF_WEEK})


class TestTags:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Vegan", "vegan"),
            (" Gluten Free ", "gluten-free"),
            ("gluten_free", "gluten-free"),
            ("GLUTEN-FREE", "gluten-free"),
        ],
    )
    def test_normalize_tag(self, raw, expected):
        assert normalize_tag(raw) == expected

    def test_required_diets_keeps_only_known_diets(self):
        assert required_diets("Vegetarian, Italian, Spicy, Gluten Free") == {
            "vegetarian",
            "gluten-free",
        }

    @pytest.mark.parametrize("prefs", [None, "", "Italian, Spicy", float("nan")])
    def test_no_diet_named(self, prefs):
        assert required_diets(prefs) == set()

    def test_diet_words_inside_other_text_do_not_count(self):
        # Only whole comma-separated entries are diets; "not vegan" is a soft preference.
        assert required_diets("not vegan, veganish") == set()

    def test_vegan_implies_vegetarian_and_pescatarian(self):
        assert satisfied_diets("Vegan") == {"vegan", "vegetarian", "pescatarian"}

    def test_vegetarian_does_not_imply_vegan(self):
        assert missing_diets("vegetarian", {"vegan"}) == {"vegan"}

    @pytest.mark.parametrize("tags", [None, "", float("nan"), "spicy"])
    def test_untagged_items_fail_closed(self, tags):
        assert missing_diets(tags, {"halal"}) == {"halal"}

    def test_every_required_diet_must_be_met(self):
        assert missing_diets("halal", {"halal", "gluten-free"}) == {"gluten-free"}
        assert missing_diets("halal, gluten free", {"halal", "gluten-free"}) == set()


class TestFilterDiets:
    ITEMS = pd.DataFrame(
        {"itm_id": [1, 2, 3, 4], "diet_tags": ["vegan", "vegetarian", None, "halal"]}
    )

    def test_no_diet_keeps_everything(self):
        assert filter_diets(self.ITEMS, "Italian").itm_id.tolist() == [1, 2, 3, 4]

    def test_vegetarian(self):
        assert filter_diets(self.ITEMS, "Vegetarian").itm_id.tolist() == [1, 2]

    def test_vegan(self):
        assert filter_diets(self.ITEMS, "vegan").itm_id.tolist() == [1]

    def test_missing_column_means_nothing_is_tagged(self):
        items = self.ITEMS.drop(columns="diet_tags")
        assert filter_diets(items, "halal").empty
        assert filter_diets(items, "spicy").itm_id.tolist() == [1, 2, 3, 4]


class TestAccountDiets:
    def test_request_cannot_drop_account_diet(self):
        assert with_account_diets("Italian", "Vegetarian, Spicy") == "Italian, vegetarian"

    def test_request_without_preferences(self):
        assert with_account_diets("", "Halal") == "halal"

    def test_diet_already_named_is_not_repeated(self):
        assert with_account_diets("Vegan, Thai", "vegan") == "Vegan, Thai"

    def test_no_account_diet(self):
        assert with_account_diets("Thai", "Spicy") == "Thai"


class TestAccountAllergies:
    def test_request_cannot_drop_account_allergy(self):
        assert with_account_allergies("Soy", "Peanuts, Shellfish") == "Soy, Peanuts, Shellfish"

    def test_empty_request_keeps_account_allergies(self):
        assert with_account_allergies("", " Peanuts ,") == "Peanuts"
        assert with_account_allergies(None, None) == ""

    def test_matching_ignores_case(self):
        assert with_account_allergies("peanuts", "Peanuts, Dairy") == "peanuts, Dairy"


class TestSchema:
    def test_ensure_column_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.execute('CREATE TABLE "MenuItem" (itm_id INTEGER PRIMARY KEY, allergens TEXT)')
        assert not has_diet_tags_column(conn)
        assert ensure_diet_tags_column(conn) is True
        assert has_diet_tags_column(conn)
        assert ensure_diet_tags_column(conn) is False

    def test_versioned_database_gets_the_column_from_its_migration(self, tmp_path):
        # A database at schema version 1 (before 002) must not get a raw ALTER TABLE,
        # or the later `flask migrate` would try to add diet_tags a second time.
        from proj2 import db_cli

        conn = sqlite3.connect(tmp_path / "v1.db")
        sql = open(db_cli.migrations()[0][1], encoding="utf-8").read()
        conn.executescript(sql + "\nPRAGMA user_version = 1;")
        assert not has_diet_tags_column(conn)

        assert ensure_diet_tags_column(conn) is True
        assert has_diet_tags_column(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db_cli.latest_version()
        assert db_cli.apply_migrations(conn) == []



## ---------------------- Meal generation ----------------------


@pytest.fixture
def generator():
    gen = MenuGenerator.__new__(MenuGenerator)
    gen.menu_items = pd.DataFrame(
        [
            {
                "itm_id": itm_id,
                "rtr_id": 1,
                "name": f"Meal {itm_id}",
                "description": "",
                "price": price,
                "calories": 500,
                "instock": 1,
                "allergens": "",
                "diet_tags": tags,
            }
            for itm_id, price, tags in [(1, 300, None), (2, 500, "vegetarian"), (3, 700, "vegan")]
        ]
    )
    gen.restaurants = pd.DataFrame([{"rtr_id": 1, "hours": ALL_WEEK}])
    gen.item_prices = dict(zip(gen.menu_items.itm_id, gen.menu_items.price))
    return gen


def test_candidates_exclude_untagged_items(generator):
    candidates = generator._eligible_candidates("", "Mon", 2000, preferences="Vegetarian")
    assert candidates.itm_id.tolist() == [2, 3]


def test_plan_uses_only_items_within_the_diet(generator):
    assert generator.update_menu("", "Vegan", "", MONDAY, [3]) == f"[{MONDAY},3,3]"


def test_cheapest_untagged_item_is_never_planned_for_a_diet(generator):
    # Item 1 is the cheapest but untagged; a week of vegetarian dinners never uses it.
    plan = generator.update_menu("", "Vegetarian", "", MONDAY, [3], 7)
    assert {itm_id for _, itm_id, _ in plan_entries(plan)} <= {2, 3}


def test_no_tagged_items_is_a_clear_error(generator):
    with pytest.raises(DietaryConstraintError, match="halal"):
        generator.update_menu("", "Halal", "", MONDAY, [3])


def test_budget_plan_reserves_cheapest_item_within_the_diet(generator):
    # Untagged item 1 ($3) would fit a $5 cap; the cheapest vegetarian item is $5.
    assert generator.update_menu("", "Vegetarian", "", MONDAY, [3], 1, 500) == f"[{MONDAY},2,3]"
    with pytest.raises(BudgetExceededError):
        generator.update_menu("", "Vegetarian", "", MONDAY, [3], 1, 499)


def test_preferences_without_a_diet_are_unchanged(generator):
    assert generator._eligible_candidates("", "Mon", 2000, preferences="Spicy").itm_id.tolist() == [
        1,
        2,
        3,
    ]


## ---------------------- Meal swaps ----------------------


def swap_item(**overrides):
    item = {
        "itm_id": 1,
        "rtr_id": 1,
        "name": "Pho",
        "instock": 1,
        "allergens": "",
        "restaurant_status": "Open",
        "hours": ALL_WEEK,
        "diet_tags": "vegetarian",
    }
    item.update(overrides)
    return item


def test_swap_rejects_item_outside_the_diet():
    code, message = swap_rejection(swap_item(), "", MONDAY, 2, "Vegan, Thai")
    assert code == "diet"
    assert "vegan" in message


def test_swap_accepts_item_within_the_diet():
    assert swap_rejection(swap_item(), "", MONDAY, 2, "Vegetarian") is None
    assert swap_rejection(swap_item(diet_tags=None), "", MONDAY, 2, "Spicy") is None
    # Existing callers that pass no preferences keep their old behaviour.
    assert swap_rejection(swap_item(diet_tags=None), "", MONDAY, 2) is None


@pytest.fixture
def swap_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        f"""
        CREATE TABLE Restaurant (rtr_id INTEGER PRIMARY KEY, status TEXT, hours TEXT);
        CREATE TABLE MenuItem (itm_id INTEGER PRIMARY KEY, rtr_id INTEGER, name TEXT,
                               instock INTEGER, allergens TEXT);
        INSERT INTO Restaurant VALUES (1, 'Open', '{ALL_WEEK}');
        INSERT INTO MenuItem VALUES (1, 1, 'Burger', 1, ''), (2, 1, 'Salad', 1, '');
        """
    )
    yield conn
    conn.close()


def test_swaps_on_a_database_without_diet_tags_treat_items_as_untagged(swap_conn):
    assert load_swap_item(swap_conn, 2)["diet_tags"] is None
    assert list_swap_options(swap_conn, "", MONDAY, 2, user_preferences="Vegetarian") == []
    assert len(list_swap_options(swap_conn, "", MONDAY, 2)) == 2


def test_swap_options_follow_diet_tags(swap_conn):
    ensure_diet_tags_column(swap_conn)
    swap_conn.execute("UPDATE MenuItem SET diet_tags = 'vegan' WHERE itm_id = 2")
    options = list_swap_options(swap_conn, "", MONDAY, 2, user_preferences="Vegetarian")
    assert [o["itm_id"] for o in options] == [2]
