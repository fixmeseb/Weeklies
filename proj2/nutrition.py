"""
Daily nutrition targets for meal planning (milestone P3-M3).

A target is a daily range for one nutrient, such as 1,800-2,200 kcal or at least 120 g
of protein; a request may set several (NUTRIENTS). Targets are soft goals: the planner
prefers meals that keep each day inside every range and, among those, still picks for
variety (proj2.menu_generation). A day can miss a range when the catalog cannot reach
it; the plan then reports how far each day is off rather than refusing, unlike the
weekly price cap, which is a hard limit.

Values come from MenuItem columns: calories as listed, and protein, carbs, fat and
sodium as estimated from USDA data (estimate_macros below). An item without a value for
a targeted nutrient is not planned, the same way a missing price is never treated as
free.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Nutrient:
    """One nutrient a target can be set on."""

    column: str  # MenuItem column holding the per-serving amount
    label: str  # as shown to people
    unit: str
    field: str  # request fields are <field>_min and <field>_max
    largest: int  # largest daily bound accepted; anything above is a typo, not a goal


## Every nutrient a target can be set on, by MenuItem column, in display order
NUTRIENTS = {
    n.column: n
    for n in (
        Nutrient("calories", "calories", "kcal", "calorie", 10000),
        Nutrient("protein_g", "protein", "g", "protein", 1000),
        Nutrient("carbs_g", "carbs", "g", "carbs", 2000),
        Nutrient("fat_g", "fat", "g", "fat", 1000),
        Nutrient("sodium_mg", "sodium", "mg", "sodium", 20000),
    )
}

## How much missing a target counts against a slot, per unit of relative miss, summed
## over the targeted nutrients. Variety scores run 0-1, so at 30 a day just 1% outside
## a range costs 0.3: the planner keeps every day it can inside the ranges and uses
## variety to choose among the meals that do. (At 1, it let reachable days sit 1-2%
## short to vary the menu.)
TARGET_WEIGHT = 30.0

## When a day cannot reach a target at all, it aims to come within this share of the
## closest total it can reach (DailyRange.within_reach), rather than repeating the
## single richest (or leanest) meals to chase it.
REACH_SLACK = 0.05


## With strict targets, a day that misses a range after planning is searched exactly
## over this many of each slot's most varied candidates (25 per slot is at most 15,625
## combinations for a three-meal day)
REPAIR_CANDIDATES = 25


class NutritionTargetError(ValueError):
    """A nutrition target from a request is malformed."""


class TargetsUnreachableError(ValueError):
    """With strict targets, no meals the user may have keep a day inside every range."""


@dataclass(frozen=True)
class DailyRange:
    """A daily range for one nutrient; low or high may be open (0 or infinity)."""

    low: float = 0
    high: float = math.inf

    def miss(self, total: float) -> float:
        """
        How far a day's total falls outside the range, relative to the bound missed

        Args:
            total (float): The day's total

        Returns:
            float: 0.0 inside the range; otherwise the shortfall over low or the excess
                over high, as a share of that bound (0.1 = 10% off)
        """
        if total < self.low:
            return (self.low - total) / self.low
        if total > self.high:
            return (total - self.high) / self.high
        return 0.0

    def within_reach(self, day_min: float, day_max: float) -> "DailyRange":
        """
        The range to aim for on a day whose meals can total only day_min to day_max

        A reachable range is returned unchanged. When the menu cannot reach a bound,
        chasing it exactly would mean the same richest (or leanest) dishes every day,
        so the day instead aims to come within REACH_SLACK of the closest total it can
        reach and keeps its variety.

        Args:
            day_min (float): The lowest total the day's meals can add up to
            day_max (float): The highest total the day's meals can add up to

        Returns:
            DailyRange: The range to aim for
        """
        low, high = self.low, self.high
        if low > day_max:
            low = day_max * (1 - REACH_SLACK)
        if high < day_min:
            high = day_min * (1 + REACH_SLACK)
        return DailyRange(low=low, high=high)

    def as_json(self) -> dict:
        return {
            "min": None if self.low == 0 else int(self.low),
            "max": None if math.isinf(self.high) else int(self.high),
        }


def _bound(value, nutrient: Nutrient, name: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        number = math.nan
    if not number.is_integer() or not 0 < number <= nutrient.largest:
        raise NutritionTargetError(
            f"Daily {nutrient.label} {name} must be a whole number from 1 to "
            f"{nutrient.largest:,} {nutrient.unit}."
        )
    return int(number)


def parse_range(nutrient: Nutrient, low, high):
    """
    Reads an optional daily range for one nutrient

    Args:
        nutrient (Nutrient): The nutrient (NUTRIENTS)
        low (str | int | None): The daily minimum; blank or None for no minimum
        high (str | int | None): The daily maximum; blank or None for no maximum

    Returns:
        DailyRange | None: The range, or None when neither bound is given

    Raises:
        NutritionTargetError: if a bound is not a whole number in range, or min > max
    """
    low, high = _bound(low, nutrient, "minimum"), _bound(high, nutrient, "maximum")
    if low is None and high is None:
        return None
    if low is not None and high is not None and low > high:
        raise NutritionTargetError(
            f"Daily {nutrient.label} minimum cannot be more than the maximum."
        )
    return DailyRange(low=low or 0, high=math.inf if high is None else high)


def parse_targets(fields) -> dict:
    """
    Reads every daily target from a request's fields

    Args:
        fields (Mapping): Request fields; <field>_min and <field>_max for each nutrient,
            e.g. calorie_min, protein_min, sodium_max

    Returns:
        dict: MenuItem column -> DailyRange for each nutrient with a bound; empty if none

    Raises:
        NutritionTargetError: for the first malformed bound
    """
    targets = {}
    for column, nutrient in NUTRIENTS.items():
        found = parse_range(
            nutrient, fields.get(f"{nutrient.field}_min"), fields.get(f"{nutrient.field}_max")
        )
        if found is not None:
            targets[column] = found
    return targets


def item_amount(value):
    """
    One item's amount of a nutrient, or None when it has no usable value

    Args:
        value: A MenuItem cell (int, float, str, None or NaN)

    Returns:
        float | None: The amount, or None for a missing, negative or non-numeric value
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number < 0:
        return None
    return number


