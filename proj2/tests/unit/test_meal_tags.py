"""
Unit tests for the descriptive menu tags (proj2/meal_tags.py) and their CSV import
"""

import io
import shutil
import sqlite3

import pytest

from proj2 import meal_tags
from proj2.db_cli import apply_migrations, latest_version, migrations
from proj2.menu_tags_io import apply_import, contradictions, plan_import


class TestNormalize:
    @pytest.mark.parametrize(
        "column, typed, stored",
        [
            ("meal_type", "Lunch/Dinner", "lunch-dinner"),
            ("meal_type", "lunch / dinner", "lunch-dinner"),
            ("meal_type", "Dinner", "lunch-dinner"),
            ("cuisine", "Middle Eastern", "middle-eastern"),
            ("cuisine", "Tex-Mex", "mexican"),
            ("protein", "Eggs", "egg"),
            ("protein", "Plant Based", "plant-based"),
            ("flavor", "  SPICY ", "spicy"),
        ],
    )
    def test_spellings(self, column, typed, stored):
        assert meal_tags.normalize(column, typed) == stored

    @pytest.mark.parametrize("value", [None, float("nan"), "", " , "])
    def test_empty_cells(self, value):
        assert meal_tags.parse_tags("flavor", value) == set()


class TestCanonical:
    def test_sorts_and_dedupes(self):
        assert meal_tags.canonical("flavor", "Spicy, smoky, spicy") == ("smoky, spicy", [])

    def test_unknown_tag_is_a_problem_not_a_new_tag(self):
        stored, problems = meal_tags.canonical("protein", "chiken, egg")
        assert stored == "egg"
        assert problems and problems[0].startswith("unknown protein tag(s) chiken; use ")

    def test_none_cannot_be_listed_with_a_protein(self):
        _, problems = meal_tags.canonical("protein", "none, chicken")
        assert problems == ["protein 'none' cannot be listed with other protein tags"]

    def test_every_meal_type(self):
        assert meal_tags.canonical("meal_type", "Breakfast, snack, dessert, lunch/dinner") == (
            "breakfast, dessert, lunch-dinner, snack",
            [],
        )


class TestProteinContradictions:
    @pytest.mark.parametrize(
        "diet, protein, message",
        [
            ("vegetarian", "chicken", "vegetarian but its protein is chicken"),
            ("vegan", "egg", "vegan but its protein is egg"),
            ("pescatarian", "beef", "pescatarian but its protein is beef"),
            ("halal", "pork", "halal but its protein is pork"),
            ("kosher", "shellfish", "kosher but its protein is shellfish"),
        ],
    )
    def test_clashes(self, diet, protein, message):
        assert message in contradictions(diet, "", protein)

    @pytest.mark.parametrize(
        "diet, protein",
        [("pescatarian", "fish"), ("vegan", "tofu, legumes"), ("vegetarian", "egg, dairy")],
    )
    def test_compatible(self, diet, protein):
        assert contradictions(diet, "", protein) == []


def make_db(with_columns=True):
    conn = sqlite3.connect(":memory:")
    extra = (
        ", diet_tags TEXT, cuisine TEXT, protein TEXT, flavor TEXT, meal_type TEXT"
        if with_columns
        else ""
    )
    conn.executescript(
        f"""
        CREATE TABLE Restaurant (rtr_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE MenuItem (itm_id INTEGER PRIMARY KEY, rtr_id INTEGER, name TEXT,
                               description TEXT, allergens TEXT{extra});
        INSERT INTO Restaurant VALUES (1, 'Saffron House');
        INSERT INTO MenuItem (itm_id, rtr_id, name, description, allergens) VALUES
          (1, 1, 'Chana Masala', 'Chickpeas, tomato', ''),
          (2, 1, 'Chicken 65', 'Fried chicken', '');
        """
    )
    return conn


def sheet(text):
    return io.StringIO(text)


