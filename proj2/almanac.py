"""
The calendar's "Seed Catalog & Almanac" style: each planned week laid out like a page
of a grower's almanac.

build_weeks turns the plan into one entry per Monday–Sunday week: the meals as
numbered catalog entries by day, a crop-rotation chart of proteins by day, and the
week's notes (variety score and the most similar nearby meals, from
proj2.planner.meal_plan.calendar_week_variety). The template draws it; static/theme.js
decides whether this style or the standard month grid is shown.
"""

import datetime

from proj2 import meal_tags
from proj2.meal_budget import week_start

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

## Rows of the crop-rotation chart; the rest of a week's proteins are left out
ROTATION_ROWS = 7

## Variety score (percent) -> the week's "forecast", highest threshold first
FORECASTS = ((90, "Very varied"), (80, "Fair and varied"), (65, "Changeable"), (0, "Monotonous"))


def ordinal(day: int) -> str:
    """1 -> "1st", 2 -> "2nd", 11 -> "11th", 22 -> "22nd"."""
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def roman(number: int) -> str:
    """2026 -> "MMXXVI"."""
    out = ""
    for value, numeral in (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ):
        while number >= value:
            out += numeral
            number -= value
    return out


def forecast(score) -> str:
    """The almanac's word for a variety score, e.g. 91 -> "Very varied"."""
    if score is None:
        return "Too few meals to judge"
    return next(word for threshold, word in FORECASTS if score >= threshold)


def week_title(start: datetime.date) -> str:
    """'the 16th to the 22nd of November, 2026', naming both months when the week spans two."""
    end = start + datetime.timedelta(days=6)
    if start.month == end.month:
        return f"the {ordinal(start.day)} to the {ordinal(end.day)} of {end:%B}, {end.year}"
    first = f"the {ordinal(start.day)} of {start:%B}"
    if start.year != end.year:
        first += f", {start.year}"
    return f"{first} to the {ordinal(end.day)} of {end:%B}, {end.year}"


def _proteins(row) -> list:
    if not row:
        return []
    return sorted(meal_tags.parse_tags("protein", row.get("protein")) - {"none"})


def build_weeks(entries, items_by_id, catalog, weekly_variety) -> list:
    """
    The almanac pages for the weeks shown in a calendar month

    Args:
        entries (Iterable[Tuple[str, int, int]]): (date, itm_id, meal) for every planned
            meal, e.g. from proj2.meal_budget.plan_entries
        items_by_id (Mapping[int, dict]): Item details by itm_id (meal_plan.fetch_menu_items_by_ids):
            name, price, calories, rtr_id, restaurant_name
        catalog (Mapping[int, Mapping]): MenuItem rows by itm_id, for the protein tags
        weekly_variety (Mapping[str, dict]): week start -> {"score", "similar"} from
            meal_plan.calendar_week_variety; its keys choose which weeks are drawn

    Returns:
        List[dict]: One dict per week, in date order (see the keys set below)
    """
    entries = [e for e in entries if e[1] in items_by_id]
    weeks = []
    for start_iso in sorted(weekly_variety):
        start = datetime.date.fromisoformat(start_iso)
        dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(7)]
        week_entries = sorted(
            (e for e in entries if week_start(e[0]) == start_iso), key=lambda e: (e[0], e[2])
        )
        days_of_item = {}
        for day, itm_id, _ in week_entries:
            days_of_item.setdefault(itm_id, []).append(day)

        days = []
        for i, iso in enumerate(dates):
            meals = {}
            for day, itm_id, meal in week_entries:
                if day != iso:
                    continue
                item = items_by_id[itm_id]
                again = sorted({d for d in days_of_item[itm_id] if d != iso})
                meals[meal] = {
                    "date": iso,
                    "meal": meal,
                    "itm_id": itm_id,
                    "name": item["name"],
                    "restaurant": item.get("restaurant_name") or "",
                    "rtr_id": item.get("rtr_id"),
                    "price": item.get("price") or 0,
                    "calories": item.get("calories"),
                    "again": [WEEKDAYS[dates.index(d)] for d in again],
                }
            day_date = datetime.date.fromisoformat(iso)
            days.append(
                {
                    "date": iso,
                    "weekday": WEEKDAYS[i],
                    "day": day_date.day,
                    "month": day_date.month,
                    "meals": meals,
                    "total": sum(m["price"] for m in meals.values()),
                }
            )

        # Crop rotation: which proteins ("beds") were planted each day; a bed planted two
        # days running is marked, the way a grower avoids the same crop twice in a row
        counts = {}
        for _, itm_id, _ in week_entries:
            for protein in _proteins(catalog.get(itm_id)):
                counts[protein] = counts.get(protein, 0) + 1
        beds = sorted(counts, key=lambda p: (-counts[p], p))[:ROTATION_ROWS]
        rotation = []
        for bed in beds:
            cells, previous = [], False
            for day in days:
                planted = any(
                    bed in _proteins(catalog.get(m["itm_id"])) for m in day["meals"].values()
                )
                cells.append("twice" if planted and previous else "on" if planted else "")
                previous = planted
            rotation.append({"bed": bed, "cells": cells})

        variety = weekly_variety[start_iso]
        weeks.append(
            {
                "start": start_iso,
                "title": week_title(start),
                "volume": roman(start.isocalendar()[0]),
                "number": start.isocalendar()[1],
                "days": days,
                "meal_count": len(week_entries),
                "distinct": len(days_of_item),
                "kitchens": len({items_by_id[i].get("rtr_id") for i in days_of_item}),
                "total": sum(day["total"] for day in days),
                "score": variety.get("score"),
                "forecast": forecast(variety.get("score")),
                "similar": variety.get("similar") or [],
                "rotation": rotation,
            }
        )
    return weeks
