"""
Unit tests for the level/flag/single-value tag columns (proj2/meal_tags.py), the checks
that span several tags, and the tagged demo menu (proj2/demo_menu.py, proj2/seed.py)
"""

import datetime
import io
import sqlite3
from collections import Counter

import pytest

from proj2 import demo_menu, meal_tags
from proj2.db_cli import apply_migrations
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator, get_meal_and_order_time
from proj2.menu_tags_io import TAG_COLUMNS, apply_import, contradictions, export_csv, plan_import
from proj2.plan_rules import parse_allergens
from proj2.seed import SeedDataError, menu_item_row, seed_database


class TestLevelsAndFlags:
    @pytest.mark.parametrize("raw, stored", [("0", 0), (" 3 ", 3), (2, 2), ("", ""), (None, "")])
    def test_spice_level(self, raw, stored):
        assert meal_tags.canonical("spice_level", raw) == (stored, [])

    @pytest.mark.parametrize("raw", ["4", "-1", "hot", "1.5", True])
    def test_spice_level_out_of_range(self, raw):
        stored, problems = meal_tags.canonical("spice_level", raw)
        assert stored == "" and problems[0].startswith(
            "spice_level must be a whole number from 0 to 3"
        )

    @pytest.mark.parametrize(
        "raw, stored",
        [("yes", 1), ("Y", 1), ("true", 1), (1, 1), ("no", 0), ("0", 0), (0, 0), ("", "")],
    )
    def test_flags(self, raw, stored):
        assert meal_tags.canonical("travels_well", raw) == (stored, [])

    def test_flag_rejects_other_words(self):
        assert meal_tags.canonical("reheats_well", "maybe") == (
            "",
            ["reheats_well must be yes or no, not 'maybe'"],
        )


class TestSingleValuedAndAliases:
    def test_course_takes_one_value(self):
        assert meal_tags.canonical("course", "starter, main") == (
            "main, starter",
            ["course takes one value, not main, starter"],
        )

    @pytest.mark.parametrize(
        "column, typed, stored",
        [
            ("course", "Appetizer", "starter"),
            ("temperature", "warm", "hot"),
            ("heaviness", "Heavy", "hearty"),
            ("cooking_method", "Stir Fried", "sauteed"),
            ("cooking_method", "sautéed", "sauteed"),
            ("carb_base", "Naan", "bread"),
            ("texture", "crispy", "crunchy"),
        ],
    )
    def test_aliases(self, column, typed, stored):
        assert meal_tags.canonical(column, typed) == (stored, [])

    @pytest.mark.parametrize("column", ["carb_base", "nutrition", "contains"])
    def test_none_stands_alone(self, column):
        other = sorted(meal_tags.COLUMNS[column].values - {"none"})[0]
        _, problems = meal_tags.canonical(column, f"none, {other}")
        assert problems == [f"{column} 'none' cannot be listed with other {column} tags"]


class TestCrossTagChecks:
    def test_low_carb_needs_no_carb_base(self):
        assert meal_tags.tag_clashes({"nutrition": "low-carb", "carb_base": "rice"}) == [
            "low-carb but its carb base is rice"
        ]
        assert meal_tags.tag_clashes({"nutrition": "low-carb", "carb_base": "none"}) == []
        assert meal_tags.tag_clashes({"nutrition": "high-fiber", "carb_base": "rice"}) == []

    def test_halal_cannot_contain_alcohol(self):
        assert contradictions("halal", "", None, "alcohol") == ["halal but contains alcohol"]
        assert contradictions("vegetarian", "", None, "alcohol") == []


def make_db():
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    conn.execute("INSERT INTO Restaurant (rtr_id, name) VALUES (1, 'Cafe')")
    conn.execute("INSERT INTO MenuItem (itm_id, rtr_id, name, allergens) VALUES (1, 1, 'Soup', '')")
    return conn


