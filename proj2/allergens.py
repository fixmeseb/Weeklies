"""
Allergen names: one spelling per allergen, and which item allergens a user's allergy rules out.

People and restaurants write the same allergen many ways ("Tree Nuts", "tree-nut",
"peanut"), and the sign-up form offers names the menu does not use ("Milk" and
"Lactose", where menu items list "dairy"). Matching only ignored case, so those
users were planned meals they are allergic to. Every allergen is now stored and
compared in one canonical spelling (normalize_allergen), and a user's allergy also
rules out the item allergens that contain it (ALLERGY_COVERS: an item that lists
"gluten" may be wheat).

The list is open: an allergen not named here is still matched by its normalized
spelling, so a rare allergy typed by hand keeps working.
"""

import pandas as pd

from proj2.dietary import normalize_tag

## Values people write to mean "no allergens"; they are not allergens themselves
NO_ALLERGENS = frozenset({"none", "n/a", "-"})

## Other spellings -> the canonical allergen (keys and values after normalize_tag)
ALLERGEN_ALIASES = {
    "peanut": "peanuts",
    "tree-nut": "tree-nuts",
    "treenuts": "tree-nuts",
    "milk": "dairy",
    "lactose": "dairy",
    "egg": "eggs",
    "sulphite": "sulphites",
    "sulfite": "sulphites",
    "sulfites": "sulphites",
    "crustacean": "crustaceans",
    "shrimps": "shrimp",
    "sesame-seeds": "sesame",
    "soya": "soy",
    "soybeans": "soy",
}

## A broad allergen and the specific ones it includes. The relation runs both ways: a
## user allergic to gluten must avoid items listing wheat, and a user allergic to
## wheat must avoid items listing only "gluten", since that item may be wheat.
## Pairs do not chain: barley and wheat share "gluten" but do not rule each other out.
_INCLUDES = {
    "gluten": {"wheat", "barley", "rye"},
    "shellfish": {"crustaceans", "shrimp", "crab", "lobster", "mollusks"},
    "crustaceans": {"shrimp", "crab", "lobster"},
    "nuts": {"peanuts", "tree-nuts"},
}


def _both_ways(includes: dict) -> dict:
    covers = {}
    for broad, members in includes.items():
        for member in members:
            covers.setdefault(broad, set()).add(member)
            covers.setdefault(member, set()).add(broad)
    return covers


## A user allergic to the key must also avoid items listing any of these, because
## those items contain (or, for a vague label, may contain) the allergen.
ALLERGY_COVERS = _both_ways(_INCLUDES)


def normalize_allergen(value) -> str:
    """
    One allergen in its stored spelling

    Args:
        value (str): The allergen as typed, e.g. "Tree Nuts", "Milk" or "peanut"

    Returns:
        str: The canonical name, e.g. "tree-nuts", "dairy" or "peanuts"
    """
    tag = normalize_tag(value)
    return ALLERGEN_ALIASES.get(tag, tag)


def parse_allergens(allergens) -> set:
    """
    Normalizes a comma-separated allergen string into a set of canonical allergens

    Args:
        allergens (str | None): A comma-separated string such as "Gluten, Soy" (None/NaN allowed)

    Returns:
        set: The canonical allergens (normalize_allergen), without empty entries or
            placeholders such as "none" (see NO_ALLERGENS)
    """
    if allergens is None or (not isinstance(allergens, str) and pd.isna(allergens)):
        return set()
    tags = {normalize_allergen(tag) for tag in str(allergens).split(",")}
    return tags - NO_ALLERGENS - {""}  # "-" normalizes to ""


def avoided_allergens(user_allergies) -> set:
    """
    Every item allergen a user must not be served

    Args:
        user_allergies (str | None): The user's comma-separated allergies

    Returns:
        set: The user's canonical allergies plus what each one covers (ALLERGY_COVERS)
    """
    allergies = parse_allergens(user_allergies)
    avoided = set(allergies)
    for allergy in allergies:
        avoided |= ALLERGY_COVERS.get(allergy, set())
    return avoided


def allergen_conflicts(item_allergens, user_allergies) -> set:
    """
    The allergens an item lists that the user must avoid

    Args:
        item_allergens (str | None): The item's comma-separated allergens
        user_allergies (str | None): The user's comma-separated allergies

    Returns:
        set: The item's canonical allergens that conflict; empty if it is safe
    """
    return parse_allergens(item_allergens) & avoided_allergens(user_allergies)
