"""
Unit tests for daily nutrition targets (proj2/nutrition.py) and how the planner aims for
them (MenuGenerator.update_menu with targets)
"""

import json
import math

import pandas as pd
import pytest

from proj2.meal_budget import plan_entries
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator, NoEligibleMealError
from proj2.nutrition import (
    NUTRIENTS,
    REACH_SLACK,
    DailyRange,
    NutritionTargetError,
    TargetsUnreachableError,
    describe_range,
    item_amount,
    nutrition_notice,
    parse_range,
    parse_targets,
)

MONDAY = "2026-11-16"
ALL_DAY = json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK})
CALORIES = NUTRIENTS["calories"]

# ---------------------------------------------------------------- the targets


class TestParseRange:
    def test_blank_bounds_mean_no_target(self):
        assert parse_range(CALORIES, None, None) is None
        assert parse_range(CALORIES, "", "  ") is None

    def test_both_bounds(self):
        assert parse_range(CALORIES, "1800", 2200) == DailyRange(1800, 2200)

    def test_one_bound_leaves_the_other_open(self):
        assert parse_range(CALORIES, "1800", "") == DailyRange(1800, math.inf)
        assert parse_range(CALORIES, None, "2200") == DailyRange(0, 2200)

    @pytest.mark.parametrize("value", ["0", "-5", "abc", "1800.5", "10001", "nan", "inf"])
    def test_rejects_values_that_are_not_a_whole_number_in_range(self, value):
        with pytest.raises(NutritionTargetError, match="whole number from 1 to 10,000 kcal"):
            parse_range(CALORIES, value, None)

    def test_each_nutrient_has_its_own_limit_and_name(self):
        with pytest.raises(NutritionTargetError, match="protein maximum .* 1 to 1,000 g"):
            parse_range(NUTRIENTS["protein_g"], None, "1500")

    def test_rejects_min_above_max(self):
        with pytest.raises(NutritionTargetError, match="calories minimum cannot be more"):
            parse_range(CALORIES, "2500", "2000")


class TestParseTargets:
    def test_reads_every_nutrient_with_a_bound(self):
        fields = {"calorie_min": "1800", "protein_min": "120", "sodium_max": "2300", "fat_min": ""}
        assert parse_targets(fields) == {
            "calories": DailyRange(1800, math.inf),
            "protein_g": DailyRange(120, math.inf),
            "sodium_mg": DailyRange(0, 2300),
        }

    def test_no_bounds_is_no_targets(self):
        assert parse_targets({"weekly_cap": "100"}) == {}

    def test_a_bad_bound_names_its_nutrient(self):
        with pytest.raises(NutritionTargetError, match="Daily carbs minimum"):
            parse_targets({"carbs_min": "lots"})


class TestMiss:
    target = DailyRange(2000, 2500)

    @pytest.mark.parametrize("total", [2000, 2250, 2500])
    def test_inside_the_range_is_no_miss(self, total):
        assert self.target.miss(total) == 0.0

    def test_miss_is_relative_to_the_bound_missed(self):
        assert self.target.miss(1800) == pytest.approx(0.1)
        assert self.target.miss(2750) == pytest.approx(0.1)

    def test_open_bounds_never_miss_on_that_side(self):
        assert DailyRange(0, 2000).miss(10) == 0.0
        assert DailyRange(1500, math.inf).miss(9000) == 0.0


class TestWithinReach:
    def test_reachable_target_is_unchanged(self):
        target = DailyRange(1800, 2200)
        assert target.within_reach(1200, 3000) == target

    def test_unreachable_minimum_aims_near_the_most_the_day_can_reach(self):
        aim = DailyRange(2500, 3000).within_reach(900, 2000)
        assert aim == DailyRange(2000 * (1 - REACH_SLACK), 3000)

    def test_unreachable_maximum_aims_near_the_least_the_day_can_reach(self):
        aim = DailyRange(0, 1000).within_reach(1500, 2600)
        assert aim == DailyRange(0, 1500 * (1 + REACH_SLACK))


