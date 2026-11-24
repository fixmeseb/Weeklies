"""
Editing a saved meal plan: removing one meal, or clearing a range of days.

A plan is saved on "User".generated_menu as "[YYYY-MM-DD,itm_id,meal],..." (see
proj2.meal_budget.plan_entries). These functions read it, change it and write it back in
the same form, keeping every other entry exactly as it was and in the same order.
"""

import datetime

from proj2.meal_budget import plan_entries


class PlanEditError(ValueError):
    """A request to change the plan names a bad date, meal or range."""


def _day(value, what="date") -> str:
    try:
        return datetime.date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise PlanEditError(f"The {what} must be a date in YYYY-MM-DD format.")


def _meal(value) -> int:
    try:
        meal = int(value)
    except (TypeError, ValueError):
        meal = 0
    if meal not in (1, 2, 3):
        raise PlanEditError("The meal must be 1 (breakfast), 2 (lunch) or 3 (dinner).")
    return meal


def serialize(entries) -> str:
    """[(day, itm_id, meal)] -> the saved form."""
    return ",".join(f"[{day},{itm_id},{meal}]" for day, itm_id, meal in entries)


def remove_meal(menu: str, day, meal):
    """
    Removes the meal planned in one slot

    Args:
        menu (str): The saved plan
        day (str): The slot's date, YYYY-MM-DD
        meal (int): 1, 2 or 3

    Returns:
        Tuple[str, list]: (the new plan, the (day, itm_id, meal) entries removed); nothing
            is removed if the slot was empty

    Raises:
        PlanEditError: for a malformed date or meal
    """
    day, meal = _day(day), _meal(meal)
    kept, removed = [], []
    for entry in plan_entries(menu):
        (removed if (entry[0], entry[2]) == (day, meal) else kept).append(entry)
    return serialize(kept), removed


def clear_days(menu: str, start, end, meals=(1, 2, 3)):
    """
    Removes the planned meals from start to end (both included)

    Args:
        menu (str): The saved plan
        start (str), end (str): The first and last day to clear, YYYY-MM-DD
        meals (Iterable[int]): Which meals to clear on those days (default all three)

    Returns:
        Tuple[str, list]: (the new plan, the entries removed)

    Raises:
        PlanEditError: for a malformed date or meal, or an end before the start
    """
    start, end = _day(start, "first day"), _day(end, "last day")
    if end < start:
        raise PlanEditError("The last day to clear is before the first.")
    meals = {_meal(meal) for meal in meals}
    if not meals:
        raise PlanEditError("Choose at least one meal to clear.")
    kept, removed = [], []
    for entry in plan_entries(menu):
        inside = start <= entry[0] <= end and entry[2] in meals
        (removed if inside else kept).append(entry)
    return serialize(kept), removed


def days_range(start, number_of_days: int):
    """(first day, last day) of number_of_days days from start, as YYYY-MM-DD."""
    first = datetime.date.fromisoformat(_day(start, "first day"))
    last = first + datetime.timedelta(days=max(1, int(number_of_days)) - 1)
    return first.isoformat(), last.isoformat()
