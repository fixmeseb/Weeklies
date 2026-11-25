"""Meal-plan helpers behind the calendar: read User.generated_menu, look up its dishes
and build month cells."""

import calendar
import re
from datetime import date, timedelta

from proj2 import variety
from proj2.db import get_db
from proj2.meal_budget import plan_entries, week_start, weekly_item_totals
from proj2.plan_rules import SLOT_NAMES
from proj2.sqlQueries import fetch_all


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

    def hsl_to_hex(h, s, lightness):
        r, g, b = colorsys.hls_to_rgb(h / 360.0, lightness / 100.0, s / 100.0)
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
    "diet": "That item does not satisfy your required diets.",
    "plan_changed": "Your plan or Diet settings changed. Refresh the calendar and try again.",
    "weekly_cap": "That swap would exceed your weekly item-price cap or the week could not be priced.",
}


# Home route (supports /<year>/<month> for nav)
def describe_similar_pair(pair, items_by_id) -> str:
    """One similar pair from proj2.variety as a sentence for the calendar."""

    def label(entry):
        day = date.fromisoformat(entry["date"])
        name = items_by_id.get(entry["itm_id"], {}).get("name", f"item {entry['itm_id']}")
        return f"{name} ({day.strftime('%a')} {SLOT_NAMES.get(entry['meal'], 'meal')})"

    shared = "; ".join(pair["shared"]) or "similar tags"
    return f"{label(pair['a'])} and {label(pair['b'])}: {shared}"


def calendar_week_variety(conn, gen_str, year, month, items_by_id):
    """
    Variety of each Monday–Sunday week planned in a calendar month (see week_variety)
    """
    return week_variety(conn, gen_str, planned_weeks(gen_str, year, month), items_by_id)


def planned_weeks(gen_str, year, month):
    """The weeks (start dates, in order) with a meal planned on a day of a calendar month."""
    prefix = f"{year:04d}-{month:02d}-"
    days = {day for day, _, _ in plan_entries(gen_str) if day.startswith(prefix)}
    return sorted({week_start(day) for day in days})


def week_variety(conn, gen_str, weeks, items_by_id):
    """
    Variety of Monday–Sunday weeks (see proj2.variety). Weeks with nothing planned are left out.

    Returns:
        dict: week start -> {"score": percent or None, "similar": [sentence, ...]}
    """
    entries = list(plan_entries(gen_str))
    weeks = sorted(set(weeks) & {week_start(day) for day, _, _ in entries})
    if not weeks:
        return {}
    catalog = variety.catalog_rows(conn)
    out = {}
    for week in weeks:
        report = variety.plan_variety([e for e in entries if week_start(e[0]) == week], catalog)
        out[week] = {
            "score": None if report.score is None else round(report.score * 100),
            "similar": [describe_similar_pair(p, items_by_id) for p in report.similar_pairs(2)],
        }
    return out


def month_item_totals(gen_str, gen_map, year, month):
    """
    Item totals of every Monday–Sunday week that has a planned meal in a calendar month

    Returns:
        Tuple[dict, str | None]: (week start -> cents, error message or None)
    """
    try:
        visible_weeks = sorted(
            {week_start(day) for day in gen_map if day.startswith(f"{year:04d}-{month:02d}-")}
        )
        visible_week_item_ids = {
            item_id for day, item_id, _ in plan_entries(gen_str) if week_start(day) in visible_weeks
        }
        totals_by_item = fetch_menu_items_by_ids(sorted(visible_week_item_ids))
        totals = weekly_item_totals(
            gen_str,
            {item: data["price"] for item, data in totals_by_item.items()},
            visible_weeks,
        )
        return totals, None
    except ValueError:
        return {}, "Item totals are unavailable because a planned meal or its price is missing."


def shown_week(requested, gen_str, year, month, today):
    """
    The week the Almanac style shows with a calendar month

    Args:
        requested (date | None): A day in the week asked for
        gen_str (str): The plan (User.generated_menu)
        year (int), month (int): The calendar month shown
        today (date): Today
    Returns:
        date: The Monday of the week asked for; else this week, when the month is this
            month; else the first week planned in the month, or its first week.
    """
    if requested:
        day = requested
    elif (year, month) == (today.year, today.month):
        day = today
    else:
        planned = planned_weeks(gen_str, year, month)
        day = date.fromisoformat(planned[0]) if planned else date(year, month, 1)
    return day - timedelta(days=day.weekday())


def month_nav(year, month):
    """(prev_year, prev_month, next_year, next_month) around a calendar month."""
    cur = date(year, month, 15)
    prev_m = (cur.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_m = (cur.replace(day=28) + timedelta(days=10)).replace(day=1)
    return prev_m.year, prev_m.month, next_m.year, next_m.month
