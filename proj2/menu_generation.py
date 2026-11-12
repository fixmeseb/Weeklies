import pandas as pd
import datetime
import time
import random
import re
from typing import Tuple, List

import proj2.llm_toolkit as llm_toolkit
from proj2.meal_budget import (
    BudgetExceededError,
    item_price_cents,
    plan_entries,
    week_start,
    weekly_item_totals,
)
from proj2.db import connect
from proj2.dietary import DietaryConstraintError, filter_diets, required_diets
from proj2.plan_rules import PlanRuleError, is_restaurant_open, item_rejection, parse_allergens

## LLM error handling
MAX_LLM_TRIES = 3
LLM_ATTRIBUTE_ERROR = -1

## Increase to increase the sample size the AI can draw from at the cost of increased runtime
ITEM_CHOICES = 10

## Days of the week in an array - should be the same as in the database*
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

## LLM Prompt - defined as global variables to enable testing
SYSTEM_TEMPLATE = "You are a health and nutrition expert planning meals for a customer based on their preferences. Use only the menu items provided under CSV CONTEXT."
PROMPT_TEMPLATE = """Choose a meal for a customer based on their preferences: {preferences}
Pay special attention that meal's dont include prohibited categories, like vegetarian meals dont have meat or halal meals dont have pork
Make sure that the item makes sense for {meal}.
Provide only the itm_id as output

CSV CONTEXT:
{context}"""

## Regex used for parsing a number from LLM Output
LLM_OUTPUT_MATCH = r"<\|start_of_role\|>assistant<\|end_of_role\|>(\d+)<\|end_of_text\|>"

## Preset Meal times - In the future, times will be user-provided
BREAKFAST_TIME = 1000
LUNCH_TIME = 1400
DINNER_TIME = 2000


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
    except:
        raise ValueError(
            "Unable to parse date string. Ensure it is formatted properly as to YYYY-MM-DD format"
        )
    next_day = date + datetime.timedelta(days=1)
    return next_day.strftime(r"%Y-%m-%d"), DAYS_OF_WEEK[date.weekday()]


def format_llm_output(output: str) -> int:
    """
    Grabs the LLM output and extracts the item ID from it

    Args:
        output (str): The output from the llm_toolkit LLM

    Returns:
        int: The item ID extracted from the LLM output

    Raises:
        ValueError: if the LLM output does not match the expected format or if multiple matches are found
    """
    match = LLM_OUTPUT_MATCH
    result = 0
    try:
        result = int(re.search(match, output).group(1))
    except AttributeError:
        return LLM_ATTRIBUTE_ERROR
    try:
        print(re.search(match, output).group(2))
        raise ValueError(
            "Injection attack may have gotten through. There should not be multiple matches for LLM output."
        )
    except Exception:
        None
    return result


def limit_scope(items: pd.DataFrame, num_choices: int) -> List[int]:
    """
    Limits the number of items to ITEM_CHOICES by randomly selecting items if necessary

    Args:
        items (pd.DataFrame): The DataFrame containing the items
        num_choices (int): The maximum number of choices to return

    Returns:
        List[int]: The list of item_ids of the selected items
    """
    num_items = items.shape[0]
    choices = range(num_items)
    if num_items > num_choices:
        choices = random.sample(choices, num_choices)
    return choices


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


