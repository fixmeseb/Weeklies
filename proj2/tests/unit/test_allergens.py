"""
Unit tests for allergen spellings and coverage (proj2/allergens.py) and their use by
the planner, swaps, account merging and the tag import check
"""

import pandas as pd
import pytest

from proj2.allergens import (
    allergen_conflicts,
    avoided_allergens,
    normalize_allergen,
    parse_allergens,
)
from proj2.dietary import with_account_allergies
from proj2.menu_generation import filter_allergens
from proj2.menu_tags_io import contradictions
from proj2.plan_rules import item_rejection

## Every allergen the sign-up and edit-profile forms offer
FORM_ALLERGENS = [
    "Peanuts", "Tree Nuts", "Milk", "Eggs", "Wheat", "Soy",
    "Fish", "Shellfish", "Sesame", "Gluten", "Lactose", "Sulphites",
]  # fmt: skip


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("Tree Nuts", "tree-nuts"),
        ("tree_nut", "tree-nuts"),
        ("Peanut", "peanuts"),
        ("Milk", "dairy"),
        ("LACTOSE", "dairy"),
        ("egg", "eggs"),
        ("Sulfites", "sulphites"),
        ("soya", "soy"),
        ("Celery", "celery"),  # not listed: kept in its normalized spelling
    ],
)
def test_spellings_share_one_stored_name(typed, stored):
    assert normalize_allergen(typed) == stored


def test_parse_allergens_drops_placeholders_and_merges_spellings():
    assert parse_allergens("Milk, dairy, none, , Tree Nuts") == {"dairy", "tree-nuts"}
    assert parse_allergens(float("nan")) == set()


@pytest.mark.parametrize(
    "allergy, item_allergens",
    [
        ("Milk", "dairy"),
        ("Lactose", "Dairy, gluten"),
        ("Tree Nuts", "tree nuts"),
        ("peanut", "Peanuts"),
        ("Gluten", "wheat"),
        ("Gluten", "barley"),
        ("Wheat", "gluten"),  # a "gluten" label may be wheat: fail closed
        ("Shellfish", "shrimp"),
        ("Peanuts", "nuts"),  # a vague "nuts" label may be peanuts
    ],
)
def test_allergy_rules_out_every_spelling_and_covered_allergen(allergy, item_allergens):
    assert allergen_conflicts(item_allergens, allergy)
    item = {
        "name": "Dish",
        "instock": 1,
        "restaurant_status": "Open",
        "hours": '{"Mon": [0, 2359]}',
        "allergens": item_allergens,
    }
    assert item_rejection(item, allergy, "", "Mon", 1200)[0] == "allergen"
    items = pd.DataFrame({"itm_id": [1], "allergens": [item_allergens]})
    assert filter_allergens(items, allergy).empty


@pytest.mark.parametrize(
    "allergy, item_allergens",
    [("Fish", "shellfish"), ("Shellfish", "fish"), ("Gluten", "soy"), ("Milk", "eggs")],
)
def test_unrelated_allergens_do_not_conflict(allergy, item_allergens):
    assert not allergen_conflicts(item_allergens, allergy)


def test_every_form_allergen_is_avoided_under_its_menu_name():
    menu_names = {
        "Milk": "dairy",
        "Lactose": "dairy",
        "Tree Nuts": "tree-nuts",
        "Wheat": "gluten",
    }
    for allergy in FORM_ALLERGENS:
        assert normalize_allergen(allergy) in avoided_allergens(allergy)
        if allergy in menu_names:
            assert menu_names[allergy] in avoided_allergens(allergy)


def test_account_allergies_merge_by_stored_name():
    assert with_account_allergies("Milk", "dairy, Peanut") == "Milk, Peanut"
    assert with_account_allergies("Tree Nuts", "tree-nut") == "Tree Nuts"


def test_vegan_item_listing_milk_is_a_contradiction():
    assert contradictions("vegan", "Milk") == ["vegan but contains dairy"]
    assert contradictions("gluten-free", "Barley") == ["gluten-free but contains barley"]
