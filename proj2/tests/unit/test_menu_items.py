"""
Rules for what a restaurant may put on its own menu.

Two of these matter more than the rest, because they are the reasons the module exists
rather than preferences about forms:

- a dish cannot enter the catalog without the planner's three strongest tags, because
  ``variety.distance`` scores an untagged dish as maximally different from everything and
  the planner then prefers it (``test_untagged_dish_*``);
- a dish a diner has planned cannot be deleted, because ``weekly_item_totals`` raises for
  a planned id that has left the catalog (``test_delete_*``).
"""

import sqlite3

import pytest

from proj2 import meal_tags, menu_items, seed, variety
from proj2.meal_budget import weekly_item_totals


@pytest.fixture()
def conn(tmp_path):
    """A seeded catalog, with the tag columns the migrations add."""
    path = str(tmp_path / "menu.db")
    seed.seed_database(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


@pytest.fixture()
def rtr_id(conn):
    return conn.execute('SELECT rtr_id FROM "Restaurant" ORDER BY rtr_id LIMIT 1').fetchone()[0]


@pytest.fixture()
def other_rtr_id(conn, rtr_id):
    return conn.execute(
        'SELECT rtr_id FROM "Restaurant" WHERE rtr_id != ? ORDER BY rtr_id LIMIT 1', (rtr_id,)
    ).fetchone()[0]


def good_dish(**overrides):
    """The smallest dish that passes every rule."""
    dish = {
        "name": "Seitan Larb Bowl",
        "price": "13.50",
        "protein": "tofu",
        "cuisine": "thai",
        "carb_base": "rice",
    }
    dish.update(overrides)
    return dish


## --- prices ---------------------------------------------------------------


@pytest.mark.parametrize(
    "typed, cents",
    [("0", 0), ("9", 900), ("12.99", 1299), ("12.90", 1290), (" $13.50 ", 1350), (7.25, 725)],
)
def test_price_accepts_whole_cent_amounts(typed, cents):
    assert menu_items.price_cents(typed) == cents


@pytest.mark.parametrize("typed", ["", "   ", None, "abc", "-1", "12.999", "1e3.5", "NaN", "Inf"])
def test_price_rejects_anything_not_a_whole_cent_amount(typed):
    with pytest.raises(ValueError):
        menu_items.price_cents(typed)


def test_price_is_never_rounded_silently():
    """A third decimal is a mistake worth reporting, not worth absorbing."""
    with pytest.raises(ValueError):
        menu_items.price_cents("12.996")


def test_price_rejects_an_implausible_amount():
    with pytest.raises(ValueError):
        menu_items.price_cents(str(menu_items.PRICE_CENTS_MAX // 100 + 1))


## --- the required tags, and why ------------------------------------------


def test_untagged_dish_scores_the_maximum_distance_against_a_real_dish(conn):
    """The reason the three tags are required: absent data reads as perfect variety."""
    rows = {
        int(row["itm_id"]): row
        for row in conn.execute('SELECT * FROM "MenuItem" ORDER BY itm_id LIMIT 2')
    }
    real = [variety.features(row) for row in rows.values()]
    conn.execute(
        'INSERT INTO "MenuItem" (rtr_id, name, price, instock) VALUES (99, "Blank", 1200, 1)'
    )
    blank_row = conn.execute('SELECT * FROM "MenuItem" WHERE name = "Blank"').fetchone()
    blank = variety.features(blank_row)

    assert variety.distance(real[0], real[1]) < 1.0
    assert variety.distance(blank, real[0]) == pytest.approx(1.0)


def test_a_dish_cannot_be_added_without_the_planner_s_strongest_tags(conn, rtr_id):
    itm_id, errors = menu_items.create(conn, rtr_id, {"name": "Mystery Plate", "price": "9.99"})
    assert itm_id is None
    assert set(errors) == set(menu_items.REQUIRED_TAGS)


def test_the_required_tags_are_the_three_highest_weighted_ones():
    """If someone reweights variety.WEIGHTS, this should be revisited deliberately."""
    ranked = sorted(
        (column for column in variety.WEIGHTS if column in meal_tags.TAG_COLUMNS),
        key=lambda column: (-variety.WEIGHTS[column], column),
    )
    assert set(menu_items.REQUIRED_TAGS) == set(ranked[: len(menu_items.REQUIRED_TAGS)])


def test_a_required_tag_message_lists_the_values_that_would_work(conn, rtr_id):
    _, errors = menu_items.create(conn, rtr_id, good_dish(protein=""))
    assert "chicken" in errors["protein"]


def test_whitespace_is_not_a_tag(conn, rtr_id):
    itm_id, errors = menu_items.create(conn, rtr_id, good_dish(cuisine="   "))
    assert itm_id is None and "cuisine" in errors


## --- tag vocabularies ----------------------------------------------------


def test_an_unknown_tag_value_is_refused_rather_than_stored(conn, rtr_id):
    itm_id, errors = menu_items.create(conn, rtr_id, good_dish(protein="unicorn"))
    assert itm_id is None
    assert "unicorn" in errors["protein"]


def test_tags_are_stored_canonically(conn, rtr_id):
    itm_id, errors = menu_items.create(
        conn, rtr_id, good_dish(flavor="Spicy,  herby", diet_tags="Vegan", spice_level="2")
    )
    assert errors == {}
    row = menu_items.get_item(conn, rtr_id, itm_id)
    assert row["flavor"] == "herby, spicy"
    assert row["diet_tags"] == "vegan"
    assert row["spice_level"] == 2


def test_a_level_outside_its_range_is_refused(conn, rtr_id):
    _, errors = menu_items.create(conn, rtr_id, good_dish(spice_level="9"))
    assert "spice_level" in errors


def test_an_empty_tag_is_stored_as_null_not_an_empty_string(conn, rtr_id):
    """spice_level is an INTEGER column; "" in it would come back as a surprise."""
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish(spice_level="", texture=""))
    row = menu_items.get_item(conn, rtr_id, itm_id)
    assert row["spice_level"] is None
    assert row["texture"] is None


## --- self-consistency ----------------------------------------------------


def test_a_vegan_dish_cannot_have_beef_in_it(conn, rtr_id):
    itm_id, errors = menu_items.create(conn, rtr_id, good_dish(protein="beef", diet_tags="vegan"))
    assert itm_id is None
    assert "vegan" in errors["_consistency"]


def test_a_vegan_dish_cannot_declare_a_dairy_allergen(conn, rtr_id):
    itm_id, errors = menu_items.create(
        conn, rtr_id, good_dish(diet_tags="vegan", allergens="dairy")
    )
    assert itm_id is None
    assert "_consistency" in errors


def test_consistency_is_judged_on_the_whole_dish_not_just_the_edit(conn, rtr_id):
    """Setting a protein must clash with a diet tag that was already stored."""
    itm_id, errors = menu_items.create(conn, rtr_id, good_dish(diet_tags="vegan"))
    assert errors == {}
    saved, errors = menu_items.update(conn, rtr_id, itm_id, {"protein": "beef"})
    assert saved is False
    assert "_consistency" in errors


def test_clearing_the_diet_tag_resolves_the_clash(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish(diet_tags="vegan"))
    saved, errors = menu_items.update(conn, rtr_id, itm_id, {"diet_tags": "", "protein": "beef"})
    assert (saved, errors) == (True, {})


## --- ownership -----------------------------------------------------------


def test_one_restaurant_cannot_read_another_s_dish(conn, rtr_id, other_rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    assert menu_items.get_item(conn, other_rtr_id, itm_id) is None


def test_one_restaurant_cannot_edit_another_s_dish(conn, rtr_id, other_rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    saved, errors = menu_items.update(conn, other_rtr_id, itm_id, {"price": "0.01"})
    assert saved is False and "_missing" in errors
    assert menu_items.get_item(conn, rtr_id, itm_id)["price"] == 1350


def test_one_restaurant_cannot_delete_another_s_dish(conn, rtr_id, other_rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    removed, errors = menu_items.delete(conn, other_rtr_id, itm_id)
    assert removed is False and "_missing" in errors
    assert menu_items.get_item(conn, rtr_id, itm_id) is not None


def test_a_request_cannot_choose_its_own_restaurant_or_item_id(conn, rtr_id, other_rtr_id):
    itm_id, errors = menu_items.create(conn, rtr_id, good_dish(rtr_id=other_rtr_id, itm_id=4242))
    assert errors == {}
    assert itm_id != 4242
    owning = conn.execute('SELECT rtr_id FROM "MenuItem" WHERE itm_id = ?', (itm_id,)).fetchone()[0]
    assert owning == rtr_id


def test_list_items_only_shows_one_restaurant_s_menu(conn, rtr_id, other_rtr_id):
    mine = {row["itm_id"] for row in menu_items.list_items(conn, rtr_id)}
    theirs = {row["itm_id"] for row in menu_items.list_items(conn, other_rtr_id)}
    assert mine and theirs
    assert mine.isdisjoint(theirs)


## --- partial edits -------------------------------------------------------


def test_an_edit_leaves_the_fields_it_does_not_mention_alone(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish(calories="620"))
    saved, errors = menu_items.update(conn, rtr_id, itm_id, {"price": "14.25"})
    assert (saved, errors) == (True, {})
    row = menu_items.get_item(conn, rtr_id, itm_id)
    assert (row["price"], row["calories"], row["protein"]) == (1425, 620, "tofu")


def test_an_edit_may_not_clear_a_required_tag(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    saved, errors = menu_items.update(conn, rtr_id, itm_id, {"protein": ""})
    assert saved is False and "protein" in errors


def test_an_edit_that_carries_nothing_editable_is_a_no_op(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    assert menu_items.update(conn, rtr_id, itm_id, {"nonsense": "1"}) == (True, {})


def test_editing_a_missing_dish_says_so(conn, rtr_id):
    saved, errors = menu_items.update(conn, rtr_id, 999_999, {"price": "1.00"})
    assert saved is False and "_missing" in errors


## --- taking a dish off the menu ------------------------------------------


def test_out_of_stock_removes_a_dish_from_the_plannable_pool(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    assert menu_items.set_stock(conn, rtr_id, itm_id, False) is True
    assert menu_items.get_item(conn, rtr_id, itm_id)["instock"] == 0
    plannable = conn.execute(
        'SELECT COUNT(*) FROM "MenuItem" WHERE itm_id = ? AND instock == 1', (itm_id,)
    ).fetchone()[0]
    assert plannable == 0


def test_out_of_stock_still_prices_a_plan_that_names_the_dish(conn, rtr_id):
    """This is why withdrawing is instock=0 and not a delete."""
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    menu_items.set_stock(conn, rtr_id, itm_id, False)
    prices = {
        int(row["itm_id"]): row["price"]
        for row in conn.execute('SELECT itm_id, price FROM "MenuItem"')
    }
    assert weekly_item_totals(f"[2026-11-23,{itm_id},3]", prices) == {"2026-11-23": 1350}


def test_a_dish_can_be_put_back(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    menu_items.set_stock(conn, rtr_id, itm_id, False)
    assert menu_items.set_stock(conn, rtr_id, itm_id, True) is True
    assert menu_items.get_item(conn, rtr_id, itm_id)["instock"] == 1


def test_stock_cannot_be_changed_on_another_restaurant_s_dish(conn, rtr_id, other_rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    assert menu_items.set_stock(conn, other_rtr_id, itm_id, False) is False
    assert menu_items.get_item(conn, rtr_id, itm_id)["instock"] == 1


## --- deleting ------------------------------------------------------------


def test_an_unreferenced_dish_can_be_deleted(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    assert menu_items.delete(conn, rtr_id, itm_id) == (True, {})
    assert menu_items.get_item(conn, rtr_id, itm_id) is None


def test_deleting_a_planned_dish_is_refused(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    conn.execute('UPDATE "User" SET generated_menu = ?', (f"[2026-11-23,{itm_id},3]",))
    removed, errors = menu_items.delete(conn, rtr_id, itm_id)
    assert removed is False
    assert "out of stock" in errors["_blocked"]
    assert menu_items.get_item(conn, rtr_id, itm_id) is not None


def test_deleting_a_planned_dish_would_otherwise_break_that_calendar(conn, rtr_id):
    """The failure the refusal prevents, stated as the error it would raise."""
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    conn.execute('DELETE FROM "MenuItem" WHERE itm_id = ?', (itm_id,))
    prices = {
        int(row["itm_id"]): row["price"]
        for row in conn.execute('SELECT itm_id, price FROM "MenuItem"')
    }
    with pytest.raises(ValueError, match="no longer in the catalog"):
        weekly_item_totals(f"[2026-11-23,{itm_id},3]", prices)


def test_a_legacy_plan_entry_without_a_meal_number_also_blocks_deletion(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    conn.execute('UPDATE "User" SET generated_menu = ?', (f"[2026-11-23,{itm_id}]",))
    assert menu_items.delete(conn, rtr_id, itm_id)[0] is False


def test_a_plan_naming_a_similar_id_does_not_block_deletion(conn, rtr_id):
    """ "[2026-11-23,70,3]" must not look like a reference to item 7."""
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    conn.execute('UPDATE "User" SET generated_menu = ?', (f"[2026-11-23,{itm_id}9,3]",))
    assert menu_items.references(conn, itm_id) == {"plans": 0, "orders": 0}


def test_deleting_an_ordered_dish_is_refused(conn, rtr_id):
    itm_id, _ = menu_items.create(conn, rtr_id, good_dish())
    conn.execute(
        'INSERT INTO "Order" (rtr_id, usr_id, details, status)'
        ' SELECT ?, MIN(usr_id), ?, "Delivered" FROM "User"',
        (rtr_id, '{"items": [{"itm_id": %d, "qty": 1}]}' % itm_id),
    )
    removed, errors = menu_items.delete(conn, rtr_id, itm_id)
    assert removed is False and "order" in errors["_blocked"]


def test_deleting_a_missing_dish_says_so(conn, rtr_id):
    removed, errors = menu_items.delete(conn, rtr_id, 999_999)
    assert removed is False and "_missing" in errors


## --- the published contract ----------------------------------------------


def test_the_schema_marks_exactly_the_fields_the_validator_requires(conn, rtr_id):
    required = menu_items.schema()["required"]
    for field in required:
        submitted = good_dish()
        submitted.pop(field, None)
        submitted[field] = ""
        _, errors = menu_items.create(conn, rtr_id, submitted)
        assert field in errors, f"schema calls {field} required but the validator allowed it"


def test_the_schema_offers_only_values_the_validator_accepts():
    for column in meal_tags.TAG_COLUMNS:
        spec = menu_items.schema()["fields"][column]
        for value in spec.get("values", []):
            _, problems = meal_tags.canonical(column, value)
            assert problems == [], f"{column}={value} is advertised but rejected"


def test_every_editable_column_appears_in_the_schema():
    fields = menu_items.schema()["fields"]
    assert set(menu_items.EDITABLE_COLUMNS) <= set(fields)


def test_the_schema_never_advertises_a_column_a_request_cannot_set():
    assert set(menu_items.schema()["fields"]) <= set(menu_items.EDITABLE_COLUMNS)
