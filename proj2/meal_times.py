"""
When a user eats each meal, which decides the time a restaurant must be open for it.

Times are whole numbers in HHMM (24h), like restaurant hours. The defaults are the times
the planner always used; a user may set their own on the Profile page, stored in the
User columns breakfast_time, lunch_time and dinner_time (NULL means the default).
"""

## Meal number -> (name, column on "User", default time)
MEALS = {
    1: ("Breakfast", "breakfast_time", 1000),
    2: ("Lunch", "lunch_time", 1400),
    3: ("Dinner", "dinner_time", 2000),
}
DEFAULT_TIMES = {meal: default for meal, (_, _, default) in MEALS.items()}
COLUMNS = tuple(column for _, column, _ in MEALS.values())


class MealTimeError(ValueError):
    """A meal time the user entered is not a valid time, or the times are out of order."""


def times_for(row) -> dict:
    """
    One user's meal times

    Args:
        row (Mapping | None): A "User" row with the meal-time columns (others are ignored);
            None, a missing column or an empty cell gives that meal's default

    Returns:
        dict: meal number (1, 2, 3) -> time in HHMM
    """
    times = {}
    for meal, (_, column, default) in MEALS.items():
        try:
            value = row[column] if row is not None else None
        except (KeyError, IndexError):
            value = None
        times[meal] = default if value is None or value == "" else int(value)
    return times


def parse_time(text) -> int:
    """
    Reads a time typed as "8:30", "08:30" or "0830" (what an <input type=time> sends)

    Returns:
        int: The time in HHMM

    Raises:
        MealTimeError: for anything that is not a time of day
    """
    raw = str(text or "").strip()
    if ":" in raw:
        hours, _, minutes = raw.partition(":")
    elif raw.isdigit() and len(raw) in (3, 4):
        hours, minutes = raw[:-2], raw[-2:]
    else:
        raise MealTimeError(f"{raw or 'An empty value'} is not a time of day.")
    if not (hours.isdigit() and minutes.isdigit() and len(minutes) == 2):
        raise MealTimeError(f"{raw} is not a time of day.")
    h, m = int(hours), int(minutes)
    if h > 23 or m > 59:
        raise MealTimeError(f"{raw} is not a time of day.")
    return h * 100 + m


def check_order(times: dict) -> None:
    """
    Breakfast must come before lunch, and lunch before dinner: the planner and the
    calendar treat the three meals of a day in that order.

    Raises:
        MealTimeError: if they are not strictly in that order
    """
    if not times[1] < times[2] < times[3]:
        raise MealTimeError("Breakfast must be before lunch, and lunch before dinner.")


def as_text(hhmm: int) -> str:
    """1930 -> "19:30" (the value an <input type=time> expects)."""
    return f"{int(hhmm) // 100:02d}:{int(hhmm) % 100:02d}"


def as_display(hhmm: int) -> str:
    """1930 -> "7:30 pm", 1000 -> "10 am"."""
    hours, minutes = divmod(int(hhmm), 100)
    suffix = "am" if hours < 12 else "pm"
    hours = hours % 12 or 12
    return f"{hours}{':%02d' % minutes if minutes else ''} {suffix}"


def meal_at(times: dict, hhmm: int) -> int:
    """
    The meal a time of day belongs to: the last meal whose time has not long passed

    Each meal owns the span from halfway after the previous meal up to halfway before the
    next, so with the defaults 10:00 / 14:00 / 20:00 an order at 11:30 is lunch and one
    at 17:30 is dinner.
    """
    minutes = (int(hhmm) // 100) * 60 + int(hhmm) % 100

    def m(meal):
        return (times[meal] // 100) * 60 + times[meal] % 100

    if minutes < (m(1) + m(2)) / 2:
        return 1
    if minutes < (m(2) + m(3)) / 2:
        return 2
    return 3
