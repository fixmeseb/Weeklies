"""
Unit tests for proj2/plan_rules.py: the shared rules, and that generation re-checks its pick.
"""

import itertools
import json

import pandas as pd
import pytest

from proj2 import menu_generation
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator
from proj2.plan_rules import PlanRuleError, item_rejection, parse_allergens, slot_rejection

MONDAY = "2025-11-03"
ALL_DAY = json.dumps({d: [0, 2359] for d in DAYS_OF_WEEK})
DINNER_ONLY = json.dumps({d: [1700, 2200] for d in DAYS_OF_WEEK})


def make_item(**overrides):
    item = {
        "name": "Pho",
        "instock": 1,
        "allergens": "",
        "restaurant_status": "Open",
        "hours": ALL_DAY,
        "diet_tags": "",
    }
    item.update(overrides)
    return item


@pytest.mark.parametrize(
    "overrides,user_allergies,user_preferences,code",
    [
        ({}, "", "", None),
        ({"instock": 0}, "", "", "out_of_stock"),
        ({"restaurant_status": "Closed"}, "", "", "restaurant_unavailable"),
        ({"hours": DINNER_ONLY}, "", "", "restaurant_closed"),
        ({"allergens": "Soy"}, "soy", "", "allergen"),
        ({"diet_tags": ""}, "", "Halal", "diet"),
        ({"diet_tags": "halal"}, "", "Halal, Thai", None),
    ],
)
def test_item_rejection(overrides, user_allergies, user_preferences, code):
    rejection = item_rejection(
        make_item(**overrides), user_allergies, user_preferences, "Mon", 1000
    )
    assert (rejection[0] if rejection else None) == code


@pytest.mark.parametrize("placeholder", ["none", "None", " N/A ", "-"])
def test_none_placeholder_is_not_an_allergen(placeholder):
    assert parse_allergens(placeholder) == set()
    # A user who writes "None" as their allergies is not kept away from items marked "none".
    assert item_rejection(make_item(allergens="none"), placeholder, "", "Mon", 1000) is None


def test_placeholder_does_not_hide_real_allergens():
    assert parse_allergens("None, Soy") == {"soy"}
    assert item_rejection(make_item(allergens="none, Soy"), "soy", "", "Mon", 1000)[0] == "allergen"


def test_missing_item():
    assert item_rejection(None, "", "", "Mon", 1000)[0] == "item_not_found"


## ---------------------- Generation agrees with the shared rules ----------------------

ITEMS = [
    # itm_id, rtr_id, instock, allergens, diet_tags
    (1, 1, 1, "", ""),
    (2, 1, 1, "Peanuts", "vegan"),
    (3, 1, 0, "", "vegetarian"),
    (4, 2, 1, "Soy, Gluten", "vegetarian, halal"),
    (5, 2, 1, None, "halal"),
    (6, 3, 1, "", "vegan, gluten-free"),
]
RESTAURANTS = {1: ALL_DAY, 2: DINNER_ONLY, 3: json.dumps({"Mon": [800, 1500]})}


@pytest.fixture
def generator():
    gen = MenuGenerator.__new__(MenuGenerator)
    gen.menu_items = pd.DataFrame(
        [
            {
                "itm_id": itm_id,
                "rtr_id": rtr_id,
                "name": f"Meal {itm_id}",
                "description": "",
                "price": 500,
                "calories": 500,
                "instock": instock,
                "allergens": allergens,
                "diet_tags": tags,
            }
            for itm_id, rtr_id, instock, allergens, tags in ITEMS
        ]
    )
    gen.restaurants = pd.DataFrame(
        [{"rtr_id": rtr_id, "hours": hours} for rtr_id, hours in RESTAURANTS.items()]
    )
    gen.item_prices = dict(zip(gen.menu_items.itm_id, gen.menu_items.price))
    return gen


