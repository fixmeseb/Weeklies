"""
Meal-plan generation: fills empty date/meal slots with the most varied eligible meals.

For every slot, the candidates are the items that pass the shared rules
(proj2.plan_rules: stock, opening hours, allergens, diets, and the slot's course and
meal type), and, with a weekly cap, that leave enough budget for the meals still to
plan. Among them the planner picks the one that adds the most variety next to the meals
already in the plan (proj2.variety), with soft preferences such as "Italian" breaking
near-ties, then the lower price, then the lower itm_id. After every slot is filled it
re-picks each slot with the rest of the plan fixed, and repeats that sweep until one
changes nothing: filling a slot changes what its neighbours should be, so a single pass
leaves stale picks behind.

The LOOKBACK_DAYS before the plan's first day count too. Meals planned then are already
in the plan; meals the user ordered then are added as neighbours for variety, and a dish
ordered then ranks like one already used for slots within LOOKBACK_DAYS of it.

The result is deterministic: the same catalog and request always give the same plan.
"""

import datetime
import json
from typing import Tuple

import pandas as pd

from proj2 import meal_times as meal_times_module
from proj2 import variety
from proj2.meal_budget import (
    BudgetExceededError,
    item_price_cents,
    plan_entries,
    week_start,
    weekly_item_totals,
)
from proj2.allergens import avoided_allergens, parse_allergens
from proj2.db import connect
from proj2.dietary import DietaryConstraintError, filter_diets, required_diets
from proj2.plan_rules import (
    SLOT_NAMES,
    PlanRuleError,
    is_restaurant_open,
    item_rejection,
    slot_rejection,
)

## Days of the week in an array - should be the same as in the database*
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

## Most improvement sweeps to run before giving up. Each sweep only accepts strict gains,
## so the plan's score rises monotonically and the loop settles on its own well inside
## this; the bound is a guard, not the usual stopping point.
MAX_IMPROVEMENT_SWEEPS = 20

## How many openings to try for the first slot besides the default one. The first slot has
## no neighbours yet, so every candidate ties and the cheapest wins by tie-break; trying a
## spread of openings and keeping the best plan is what stops that arbitrary pick from
## deciding the week. Twelve keeps a week's planning well under a tenth of a second.
RESTART_OPENINGS = 12

## Days before a new plan's first day whose ordered meals shape its variety
LOOKBACK_DAYS = 3

## Default meal times (HHMM); a user's own come from proj2.meal_times.times_for
BREAKFAST_TIME = meal_times_module.DEFAULT_TIMES[1]
LUNCH_TIME = meal_times_module.DEFAULT_TIMES[2]
DINNER_TIME = meal_times_module.DEFAULT_TIMES[3]


class NoEligibleMealError(ValueError):
    """No menu item passes the rules for one of the requested slots."""