@pytest.mark.parametrize(
    "value, amount",
    [(550, 550), ("720", 720), (32.1, 32.1), (None, None), (float("nan"), None), ("x", None)],
)
def test_item_amount(value, amount):
    assert item_amount(value) == amount


def test_negative_amounts_are_unknown():
    assert item_amount(-10) is None


@pytest.mark.parametrize(
    "column, target, text",
    [
        ("calories", DailyRange(1800, 2200), "calories 1,800–2,200 kcal"),
        ("protein_g", DailyRange(120, math.inf), "protein at least 120 g"),
        ("sodium_mg", DailyRange(0, 2300), "sodium at most 2,300 mg"),
    ],
)
def test_describe_range(column, target, text):
    assert describe_range(column, target) == text


def test_nutrition_notice_names_each_missed_target():
    report = {
        "targets": {
            "calories": {"min": 1800, "max": 2200},
            "sodium_mg": {"min": None, "max": 2300},
        },
        "days": [{"date": MONDAY}, {"date": "2026-11-17"}, {"date": "2026-11-18"}],
        "days_outside": 2,
        "outside_by_nutrient": {"calories": 0, "sodium_mg": 2},
    }
    assert nutrition_notice(report).startswith(
        "2 of 3 planned days miss your daily targets (sodium at most 2,300 mg on 2 days)."
    )
    assert nutrition_notice(dict(report, days_outside=0)) is None
    assert nutrition_notice(None) is None


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


## Ten mains from 300 to 1200 kcal, each a different protein so variety has a say.
## Protein grams fall as calories rise, so calories and protein pull different ways.
PROTEINS = ["chicken", "beef", "tofu", "fish", "legumes", "egg", "lamb", "turkey", "pork", "dairy"]
CATALOG = [
    {
        "calories": 300 + 100 * i,
        "protein": protein,
        "protein_g": 60 - 5 * i,
        "sodium_mg": 400 + 150 * i,
    }
    for i, protein in enumerate(PROTEINS)
]


def day_totals(gen, menu, column="calories"):
    amounts = dict(zip(gen.catalog.itm_id, gen.catalog[column]))
    totals = {}
    for day, itm_id, _ in plan_entries(menu):
        totals[day] = totals.get(day, 0) + amounts[itm_id]
    return totals


def plan(gen, targets=None, menu="", days=5, meals=(1, 2, 3)):
    return gen.update_menu(menu, "", "", MONDAY, list(meals), number_of_days=days, targets=targets)


@pytest.mark.parametrize("low, high", [(1200, 1400), (1800, 2000), (2600, 2800)])
def test_every_reachable_day_lands_inside_the_calorie_target(low, high):
    gen = make_generator(CATALOG)
    menu = plan(gen, {"calories": DailyRange(low, high)})
    assert all(low <= total <= high for total in day_totals(gen, menu).values())
    report = gen.nutrition_report()
    assert report["days_outside"] == 0
    assert report["targets"] == {"calories": {"min": low, "max": high}}


def test_several_targets_are_met_together():
    gen = make_generator(CATALOG)
    targets = {
        "calories": DailyRange(1800, 2200),
        "protein_g": DailyRange(110, math.inf),
        "sodium_mg": DailyRange(0, 3000),
    }
    menu = plan(gen, targets)
    for column, target in targets.items():
        assert all(target.miss(t) == 0 for t in day_totals(gen, menu, column).values()), column
    assert gen.nutrition_report()["outside_by_nutrient"] == dict.fromkeys(targets, 0)


def test_a_target_every_day_already_meets_changes_nothing():
    untargeted = plan(make_generator(CATALOG))
    wide = plan(make_generator(CATALOG), {"calories": DailyRange(1, 10000)})
    assert wide == untargeted


def test_no_targets_means_no_report():
    gen = make_generator(CATALOG)
    plan(gen)
    assert gen.nutrition_report() is None
    plan(gen, {})
    assert gen.nutrition_report() is None


