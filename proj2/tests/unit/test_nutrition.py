"""
Unit tests for daily calorie targets (proj2/nutrition.py) and how the planner aims for
them (MenuGenerator.update_menu with calorie_target)
"""

import json
import math

import pandas as pd
import pytest

from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator, NoEligibleMealError
from proj2.meal_budget import plan_entries
from proj2.nutrition import (
    REACH_SLACK,
    CalorieTarget,
    NutritionTargetError,
    calorie_notice,
    describe_target,
    item_calories,
    parse_calorie_target,
)

MONDAY = "2026-11-16"
ALL_DAY = json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK})

# ---------------------------------------------------------------- the target


class TestParse:
    def test_blank_bounds_mean_no_target(self):
        assert parse_calorie_target(None, None) is None
        assert parse_calorie_target("", "  ") is None

    def test_both_bounds(self):
        assert parse_calorie_target("1800", 2200) == CalorieTarget(1800, 2200)

    def test_one_bound_leaves_the_other_open(self):
        assert parse_calorie_target("1800", "") == CalorieTarget(1800, math.inf)
        assert parse_calorie_target(None, "2200") == CalorieTarget(0, 2200)

    @pytest.mark.parametrize("value", ["0", "-5", "abc", "1800.5", "10001", "nan", "inf"])
    def test_rejects_values_that_are_not_a_whole_number_in_range(self, value):
        with pytest.raises(NutritionTargetError, match="whole number from 1 to 10000"):
            parse_calorie_target(value, None)

    def test_rejects_min_above_max(self):
        with pytest.raises(NutritionTargetError, match="minimum cannot be more"):
            parse_calorie_target("2500", "2000")


class TestMiss:
    target = CalorieTarget(2000, 2500)

    @pytest.mark.parametrize("total", [2000, 2250, 2500])
    def test_inside_the_range_is_no_miss(self, total):
        assert self.target.miss(total) == 0.0

    def test_miss_is_relative_to_the_bound_missed(self):
        assert self.target.miss(1800) == pytest.approx(0.1)
        assert self.target.miss(2750) == pytest.approx(0.1)

    def test_open_bounds_never_miss_on_that_side(self):
        assert CalorieTarget(0, 2000).miss(10) == 0.0
        assert CalorieTarget(1500, math.inf).miss(9000) == 0.0


class TestWithinReach:
    def test_reachable_target_is_unchanged(self):
        target = CalorieTarget(1800, 2200)
        assert target.within_reach(1200, 3000) == target

    def test_unreachable_minimum_aims_near_the_most_the_day_can_reach(self):
        aim = CalorieTarget(2500, 3000).within_reach(900, 2000)
        assert aim == CalorieTarget(2000 * (1 - REACH_SLACK), 3000)

    def test_unreachable_maximum_aims_near_the_least_the_day_can_reach(self):
        aim = CalorieTarget(0, 1000).within_reach(1500, 2600)
        assert aim == CalorieTarget(0, 1500 * (1 + REACH_SLACK))


@pytest.mark.parametrize(
    "value, calories",
    [(550, 550), ("720", 720), (99.6, 100), (None, None), (float("nan"), None), ("x", None)],
)
def test_item_calories(value, calories):
    assert item_calories(value) == calories


def test_negative_calories_are_unknown():
    assert item_calories(-10) is None


@pytest.mark.parametrize(
    "target, text",
    [
        (CalorieTarget(1800, 2200), "1,800–2,200 kcal"),
        (CalorieTarget(1800, math.inf), "at least 1,800 kcal"),
        (CalorieTarget(0, 2200), "at most 2,200 kcal"),
    ],
)
def test_describe_target(target, text):
    assert describe_target(target) == text


def test_calorie_notice_names_the_days_outside():
    report = {
        "target": {"min": 1800, "max": 2200},
        "days": [{"date": MONDAY, "calories": 1500, "miss": 0.17}, {"miss": 0.0}],
        "days_outside": 1,
    }
    notice = calorie_notice(report)
    assert notice.startswith(
        "1 of 2 planned days falls outside your daily calorie target (1,800–2,200 kcal)."
    )
    assert calorie_notice(dict(report, days_outside=0)) is None
    assert calorie_notice(None) is None


# ---------------------------------------------------------------- the planner