class MenuGenerator:
    """
    MenuGenerator class that uses an LLM to generate menu items based on user preferences and restrictions
    """

    def __init__(self, tokens: int = 500, *, database_path: str):
        """
        Initializes the MenuGenerator with menu items and restaurants from the database and initializes
        the local LLM.

        Args:
            tokens (int): The number of tokens to use for the LLM generation
            database_path (str): The SQLite database to read the catalog from.
        """
        conn = connect(database_path)
        conn.row_factory = None  # pandas expects plain tuples
        try:
            catalog = pd.read_sql_query("SELECT itm_id, price FROM MenuItem", conn)
            self.item_prices = dict(zip(catalog.itm_id, catalog.price))
            self.menu_items = pd.read_sql_query("SELECT * FROM MenuItem WHERE instock == 1", conn)
            self.restaurants = pd.read_sql_query(
                'SELECT rtr_id, hours FROM Restaurant WHERE status=="Open"', conn
            )
        finally:
            conn.close()

        self.tokens = tokens
        self._generator = None

    @property
    def generator(self):
        """Load the model only after a feasible set of meals has been found."""
        if self._generator is None:
            self._generator = llm_toolkit.LLM(tokens=self.tokens)
        return self._generator

    @generator.setter
    def generator(self, value):
        self._generator = value

    def _eligible_candidates(
        self, allergens, weekday, order_time, max_price_cents=None, preferences=None
    ):
        """
        Filter stock, open restaurants, allergens and required diets; rank valid prices
        cheapest first.

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

    def _check_pick(self, itm_id, preferences, allergens, weekday, order_time):
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
                # self.restaurants holds only restaurants whose status is Open
                "restaurant_status": None if restaurant.empty else "Open",
                "hours": None if restaurant.empty else restaurant.iloc[0]["hours"],
            }
        rejection = item_rejection(item, allergens, preferences, weekday, order_time)
        if rejection:
            raise PlanRuleError(f"Chosen item {itm_id} broke a plan rule: {rejection[1]}")

    def __get_context(
        self,
        allergens: str,
        weekday: str,
        order_time: int,
        num_choices: int,
        candidates=None,
        preferences: str = None,
    ) -> str:
        """
        Generates the context block for the LLM based on the provided allergens, date, and order time

        Args:
            allergens (str): A comma-separated string of allergens to filter out
            weekday (str): The day of the week (e.g., "Mon", "Tue", etc.)
            order_time (int): The time the meal is typically ordered at in HHMM format (in 24H time)
            num_choices (int): The maximum number of choices to provide in the context
            item_ids (List[int]): The list of item_ids passed - used for checking validity

        Returns:
            str: The context block for the LLM in CSV format
        """
        start = time.time()

        if candidates is None:
            combined = self._eligible_candidates(
                allergens, weekday, order_time, preferences=preferences
            )
            choices = limit_scope(combined, num_choices)
        else:
            # Budgeted generation always exposes the cheapest ranked options first.
            combined = candidates.head(num_choices)
            choices = range(len(combined))

        context_data = "item_id,name,description,price,calories\n"

        ## Create the context data with the chosen items
        item_ids = []
        for x in choices:
            row = combined.iloc[x]
            context_data += f"{row['itm_id']},{row['name']},{row['description']},{row['price']},{row['calories']}\n"
            item_ids.append(row["itm_id"])

        end = time.time()
        print("Context block generated in %.4f seconds" % (end - start))
        return context_data, item_ids

    def __pick_menu_item(
        self, preferences: str, allergens: str, weekday: str, meal_number: int, candidates=None
    ) -> int:
        """
        Picks a menu item based on user preferences, allergens, date, and meal number

        Args:
            preferences (str): A comma-separated string of user preferences
            allergens (str): A comma-separated string of allergens to filter out
            weekday (str): The day of the week (e.g., "Mon", "Tue", etc.)
            meal_number (int): The meal number (1 for breakfast, 2 for lunch, 3 for dinner)

        Returns:
            int: The item_id of the selected menu item
        """
        meal, order_time = get_meal_and_order_time(meal_number)

        num_choices = ITEM_CHOICES

        ## Tries to get output from LLM a number of times, increasing the number of options every time
        for x in range(MAX_LLM_TRIES):
            context, item_ids = self.__get_context(
                allergens, weekday, order_time, num_choices, candidates, preferences
            )
            if not item_ids:
                raise RuntimeError("No eligible menu items are available for this meal.")

            ## Gets the prompt
            system = SYSTEM_TEMPLATE
            prompt = PROMPT_TEMPLATE

            ## Initializes variables in prompt
            prompt = prompt.replace("{preferences}", preferences)
            prompt = prompt.replace("{context}", context)
            prompt = prompt.replace("{meal}", meal)

            llm_output = self.generator.generate(system, prompt)
            output = format_llm_output(llm_output)
            if output > 0 and output in item_ids:
                self._check_pick(output, preferences, allergens, weekday, order_time)
                return output
            ## If failed, try increasing the number of choices
            num_choices += ITEM_CHOICES
        raise RuntimeError(
            f"""LLM has failed {MAX_LLM_TRIES} times to generate a meal. This may be a critical error, a lack of options, or a bad prompt. 