def describe_range(column: str, target: DailyRange) -> str:
    """A target as people write it: "calories 1,800–2,200 kcal", "protein at least 120 g"."""
    nutrient = NUTRIENTS[column]
    data = target.as_json()
    unit = nutrient.unit
    if data["min"] is not None and data["max"] is not None:
        bounds = f"{data['min']:,}–{data['max']:,} {unit}"
    elif data["min"] is not None:
        bounds = f"at least {data['min']:,} {unit}"
    else:
        bounds = f"at most {data['max']:,} {unit}"
    return f"{nutrient.label} {bounds}"


def targets_from_json(data: dict) -> dict:
    """DailyRange per column from a report's "targets" ({column: {"min", "max"}})."""
    return {
        column: DailyRange(
            low=bounds["min"] or 0, high=math.inf if bounds["max"] is None else bounds["max"]
        )
        for column, bounds in data.items()
    }


def nutrition_notice(report):
    """
    One sentence for the calendar when planned days miss a nutrition target

    Args:
        report (dict | None): MenuGenerator.nutrition_report()

    Returns:
        str | None: The notice, or None when there is no target or every day is in range
    """
    if not report or not report["days_outside"]:
        return None
    targets = targets_from_json(report["targets"])
    outside = report["days_outside"]
    total = len(report["days"])
    missed = "; ".join(
        f"{describe_range(column, targets[column])} on {count} day{'s' if count != 1 else ''}"
        for column, count in report["outside_by_nutrient"].items()
        if count
    )
    return (
        f"{outside} of {total} planned day{'s' if total != 1 else ''} "
        f"{'misses' if outside == 1 else 'miss'} your daily targets ({missed}). "
        "With your diet, allergies and budget, the planner could not reach them on "
        f"{'that day' if outside == 1 else 'those days'}, so it planned as close as it could."
    )


## The macro fields estimated for each menu item, as MenuItem columns
MACRO_FIELDS = ("protein_g", "carbs_g", "fat_g", "sodium_mg")


def estimate_macros(calories, parts, foods) -> dict:
    """
    Estimates an item's protein, carbs, fat and sodium from USDA foods

    Each part covers a share of the item's calories; its food's per-100 g nutrients are
    scaled to that many calories. The item's own calorie count is kept, and USDA gives
    the mix of nutrients.

    Args:
        calories (float): The item's calories (MenuItem.calories)
        parts (Iterable[Tuple[int, float]]): (fdc_id, share of calories); shares add to 1
        foods (Mapping[int, dict]): fdc_id -> per-100 g values (proj2.fndds_foods.FOODS)

    Returns:
        dict: protein_g, carbs_g, fat_g (rounded to 0.1) and sodium_mg (whole mg)

    Raises:
        ValueError: if the shares do not add up to 1 or a food has no calories
    """
    parts = list(parts)
    if abs(sum(share for _, share in parts) - 1) > 1e-6:
        raise ValueError("The shares of an item's calories must add up to 1.")
    totals = dict.fromkeys(MACRO_FIELDS, 0.0)
    for fdc_id, share in parts:
        food = foods[fdc_id]
        if food["kcal"] <= 0:
            raise ValueError(f"{food['description']} has no calories to scale by.")
        hundred_grams = calories * share / food["kcal"]
        for field in MACRO_FIELDS:
            totals[field] += food[field] * hundred_grams
    return {
        "protein_g": round(totals["protein_g"], 1),
        "carbs_g": round(totals["carbs_g"], 1),
        "fat_g": round(totals["fat_g"], 1),
        "sodium_mg": int(round(totals["sodium_mg"])),
    }


def describe_source(parts, foods, release) -> str:
    """What an estimate came from, for MenuItem.nutrition_source."""
    named = "; ".join(
        f"{foods[fdc_id]['description']} (FDC {fdc_id}, {share:.0%})" for fdc_id, share in parts
    )
    return f"Estimated from USDA FoodData Central FNDDS {release}: {named}"
