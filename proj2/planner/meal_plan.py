"""Meal-plan helpers behind the calendar: parse User.generated_menu and build month cells.

Transitional: the task-planner pivot (Phase 4) replaces these with PlanEntry rows.
"""

import re
import calendar

from proj2.sqlQueries import fetch_all
from proj2.db import get_db


def parse_generated_menu(gen_str):
    """
    Parse a serialized generated-menu string into a date-indexed structure.
    Args:
        gen_str (str): A string like "[YYYY-MM-DD,ID,(meal)]..." where meal is 1|2|3 (optional).
    Returns:
        dict: Mapping 'YYYY-MM-DD' -> [{'itm_id': int, 'meal': int}, ...].
    """
    if not gen_str:
        return {}

    # date, id, optional meal (1,2,3)
    pairs = re.findall(r"\[\s*(\d{4}-\d{2}-\d{2})\s*,\s*([0-9]+)\s*(?:,\s*([123])\s*)?\]", gen_str)
    out = {}
    for d, mid, meal in pairs:
        try:
            itm_id = int(mid)
            meal_i = int(meal) if meal else 3  # default to Dinner for legacy entries
            out.setdefault(d, []).append({"itm_id": itm_id, "meal": meal_i})
        except ValueError:
            continue
    return out


def palette_for_item_ids(item_ids):
    """
    Generate a deterministic, pleasant color palette for item IDs.
    Args:
        item_ids (Iterable[int]): The menu item IDs to colorize.
    Returns:
        dict: Mapping itm_id -> hex color string (e.g., '#a1b2c3').
    """
    import colorsys

    def hsl_to_hex(h, s, l):
        r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    palette = {}
    for iid in item_ids:
        seed = (iid * 9301 + 49297) % 233280
        hue = seed % 360
        palette[iid] = hsl_to_hex(hue, 65, 52)
    return palette


def fetch_menu_items_by_ids(ids):
    """
    Load menu items (and their restaurant metadata) for given item IDs.
    Args:
        ids (Iterable[int]): The item IDs to fetch.
    Returns:
        dict: Mapping itm_id -> dict with fields like name, price, calories, allergens,
            and restaurant info (name, address, hours, phone).
    """
    if not ids:
        return {}
    conn = get_db()
    qmarks = ",".join(["?"] * len(ids))
    sql = f"""
      SELECT m.itm_id, m.rtr_id, m.name, m.description, m.price, m.calories,
             m.allergens, r.name AS restaurant_name, r.address, r.city, r.state, r.zip,
             r.hours, r.phone
      FROM MenuItem m
      JOIN Restaurant r ON r.rtr_id = m.rtr_id
      WHERE m.itm_id IN ({qmarks})
    """
    rows = fetch_all(conn, sql, tuple(ids))

    def _addr(a, c, s, z) -> str:
        parts_raw = [a, c, s, z]
        parts = []
        for p in parts_raw:
            if p is None:
                continue
            sp = str(p).strip()
            if sp:
                parts.append(sp)
        return ", ".join(parts)

    out = {}
    for r in rows:
        out[r[0]] = {
            "itm_id": r[0],
            "rtr_id": r[1],
            "name": r[2],
            "description": r[3],
            "price": r[4],
            "calories": r[5],
            "allergens": r[6],
            "restaurant_name": r[7],
            "restaurant_address": _addr(r[8], r[9], r[10], r[11]),
            "restaurant_hours": r[12] or "",
            "restaurant_phone": r[13] or "",
        }
    return out


def build_calendar_cells(gen_map, year, month, items_by_id):
    """
    Build month-view calendar cells enriched with menu items per day.
    Args:
        gen_map (dict): Mapping 'YYYY-MM-DD' -> [{'itm_id': int, 'meal': 1|2|3}, ...].
        year (int): The calendar year.
        month (int): The calendar month (1–12).
        items_by_id (dict): Mapping itm_id -> item detail dict from DB.
    Returns:
        list: A flat list of calendar cell dicts with day number and a 'meals' list.
    """

    def meal_sort_key(e):
        # Breakfast(1) first, then Lunch(2), then Dinner(3)
        return e.get("meal", 3)

    palette = palette_for_item_ids(items_by_id.keys())
    cal = calendar.Calendar(firstweekday=6)  # Sunday start
    cells = []

    for week in cal.monthdayscalendar(year, month):
        for d in week:
            if d == 0:
                cells.append({"day": 0})
                continue

            iso = f"{year:04d}-{month:02d}-{d:02d}"
            entries = sorted(gen_map.get(iso, []), key=meal_sort_key)

            meals = []
            for e in entries:
                itm = items_by_id.get(e["itm_id"])
                if not itm:
                    continue
                meals.append(
                    {
                        "meal": e.get("meal", 3),
                        "item": itm,
                        "color": palette.get(itm["itm_id"], "#7aa2f7"),
                    }
                )

            cells.append({"day": d, "meals": meals})

    return cells


## Banner text for /?swap_error=<code> after a form-based swap
SWAP_ERROR_MESSAGES = {
    "invalid_slot": "That meal slot is not valid.",
    "invalid_item": "Choose an item to swap in.",
    "slot_not_found": "There is no planned meal in that slot.",
    "same_item": "That item is already planned for this slot.",
    "item_not_found": "That menu item does not exist.",
    "out_of_stock": "That item is out of stock.",
    "restaurant_unavailable": "That restaurant is not currently taking orders.",
    "restaurant_closed": "That restaurant is closed at that meal time.",
    "allergen": "That item contains one of your allergens.",
}
