"""The generation path and the swap path must agree on what "open for orders" means.

meal_swap.check_swap treats a restaurant as available when
`(status or "").strip().lower() == "open"`. MenuGenerator compared against the literal
"Open" instead, which excluded every restaurant the seeds and fixtures create, because all
of them store 'open'. These tests pin the two to the same rule.
"""

import json
import sqlite3

import pytest

from proj2.menu_generation import MenuGenerator, is_taking_orders

ALL_DAY = json.dumps({d: [0, 2359] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]})

SCHEMA = """
CREATE TABLE Restaurant (rtr_id INTEGER PRIMARY KEY, name TEXT, status TEXT, hours TEXT);
CREATE TABLE MenuItem (itm_id INTEGER PRIMARY KEY, rtr_id INTEGER, name TEXT, description TEXT,
                       price INTEGER, calories INTEGER, instock INTEGER, allergens TEXT);
"""


def _db(tmp_path, status):
    """A one-restaurant, one-item catalog whose restaurant carries `status`."""
    path = str(tmp_path / "status.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO Restaurant VALUES (1, 'Cafe', ?, ?)", (status, ALL_DAY))
        conn.execute(
            "INSERT INTO MenuItem VALUES (1, 1, 'Soup', 'Hot', 500, 300, 1, '')",
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _swap_rule(status):
    """The rule the swap path applies; both paths now call this same function."""
    return is_taking_orders(status)


@pytest.mark.parametrize("status", ["open", "Open", "OPEN", " open ", "\topen\n"])
def test_any_casing_or_padding_of_open_is_available(tmp_path, status):
    gen = MenuGenerator(tokens=10, database_path=_db(tmp_path, status))
    assert set(gen.restaurants["rtr_id"]) == {1}
    assert _swap_rule(status) is True


@pytest.mark.parametrize("status", ["Closed", "closed", "", "   ", None, "pending", "open for now"])
def test_anything_that_is_not_open_is_excluded(tmp_path, status):
    gen = MenuGenerator(tokens=10, database_path=_db(tmp_path, status))
    assert set(gen.restaurants["rtr_id"]) == set()
    assert _swap_rule(status) is False


@pytest.mark.parametrize(
    "status",
    ["open", "Open", "OPEN", " open ", "Closed", "closed", "", "   ", None, "pending"],
)
def test_generation_and_swap_never_disagree(tmp_path, status):
    """Whatever the stored value, both halves of the app reach the same verdict."""
    gen = MenuGenerator(tokens=10, database_path=_db(tmp_path, status))
    assert bool(set(gen.restaurants["rtr_id"])) == _swap_rule(status)


def test_a_closed_restaurant_does_not_hide_an_open_one(tmp_path):
    path = str(tmp_path / "mixed.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO Restaurant VALUES (?, ?, ?, ?)",
            [
                (1, "Shut", "Closed", ALL_DAY),
                (2, "Lowercase", "open", ALL_DAY),
                (3, "Unrecorded", None, ALL_DAY),
                (4, "Capitalised", "Open", ALL_DAY),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    gen = MenuGenerator(tokens=10, database_path=path)
    assert set(gen.restaurants["rtr_id"]) == {2, 4}
