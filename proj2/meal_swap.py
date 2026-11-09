"""
Single-meal swaps: replace one date/meal slot of a user's generated menu.

The generated menu is stored on the User row as a string of entries like
"[YYYY-MM-DD,itm_id,meal]" where meal is 1 (breakfast), 2 (lunch) or 3 (dinner).
Legacy entries without a meal number are treated as dinner, matching
Flask_app.parse_generated_menu.
"""

import datetime
import json
import re

import pandas as pd

from proj2.menu_generation import DAYS_OF_WEEK, get_meal_and_order_time, is_taking_orders
from proj2.sqlQueries import fetch_all, fetch_one

## Matches one menu entry; the meal number is optional for legacy entries
SLOT_PATTERN = re.compile(r"\[\s*(\d{4}-\d{2}-\d{2})\s*,\s*([0-9]+)\s*(?:,\s*([123])\s*)?\]")

## Meal number assumed for entries that do not store one
DEFAULT_MEAL = 3


class SlotNotFoundError(LookupError):
    """Raised when the requested date/meal slot is not in the user's menu"""

    pass


def find_slot_item(menu: str, date: str, meal: int):
    """
    Finds the item currently planned for a date/meal slot

    Args:
        menu (str): The generated menu string (can be empty or None)
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)

    Returns:
        int | None: The planned itm_id, or None if the slot is empty
    """
    for match in SLOT_PATTERN.finditer(menu or ""):
        d, itm_id, m = match.groups()
        if d == date and int(m or DEFAULT_MEAL) == meal:
            return int(itm_id)
    return None


def replace_menu_slot(menu: str, date: str, meal: int, new_itm_id: int) -> str:
    """
    Replaces the item in one date/meal slot, leaving every other entry untouched

    Args:
        menu (str): The generated menu string
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)
        new_itm_id (int): The replacement menu item ID

    Returns:
        str: The menu string with only the matching slot rewritten as "[date,new_itm_id,meal]"

    Raises:
        SlotNotFoundError: if the menu has no entry for that date/meal
    """
    found = False

    def _swap(match):
        nonlocal found
        d, _, m = match.groups()
        if d == date and int(m or DEFAULT_MEAL) == meal:
            found = True
            return f"[{date},{int(new_itm_id)},{meal}]"
        return match.group(0)

    updated = SLOT_PATTERN.sub(_swap, menu or "")
    if not found:
        raise SlotNotFoundError(f"No planned meal {meal} on {date}")
    return updated


def parse_allergens(allergens) -> set:
    """
    Normalizes a comma-separated allergen string into a set of casefolded tags.
    Follows the same rules as menu_generation.filter_allergens.

    Args:
        allergens (str | None): A comma-separated string such as "Gluten, Soy" (None/NaN allowed)

    Returns:
        set: The allergen tags, stripped and casefolded, with empty entries removed
    """
    if allergens is None or (not isinstance(allergens, str) and pd.isna(allergens)):
        return set()
    return {tag.strip().casefold() for tag in str(allergens).split(",") if tag.strip()}


def is_restaurant_open(hours: str, weekday: str, time: int) -> bool:
    """
    Checks whether one restaurant's stored hours JSON has it open at the specified weekday and time.
    Follows the same rules as menu_generation.filter_closed_restaurants.

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


## Columns loaded for a swap candidate; keys of the dicts returned by load_swap_item
_ITEM_COLUMNS = ("itm_id", "rtr_id", "name", "instock", "allergens", "restaurant_status", "hours")

_ITEM_SQL = """
    SELECT m.itm_id, m.rtr_id, m.name, m.instock, m.allergens, r.status, r.hours
    FROM MenuItem m
    JOIN Restaurant r ON r.rtr_id = m.rtr_id
"""


def slot_weekday_and_time(date: str, meal: int):
    """
    Maps a slot to the weekday and order time used for availability checks

    Args:
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)

    Returns:
        Tuple[str, int]: The weekday ("Mon".."Sun") and the meal's order time in HHMM format

    Raises:
        ValueError: if the date is not a valid YYYY-MM-DD date or the meal is not 1, 2, or 3
    """
    weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(date).weekday()]
    _, order_time = get_meal_and_order_time(meal)
    return weekday, order_time


def swap_rejection(item, user_allergies: str, date: str, meal: int):
    """
    Checks whether a menu item may fill a date/meal slot for a user

    Args:
        item (dict | None): A candidate loaded by load_swap_item
        user_allergies (str): The user's comma-separated allergies, as stored on their account
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)

    Returns:
        Tuple[str, str] | None: (error_code, message) if the item is not allowed, otherwise None
    """
    if item is None:
        return "item_not_found", "That menu item does not exist."
    if not item["instock"]:
        return "out_of_stock", f"{item['name']} is currently out of stock."
    if not is_taking_orders(item["restaurant_status"]):
        return "restaurant_unavailable", "That restaurant is not currently taking orders."

    weekday, order_time = slot_weekday_and_time(date, meal)
    if not is_restaurant_open(item["hours"], weekday, order_time):
        return "restaurant_closed", f"That restaurant is closed at that meal time on {weekday}."

    conflicts = parse_allergens(item["allergens"]) & parse_allergens(user_allergies)
    if conflicts:
        return (
            "allergen",
            f"{item['name']} contains your allergens: {', '.join(sorted(conflicts))}.",
        )
    return None


def load_swap_item(conn, itm_id: int):
    """
    Loads one menu item with the restaurant fields needed for swap checks

    Args:
        conn (sqlite3.Connection): An open database connection
        itm_id (int): The menu item ID

    Returns:
        dict | None: The item fields keyed by _ITEM_COLUMNS, or None if it does not exist
    """
    row = fetch_one(conn, _ITEM_SQL + " WHERE m.itm_id = ?", (itm_id,))
    return dict(zip(_ITEM_COLUMNS, row)) if row else None


def list_swap_options(conn, user_allergies: str, date: str, meal: int, exclude_itm_id=None):
    """
    Lists every menu item that would pass swap_rejection for a slot

    Args:
        conn (sqlite3.Connection): An open database connection
        user_allergies (str): The user's comma-separated allergies
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)
        exclude_itm_id (int | None): An item to leave out, typically the one already planned

    Returns:
        List[dict]: The eligible items, ordered by itm_id
    """
    rows = fetch_all(conn, _ITEM_SQL + " WHERE m.instock = 1 ORDER BY m.itm_id")
    options = []
    for row in rows:
        item = dict(zip(_ITEM_COLUMNS, row))
        if item["itm_id"] == exclude_itm_id:
            continue
        if swap_rejection(item, user_allergies, date, meal) is None:
            options.append(item)
    return options