def recent_repeats(recent, position: int) -> set:
    """
    The items from the lookback days that count as repeats for one slot

    Args:
        recent: (slot position, itm_id) of meals from the lookback days
        position (int): variety.slot_position() of the slot being filled

    Returns:
        set: itm_ids eaten within LOOKBACK_DAYS calendar days of the slot
    """
    day = position // variety.SLOTS_PER_DAY
    return {
        itm_id for pos, itm_id in recent if abs(day - pos // variety.SLOTS_PER_DAY) <= LOOKBACK_DAYS
    }


def get_meal_and_order_time(meal_number: int, times: dict = None) -> Tuple[str, int]:
    """
    Maps a meal number to its meal name and the time it is eaten

    Args:
        meal_number (int): The meal number to get the meal and order times for
        times (dict | None): The user's meal times (proj2.meal_times.times_for); None
            uses the defaults

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
    if times:
        order_time = int(times[meal_number])
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
    prohibited = avoided_allergens(allergens)

    def allowed(value):
        return not prohibited.intersection(parse_allergens(value))

    return menu_items.loc[map_distinct(menu_items["allergens"], allowed)].copy()


def map_distinct(values: pd.Series, check) -> pd.Series:
    """
    Applies a check to each distinct value of a column once, rather than to every row

    Menu columns repeat heavily (many items share one allergen list, course or opening
    hours), and the checks parse strings, so this is much faster on a large catalog.

    Args:
        values (pd.Series): The column to check
        check (Callable): Returns a truthy value for a cell that passes

    Returns:
        pd.Series: A boolean mask aligned with values
    """
    results = {}
    mask = []
    for value in values:
        key = None if _is_missing(value) else value
        if key not in results:
            results[key] = bool(check(value))
        mask.append(results[key])
    return pd.Series(mask, index=values.index, dtype=bool)


def _is_missing(value) -> bool:
    """None, NaN or pd.NA: the empty cells pandas may give for one SQL NULL."""
    return value is None or value is pd.NA or (isinstance(value, float) and value != value)


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
    is_open = map_distinct(
        restaurant["hours"], lambda hours: is_restaurant_open(hours, weekday, time)
    )
    return restaurant[is_open]


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

    def column(name):
        if name in menu_items.columns:
            return menu_items[name].map(lambda value: None if _is_missing(value) else value)
        return pd.Series(None, index=menu_items.index, dtype=object)

    # The rule reads only course and meal_type (the name is just for its message)
    pairs = pd.Series(list(zip(column("course"), column("meal_type"))), index=menu_items.index)
    keep = map_distinct(
        pairs,
        lambda pair: slot_rejection({"name": "", "course": pair[0], "meal_type": pair[1]}, meal)
        is None,
    )
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
            self._distances = variety.ItemDistances(self._rows_cache)
            self._preference_cache = {}
        return self._rows_cache

    def _neighbours(self, planned: dict, position: int) -> list:
        """(position, itm_id) of every planned meal except the one in this slot."""
        rows = self._rows()
        return [
            (other, itm_id)
            for other, itm_id in planned.items()
            if other != position and itm_id in rows
        ]

    def _preference(self, itm_id: int, preferences) -> float:
        """variety.preference_match for one item, cached (preferences are fixed per request)."""
        if itm_id not in self._preference_cache:
            self._preference_cache[itm_id] = variety.preference_match(
                self._rows()[itm_id], preferences
            )
        return self._preference_cache[itm_id]

    def _ranked(
        self, pool: pd.DataFrame, position: int, neighbours: list, preferences, avoid=()
    ) -> list:
        """
        Ranks a slot's candidates, best first

        Args:
            avoid (Container): Items already in the plan. A meal the week has not used yet
                always outranks one it has, whatever the scores. The variety score alone
                does not do this: `closeness` has decayed to 0.16 three days out, so
                repeating a dish that far away can score higher than a fresh one, and a
                plan is allowed to repeat only once it has run out of different meals.

        Returns:
            List[Tuple[tuple, int]]: (sort key, itm_id); the key is
                (already used, -score, price, itm_id), so an unused meal wins first, then
                the most varied fit, then the cheaper one, then the lower ID
        """
        self._rows()
        ranked = []
        for itm_id, price_cents in zip(pool["itm_id"].tolist(), pool["price_cents"].tolist()):
            itm_id = int(itm_id)
            gain, weight_sum = self._distances.slot_gain(itm_id, position, neighbours)
            score = variety.candidate_score(gain, weight_sum, self._preference(itm_id, preferences))
            key = (int(itm_id in avoid), -score, int(price_cents), itm_id)
            ranked.append((key, itm_id))
        ranked.sort()
        return ranked

    def _restart_openings(self, slots, limit=None):
        """
        The items to try in the first slot, spread across its candidates

        Args:
            slots (list): The slots to be planned, in time order
            limit (int | None): How many openings to try besides the default; None reads
                RESTART_OPENINGS. Read here rather than taken as a default argument,
                which would bind the constant at import and make it untunable.

        Returns:
            list: itm_ids to force into the first slot, led by None, which means "pick
                the first slot the usual way". Keeping None first means the restarts can
                only improve on the plan the planner would have produced without them.
        """
        limit = RESTART_OPENINGS if limit is None else limit
        if not slots or limit < 1:
            return [None]
        pool = [int(itm_id) for itm_id in slots[0]["candidates"]["itm_id"]]
        if not pool:
            return [None]
        if len(pool) <= limit:
            return [None] + pool
        if limit == 1:
            # One extra opening cannot be "spread" across the pool, and the step below
            # would divide by limit - 1.
            return [None, pool[0]]
        # The pool is ordered by price then itm_id, so even steps through it sample the
        # whole price range instead of crowding the cheap end the tie-break already favours.
        step = (len(pool) - 1) / (limit - 1)
        spread = {pool[round(index * step)] for index in range(limit)}
        return [None] + sorted(spread, key=pool.index)

    def _plan_objective(self, planned) -> float:
        """
        The closeness-weighted distance summed over every pair of planned meals

        This is the numerator of the score `variety.plan_variety` reports. Its denominator
        depends only on which slots are filled, so for one request this ranks plans exactly
        as the reported score does, without recomputing the constant each time.

        Args:
            planned (dict): slot position -> itm_id, including meals already in the plan

        Returns:
            float: The weighted total; larger is more varied
        """
        self._rows()
        positions = sorted(planned)
        total = 0.0
        for index, here in enumerate(positions):
            for other in positions[index + 1 :]:
                weight = variety.closeness(here, other)
                if weight:
                    # Through the shared cache: restarts score overlapping plans, so most
                    # of these pairs have already been computed by an earlier one.
                    total += weight * self._distances.distance(planned[here], planned[other])
        return total

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
        ordered_meals=(),
        meal_times=None,
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
            ordered_meals: (date, itm_id, meal) of meals the user ordered; those in the
                LOOKBACK_DAYS before {date} count as described in the module docstring
            meal_times (dict | None): The user's meal times (proj2.meal_times.times_for);
                restaurants must be open then. None uses the defaults.

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
        # Candidates depend only on the weekday and meal (the user's rules are fixed for
        # this request), so a plan longer than a week reuses them. Never mutated below.
        candidates_for = {}
        for day in days:
            weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(day).weekday()]
            for meal in meals:
                if (day, meal) in occupied:
                    continue
                _, order_time = get_meal_and_order_time(meal, meal_times)
                key = (weekday, order_time, meal)
                if key not in candidates_for:
                    candidates_for[key] = self._eligible_candidates(
                        allergens, weekday, order_time, preferences=preferences, meal=meal
                    )
                candidates = candidates_for[key]
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
        already = {
            variety.slot_position(day, meal): itm_id
            for day, itm_id, meal in existing
            if itm_id in rows
        }

        # The lookback days: meals the user ordered then (planned ones are in `already`).
        # They are extra neighbours, and repeats for the slots within LOOKBACK_DAYS of them.
        first_back = (start - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
        recent = sorted(
            {
                (variety.slot_position(day, meal), int(itm_id))
                for day, itm_id, meal in ordered_meals
                if first_back <= day < start.isoformat()
                and int(itm_id) in rows
                and int(meal) in (1, 2, 3)
                and already.get(variety.slot_position(day, meal)) != int(itm_id)
            }
        )

        def neighbours(planned, position):
            return self._neighbours(planned, position) + recent

        def avoid(planned, position, current=None):
            used = set(planned.values()) - ({current} if current is not None else set())
            return used | recent_repeats(recent, position)

        def build(opening):
            """Fill every slot, then improve it, starting the first slot with `opening`.

            Returns (chosen, planned, totals). Each call works on its own copies, so a
            restart never inherits the previous one's state.
            """
            planned = dict(already)
            totals_here = dict(totals) if capped else None
            remaining = dict(minimum_remaining)

            # Pass 1: fill slots in time order, each next to the meals already planned.
            chosen = []
            for index, slot in enumerate(slots):
                pool = slot["candidates"]
                if capped:
                    # Keep enough for the cheapest meal in every later slot of this week.
                    remaining[slot["week"]] -= slot["minimum"]
                    available = cap - totals_here[slot["week"]] - remaining[slot["week"]]
                    pool = pool[pool.price_cents <= available]
                if index == 0 and opening is not None and opening in set(pool["itm_id"]):
                    itm_id = opening
                else:
                    ranked = self._ranked(
                        pool,
                        slot["position"],
                        neighbours(planned, slot["position"]),
                        preferences,
                        avoid=avoid(planned, slot["position"]),
                    )
                    itm_id = ranked[0][1]
                check(itm_id, slot)
                planned[slot["position"]] = itm_id
                chosen.append(itm_id)
                if capped:
                    totals_here[slot["week"]] += price(itm_id)

            # Pass 2: re-pick each slot with the rest of the plan fixed, keeping strict
            # gains, and repeat until a sweep changes nothing.
            #
            # One sweep was not enough. Re-picking a slot changes the neighbourhood of
            # the slots around it, which can make a meal that was the best choice a
            # moment ago no longer the best; a single pass leaves those stale. Each
            # accepted move strictly raises that slot's gain and leaves every pair not
            # touching it alone, so the plan's total closeness-weighted distance rises on
            # every move and can never revisit a plan. The loop therefore settles on its
            # own, and the bound only guards against a pathological catalog.
            for _ in range(MAX_IMPROVEMENT_SWEEPS):
                changed = False
                for i, slot in enumerate(slots):
                    current = chosen[i]
                    pool = slot["candidates"]
                    if capped:
                        available = cap - totals_here[slot["week"]] + price(current)
                        pool = pool[pool.price_cents <= available]
                    ranked = self._ranked(
                        pool,
                        slot["position"],
                        neighbours(planned, slot["position"]),
                        preferences,
                        # The slot's own meal is not a repeat of itself.
                        avoid=avoid(planned, slot["position"], current),
                    )
                    best_key, best = ranked[0]
                    current_key = next(key for key, itm_id in ranked if itm_id == current)
                    # Only (already used, -score) justifies a move. Price and itm_id order
                    # the ranking but must not trigger one: swapping to an equally varied
                    # cheaper meal leaves the plan's score untouched, so sweeps could keep
                    # trading between equal plans and never settle.
                    if best != current and best_key[:2] < current_key[:2]:
                        check(best, slot)
                        planned[slot["position"]] = best
                        chosen[i] = best
                        if capped:
                            totals_here[slot["week"]] += price(best) - price(current)
                        changed = True
                if not changed:
                    break
            return chosen, planned, totals_here

        # The first slot has nothing planned around it yet, so every candidate scores the
        # same zero gain and the tie-break hands the slot to the cheapest item. That one
        # arbitrary pick shapes everything after it, and single-slot improvement cannot
        # undo it: measuring against an exact solver showed plans 4% less varied *and*
        # $6 dearer than a week that was available. So the whole fill-and-improve is run
        # again from a spread of openings and the best plan wins. Planning a week costs
        # about 30 ms, against a 5 s target, so the restarts are affordable.
        best = None
        for opening in self._restart_openings(slots):
            chosen, planned, totals_here = build(opening)
            key = (self._plan_objective(planned), -sum(price(itm_id) for itm_id in chosen))
            if best is None or key > best[0]:
                best = (key, chosen, planned, totals_here)
        chosen, planned = best[1], best[2]
        if capped:
            totals = best[3]

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