class TestImport:
    def test_writes_descriptive_tags(self):
        conn = make_db()
        plan = plan_import(
            conn,
            sheet(
                "itm_id,cuisine,protein,flavor,meal_type\n"
                '1,Indian,Beans,"Spicy, Herby",Lunch/Dinner\n'
                "2,indian,chicken,spicy,snack\n"
            ),
        )
        assert plan.ok, plan.errors
        apply_import(conn, plan)
        rows = conn.execute(
            "SELECT itm_id, cuisine, protein, flavor, meal_type FROM MenuItem"
        ).fetchall()
        assert rows == [
            (1, "indian", "legumes", "herby, spicy", "lunch-dinner"),
            (2, "indian", "chicken", "spicy", "snack"),
        ]

    def test_columns_left_out_of_the_csv_are_not_touched(self):
        conn = make_db()
        conn.execute("UPDATE MenuItem SET diet_tags='vegan', cuisine='indian' WHERE itm_id=1")
        apply_import(conn, plan_import(conn, sheet("itm_id,flavor\n1,spicy\n")))
        assert conn.execute(
            "SELECT diet_tags, cuisine, flavor FROM MenuItem WHERE itm_id=1"
        ).fetchone() == ("vegan", "indian", "spicy")

    def test_protein_is_checked_against_the_stored_diet(self):
        conn = make_db()
        conn.execute("UPDATE MenuItem SET diet_tags='vegetarian' WHERE itm_id=2")
        plan = plan_import(conn, sheet("itm_id,protein\n2,chicken\n"))
        # vegetarian implies pescatarian, so both are reported
        assert plan.errors == [
            "line 2: Chicken 65 is tagged pescatarian but its protein is chicken",
            "line 2: Chicken 65 is tagged vegetarian but its protein is chicken",
        ]

    def test_unknown_tags_block_the_whole_import(self):
        conn = make_db()
        plan = plan_import(
            conn, sheet("itm_id,cuisine,meal_type\n1,indian,brunch\n2,klingon,snack\n")
        )
        assert len(plan.errors) == 2
        assert "unknown meal_type tag(s) brunch" in plan.errors[0]
        assert "unknown cuisine tag(s) klingon" in plan.errors[1]
        with pytest.raises(ValueError):
            apply_import(conn, plan)

    def test_unchanged_counts_items_not_cells(self):
        conn = make_db()
        conn.execute("UPDATE MenuItem SET cuisine='indian', flavor='spicy'")
        plan = plan_import(conn, sheet("itm_id,cuisine,flavor\n1,indian,spicy\n2,indian,mild\n"))
        assert plan.unchanged == 1
        assert [(c[0], c[2], c[4]) for c in plan.changes] == [(2, "flavor", "mild")]

    def test_adds_missing_columns_to_an_unversioned_database(self):
        conn = make_db(with_columns=False)
        apply_import(conn, plan_import(conn, sheet("itm_id,meal_type\n1,dessert\n")))
        assert meal_tags.has_column(conn, "meal_type")
        assert not meal_tags.has_column(conn, "flavor")  # only the columns the CSV uses


class TestMigration:
    def test_migrations_add_every_tag_column(self):
        conn = sqlite3.connect(":memory:")
        apply_migrations(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version()
        for column in ("diet_tags", *meal_tags.TAG_COLUMNS):
            assert meal_tags.has_column(conn, column)

    def test_ensure_columns_on_a_versioned_database_uses_the_migrations(self, tmp_path):
        # A database made by init-db before migration 003 existed
        older = tmp_path / "migrations"
        older.mkdir()
        for version, path in migrations()[:2]:
            shutil.copy(path, older)
        conn = sqlite3.connect(":memory:")
        apply_migrations(conn, directory=str(older))
        assert not meal_tags.has_column(conn, "cuisine")

        assert meal_tags.ensure_columns(conn, ["cuisine"]) == ["cuisine"]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version()
        assert all(meal_tags.has_column(conn, column) for column in meal_tags.TAG_COLUMNS)
        # so a later `flask migrate` has nothing left to add
        assert apply_migrations(conn) == []
        assert meal_tags.ensure_columns(conn, meal_tags.TAG_COLUMNS) == []


def test_demo_seed_tags_are_valid_and_canonical(tmp_path):
    """Exporting the seeded menu and importing it back must change nothing and pass every check."""
    from proj2.menu_tags_io import export_csv
    from proj2.seed import seed_database

    path = str(tmp_path / "seed.db")
    seed_database(path, password="pw-for-tests")
    conn = sqlite3.connect(path)
    try:
        out = io.StringIO()
        export_csv(conn, out)
        plan = plan_import(conn, io.StringIO(out.getvalue()))
        assert plan.ok, plan.errors
        assert plan.changes == []
        # Every descriptive tag is filled in (diet_tags may be empty: no diet applies)
        missing = " OR ".join(f"{column} IS NULL" for column in meal_tags.TAG_COLUMNS)
        untagged = conn.execute(f"SELECT name FROM MenuItem WHERE {missing}").fetchall()
        assert untagged == []
    finally:
        conn.close()