def test_meals_already_in_the_plan_count_toward_the_day():
    gen = make_generator(CATALOG)
    heavy_breakfast = 10  # 1,200 kcal
    menu = plan(
        gen, {"calories": DailyRange(1700, 1900)}, menu=f"[{MONDAY},{heavy_breakfast},1]", days=1
    )
    assert 1700 <= day_totals(gen, menu)[MONDAY] <= 1900


def test_items_without_a_targeted_value_are_not_planned():
    items = CATALOG + [{"calories": 700, "protein_g": None, "protein": "goat"}]
    unknown = len(items)
    menu = plan(make_generator(items), {"protein_g": DailyRange(1, 1000)}, days=7)
    assert unknown not in {itm_id for _, itm_id, _ in plan_entries(menu)}
    # Without a protein target the same item can be planned
    menu = plan(make_generator(items), {"calories": DailyRange(1, 10000)}, days=7)
    assert unknown in {itm_id for _, itm_id, _ in plan_entries(menu)}


def test_a_slot_with_no_values_for_a_target_is_a_clear_error():
    gen = make_generator([{"protein_g": None}, {"protein_g": float("nan")}])
    with pytest.raises(NoEligibleMealError, match="no item that fits lists its protein"):
        plan(gen, {"protein_g": DailyRange(50, 200)}, days=1)


def test_an_unreachable_target_still_plans_and_reports_every_day():
    gen = make_generator(CATALOG)
    menu = plan(gen, {"calories": DailyRange(5000, 6000)}, days=3)
    totals = day_totals(gen, menu)
    most = 3 * 1200
    # Each day comes close to the most it can reach (REACH_SLACK is its aim; the
    # planner may give up a little of it rather than repeat one dish all day)
    assert all(total >= most * 0.9 for total in totals.values())
    assert all(total < most for total in totals.values())
    report = gen.nutrition_report()
    assert report["days_outside"] == 3
    assert report["outside_by_nutrient"] == {"calories": 3}
    assert [day["totals"]["calories"] for day in report["days"]] == [
        totals[d] for d in sorted(totals)
    ]


def test_report_has_no_total_for_a_day_with_an_unknown_meal():
    gen = make_generator(CATALOG + [{"calories": None}])
    unknown = len(CATALOG) + 1
    plan(
        gen,
        {"calories": DailyRange(1, 10000)},
        menu=f"[{MONDAY},{unknown},1]",
        days=1,
        meals=(2, 3),
    )
    assert gen.nutrition_report()["days"] == [
        {"date": MONDAY, "totals": {"calories": None}, "miss": {"calories": None}}
    ]


# ---------------------------------------------------------------- strict targets


def plan_strict(gen, targets, **kwargs):
    return gen.update_menu(
        kwargs.pop("menu", ""),
        "",
        "",
        MONDAY,
        list(kwargs.pop("meals", (1, 2, 3))),
        number_of_days=kwargs.pop("days", 5),
        targets=targets,
        strict_targets=True,
        **kwargs,
    )


def test_strict_targets_keep_every_day_inside_every_range():
    gen = make_generator(CATALOG)
    targets = {"calories": DailyRange(1500, 1600), "protein_g": DailyRange(120, math.inf)}
    menu = plan_strict(gen, targets, days=7)
    for column, target in targets.items():
        assert all(target.miss(t) == 0 for t in day_totals(gen, menu, column).values()), column
    assert gen.nutrition_report()["days_outside"] == 0


def test_strict_targets_change_nothing_when_the_soft_plan_already_fits():
    targets = {"calories": DailyRange(1800, 2000)}
    assert plan_strict(make_generator(CATALOG), targets) == plan(make_generator(CATALOG), targets)


## A catalog where calories and protein vary independently. Soft planning, one slot at
## a time, misses 2,000-2,100 kcal with 130 g protein on some days; an exact search of
## each day finds meals that fit (found by searching random catalogs).
INDEPENDENT = [
    {"calories": kcal, "protein_g": grams, "protein": protein}
    for (kcal, grams), protein in zip(
        [(500, 50), (400, 25), (450, 40), (1000, 40), (900, 65),
         (600, 10), (1050, 5), (900, 35), (1250, 65), (300, 60)],
        PROTEINS,
    )
]  # fmt: skip


