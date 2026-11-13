"""
Meal-plan generation: fills empty date/meal slots with the most varied eligible meals.

For every slot, the candidates are the items that pass the shared rules
(proj2.plan_rules: stock, opening hours, allergens, diets, and the slot's course and
meal type), and, with a weekly cap, that leave enough budget for the meals still to
plan. Among them the planner picks the one that adds the most variety next to the meals
already in the plan (proj2.variety), with soft preferences such as "Italian" breaking
near-ties, then the lower price, then the lower itm_id. After every slot is filled it
makes one improvement pass, re-picking each new slot with the rest of the plan fixed.

The result is deterministic: the same catalog and request always give the same plan.
"""

import datetime
import json
from typing import Tuple

import pandas as pd

from proj2 import variety
from proj2.meal_budget import (
    BudgetExceededError,
    item_price_cents,
    plan_entries,
    week_start,
    weekly_item_totals,
)
from proj2.db import connect
from proj2.dietary import DietaryConstraintError, filter_diets, required_diets
from proj2.plan_rules import (
    SLOT_NAMES,
    PlanRuleError,
    is_restaurant_open,
    item_rejection,
    parse_allergens,
    slot_rejection,
)

## Days of the week in an array - should be the same as in the database*
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

## Preset Meal times - In the future, times will be user-provided
BREAKFAST_TIME = 1000
LUNCH_TIME = 1400
DINNER_TIME = 2000


class NoEligibleMealError(ValueError):
    """No menu item passes the rules for one of the requested slots."""


def get_meal_and_order_time(meal_number: int) -> Tuple[str, int]:
    """
    Maps a meal number to it's cooresponding meal as a string as well as its cooreponding meal time

    Args:
        meal_number (int): The meal number to get the meal and order times for

    Returns:
        str: The name of the meal as a string ("breakfast", "lunch", or "dinner")
        int: The time the meal is typically ordered at in HHMM format (in 24H time)

    Raises:
        ValueError: if meal_number is not 1, 2, or 3
    """
    meal = ""
    order_time = -1
    match meal_number:
        case 1:
            meal = "breakfast"
            order_time = BREAKFAST_TIME
        case 2:
            meal = "lunch"
            order_time = LUNCH_TIME
        case 3:
            meal = "dinner"
            order_time = DINNER_TIME
        case _:
            raise ValueError("The meal number must be 1, 2, or 3")
    return meal, order_time


def get_weekday_and_increment(date: str) -> Tuple[str, str]:
    """
    Converts a date string in YYYY-MM-DD format to the corresponding day of the week and returns the next date

    Args:
        date (str): The date string in YYYY-MM-DD format

    Returns:
        str: The next day, in YYYY-MM-DD format
        str: The corresponding day of the week ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    Raises:
        ValueError: if the date string is not in the correct format (YYYY-MM-DD) or is invalid
    """
    year, month, day = map(int, date.split("-"))
    try:
        date = datetime.datetime(year, month, day)
    except ValueError:
        raise ValueError(
            "Unable to parse date string. Ensure it is formatted properly as to YYYY-MM-DD format"
        )
    next_day = date + datetime.timedelta(days=1)
    return next_day.strftime(r"%Y-%m-%d"), DAYS_OF_WEEK[date.weekday()]


def filter_allergens(menu_items: pd.DataFrame, allergens: str) -> pd.DataFrame:
    """
    Filters out menu items that contain any of the specified allergens from the provided DataFrame

    Args:
        menu_items (pd.DataFrame): The DataFrame containing the menu items
        allergens (str): A comma-separated string of allergens to filter out

    Returns:
        pd.DataFrame: The filtered DataFrame with menu items containing the specified allergens removed
    """
    prohibited = parse_allergens(allergens)

    def allowed(value):
        return not prohibited.intersection(parse_allergens(value))

    return menu_items.loc[menu_items["allergens"].map(allowed).astype(bool)].copy()


def filter_closed_restaurants(restaurant: pd.DataFrame, weekday: str, time: int) -> pd.DataFrame:
    """
    Filters out restaurants that are closed at the specified time on the specified weekday

    Args:
        restaurant (pd.DataFrame): The DataFrame containing the restaurant data
        weekday (str): The day of the week to check (e.g., "Mon", "Tue", etc.)
        time (int): The time to check in HHMM format (24H time)

    Returns:
        pd.DataFrame: The filtered DataFrame with closed restaurants removed
    """
    is_open = restaurant["hours"].map(lambda hours: is_restaurant_open(hours, weekday, time))
    return restaurant[is_open.astype(bool)]


