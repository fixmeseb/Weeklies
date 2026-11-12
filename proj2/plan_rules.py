"""
The rules every planned meal must pass, in one place.

Meal generation filters its candidates with these rules and checks its final pick
against item_rejection before the plan is saved; meal swaps check the replacement
with the same function. A new way of choosing meals (another model, a manual editor)
should also call item_rejection before saving.

Imports only pandas and proj2.dietary so menu_generation and meal_swap can both use it.
"""

import json

import pandas as pd

from proj2.dietary import missing_diets, required_diets


class PlanRuleError(RuntimeError):
    """A chosen item broke a plan rule; the plan must not be saved."""


## Values people write to mean "no allergens"; they are not allergens themselves
NO_ALLERGENS = frozenset({"none", "n/a", "-"})


def parse_allergens(allergens) -> set:
    """
    Normalizes a comma-separated allergen string into a set of casefolded tags

    Args:
        allergens (str | None): A comma-separated string such as "Gluten, Soy" (None/NaN allowed)

    Returns:
        set: The allergen tags, stripped and casefolded, without empty entries or
            placeholders such as "none" (see NO_ALLERGENS)
    """
    if allergens is None or (not isinstance(allergens, str) and pd.isna(allergens)):
        return set()
    tags = {tag.strip().casefold() for tag in str(allergens).split(",") if tag.strip()}
    return tags - NO_ALLERGENS


def is_restaurant_open(hours: str, weekday: str, time: int) -> bool:
    """
    Checks whether one restaurant's stored hours JSON has it open at the specified weekday and time

    Args:
        hours (str): The restaurant hours JSON, e.g. '{"Mon": [1100, 2200], ...}'
        weekday (str): The day of the week to check (e.g., "Mon", "Tue", etc.)
        time (int): The time to check in HHMM format (24H time)

    Returns:
        bool: True if any open/close window contains the time; False if closed, or if the
            hours are unparseable, missing the weekday, non-numeric, or an odd-length list
    """
    try:
        opening_times = json.loads(hours)[weekday]
        if not isinstance(opening_times, list) or not all(
            isinstance(value, (int, float)) for value in opening_times
        ):
            raise ValueError("Invalid hours")
    except (TypeError, ValueError, KeyError):
        return False
    if len(opening_times) % 2 == 1:
        return False
    for x in range(len(opening_times) // 2):
        if opening_times[x * 2] <= time and opening_times[x * 2 + 1] >= time:
            return True
    return False


def item_rejection(item, user_allergies, user_preferences, weekday: str, order_time: int):
    """
    Checks whether a menu item may fill a meal slot for a user

    Args:
        item (dict | None): The item, with keys name, instock, allergens, restaurant_status,
            hours and (optionally) diet_tags; None if it does not exist
        user_allergies (str | None): The user's comma-separated allergies
        user_preferences (str | None): The user's comma-separated preferences; the diets
            they name (see proj2.dietary) must all be satisfied by the item's diet_tags
        weekday (str): The slot's day of the week ("Mon".."Sun")
        order_time (int): The slot's order time in HHMM format

    Returns:
        Tuple[str, str] | None: (error_code, message) if the item is not allowed, otherwise None
    """
    if item is None:
        return "item_not_found", "That menu item does not exist."
    if not item["instock"]:
        return "out_of_stock", f"{item['name']} is currently out of stock."
    if (item["restaurant_status"] or "").strip().lower() != "open":
        return "restaurant_unavailable", "That restaurant is not currently taking orders."
    if not is_restaurant_open(item["hours"], weekday, order_time):
        return "restaurant_closed", f"That restaurant is closed at that meal time on {weekday}."

    conflicts = parse_allergens(item["allergens"]) & parse_allergens(user_allergies)
    if conflicts:
        return (
            "allergen",
            f"{item['name']} contains your allergens: {', '.join(sorted(conflicts))}.",
        )

    unmet = missing_diets(item.get("diet_tags"), required_diets(user_preferences))
    if unmet:
        return "diet", f"{item['name']} is not tagged as {', '.join(sorted(unmet))}."
    return None