def test_strict_repair_finds_a_day_the_soft_plan_misses():
    targets = {"calories": DailyRange(2000, 2100), "protein_g": DailyRange(130, math.inf)}
    gen = make_generator(INDEPENDENT)
    plan(gen, targets, days=3)
    assert gen.nutrition_report()["days_outside"] > 0  # soft planning gives up some days
    gen = make_generator(INDEPENDENT)
    menu = plan_strict(gen, targets, days=3)
    assert gen.nutrition_report()["days_outside"] == 0
    assert all(2000 <= t <= 2100 for t in day_totals(gen, menu).values())
    assert all(t >= 130 for t in day_totals(gen, menu, "protein_g").values())


def test_strict_target_out_of_reach_names_the_day_and_the_limit():
    gen = make_generator(CATALOG)
    with pytest.raises(TargetsUnreachableError) as caught:
        plan_strict(gen, {"calories": DailyRange(5000, math.inf)})
    assert str(caught.value).startswith(
        f"No plan for {MONDAY} can meet your daily target of calories at least 5,000 kcal: "
        "the most its meals can add up to is 3,600 kcal"
    )


def test_strict_target_below_reach_names_the_least():
    with pytest.raises(TargetsUnreachableError, match="the least its meals can add up to is 900"):
        plan_strict(make_generator(CATALOG), {"calories": DailyRange(0, 800)})


def test_strict_targets_reachable_alone_but_not_together_are_refused():
    # 3,000+ kcal needs the richest meals, which have the least protein
    targets = {"calories": DailyRange(3000, math.inf), "protein_g": DailyRange(120, math.inf)}
    with pytest.raises(TargetsUnreachableError, match="No combination of meals for"):
        plan_strict(make_generator(CATALOG), targets)


def test_strict_error_says_when_only_part_of_the_menu_was_searched(monkeypatch):
    monkeypatch.setattr("proj2.menu_generation.REPAIR_CANDIDATES", 3)
    targets = {"calories": DailyRange(3000, math.inf), "protein_g": DailyRange(120, math.inf)}
    with pytest.raises(TargetsUnreachableError, match="Among the 3 most varied meals"):
        plan_strict(make_generator(CATALOG), targets)


def test_strict_repair_stays_within_the_weekly_cap():
    targets = {"calories": DailyRange(2000, 2100), "protein_g": DailyRange(130, math.inf)}
    items = [dict(item, price=500 + 100 * i) for i, item in enumerate(INDEPENDENT)]
    gen = make_generator(items)
    cap = 6000  # the uncapped strict plan costs $82, so the cap shapes the repair
    menu = plan_strict(gen, targets, days=3, weekly_cap_cents=cap)
    prices = dict(zip(gen.catalog.itm_id, gen.catalog.price))
    assert sum(prices[itm_id] for _, itm_id, _ in plan_entries(menu)) <= cap
    assert gen.nutrition_report()["days_outside"] == 0


def test_strict_repair_counts_meals_already_planned():
    targets = {"calories": DailyRange(2000, 2100), "protein_g": DailyRange(130, math.inf)}
    breakfast = 5  # 900 kcal, 65 g protein
    gen = make_generator(INDEPENDENT)
    menu = plan_strict(gen, targets, menu=f"[{MONDAY},{breakfast},1]", days=1, meals=(2, 3))
    assert 2000 <= day_totals(gen, menu)[MONDAY] <= 2100
    assert day_totals(gen, menu, "protein_g")[MONDAY] >= 130


def test_strict_repair_refuses_a_day_with_an_unknown_existing_meal():
    items = INDEPENDENT + [{"calories": 900, "protein_g": None, "protein": "goat"}]
    unknown = len(items)
    targets = {"calories": DailyRange(2000, 2100), "protein_g": DailyRange(130, math.inf)}
    with pytest.raises(
        TargetsUnreachableError, match=f"already planned for {MONDAY} has no protein"
    ):
        plan_strict(
            make_generator(items), targets, menu=f"[{MONDAY},{unknown},1]", days=1, meals=(2, 3)
        )