def filter_meal_slot(menu_items: pd.DataFrame, meal) -> pd.DataFrame:
    """
    Keeps only the items that may fill a meal slot on their own (see plan_rules.slot_rejection)

    Args:
        menu_items (pd.DataFrame): The candidate items
        meal (int | None): The slot's meal number (1, 2, 3); None keeps every item

    Returns:
        pd.DataFrame: The items whose course and meal type fit the slot
    """
    if meal is None or menu_items.empty:
        return menu_items.copy()
    keep = [slot_rejection(row, meal) is None for _, row in menu_items.iterrows()]
    return menu_items.loc[keep].copy()


def _hours_are_readable(hours) -> bool:
    """True if a restaurant's hours are the per-day JSON that is_restaurant_open reads."""
    try:
        parsed = json.loads(hours)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and any(day in parsed for day in DAYS_OF_WEEK)


class MenuGenerator:
    """
    Plans meals from the catalog in one database, choosing for variety (see module docstring)
    """

    def __init__(self, *, database_path: str):
        """
        Loads menu items and open restaurants from the database

        Args:
            database_path (str): The SQLite database to read the catalog from.
        """
        conn = connect(database_path)
        conn.row_factory = None  # pandas expects plain tuples
        try:
            self.catalog = pd.read_sql_query("SELECT * FROM MenuItem", conn)
            self.item_prices = dict(zip(self.catalog.itm_id, self.catalog.price))
            self.menu_items = pd.read_sql_query("SELECT * FROM MenuItem WHERE instock == 1", conn)
            # Same match as plan_rules.item_rejection: trimmed, case-insensitive
            self.restaurants = pd.read_sql_query(
                "SELECT rtr_id, hours FROM Restaurant WHERE LOWER(TRIM(status)) = 'open'", conn
            )
        finally:
            conn.close()
        self.weekly_totals_cents = None
        self.item_total_cents = None
        self.variety = None

    def _eligible_candidates(
        self, allergens, weekday, order_time, max_price_cents=None, preferences=None, meal=None
    ):
        """
        Filter stock, open restaurants, the slot's course and meal type, allergens and
        required diets; rank valid prices cheapest first.

        Args:
            meal (int | None): The slot's meal number; None skips the course/meal-type rule

        Raises:
            DietaryConstraintError: if items are available but none satisfies the diets
                named in preferences (see proj2.dietary)
        """
        combined = pd.merge(
            self.menu_items[self.menu_items["instock"] == 1],
            self.restaurants,
            on="rtr_id",
            how="inner",
        )
        combined = filter_closed_restaurants(combined, weekday, order_time)
        combined = filter_meal_slot(combined, meal)
        combined = filter_allergens(combined, allergens)
        if not combined.empty:
            combined = filter_diets(combined, preferences)
            if combined.empty:
                diets = ", ".join(sorted(required_diets(preferences)))
                raise DietaryConstraintError(
                    f"No available menu item on {weekday} at {order_time:04d} is tagged as "
                    f"meeting your diet ({diets}). Restaurants must tag items before they "
                    f"can be planned for {diets} meals."
                )

        def valid_price(value):
            try:
                return item_price_cents(value)
            except ValueError:
                return None

        combined = combined.assign(price_cents=combined["price"].map(valid_price))
        combined = combined[combined["price_cents"].notna()]
        if max_price_cents is not None:
            combined = combined[combined["price_cents"] <= max_price_cents]
        return combined.sort_values(["price_cents", "itm_id"], kind="stable")

    def _empty_slot_reason(self, allergens, weekday, order_time, meal) -> str:
        """
        Says which rule left a slot with no candidates, replaying _eligible_candidates'
        filters in order, so the error points at the cause rather than just the slot

        Returns:
            str: One sentence, e.g. "no restaurant is open at 10:00 on Tue."
        """
        when = f"{order_time // 100:02d}:{order_time % 100:02d} on {weekday}"
        if self.restaurants.empty:
            return "no restaurant is currently taking orders."
        stocked = pd.merge(
            self.menu_items[self.menu_items["instock"] == 1], self.restaurants, on="rtr_id"
        )
        if stocked.empty:
            return "no open restaurant has any item in stock."
        open_now = filter_closed_restaurants(stocked, weekday, order_time)
        if open_now.empty:
            unreadable = [
                hours for hours in self.restaurants["hours"] if not _hours_are_readable(hours)
            ]
            if unreadable:
                return (
                    f"no restaurant is open at {when}. {len(unreadable)} restaurant(s) list "
                    f'hours the planner cannot read (for example "{unreadable[0]}"); hours must '
                    'be stored per day, like {"Mon": [1100, 2200]}. Reseeding the demo '
                    "database (flask seed) adds restaurants with readable hours."
                )
            return f"no restaurant is open at {when}."
        fits = filter_meal_slot(open_now, meal)
        if fits.empty:
            return (
                f"none of the restaurants open at {when} serves a main dish for {SLOT_NAMES[meal]}."
            )
        if filter_allergens(fits, allergens).empty:
            return f"every item that fits contains one of your allergens ({allergens})."
        return "no item that fits has a valid price."

    def _check_pick(self, itm_id, preferences, allergens, weekday, order_time, meal=None):
        """
        Re-checks a chosen item against proj2.plan_rules before it goes into the plan

        Candidates are already filtered, so a rejection here means a filter and the
        shared rules disagree; generation stops rather than save a non-compliant plan.

        Raises:
            PlanRuleError: if the item breaks a rule
        """
        rows = self.menu_items[self.menu_items["itm_id"] == itm_id]
        item = None
        if not rows.empty:
            row = rows.iloc[0]
            restaurant = self.restaurants[self.restaurants["rtr_id"] == row["rtr_id"]]
            item = {
                "name": row["name"],
                "instock": row["instock"],
                "allergens": row["allergens"],
                "diet_tags": row.get("diet_tags"),
                "course": row.get("course"),
                "meal_type": row.get("meal_type"),
                # self.restaurants holds only restaurants whose status is Open
                "restaurant_status": None if restaurant.empty else "Open",
                "hours": None if restaurant.empty else restaurant.iloc[0]["hours"],
            }
        rejection = item_rejection(item, allergens, preferences, weekday, order_time, meal)
        if rejection:
            raise PlanRuleError(f"Chosen item {itm_id} broke a plan rule: {rejection[1]}")

    # ---------------------------------------------------------------- variety

    def _rows(self) -> dict:
        """itm_id -> catalog row (every item, in stock or not), for scoring saved meals too."""
        if getattr(self, "_rows_cache", None) is None:
            catalog = getattr(self, "catalog", None)
            if catalog is None:  # built without __init__ (tests): the in-stock items
                catalog = self.menu_items
            self._rows_cache = {int(row["itm_id"]): row for row in catalog.to_dict("records")}
            self._feature_cache = {}
        return self._rows_cache

    def _features(self, itm_id: int) -> dict:
        rows = self._rows()
        if itm_id not in self._feature_cache:
            self._feature_cache[itm_id] = variety.features(rows[itm_id])
        return self._feature_cache[itm_id]

    def _neighbours(self, planned: dict, position: int) -> list:
        """(position, features) of every planned meal except the one in this slot."""
        rows = self._rows()
        return [
            (other, self._features(itm_id))
            for other, itm_id in planned.items()
            if other != position and itm_id in rows
        ]

    def _ranked(self, pool: pd.DataFrame, position: int, neighbours: list, preferences) -> list:
        """
        Ranks a slot's candidates, best first

        Returns:
            List[Tuple[tuple, int]]: (sort key, itm_id); the key is (-score, price, itm_id),
                so the most varied fit wins, then the cheaper one, then the lower ID
        """
        ranked = []
        for row in pool.to_dict("records"):
            itm_id = int(row["itm_id"])
            gain, weight_sum = variety.slot_gain(self._features(itm_id), position, neighbours)
            score = variety.candidate_score(
                gain, weight_sum, variety.preference_match(row, preferences)
            )
            ranked.append(((-score, int(row["price_cents"]), itm_id), itm_id))
        ranked.sort()
        return ranked

    # ---------------------------------------------------------------- planning

    def update_menu(
        self,
        menu: str,
        preferences: str,
        allergens: str,
        date: str,
        meal_numbers,
        number_of_days: int = 1,
        weekly_cap_cents: int = None,
    ) -> str:
        """
        Fills the empty slots of a plan with the most varied eligible meals

        Args:
            menu (str): The current menu string (can be empty or None); its meals stay
                as they are and count as neighbours for variety
            preferences (str): A comma-separated string of user preferences; diets in it
                are hard rules, other words ("Italian", "spicy") are soft preferences
            allergens (str): A comma-separated string of allergens to avoid
            date (str): The first day to plan, in YYYY-MM-DD format
            meal_numbers (List[int]): The meals to plan each day (1 breakfast, 2 lunch, 3 dinner)
            number_of_days (int): The number of days to plan, starting at {date}
            weekly_cap_cents (int | None): Item-price limit per Monday–Sunday week,
                counting all existing meals in that week. None leaves generation uncapped.

        Returns:
            str: The updated menu string. Also sets self.variety (proj2.variety.PlanVariety
                for the requested days) and, with a cap, self.weekly_totals_cents and
                self.item_total_cents.

        Raises:
            ValueError: for a malformed date or meal number
            NoEligibleMealError: if no item passes the rules for a slot
            DietaryConstraintError: if items are available but none meets the user's diet
            BudgetExceededError: if the cheapest possible plan does not fit the cap
        """
        self._rows_cache = None
        try:
            start = datetime.date.fromisoformat(date)
        except (TypeError, ValueError):
            raise ValueError(
                "Unable to parse date string. Ensure it is formatted properly as to YYYY-MM-DD format"
            )
        meals = sorted(dict.fromkeys(int(meal) for meal in meal_numbers))
        for meal in meals:
            get_meal_and_order_time(meal)  # rejects anything but 1, 2, 3
        days = [(start + datetime.timedelta(days=i)).isoformat() for i in range(number_of_days)]
        weeks = list(dict.fromkeys(week_start(day) for day in days))
        capped = weekly_cap_cents is not None
        if capped:
            cap = item_price_cents(weekly_cap_cents)
            totals = weekly_item_totals(menu, self.item_prices, weeks)

        existing = list(plan_entries(menu))
        occupied = {(day, meal) for day, _, meal in existing}
        slots = []
        minimum_remaining = dict.fromkeys(weeks, 0)
        for day in days:
            weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(day).weekday()]
            for meal in meals:
                if (day, meal) in occupied:
                    continue
                _, order_time = get_meal_and_order_time(meal)
                candidates = self._eligible_candidates(
                    allergens, weekday, order_time, preferences=preferences, meal=meal
                )
                if candidates.empty:
                    reason = self._empty_slot_reason(allergens, weekday, order_time, meal)
                    raise NoEligibleMealError(
                        f"No menu item can be planned for {SLOT_NAMES[meal]} on {day}: {reason}"
                    )
                week = week_start(day)
                minimum = int(candidates.price_cents.min())
                minimum_remaining[week] += minimum
                slots.append(
                    {
                        "day": day,
                        "meal": meal,
                        "weekday": weekday,
                        "order_time": order_time,
                        "week": week,
                        "candidates": candidates,
                        "minimum": minimum,
                        "position": variety.slot_position(day, meal),
                    }
                )

        if capped:
            # Check every affected week before choosing anything; never save a partial plan.
            for week in weeks:
                required = totals[week] + minimum_remaining[week]
                if required > cap:
                    raise BudgetExceededError(
                        f"Week of {week} needs at least ${required / 100:.2f} in items; "
                        f"the weekly cap is ${cap / 100:.2f}. "
                        "Raise the cap or request fewer meals."
                    )

        def price(itm_id):
            return item_price_cents(self.item_prices[itm_id])

        def check(itm_id, slot):
            self._check_pick(
                itm_id, preferences, allergens, slot["weekday"], slot["order_time"], slot["meal"]
            )

        rows = self._rows()
        planned = {
            variety.slot_position(day, meal): itm_id
            for day, itm_id, meal in existing
            if itm_id in rows
        }

        # Pass 1: fill slots in time order, each next to the meals already planned.
        chosen = []
        for slot in slots:
            pool = slot["candidates"]
            if capped:
                # Keep enough for the cheapest meal in every later slot of this week.
                minimum_remaining[slot["week"]] -= slot["minimum"]
                available = cap - totals[slot["week"]] - minimum_remaining[slot["week"]]
                pool = pool[pool.price_cents <= available]
            ranked = self._ranked(
                pool, slot["position"], self._neighbours(planned, slot["position"]), preferences
            )
            itm_id = ranked[0][1]
            check(itm_id, slot)
            planned[slot["position"]] = itm_id
            chosen.append(itm_id)
            if capped:
                totals[slot["week"]] += price(itm_id)

        # Pass 2: re-pick each new slot with the rest of the plan fixed; keep strict gains.
        for i, slot in enumerate(slots):
            current = chosen[i]
            pool = slot["candidates"]
            if capped:
                available = cap - totals[slot["week"]] + price(current)
                pool = pool[pool.price_cents <= available]
            ranked = self._ranked(
                pool, slot["position"], self._neighbours(planned, slot["position"]), preferences
            )
            best_key, best = ranked[0]
            current_score = next(key[0] for key, itm_id in ranked if itm_id == current)
            if best != current and best_key[0] < current_score:
                check(best, slot)
                planned[slot["position"]] = best
                chosen[i] = best
                if capped:
                    totals[slot["week"]] += price(best) - price(current)

        updated = menu or ""
        for slot, itm_id in zip(slots, chosen):
            entry = f"[{slot['day']},{itm_id},{slot['meal']}]"
            updated = f"{updated},{entry}" if updated else entry

        if capped:
            self.weekly_totals_cents = totals
            self.item_total_cents = sum(totals.values())
        requested = set(days)
        self.variety = variety.plan_variety(
            [entry for entry in plan_entries(updated) if entry[0] in requested], rows
        )
        return updated