class TestImportOfNumbers:
    def test_zero_is_stored_as_zero_not_null(self):
        conn = make_db()
        plan = plan_import(conn, io.StringIO("itm_id,spice_level,travels_well\n1,0,no\n"))
        assert plan.ok, plan.errors
        apply_import(conn, plan)
        assert conn.execute("SELECT spice_level, travels_well FROM MenuItem").fetchone() == (0, 0)

    def test_stored_zero_round_trips_unchanged(self):
        conn = make_db()
        conn.execute("UPDATE MenuItem SET spice_level = 0, reheats_well = 0")
        out = io.StringIO()
        export_csv(conn, out)
        plan = plan_import(conn, io.StringIO(out.getvalue()))
        assert plan.ok and plan.changes == []

    def test_database_rejects_out_of_range_values(self):
        conn = make_db()
        for sql in (
            "UPDATE MenuItem SET spice_level = 4",
            "UPDATE MenuItem SET travels_well = 2",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                conn.execute(sql)

    def test_low_carb_with_a_carb_base_blocks_the_import(self):
        conn = make_db()
        plan = plan_import(conn, io.StringIO("itm_id,carb_base,nutrition\n1,pasta,low-carb\n"))
        assert plan.errors == ["line 2: Soup is tagged low-carb but its carb base is pasta"]


class TestDemoMenu:
    def test_new_meals_come_after_the_original_seven(self):
        assert len(demo_menu.MENU_ITEMS) - 7 == 69
        assert [item["name"] for item in demo_menu.MENU_ITEMS[:2]] == [
            "Margherita Pizza",
            "Penne Arrabbiata",
        ]  # Cypress orders itm_id 1 and 2
        assert [r["name"] for r in demo_menu.RESTAURANTS[:2]] == [
            "Taste of Italy",
            "Green Garden Bistro",
        ]

    def test_every_item_has_every_tag(self):
        for item in demo_menu.MENU_ITEMS:
            assert set(TAG_COLUMNS) <= set(item), item["name"]

    def test_every_meal_has_a_distinct_tag_set(self):
        """The point of the tags: no two meals look identical to a variety score."""

        def signature(row):
            return frozenset((column, row[column]) for column in TAG_COLUMNS)

        rows = [menu_item_row(item) for item in demo_menu.MENU_ITEMS]
        repeats = [sig for sig, n in Counter(map(signature, rows)).items() if n > 1]
        assert repeats == []

    def test_every_tag_value_kind_is_used(self):
        rows = [menu_item_row(item) for item in demo_menu.MENU_ITEMS]
        for column in ("meal_type", "course", "temperature", "heaviness"):
            used = set().union(*(meal_tags.parse_tags(column, row[column]) for row in rows))
            assert used == meal_tags.COLUMNS[column].values, column
        assert {row["spice_level"] for row in rows} == {0, 1, 2, 3}

    def test_names_are_unique(self):
        names = [item["name"] for item in demo_menu.MENU_ITEMS]
        assert len(names) == len(set(names))

    def test_seed_refuses_a_contradictory_item(self):
        bad = dict(demo_menu.MENU_ITEMS[0], diet_tags="vegan")  # Margherita has dairy
        with pytest.raises(SeedDataError, match="Margherita Pizza: vegan but contains dairy"):
            menu_item_row(bad)

    def test_seed_refuses_an_item_missing_a_tag(self):
        bad = {k: v for k, v in demo_menu.MENU_ITEMS[0].items() if k != "texture"}
        with pytest.raises(SeedDataError, match="no texture"):
            menu_item_row(bad)


class TestDemoMenuIsPlannable:
    """The new restaurants' hours are JSON, so the planner can use their meals, and every
    demo diet has at least three mains of the right meal type for every slot of the week."""

    @pytest.fixture(scope="class")
    def generator(self, tmp_path_factory):
        path = str(tmp_path_factory.mktemp("seed") / "seed.db")
        seed_database(path, password="pw-for-tests")
        return MenuGenerator(database_path=path)

    @pytest.mark.parametrize("meal", [1, 2, 3])
    @pytest.mark.parametrize(
        "preferences, allergies",
        [
            ("", ""),
            ("Vegetarian, Italian", "Peanuts"),
            ("Gluten-Free, Healthy", "Dairy"),
            ("Vegan", ""),
            ("Halal", ""),
            ("Kosher", ""),
            ("Pescatarian", "Shellfish"),
        ],
    )
    def test_every_slot_has_choices_for_the_demo_diets(
        self, generator, preferences, allergies, meal
    ):
        _, order_time = get_meal_and_order_time(meal)
        for offset in range(7):
            day = datetime.date(2026, 11, 16) + datetime.timedelta(days=offset)
            weekday = DAYS_OF_WEEK[day.weekday()]
            candidates = generator._eligible_candidates(
                allergies, weekday, order_time, preferences=preferences, meal=meal
            )
            assert len(candidates) >= 3, (preferences, weekday, meal)
            for value in candidates["allergens"]:
                assert not parse_allergens(value) & parse_allergens(allergies)
