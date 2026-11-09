"""Deciding, per meal, whether it is ordered out or cooked at home.

Cooking is the cheaper way to fill a slot but it costs time, and the time a person has on
a given day is the scarce resource. This module holds that decision and nothing else: it
takes the slots to fill, the minutes free on each day and how long each slot would take to
cook, and returns which slots are cooked. It touches no database, no clock and no LLM, so
a plan is reproducible and the rule can be tested on its own.

Cook times come from a `CookTimes` lookup rather than being read here. Today that is built
from a mapping; once the schema rewrite on `task-scheduler` lands it can be built from a
`MenuItem` column without changing any of the logic below.
"""

from decimal import Decimal, InvalidOperation

ORDER = "order"
COOK = "cook"


class ScheduleInfeasibleError(ValueError):
    """The requested meals cannot be cooked within the time available."""


def parse_minutes(value, label="Cooking time"):
    """Convert a whole number of minutes to an int, rejecting anything else.

    Args:
        value: Minutes, as an int or a string. None and blank are not accepted; a caller
            that means "no time at all" says 0, so a missing value is never read as free.
        label (str): Name used in the error message.

    Returns:
        int: The value in whole minutes.

    Raises:
        ValueError: If the value is negative, fractional, non-finite or unparseable.
    """
    # bool is an int subclass, and True would otherwise silently mean one minute.
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number of minutes, at least 0.")
    try:
        minutes = Decimal(str(value))
        if not minutes.is_finite() or minutes < 0 or minutes != minutes.to_integral_value():
            raise ValueError
        return int(minutes)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a whole number of minutes, at least 0.")


class CookTimes:
    """How long each catalog item takes to cook, in whole minutes.

    An item absent from the lookup is not cookable, which is different from being cookable
    in zero minutes. The distinction matters: a missing cook time must never let a slot be
    scheduled as cooked for free.
    """

    def __init__(self, minutes_by_item=None):
        """Build the lookup.

        Args:
            minutes_by_item (Mapping | None): itm_id -> minutes. Validated eagerly so a bad
                figure is a loud error at construction rather than a silent skip mid-plan.

        Raises:
            ValueError: If any value is not a whole, non-negative number of minutes.
        """
        source = minutes_by_item or {}
        self._minutes = {
            int(item): parse_minutes(value, f"Cook time for item {item}")
            for item, value in source.items()
        }

    def minutes_for(self, itm_id):
        """Minutes to cook one item, or None when it cannot be cooked.

        Args:
            itm_id (int): Catalog item id.

        Returns:
            int | None: Whole minutes, or None if the item has no cook time.
        """
        return self._minutes.get(int(itm_id))

    def cookable(self, item_ids):
        """The subset of item_ids that can be cooked, cheapest in time first.

        Args:
            item_ids (Iterable[int]): Candidate items, already filtered for allergens and
                stock by the caller.

        Returns:
            list[tuple[int, int]]: (itm_id, minutes) sorted by minutes then itm_id, so the
                order is stable for a given catalog.
        """
        found = []
        for itm_id in item_ids:
            minutes = self.minutes_for(itm_id)
            if minutes is not None:
                found.append((int(itm_id), minutes))
        return sorted(found, key=lambda pair: (pair[1], pair[0]))

    def quickest(self, item_ids):
        """The least time any of these items takes to cook, or None if none is cookable.

        Args:
            item_ids (Iterable[int]): Candidate items.

        Returns:
            int | None: Minutes for the quickest cookable item, else None.
        """
        cookable = self.cookable(item_ids)
        return cookable[0][1] if cookable else None


def daily_minutes(available, days, default=0):
    """Normalise the minutes free on each day of the plan.

    Args:
        available (Mapping | int | None): Minutes per day. An int applies to every day; a
            mapping may be keyed by ISO date or by weekday name ("Mon"), with the date
            winning when both are present. None means `default` everywhere.
        days (Sequence[tuple[str, str]]): (iso_date, weekday) for each day being planned.
        default (int): Minutes for a day the mapping does not mention.

    Returns:
        dict[str, int]: iso_date -> whole minutes.

    Raises:
        ValueError: If any figure is not a whole, non-negative number of minutes.
    """
    default = parse_minutes(default, "Cooking time")
    if available is None:
        return {day: default for day, _ in days}
    if not hasattr(available, "get"):
        flat = parse_minutes(available, "Cooking time")
        return {day: flat for day, _ in days}

    resolved = {}
    for day, weekday in days:
        if day in available:
            resolved[day] = parse_minutes(available[day], f"Cooking time for {day}")
        elif weekday in available:
            resolved[day] = parse_minutes(available[weekday], f"Cooking time for {weekday}")
        else:
            resolved[day] = default
    return resolved


