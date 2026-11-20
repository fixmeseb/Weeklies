"""
Daily nutrition targets for meal planning (milestone P3-M3, phase 1: calories).

A target is a daily range, such as 1,800-2,200 kcal, or one bound of it. It is a soft
goal: the planner prefers meals that keep each day inside the range and, among those,
still picks for variety (proj2.menu_generation). A day can miss the range when the
catalog cannot reach it; the plan then reports how far each day is off rather than
refusing, unlike the weekly price cap, which is a hard limit.

Calories come from MenuItem.calories. An item without a calorie value is not planned
while a target is set, the same way a missing price is never treated as free.
"""

import math
from dataclasses import dataclass

## Largest daily calorie bound accepted; anything above is a typo, not a goal
MAX_DAILY_CALORIES = 10000

## How much missing the target counts against a slot, per unit of relative miss.
## Variety scores run 0-1, so at 30 a day just 1% outside the range costs 0.3: the
## planner keeps every day it can inside the range and uses variety to choose among
## the meals that do. (At 1, it let reachable days sit 1-2% short to vary the menu.)
CALORIE_WEIGHT = 30.0

## When a day cannot reach the target at all, it aims to come within this share of the
## closest total it can reach (CalorieTarget.within_reach), rather than repeating the
## single most (or least) caloric meals to chase it.
REACH_SLACK = 0.05


class NutritionTargetError(ValueError):
    """A nutrition target from a request is malformed."""


@dataclass(frozen=True)
class CalorieTarget:
    """A daily calorie range; low or high may be open (0 or infinity)."""

    low: float = 0
    high: float = math.inf

    def miss(self, total: float) -> float:
        """
        How far a day's calories fall outside the range, relative to the bound missed

        Args:
            total (float): The day's calories

        Returns:
            float: 0.0 inside the range; otherwise the shortfall over low or the excess
                over high, as a share of that bound (0.1 = 10% off)
        """
        if total < self.low:
            return (self.low - total) / self.low
        if total > self.high:
            return (total - self.high) / self.high
        return 0.0

    def within_reach(self, day_min: float, day_max: float) -> "CalorieTarget":
        """
        The range to aim for on a day whose meals can total only day_min to day_max

        A reachable target is returned unchanged. When the menu cannot reach a bound,
        chasing it exactly would mean the same highest- (or lowest-) calorie dishes
        every day, so the day instead aims to come within REACH_SLACK of the closest
        total it can reach and keeps its variety.

        Args:
            day_min (float): The lowest calorie total the day's meals can add up to
            day_max (float): The highest calorie total the day's meals can add up to

        Returns:
            CalorieTarget: The range to aim for
        """
        low, high = self.low, self.high
        if low > day_max:
            low = day_max * (1 - REACH_SLACK)
        if high < day_min:
            high = day_min * (1 + REACH_SLACK)
        return CalorieTarget(low=low, high=high)

    def as_json(self) -> dict:
        return {
            "min": None if self.low == 0 else int(self.low),
            "max": None if math.isinf(self.high) else int(self.high),
        }


def _bound(value, name: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        number = math.nan
    if not number.is_integer() or not 0 < number <= MAX_DAILY_CALORIES:
        raise NutritionTargetError(
            f"Daily calorie {name} must be a whole number from 1 to {MAX_DAILY_CALORIES}."
        )
    return int(number)


def parse_calorie_target(low, high):
    """
    Reads an optional daily calorie range from a request

    Args:
        low (str | int | None): The daily minimum; blank or None for no minimum
        high (str | int | None): The daily maximum; blank or None for no maximum

    Returns:
        CalorieTarget | None: The target, or None when neither bound is given

    Raises:
        NutritionTargetError: if a bound is not a whole number in range, or min > max
    """
    low, high = _bound(low, "minimum"), _bound(high, "maximum")
    if low is None and high is None:
        return None
    if low is not None and high is not None and low > high:
        raise NutritionTargetError("Daily calorie minimum cannot be more than the maximum.")
    return CalorieTarget(low=low or 0, high=math.inf if high is None else high)


def item_calories(value):
    """
    One item's calories, or None when it has no usable value

    Args:
        value: A MenuItem.calories cell (int, float, str, None or NaN)

    Returns:
        int | None: The calories, or None for a missing, negative or non-numeric value
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number < 0:
        return None
    return int(round(number))


def describe_target(target: CalorieTarget) -> str:
    """A target as people write it: "1,800–2,200 kcal", "at least 1,800 kcal", ..."""
    data = target.as_json()
    if data["min"] is not None and data["max"] is not None:
        return f"{data['min']:,}–{data['max']:,} kcal"
    if data["min"] is not None:
        return f"at least {data['min']:,} kcal"
    return f"at most {data['max']:,} kcal"


def calorie_notice(report):
    """
    One sentence for the calendar when planned days miss the calorie target

    Args:
        report (dict | None): MenuGenerator.calorie_report()

    Returns:
        str | None: The notice, or None when there is no target or every day is in range
    """
    if not report or not report["days_outside"]:
        return None
    target = CalorieTarget(
        low=report["target"]["min"] or 0,
        high=math.inf if report["target"]["max"] is None else report["target"]["max"],
    )
    outside = report["days_outside"]
    total = len(report["days"])
    return (
        f"{outside} of {total} planned day{'s' if total != 1 else ''} "
        f"{'falls' if outside == 1 else 'fall'} outside your daily calorie target "
        f"({describe_target(target)}). "
        "With your diet, allergies and budget, the planner could not reach it on "
        f"{'that day' if outside == 1 else 'those days'}, so it planned as close as it could."
    )
