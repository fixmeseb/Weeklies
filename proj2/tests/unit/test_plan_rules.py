"""
Unit tests for proj2/plan_rules.py: the shared rules, and that generation re-checks its pick.
"""

import itertools
import json
from unittest.mock import Mock

import pandas as pd
import pytest

from proj2 import menu_generation
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator
from proj2.plan_rules import PlanRuleError, item_rejection, parse_allergens

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
    gen.generator = Mock()
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
    generator.generator.generate.return_value = (
        "<|start_of_role|>assistant<|end_of_role|>1<|end_of_text|>"
    )
    with pytest.raises(PlanRuleError, match="halal"):
        generator.update_menu("", "Halal", "", MONDAY, [1])


def test_pick_from_a_restaurant_no_longer_open_is_not_saved(generator):
    generator.generator.generate.return_value = (
        "<|start_of_role|>assistant<|end_of_role|>1<|end_of_text|>"
    )
    candidates = generator._eligible_candidates("", "Mon", 1000)
    generator.restaurants = generator.restaurants[generator.restaurants.rtr_id != 1]
    with pytest.raises(PlanRuleError, match="not currently taking orders"):
        generator._MenuGenerator__pick_menu_item("", "", "Mon", 1, candidates)
