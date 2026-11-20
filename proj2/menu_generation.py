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
leaves stale picks behind. With nutrition targets, meals that keep a day inside its
targets outrank everything else (proj2.nutrition).

The result is deterministic: the same catalog and request always give the same plan.
"""

import datetime
import itertools
import json
import math
import statistics
from typing import Tuple

import numpy as np
import pandas as pd

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
from proj2.nutrition import (
    JOINT_SEARCH_LIMIT,
    JOINT_SLACK,
    NUTRIENTS,
    REPAIR_CANDIDATES,
    TargetsUnreachableError,
    describe_range,
    item_amount,
)
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
        self.targets = {}
        self.daily_totals = None

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

    def _amount(self, itm_id: int, column: str):
        """One catalog item's amount of a nutrient, or None if unknown (nutrition.item_amount)."""
        row = self._rows().get(itm_id)
        return None if row is None else item_amount(row.get(column))

    def _ranked(
        self,
        pool: pd.DataFrame,
        position: int,
        neighbours: list,
        preferences,
        target_miss=None,
        avoid=(),
    ) -> list:
        """
        Ranks a slot's candidates, best first

        Args:
            target_miss (Callable[[int], float] | None): How far the slot's day would miss
                its nutrition targets with each item, beyond any allowance, summed over
                nutrients (proj2.nutrition.DailyRange.miss). It ranks first: a meal that
                keeps the day closer to its targets wins whatever the other keys say.
                None when there are no targets (every miss is 0).
            avoid (Container): Items already in the plan. A meal the week has not used yet
                outranks one it has, whatever the variety scores. The variety score alone
                does not do this: `closeness` has decayed to 0.16 three days out, so
                repeating a dish that far away can score higher than a fresh one, and a
                plan is allowed to repeat only once it has run out of different meals.
                Targets rank above this, so a plan repeats a dish when only that dish
                keeps a day inside them.

        Returns:
            List[Tuple[tuple, int]]: (sort key, itm_id); the key is
                (target miss, already used, -score, price, itm_id), so the meal nearest the
                targets wins first, then an unused one, then the most varied fit, then the
                cheaper one, then the lower ID
        """
        self._rows()
        ranked = []
        for itm_id, price_cents in zip(pool["itm_id"].tolist(), pool["price_cents"].tolist()):
            itm_id = int(itm_id)
            gain, weight_sum = self._distances.slot_gain(itm_id, position, neighbours)
            score = variety.candidate_score(gain, weight_sum, self._preference(itm_id, preferences))
            miss = 0.0 if target_miss is None else round(target_miss(itm_id), 9)
            key = (miss, int(itm_id in avoid), -score, int(price_cents), itm_id)
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

    # ---------------------------------------------------------------- strict targets

    def _day_miss(self, positions, planned, aims) -> float:
        """A day's total miss against its aims, summed over nutrients (unknowns count 0)."""
        return sum(
            aim.miss(sum(self._amount(planned[p], column) or 0 for p in positions))
            for column, aim in aims.items()
        )

    def _best_day_miss(self, positions, new_slots, fixed_meals, aims) -> float:
        """
        The smallest total miss any combination of a day's candidates can reach

        Combines the new slots' candidates' nutrient amounts one slot at a time, keeping
        only distinct totals. If the combinations would exceed JOINT_SEARCH_LIMIT, gives
        up and returns None.

        Args:
            positions (set): The day's slot positions
            new_slots (dict): position -> slot being planned
            fixed_meals (dict): position -> itm_id of meals already in the plan
            aims (dict): column -> DailyRange the day aims for

        Returns:
            float | None: The smallest summed miss (0.0 when every aim can be met), or
                None if the search was too large
        """
        columns = list(aims)
        fixed = np.array(
            [
                sum(
                    self._amount(fixed_meals[p], c) or 0
                    for p in positions
                    if p not in new_slots and p in fixed_meals
                )
                for c in columns
            ]
        )
        sums = fixed[None, :]
        for position in sorted(p for p in positions if p in new_slots):
            ids = new_slots[position]["candidates"]["itm_id"]
            amounts = np.unique(
                np.array([[self._amount(int(i), c) for c in columns] for i in ids]), axis=0
            )
            if len(sums) * len(amounts) > JOINT_SEARCH_LIMIT:
                return None
            sums = np.unique(
                (sums[:, None, :] + amounts[None, :, :]).reshape(-1, len(columns)), axis=0
            )
        miss = np.zeros(len(sums))
        for k, column in enumerate(columns):
            aim, total = aims[column], sums[:, k]
            if aim.low > 0:
                miss += np.where(total < aim.low, (aim.low - total) / aim.low, 0.0)
            if not math.isinf(aim.high):
                miss += np.where(total > aim.high, (total - aim.high) / aim.high, 0.0)
        return float(miss.min())

    def _day_misses(self, positions, planned, targets) -> bool:
        """Whether a day's planned meals miss any target (or a meal's amount is unknown)."""
        for column, target in targets.items():
            amounts = [self._amount(planned[p], column) for p in positions]
            if None in amounts or target.miss(sum(amounts)):
                return True
        return False

    def _out_of_reach(self, positions, new_slots, planned, column, target, low, high) -> str:
        """The message for a day whose meals cannot reach a target in any combination."""
        day = datetime.date.fromordinal(min(positions) // variety.SLOTS_PER_DAY).isoformat()
        unit = NUTRIENTS[column].unit
        if high < target.low:
            reach = f"the most its meals can add up to is {high:,.0f} {unit}"
        else:
            reach = f"the least its meals can add up to is {low:,.0f} {unit}"
        return (
            f"No plan for {day} can meet your daily target of {describe_range(column, target)}: "
            f"{reach} with your diet, allergies and the menu. Change the target, or turn off "
            "strict targets to plan as close as possible."
        )

    def _repair_day(self, positions, new_slots, planned, targets, preferences, budget, price):
        """
        Finds the most varied meals for a day's new slots that keep it inside every target

        Searches every combination of each new slot's REPAIR_CANDIDATES most varied
        candidates (by variety next to the meals around it), with the day's existing
        meals fixed.

        Args:
            positions (set): The day's slot positions (existing and new)
            new_slots (dict): position -> slot for the slots being planned
            planned (dict): position -> itm_id of the current plan
            targets (dict): column -> DailyRange
            preferences (str): The user's preferences, for ranking
            budget (int | None): Cents left in the day's week for its new slots' current
                picks to be replaced within (cap minus the week's total), or None if uncapped
            price (Callable[[int], int]): itm_id -> price in cents

        Returns:
            dict: position -> itm_id for the day's new slots

        Raises:
            TargetsUnreachableError: if no combination keeps the day inside every target
        """
        open_positions = sorted(p for p in positions if p in new_slots)
        day = datetime.date.fromordinal(min(positions) // variety.SLOTS_PER_DAY).isoformat()
        fixed = dict.fromkeys(targets, 0.0)
        for position in positions - set(open_positions):
            for column in targets:
                amount = self._amount(planned[position], column)
                if amount is None:
                    raise TargetsUnreachableError(
                        f"A meal already planned for {day} has no {NUTRIENTS[column].label} "
                        "value, so the day cannot be checked against your targets."
                    )
                fixed[column] += amount
        current_cost = sum(price(planned[p]) for p in open_positions)
        # Meals planned on other days; the day's own picks are about to be replaced
        elsewhere = {itm_id for p, itm_id in planned.items() if p not in open_positions}
        options = []
        truncated = False
        for position in open_positions:
            ranked = self._ranked(
                new_slots[position]["candidates"],
                position,
                self._neighbours(planned, position),
                preferences,
                avoid=elsewhere,
            )
            truncated = truncated or len(ranked) > REPAIR_CANDIDATES
            options.append(
                [
                    (key[1:3], itm_id, price(itm_id), [self._amount(itm_id, c) for c in targets])
                    for key, itm_id in ranked[:REPAIR_CANDIDATES]
                ]
            )
        columns = list(targets)
        best, best_key = None, None
        for combo in itertools.product(*options):
            cost = sum(option[2] for option in combo)
            if budget is not None and cost - current_cost > budget:
                continue
            if any(
                targets[column].miss(fixed[column] + sum(option[3][i] for option in combo))
                for i, column in enumerate(columns)
            ):
                continue
            # Fewest repeats, then most varied, then cheapest, then lowest itm_ids
            key = (
                sum(option[0][0] for option in combo)
                + (len({option[1] for option in combo}) < len(combo)),
                sum(option[0][1] for option in combo),
                cost,
                [option[1] for option in combo],
            )
            if best_key is None or key < best_key:
                best, best_key = combo, key
        if best is None:
            ranges = "; ".join(describe_range(c, t) for c, t in targets.items())
            searched = (
                f"Among the {REPAIR_CANDIDATES} most varied meals for each of its slots, no "
                if truncated
                else "No "
            )
            raise TargetsUnreachableError(
                f"{searched}combination of meals for {day} keeps it inside all of your daily "
                f"targets ({ranges}) with your diet, allergies and budget. Loosen a target, "
                "or turn off strict targets to plan as close as possible."
            )
        return {position: option[1] for position, option in zip(open_positions, best)}

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
        targets=None,
        strict_targets: bool = False,
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
            targets (dict | None): Daily nutrition ranges to aim for, MenuItem column ->
                proj2.nutrition.DailyRange (proj2.nutrition.parse_targets), counting existing
                meals on each day. Soft goals: days stay inside them where the catalog
                allows, then variety decides. Items without a value for a targeted
                nutrient are not planned. None or empty plans as before.
            strict_targets (bool): Make the targets hard limits: every requested day must
                end up inside every range, or nothing is planned (see _repair_day).

        Returns:
            str: The updated menu string. Also sets self.variety (proj2.variety.PlanVariety
                for the requested days), self.daily_totals (see nutrition_report) and, with a
                cap, self.weekly_totals_cents and self.item_total_cents.

        Raises:
            ValueError: for a malformed date or meal number
            NoEligibleMealError: if no item passes the rules for a slot
            DietaryConstraintError: if items are available but none meets the user's diet
            BudgetExceededError: if the cheapest possible plan does not fit the cap
            TargetsUnreachableError: with strict_targets, if a requested day cannot be
                kept inside every range
        """
        self._rows_cache = None
        targets = dict(targets or {})
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
                _, order_time = get_meal_and_order_time(meal)
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
                estimate, spread = {}, {}
                for column in targets:
                    # A target cannot be checked against an item with no value for it
                    known = [self._amount(int(i), column) for i in candidates["itm_id"]]
                    candidates = candidates[[value is not None for value in known]]
                    if candidates.empty:
                        label = NUTRIENTS[column].label
                        raise NoEligibleMealError(
                            f"No menu item can be planned for {SLOT_NAMES[meal]} on {day}: "
                            f"no item that fits lists its {label}, so the {label} target "
                            f"cannot be checked. Remove the target or add {label} to the menu."
                        )
                for column in targets:
                    known = [self._amount(int(i), column) for i in candidates["itm_id"]]
                    estimate[column] = statistics.median(known)
                    spread[column] = (min(known), max(known))
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
                        "estimate": estimate,  # column -> candidates' median amount
                        "spread": spread,  # column -> (least, most) among candidates
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

        # Each day's slots (existing meals and new ones), for its nutrient totals
        day_slots = {}
        for position in [*already, *(slot["position"] for slot in slots)]:
            day_slots.setdefault(position // variety.SLOTS_PER_DAY, set()).add(position)
        new_slots = {slot["position"]: slot for slot in slots}
        requested_days = sorted({slot["position"] // variety.SLOTS_PER_DAY for slot in slots})

        # The ranges each day aims for: the targets, eased only where the day's meals
        # cannot reach them (DailyRange.within_reach)
        day_targets = {}
        for day, positions in day_slots.items():
            day_targets[day] = {}
            for column, target in targets.items():
                low = high = 0
                for position in positions:
                    if position in new_slots:
                        least, most = new_slots[position]["spread"][column]
                    else:
                        least = most = self._amount(already[position], column) or 0
                    low, high = low + least, high + most
                day_targets[day][column] = target.within_reach(low, high)
                requested_day = any(position in new_slots for position in positions)
                if strict_targets and requested_day and (high < target.low or low > target.high):
                    # Even the richest (or leanest) meals miss on the same side
                    raise TargetsUnreachableError(
                        self._out_of_reach(positions, new_slots, already, column, target, low, high)
                    )

        def target_miss(slot, planned, allowance):
            """
            How far the slot's day misses its aims with each item, beyond the day's
            allowance (None: no targets)
            """
            if not targets:
                return None
            position = slot["position"]
            day = position // variety.SLOTS_PER_DAY
            others = dict.fromkeys(targets, 0)
            for other in day_slots[day] - {position}:
                for column in targets:
                    if other in planned:  # an existing meal, or a new one already chosen
                        others[column] += self._amount(planned[other], column) or 0
                    else:  # a new slot not chosen yet (pass 1): its candidates' median
                        others[column] += new_slots[other]["estimate"][column]
            aims = day_targets[day]
            allowed = allowance.get(day, 0.0)
            return lambda itm_id: max(
                0.0,
                sum(
                    aims[column].miss(others[column] + self._amount(itm_id, column))
                    for column in targets
                )
                - allowed,
            )

        def plan_miss(planned, allowance):
            """The requested days' total miss beyond their allowances (0 with no targets)."""
            if not targets:
                return 0.0
            return sum(
                max(
                    0.0,
                    self._day_miss(day_slots[day], planned, day_targets[day])
                    - allowance.get(day, 0.0),
                )
                for day in requested_days
            )

        def build(opening, allowance):
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
                        self._neighbours(planned, slot["position"]),
                        preferences,
                        target_miss(slot, planned, allowance),
                        avoid=set(planned.values()),
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
            # accepted move strictly improves that slot's (target miss, already used,
            # gain), so the loop settles on its own, and the bound only guards against
            # a pathological catalog.
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
                        self._neighbours(planned, slot["position"]),
                        preferences,
                        target_miss(slot, planned, allowance),
                        # The slot's own meal is not a repeat of itself.
                        avoid=set(planned.values()) - {current},
                    )
                    best_key, best = ranked[0]
                    current_key = next(key for key, itm_id in ranked if itm_id == current)
                    # Only (target miss, already used, -score) justifies a move. Price and
                    # itm_id order the ranking but must not trigger one: swapping to an
                    # equally good cheaper meal leaves the plan's score untouched, so
                    # sweeps could keep trading between equal plans and never settle.
                    if best != current and best_key[:3] < current_key[:3]:
                        check(best, slot)
                        planned[slot["position"]] = best
                        chosen[i] = best
                        if capped:
                            totals_here[slot["week"]] += price(best) - price(current)
                        changed = True
                if not changed:
                    break
            return chosen, planned, totals_here

        def best_plan(allowance):
            """
            Builds the plan from every restart opening and keeps the best: nearest the
            targets first, then the most varied, then the cheapest
            """
            # The first slot has nothing planned around it yet, so every candidate scores
            # the same zero gain and the tie-break hands the slot to the cheapest item.
            # That one arbitrary pick shapes everything after it, and single-slot
            # improvement cannot undo it: measuring against an exact solver showed plans
            # 4% less varied *and* $6 dearer than a week that was available. So the whole
            # fill-and-improve is run again from a spread of openings and the best plan
            # wins. Planning a week costs about 30 ms, against a 5 s target, so the
            # restarts are affordable.
            best = None
            for opening in self._restart_openings(slots):
                chosen, planned, totals_here = build(opening, allowance)
                key = (
                    -round(plan_miss(planned, allowance), 9),
                    self._plan_objective(planned),
                    -sum(price(itm_id) for itm_id in chosen),
                )
                if best is None or key > best[0]:
                    best = (key, chosen, planned, totals_here)
            return best[1], best[2], best[3]

        chosen, planned, totals_best = best_plan({})

        if targets and not strict_targets:
            # A day that cannot meet every target at once would otherwise chase the one
            # closest combination every day. It may instead come within JOINT_SLACK of
            # the closest its meals can get (_best_day_miss), and variety picks among
            # those. Days that meet their targets keep their plans.
            allowance = {}
            for day in requested_days:
                if self._day_miss(day_slots[day], planned, day_targets[day]) > 0:
                    best = self._best_day_miss(day_slots[day], new_slots, already, day_targets[day])
                    # Only a day that truly cannot meet them all (best > 0) is eased; a
                    # day that could, or one too large to search (None), keeps chasing
                    if best:
                        allowance[day] = best + JOINT_SLACK
            if allowance:
                chosen, planned, totals_best = best_plan(allowance)
        if capped:
            totals = totals_best

        if strict_targets and targets:
            index = {slot["position"]: i for i, slot in enumerate(slots)}
            for day in sorted({slot["position"] // variety.SLOTS_PER_DAY for slot in slots}):
                positions = day_slots[day]
                if self._day_misses(positions, planned, targets):
                    picks = self._repair_day(
                        positions,
                        new_slots,
                        planned,
                        targets,
                        preferences,
                        (
                            (cap - totals[new_slots[min(positions & set(new_slots))]["week"]])
                            if capped
                            else None
                        ),
                        price,
                    )
                    for position, itm_id in picks.items():
                        slot = new_slots[position]
                        check(itm_id, slot)
                        if capped:
                            totals[slot["week"]] += price(itm_id) - price(planned[position])
                        planned[position] = chosen[index[position]] = itm_id

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
        self.targets = targets
        self.daily_totals = {}
        for day, itm_id, _ in plan_entries(updated):
            if day not in requested:
                continue
            totals_today = self.daily_totals.setdefault(day, dict.fromkeys(targets, 0))
            for column in targets:
                amount = self._amount(itm_id, column)
                # A day with a meal of unknown amount has no reliable total
                if amount is None or totals_today[column] is None:
                    totals_today[column] = None
                else:
                    totals_today[column] += amount
        return updated

    def nutrition_report(self):
        """
        Each requested day's nutrient totals and how far they are from the targets

        Returns:
            dict | None: {"targets": {column: {"min", "max"}}, "days": [{"date", "totals":
                {column: amount}, "miss": {column: share}}], "days_outside": int,
                "outside_by_nutrient": {column: int}}; None if the last plan had no
                targets. A total (and its miss) is None when one of the day's meals has
                no value for that nutrient.
        """
        if not self.targets:
            return None
        days = []
        for day in sorted(self.daily_totals):
            totals = self.daily_totals[day]
            days.append(
                {
                    "date": day,
                    "totals": {c: None if v is None else round(v, 1) for c, v in totals.items()},
                    "miss": {
                        column: None if total is None else round(target.miss(total), 4)
                        for column, target in self.targets.items()
                        for total in [totals[column]]
                    },
                }
            )
        return {
            "targets": {column: target.as_json() for column, target in self.targets.items()},
            "days": days,
            "days_outside": sum(1 for day in days if any(day["miss"].values())),
            "outside_by_nutrient": {
                column: sum(1 for day in days if day["miss"][column]) for column in self.targets
            },
        }
