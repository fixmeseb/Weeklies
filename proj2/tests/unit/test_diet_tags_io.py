"""
Unit tests for the diet tag CSV export/import (proj2/diet_tags_io.py, proj2/scripts/diet_tags.py)
"""

import csv
import io
import sqlite3

import pytest

from proj2.diet_tags_io import (
    apply_import,
    canonical_tags,
    contradictions,
    export_csv,
    plan_import,
)
from proj2.dietary import has_diet_tags_column
from proj2.scripts.diet_tags import main


def make_db(path=":memory:", with_column=False):
    conn = sqlite3.connect(path)
    tags = ", diet_tags TEXT" if with_column else ""
    conn.executescript(
        f"""
        CREATE TABLE Restaurant (rtr_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE MenuItem (itm_id INTEGER PRIMARY KEY, rtr_id INTEGER, name TEXT,
                               description TEXT, allergens TEXT{tags});
        INSERT INTO Restaurant VALUES (1, 'Saffron House'), (2, 'Bida Pho');
        INSERT INTO MenuItem (itm_id, rtr_id, name, description, allergens) VALUES
          (1, 1, 'Chana Masala', 'Chickpeas, tomato', ''),
          (2, 1, 'Paneer Tikka', 'Grilled paneer, "smoky"', 'Dairy'),
          (3, 2, 'Beef Pho', 'Brisket, rice noodles', 'Soy, Fish'),
          (4, 2, 'Shrimp Rolls', 'Shrimp, herbs', 'Shellfish');
        """
    )
    conn.commit()
    return conn


def tagged(rows, header="itm_id,diet_tags"):
    return io.StringIO(header + "\n" + "\n".join(rows) + "\n")


def tags_in(conn):
    return dict(conn.execute("SELECT itm_id, diet_tags FROM MenuItem").fetchall())


class TestCanonicalTags:
    def test_normalizes_sorts_and_dedupes(self):
        assert canonical_tags("Vegan,  Gluten Free, vegan") == ("gluten-free, vegan", [])

    def test_reports_unknown_tags(self):
        assert canonical_tags("veggie, Halal") == ("halal", ["veggie"])

    @pytest.mark.parametrize("raw", ["", None, " , "])
    def test_empty(self, raw):
        assert canonical_tags(raw) == ("", [])


class TestContradictions:
    def test_vegan_with_dairy(self):
        assert contradictions("vegan", "Dairy, Soy") == ["vegan but contains dairy"]

    def test_implied_diets_are_checked_too(self):
        # vegan implies vegetarian, which fish rules out
        assert "vegetarian but contains fish" in contradictions("vegan", "Fish")

    def test_pescatarian_allows_fish(self):
        assert contradictions("pescatarian", "Fish, Shellfish") == []

    def test_gluten_free_with_gluten(self):
        assert contradictions("gluten-free", "WHEAT") == ["gluten-free but contains wheat"]


class TestExport:
    def test_writes_every_item_with_context_columns(self):
        out = io.StringIO()
        assert export_csv(make_db(), out) == 4
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        assert [r["itm_id"] for r in rows] == ["3", "4", "1", "2"]  # by restaurant name
        assert rows[3]["description"] == 'Grilled paneer, "smoky"'
        assert rows[3]["restaurant"] == "Saffron House"
        assert all(r["diet_tags"] == "" for r in rows)

    def test_export_round_trips_through_import_unchanged(self):
        conn = make_db(with_column=True)
        conn.execute("UPDATE MenuItem SET diet_tags='halal, vegan' WHERE itm_id=1")
        out = io.StringIO()
        export_csv(conn, out)
        plan = plan_import(conn, io.StringIO(out.getvalue()))
        assert plan.ok and plan.changes == [] and plan.unchanged == 4