@pytest.mark.parametrize(
    "allergies,preferences,weekday,order_time",
    itertools.product(
        ["", "peanuts", "SOY"],
        ["", "Vegetarian", "halal", "Vegan, Gluten Free"],
        ["Mon", "Tue"],
        [1000, 2000],
    ),
)
def test_generation_filters_match_shared_rules(
    generator, allergies, preferences, weekday, order_time
):
    """An item is a generation candidate exactly when item_rejection allows it."""
    try:
        candidates = set(
            generator._eligible_candidates(
                allergies, weekday, order_time, preferences=preferences
            ).itm_id
        )
    except menu_generation.DietaryConstraintError:
        candidates = set()
    allowed = set()
    for itm_id, rtr_id, instock, item_allergens, tags in ITEMS:
        item = make_item(
            instock=instock,
            allergens=item_allergens,
            diet_tags=tags,
            hours=RESTAURANTS[rtr_id],
        )
        if item_rejection(item, allergies, preferences, weekday, order_time) is None:
            allowed.add(itm_id)
    assert candidates == allowed


def test_pick_that_slips_past_a_filter_is_not_saved(generator, monkeypatch):
    """If a candidate filter has a bug, the final check still stops the plan."""
    monkeypatch.setattr(menu_generation, "filter_diets", lambda items, preferences: items.copy())
    # Every item now looks eligible; the planner's first pick (item 1) is not halal.
    with pytest.raises(PlanRuleError, match="halal"):
        generator.update_menu("", "Halal", "", MONDAY, [1])


def test_pick_from_a_restaurant_no_longer_open_is_not_saved(generator):
    generator.restaurants = generator.restaurants[generator.restaurants.rtr_id != 1]
    with pytest.raises(PlanRuleError, match="not currently taking orders"):
        generator._check_pick(1, "", "", "Mon", 1000, 1)


## ---------------------- The meal slot: course and meal type ----------------------


@pytest.mark.parametrize(
    "course, meal_type, meal, code",
    [
        (None, None, 1, None),  # untagged items fit any slot
        ("main", None, 3, None),
        ("main", "breakfast", 1, None),
        ("main", "breakfast", 2, "wrong_meal_type"),
        ("main", "lunch-dinner", 1, "wrong_meal_type"),
        ("main", "lunch-dinner", 2, None),
        ("main", "lunch-dinner", 3, None),
        ("main", "breakfast, lunch-dinner", 1, None),
        ("main", "breakfast, lunch-dinner", 3, None),
        ("drink", "breakfast", 1, "not_a_meal"),
        ("dessert", None, 3, "not_a_meal"),
        ("starter", "lunch-dinner", 2, "not_a_meal"),
        (None, "snack", 2, "wrong_meal_type"),
        (None, "dessert", 3, "wrong_meal_type"),
    ],
)
def test_slot_rejection(course, meal_type, meal, code):
    item = make_item(course=course, meal_type=meal_type)
    rejection = slot_rejection(item, meal)
    assert (rejection[0] if rejection else None) == code
    # item_rejection applies it when told the meal, and skips it otherwise
    full = item_rejection(item, "", "", "Mon", 1000, meal)
    assert (full[0] if full else None) == code
    assert item_rejection(item, "", "", "Mon", 1000) is None


def test_slot_messages_name_the_dish_and_meal():
    assert slot_rejection(make_item(course="drink"), 1) == (
        "not_a_meal",
        "Pho is a drink, not a main dish.",
    )
    assert slot_rejection(make_item(meal_type="breakfast"), 3) == (
        "wrong_meal_type",
        "Pho is not served as dinner.",
    )


def test_generation_uses_the_slot_rule(generator):
    generator.menu_items["course"] = None
    generator.menu_items["meal_type"] = None
    generator.menu_items.loc[generator.menu_items.itm_id == 1, "course"] = "drink"
    generator.menu_items.loc[generator.menu_items.itm_id == 4, "meal_type"] = "breakfast"
    candidates = set(generator._eligible_candidates("", "Mon", 2000, meal=3).itm_id)
    assert 1 not in candidates and 4 not in candidates
    assert 2 in candidates
    # Without a meal (older callers) the slot rule is skipped.
    assert {1, 4} <= set(generator._eligible_candidates("", "Mon", 2000).itm_id)