def make_generator(items):
    """A MenuGenerator over an in-memory catalog: one open restaurant, every item a main."""
    gen = MenuGenerator.__new__(MenuGenerator)
    rows = []
    for itm_id, item in enumerate(items, start=1):
        row = {
            "itm_id": itm_id,
            "rtr_id": 1,
            "name": f"Meal {itm_id}",
            "price": 500,
            "calories": 500,
            "instock": 1,
            "allergens": "",
            "course": "main",
        }
        row.update(item)
        rows.append(row)
    gen.menu_items = pd.DataFrame(rows)
    gen.catalog = gen.menu_items.copy()
    gen.restaurants = pd.DataFrame([{"rtr_id": 1, "hours": ALL_DAY}])
    gen.item_prices = dict(zip(gen.menu_items.itm_id, gen.menu_items.price))
    gen.variety = None
    return gen


## Ten mains from 300 to 1200 kcal, each a different protein so variety has a say
PROTEINS = ["chicken", "beef", "tofu", "fish", "legumes", "egg", "lamb", "turkey", "pork", "dairy"]
CATALOG = [{"calories": 300 + 100 * i, "protein": protein} for i, protein in enumerate(PROTEINS)]


def day_totals(gen, menu):
    calories = dict(zip(gen.catalog.itm_id, gen.catalog.calories))
    totals = {}
    for day, itm_id, _ in plan_entries(menu):
        totals[day] = totals.get(day, 0) + calories[itm_id]
    return totals


def plan(gen, target=None, menu="", days=5, meals=(1, 2, 3)):
    return gen.update_menu(
        menu, "", "", MONDAY, list(meals), number_of_days=days, calorie_target=target
    )


@pytest.mark.parametrize("low, high", [(1200, 1400), (1800, 2000), (2600, 2800)])
def test_every_reachable_day_lands_inside_the_target(low, high):
    gen = make_generator(CATALOG)
    menu = plan(gen, CalorieTarget(low, high))
    assert all(low <= total <= high for total in day_totals(gen, menu).values())
    report = gen.calorie_report()
    assert report["days_outside"] == 0
    assert report["target"] == {"min": low, "max": high}


def test_a_target_every_day_already_meets_changes_nothing():
    untargeted = plan(make_generator(CATALOG))
    wide = plan(make_generator(CATALOG), CalorieTarget(1, 10000))
    assert wide == untargeted


def test_no_target_means_no_report():
    gen = make_generator(CATALOG)
    plan(gen)
    assert gen.calorie_report() is None


def test_meals_already_in_the_plan_count_toward_the_day():
    gen = make_generator(CATALOG)
    heavy_breakfast = 10  # 1,200 kcal
    menu = plan(gen, CalorieTarget(1700, 1900), menu=f"[{MONDAY},{heavy_breakfast},1]", days=1)
    assert 1700 <= day_totals(gen, menu)[MONDAY] <= 1900


def test_items_without_calories_are_not_planned_with_a_target():
    items = CATALOG + [{"calories": None, "protein": "goat"}]
    unknown = len(items)
    gen = make_generator(items)
    menu = plan(gen, CalorieTarget(1, 10000), days=7)
    assert unknown not in {itm_id for _, itm_id, _ in plan_entries(menu)}


def test_a_slot_with_no_calorie_values_is_a_clear_error():
    gen = make_generator([{"calories": None}, {"calories": float("nan")}])
    with pytest.raises(NoEligibleMealError, match="no item that fits lists its calories"):
        plan(gen, CalorieTarget(1800, 2200), days=1)


def test_an_unreachable_target_still_plans_and_reports_every_day():
    gen = make_generator(CATALOG)
    menu = plan(gen, CalorieTarget(5000, 6000), days=3)
    totals = day_totals(gen, menu)
    most = 3 * 1200
    # Each day comes close to the most it can reach (REACH_SLACK is its aim; the
    # planner may give up a little of it rather than repeat one dish all day)
    assert all(total >= most * 0.9 for total in totals.values())
    assert all(total < most for total in totals.values())
    report = gen.calorie_report()
    assert report["days_outside"] == 3
    assert [day["calories"] for day in report["days"]] == [totals[d] for d in sorted(totals)]


def test_report_has_no_total_for_a_day_with_an_unknown_meal():
    gen = make_generator(CATALOG + [{"calories": None}])
    unknown = len(CATALOG) + 1
    plan(gen, CalorieTarget(1, 10000), menu=f"[{MONDAY},{unknown},1]", days=1, meals=(2, 3))
    assert gen.calorie_report()["days"] == [{"date": MONDAY, "calories": None, "miss": None}]