class TestPlanImport:
    def test_dry_run_lists_changes_and_writes_nothing(self):
        conn = make_db()
        plan = plan_import(conn, tagged(['1,"Vegan, Halal"', "2,vegetarian"]))
        assert plan.ok
        assert [(c[0], c[3]) for c in plan.changes] == [(1, "halal, vegan"), (2, "vegetarian")]
        assert not has_diet_tags_column(conn)

    def test_reports_every_problem(self):
        plan = plan_import(
            make_db(),
            tagged(
                [
                    "abc,vegan",
                    "99,vegan",
                    "1,veggie",
                    "2,vegan",  # Paneer contains dairy
                    "3,halal",
                    "3,halal",  # repeated
                ]
            ),
        )
        assert not plan.ok
        assert plan.errors == [
            "line 2: itm_id 'abc' is not a number",
            "line 3: there is no menu item 99",
            "line 4: Chana Masala has unknown tag(s) veggie; use gluten-free, halal, "
            "kosher, pescatarian, vegan, vegetarian",
            "line 5: Paneer Tikka is tagged vegan but contains dairy",
            "line 7: item 3 already appears on line 6",
        ]

    def test_unquoted_tag_list_is_rejected_not_truncated(self):
        plan = plan_import(make_db(), tagged(["1,Vegan, Halal"]))
        assert plan.errors == [
            'line 2: more cells than columns; put several tags in quotes, e.g. "vegan, halal"'
        ]

    def test_missing_column(self):
        plan = plan_import(make_db(), tagged(["1"], header="itm_id"))
        assert plan.errors == ["line 1: missing column(s) diet_tags"]

    def test_extra_columns_blank_lines_and_header_spaces_are_fine(self):
        csv_text = io.StringIO(" itm_id , name , diet_tags \n1,Chana,vegan\n\n,,\n")
        plan = plan_import(make_db(), csv_text)
        assert plan.ok and len(plan.changes) == 1

    def test_empty_cell_clears_tags_and_missing_rows_are_left_alone(self):
        conn = make_db(with_column=True)
        conn.execute("UPDATE MenuItem SET diet_tags='halal' WHERE itm_id IN (1, 3)")
        plan = plan_import(conn, tagged(["1,"]))
        apply_import(conn, plan)
        assert tags_in(conn) == {1: None, 2: None, 3: "halal", 4: None}


class TestApply:
    def test_adds_column_and_writes_canonical_tags(self):
        conn = make_db()
        apply_import(conn, plan_import(conn, tagged(['1,"Vegan, Gluten Free"'])))
        assert tags_in(conn)[1] == "gluten-free, vegan"

    def test_refuses_a_plan_with_errors(self):
        conn = make_db()
        plan = plan_import(conn, tagged(["1,vegan", "2,vegan"]))
        with pytest.raises(ValueError):
            apply_import(conn, plan)
        assert not has_diet_tags_column(conn)


class TestCommandLine:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = str(tmp_path / "menu.db")
        make_db(path).close()
        return path

    def run(self, *argv):
        out = io.StringIO()
        code = main(list(argv), out=out)
        return code, out.getvalue()

    def test_export_then_dry_run_then_apply(self, db_path, tmp_path):
        sheet = tmp_path / "tags.csv"
        assert self.run("--db", db_path, "export", str(sheet))[0] == 0
        assert sheet.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel

        with open(sheet, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["diet_tags"] = {"1": "Vegan, Halal", "4": "pescatarian"}.get(row["itm_id"], "")
        with open(sheet, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

        code, text = self.run("--db", db_path, "import", str(sheet))
        assert code == 0
        assert "Chana Masala: (none) -> halal, vegan" in text
        assert "Dry run: 2 to change, 2 unchanged" in text
        assert not has_diet_tags_column(sqlite3.connect(db_path))

        code, text = self.run("--db", db_path, "import", str(sheet), "--apply")
        assert code == 0 and "Applied: 2 to change" in text
        assert tags_in(sqlite3.connect(db_path)) == {
            1: "halal, vegan",
            2: None,
            3: None,
            4: "pescatarian",
        }

    def test_import_with_errors_exits_1_and_changes_nothing(self, db_path, tmp_path):
        sheet = tmp_path / "bad.csv"
        sheet.write_text("itm_id,diet_tags\n1,vegan\n3,vegetarian\n")
        code, text = self.run("--db", db_path, "import", str(sheet), "--apply")
        assert code == 1
        assert "nothing was changed" in text and "Beef Pho is tagged vegetarian" in text
        assert not has_diet_tags_column(sqlite3.connect(db_path))

    def test_missing_database(self, tmp_path):
        code, text = self.run("--db", str(tmp_path / "nope.db"), "export", "-")
        assert code == 1 and "No database" in text
