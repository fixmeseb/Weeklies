"""
Single-meal swaps: replace one date/meal slot of a user's generated menu.

The generated menu is stored on the User row as a string of entries like
"[YYYY-MM-DD,itm_id,meal]" where meal is 1 (breakfast), 2 (lunch) or 3 (dinner).
Legacy entries without a meal number are treated as dinner, matching
Flask_app.parse_generated_menu.
"""

import datetime
import re

from proj2 import variety
from proj2.meal_budget import item_price_cents, plan_entries
from proj2.meal_tags import has_column
from proj2.plan_rules import (  # noqa: F401  parse_allergens/is_restaurant_open re-exported
    is_restaurant_open,
    item_rejection,
    parse_allergens,
)
from proj2.menu_generation import DAYS_OF_WEEK, get_meal_and_order_time
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


## Columns loaded for a swap candidate; keys of the dicts returned by load_swap_item
_ITEM_COLUMNS = (
    "itm_id",
    "rtr_id",
    "name",
    "instock",
    "allergens",
    "restaurant_status",
    "hours",
    "diet_tags",
    "course",
    "meal_type",
)

## Tag columns read when the database has them; older databases read them as untagged
_OPTIONAL_COLUMNS = ("diet_tags", "course", "meal_type")


def _item_sql(conn) -> str:
    """The candidate query; tag columns a database lacks read as NULL (untagged)."""
    optional = ", ".join(
        f"m.{column}" if has_column(conn, column) else "NULL" for column in _OPTIONAL_COLUMNS
    )
    return f"""
    SELECT m.itm_id, m.rtr_id, m.name, m.instock, m.allergens, r.status, r.hours, {optional}
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


def swap_rejection(item, user_allergies: str, date: str, meal: int, user_preferences: str = None):
    """
    Checks whether a menu item may fill a date/meal slot for a user (see proj2.plan_rules)

    Args:
        item (dict | None): A candidate loaded by load_swap_item
        user_allergies (str): The user's comma-separated allergies, as stored on their account
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)
        user_preferences (str | None): The user's comma-separated preferences; the diets
            they name (see proj2.dietary) must all be satisfied by the item's diet_tags

    Returns:
        Tuple[str, str] | None: (error_code, message) if the item is not allowed, otherwise None
    """
    if item is None:
        return item_rejection(None, user_allergies, user_preferences, None, None)
    weekday, order_time = slot_weekday_and_time(date, meal)
    return item_rejection(item, user_allergies, user_preferences, weekday, order_time, meal)


def load_swap_item(conn, itm_id: int):
    """
    Loads one menu item with the restaurant fields needed for swap checks

    Args:
        conn (sqlite3.Connection): An open database connection
        itm_id (int): The menu item ID

    Returns:
        dict | None: The item fields keyed by _ITEM_COLUMNS, or None if it does not exist
    """
    row = fetch_one(conn, _item_sql(conn) + " WHERE m.itm_id = ?", (itm_id,))
    return dict(zip(_ITEM_COLUMNS, row)) if row else None


def list_swap_options(
    conn, user_allergies: str, date: str, meal: int, exclude_itm_id=None, user_preferences=None
):
    """
    Lists every menu item that would pass swap_rejection for a slot

    Args:
        conn (sqlite3.Connection): An open database connection
        user_allergies (str): The user's comma-separated allergies
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)
        exclude_itm_id (int | None): An item to leave out, typically the one already planned
        user_preferences (str | None): The user's comma-separated preferences (diet rules)

    Returns:
        List[dict]: The eligible items, ordered by itm_id
    """
    rows = fetch_all(conn, _item_sql(conn) + " WHERE m.instock = 1 ORDER BY m.itm_id")
    options = []
    for row in rows:
        item = dict(zip(_ITEM_COLUMNS, row))
        if item["itm_id"] == exclude_itm_id:
            continue
        if swap_rejection(item, user_allergies, date, meal, user_preferences) is None:
            options.append(item)
    return options


def rank_swap_options(options, catalog: dict, menu: str, date: str, meal: int, preferences=None):
    """
    Orders swap options by how much variety each adds next to the rest of the plan

    Uses the same score as generation (proj2.variety): the option's weighted distance
    to the other planned meals around the slot, plus the soft-preference bonus; ties go
    to the cheaper item, then the lower itm_id.

    Args:
        options (List[dict]): Eligible items from list_swap_options
        catalog (dict): itm_id -> MenuItem row (proj2.variety.catalog_rows)
        menu (str): The user's generated menu string
        date (str): The slot date in YYYY-MM-DD format
        meal (int): The slot meal number (1, 2, or 3)
        preferences (str | None): The user's comma-separated preferences

    Returns:
        List[dict]: The options, best first, each with a "variety" score from 0 to about 1
    """
    position = variety.slot_position(date, meal)
    neighbours = [
        (variety.slot_position(day, slot_meal), variety.features(catalog[itm_id]))
        for day, itm_id, slot_meal in plan_entries(menu)
        if itm_id in catalog and variety.slot_position(day, slot_meal) != position
    ]

    def price(option):
        try:
            return item_price_cents(catalog.get(option["itm_id"], {}).get("price"))
        except ValueError:
            return float("inf")

    ranked = []
    for option in options:
        row = catalog.get(option["itm_id"], option)
        gain, weight_sum = variety.slot_gain(variety.features(row), position, neighbours)
        score = variety.candidate_score(
            gain, weight_sum, variety.preference_match(row, preferences)
        )
        ranked.append(((-score, price(option), option["itm_id"]), dict(option, variety=score)))
    ranked.sort(key=lambda pair: pair[0])
    return [option for _, option in ranked]