LLM output:
{llm_output}"""
        )

    def _update_budgeted_menu(
        self, menu, preferences, allergens, date, meal_numbers, number_of_days, cap_cents
    ):
        """Reserve cheapest remaining meals before offering any budgeted choice."""
        cap_cents = item_price_cents(cap_cents)
        start = datetime.date.fromisoformat(date)
        days = [(start + datetime.timedelta(days=i)).isoformat() for i in range(number_of_days)]
        weeks = list(dict.fromkeys(week_start(day) for day in days))
        totals = weekly_item_totals(menu, self.item_prices, weeks)
        occupied = {(day, meal) for day, _, meal in plan_entries(menu)}
        slots = []
        minimum_remaining = dict.fromkeys(weeks, 0)
        for day in days:
            weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(day).weekday()]
            for meal in dict.fromkeys(meal_numbers):
                _, order_time = get_meal_and_order_time(meal)
                if (day, meal) in occupied:
                    continue
                candidates = self._eligible_candidates(
                    allergens, weekday, order_time, preferences=preferences
                )
                if candidates.empty:
                    raise BudgetExceededError(f"No eligible meals are available for {day}.")
                minimum = int(candidates.price_cents.min())
                week = week_start(day)
                minimum_remaining[week] += minimum
                slots.append((day, weekday, meal, week, candidates, minimum))

        # Check every affected week before generating anything; never save a partial plan.
        for week in weeks:
            required = totals[week] + minimum_remaining[week]
            if required > cap_cents:
                raise BudgetExceededError(
                    f"Week of {week} needs at least ${required / 100:.2f} in items; "
                    f"the weekly cap is ${cap_cents / 100:.2f}. "
                    "Raise the cap or request fewer meals."
                )

        updated = menu or ""
        for day, weekday, meal, week, candidates, minimum in slots:
            minimum_remaining[week] -= minimum
            available = cap_cents - totals[week] - minimum_remaining[week]
            affordable = candidates[candidates.price_cents <= available]
            item = self.__pick_menu_item(preferences, allergens, weekday, meal, affordable)
            totals[week] += item_price_cents(self.item_prices[item])
            updated = f"{updated},[{day},{item},{meal}]" if updated else f"[{day},{item},{meal}]"
        self.weekly_totals_cents = totals
        self.item_total_cents = sum(totals.values())
        return updated

    def update_menu(
        self,
        menu: str,
        preferences: str,
        allergens: str,
        date: str,
        meal_numbers: List[int],
        number_of_days: int = 1,
        weekly_cap_cents: int = None,
    ) -> str:
        """
        Updates the menu string with a new menu item based on user preferences, allergens, date, and meal number

        Args:
            menu (str): The current menu string (can be empty or None)
            preferences (str): A comma-separated string of user preferences
            allergens (str): A comma-separated string of allergens to avoid
            date (str): The date string in YYYY-MM-DD format
            meal_number (List[int]): The list of meal numbers to generate (1 for breakfast, 2 for lunch, 3 for dinner). e.g. [1,2,3]
            number_of_days (int): The number of days to generate meals for, past the {date} specified
            weekly_cap_cents (int | None): Item-price limit per Monday–Sunday week,
                counting all existing meals in that week. None leaves generation uncapped.

        Returns:
            str: The updated menu string
        """
        if weekly_cap_cents is not None:
            return self._update_budgeted_menu(
                menu, preferences, allergens, date, meal_numbers, number_of_days, weekly_cap_cents
            )
        next_date, current_weekday = get_weekday_and_increment(date)
        for x in range(number_of_days):
            for meal_number in meal_numbers:
                if menu is None or len(menu) < 1:
                    itm_id = self.__pick_menu_item(
                        preferences, allergens, current_weekday, meal_number
                    )
                    menu = f"[{date},{itm_id},{meal_number}]"
                elif re.search(rf"\[{date},\d+,{meal_number}\]", menu) is None:
                    print(rf"\[{date},\d+,{meal_number}\]")
                    print(menu)
                    itm_id = self.__pick_menu_item(
                        preferences, allergens, current_weekday, meal_number
                    )
                    menu = f"{menu},[{date},{itm_id},{meal_number}]"
            date = next_date
            next_date, current_weekday = get_weekday_and_increment(date)
        return menu