def plan_cook_or_order(slots, cook_minutes, minutes_free, must_cook=(), must_order=()):
    """Choose which meals are cooked, filling each day's time without exceeding it.

    Within one day the choice is "cook as many meals as the time allows", taking the
    quickest first. For a single per-day limit that greedy order is optimal for the number
    of meals cooked: swapping in any slower meal can only displace one that already fit.

    Args:
        slots (Sequence[tuple[str, int]]): (iso_date, meal_number) to fill, in plan order.
        cook_minutes (Mapping): slot -> minutes to cook it, or None/absent when the slot has
            nothing cookable. Usually `CookTimes.quickest` over that slot's eligible items.
        minutes_free (Mapping[str, int]): iso_date -> minutes available to cook that day.
        must_cook (Iterable): Slots the user pinned as cooked. Each must have a cook time
            and must fit the day, or the whole schedule is refused.
        must_order (Iterable): Slots the user pinned as ordered; never cooked, and they
            consume no time.

    Returns:
        dict[tuple[str, int], str]: slot -> COOK or ORDER, covering every slot given.

    Raises:
        ScheduleInfeasibleError: If a slot is pinned both ways, or a slot pinned as cooked
            cannot be cooked or does not fit its day.
    """
    pinned_cook = {tuple(slot) for slot in must_cook}
    pinned_order = {tuple(slot) for slot in must_order}

    both = sorted(pinned_cook & pinned_order)
    if both:
        day, meal = both[0]
        raise ScheduleInfeasibleError(
            f"Meal {meal} on {day} is pinned as both cooked and ordered; pick one."
        )

    remaining = {
        day: parse_minutes(value, f"Cooking time for {day}") for day, value in minutes_free.items()
    }
    decision = {}

    # Pinned cook slots are honoured first: they are the user's instruction, so they get
    # the day's time before anything chosen on their behalf, and a conflict is reported
    # against the request rather than hidden behind a greedy pick.
    for slot in slots:
        key = tuple(slot)
        if key not in pinned_cook:
            continue
        day, meal = key
        needed = cook_minutes.get(key)
        if needed is None:
            raise ScheduleInfeasibleError(
                f"Meal {meal} on {day} is pinned as cooked, but nothing cookable fits that "
                "slot's allergens and stock."
            )
        needed = parse_minutes(needed, f"Cook time for meal {meal} on {day}")
        free = remaining.get(day, 0)
        if needed > free:
            raise ScheduleInfeasibleError(
                f"Meal {meal} on {day} needs {needed} min to cook but {free} min are free "
                f"on {day}. Allow more time or order that meal instead."
            )
        remaining[day] = free - needed
        decision[key] = COOK

    # Everything else: quickest first within each day, so the time buys the most meals.
    unpinned = [
        tuple(slot)
        for slot in slots
        if tuple(slot) not in pinned_cook and tuple(slot) not in pinned_order
    ]
    by_day = {}
    for key in unpinned:
        by_day.setdefault(key[0], []).append(key)

    for day, day_slots in by_day.items():
        cookable = [
            (key, parse_minutes(cook_minutes[key], f"Cook time for {key[1]} on {day}"))
            for key in day_slots
            if cook_minutes.get(key) is not None
        ]
        for key, needed in sorted(cookable, key=lambda pair: (pair[1], pair[0][1])):
            if needed <= remaining.get(day, 0):
                remaining[day] -= needed
                decision[key] = COOK

    for slot in slots:
        decision.setdefault(tuple(slot), ORDER)

    return decision


def cook_days(decision):
    """The dates on which at least one meal is cooked.

    Args:
        decision (Mapping): The result of `plan_cook_or_order`.

    Returns:
        list[str]: ISO dates, sorted.
    """
    return sorted({day for (day, _), choice in decision.items() if choice == COOK})


def order_days(decision):
    """The dates on which at least one meal has to be ordered.

    These are the days a restaurant has to be open, so this is what the ordering side of
    the planner needs from the schedule.

    Args:
        decision (Mapping): The result of `plan_cook_or_order`.

    Returns:
        list[str]: ISO dates, sorted.
    """
    return sorted({day for (day, _), choice in decision.items() if choice == ORDER})
