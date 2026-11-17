import json
import pandas as pd
import pytest

from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator, NoEligibleMealError
from proj2.meal_budget import BudgetExceededError


@pytest.fixture
def generator():
    gen = MenuGenerator.__new__(MenuGenerator)
    gen.menu_items = pd.DataFrame(
        [
            {
                "itm_id": item,
                "rtr_id": 1,
                "name": f"Meal {item}",
                "description": "Dinner",
                "price": price,
                "calories": 500,
                "instock": 1,
                "allergens": "",
            }
            for item, price in [(1, 1000), (2, 500), (3, 500)]
        ]
    )
    gen.restaurants = pd.DataFrame(
        [{"rtr_id": 1, "hours": json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK})}]
    )
    gen.item_prices = dict(zip(gen.menu_items.itm_id, gen.menu_items.price))
    return gen


def test_rank_affordable_candidates_including_exact_limit(generator):
    candidates = generator._eligible_candidates("", "Mon", 2000, 500)
    assert candidates.itm_id.tolist() == [2, 3]
    assert generator._eligible_candidates("", "Mon", 2000, 499).empty


def test_eligibility_rejects_stock_allergens_missing_restaurants_and_bad_prices(generator):
    generator.menu_items.loc[0, "allergens"] = " Peanuts, MILK "
    generator.menu_items.loc[1, "instock"] = 0
    generator.menu_items.loc[2, "rtr_id"] = 99
    assert generator._eligible_candidates("milk", "Mon", 2000).empty
    generator.menu_items.loc[1, "instock"] = 1
    generator.menu_items.loc[1, "price"] = -1
    assert generator._eligible_candidates("milk", "Mon", 2000).empty


@pytest.mark.parametrize("hours", ['{"Mon": []}', "bad json", '{"Tue": [0, 2359]}'])
def test_unavailable_hours_exclude_candidates(generator, hours):
    generator.restaurants.loc[0, "hours"] = hours
    assert generator._eligible_candidates("", "Mon", 2000).empty


def test_no_candidate_for_a_slot_is_a_clear_error(generator):
    generator.menu_items["instock"] = 0
    with pytest.raises(NoEligibleMealError, match="dinner on 2026-10-05"):
        generator.update_menu("", "", "", "2026-10-05", [3])


def generate(generator, **overrides):
    args = dict(
        menu="",
        preferences="",
        allergens="",
        date="2026-10-05",
        meal_numbers=[3],
        number_of_days=2,
        weekly_cap_cents=1000,
    )
    args.update(overrides)
    return generator.update_menu(**args)


def test_plan_fits_exact_cap_and_reserves_later_meals(generator):
    # Monday must leave $5 for Tuesday, so only the $5 items fit; Tuesday then avoids
    # repeating Monday's item, which counts as the least varied choice.
    assert generate(generator) == "[2026-10-05,2,3],[2026-10-06,3,3]"
    assert generator.item_total_cents == 1000
    assert generator.weekly_totals_cents == {"2026-10-05": 1000}


def test_impossible_budget_is_rejected_before_generation(generator):
    with pytest.raises(BudgetExceededError, match=r"needs at least \$10.00"):
        generate(generator, weekly_cap_cents=999)


def test_existing_meals_outside_requested_dates_consume_weekly_budget(generator):
    # Sunday's saved dinner still belongs to the week of the Monday request.
    existing = "[2026-10-11,1,3]"
    with pytest.raises(BudgetExceededError, match=r"needs at least \$20.00"):
        generate(generator, menu=existing)
    assert existing == "[2026-10-11,1,3]"


def test_each_calendar_week_has_its_own_cap(generator):
    generate(generator, date="2026-10-11", weekly_cap_cents=500)
    assert generator.weekly_totals_cents == {"2026-10-05": 500, "2026-10-12": 500}


def test_existing_legacy_dinner_is_preserved_and_counted_once(generator):
    existing = "[2026-10-05,2]"
    assert generate(generator, menu=existing, number_of_days=1, weekly_cap_cents=500) == existing
    assert generator.item_total_cents == 500


def test_reservation_uses_each_days_eligible_prices(generator):
    # Cheap meals are available only Monday; Tuesday requires the $10 option.
    generator.menu_items.loc[generator.menu_items.itm_id.isin([2, 3]), "rtr_id"] = 2
    hours = {day: ([0, 2359] if day == "Mon" else []) for day in DAYS_OF_WEEK}
    generator.restaurants.loc[1] = {"rtr_id": 2, "hours": json.dumps(hours)}
    assert generate(generator, weekly_cap_cents=1500) == "[2026-10-05,2,3],[2026-10-06,1,3]"
    assert generator.item_total_cents == 1500


def test_preflight_rejects_impossible_later_week_before_any_generation(generator):
    with pytest.raises(BudgetExceededError, match="2026-10-12"):
        generate(generator, menu="[2026-10-13,1,3]", date="2026-10-11", weekly_cap_cents=500)


def test_saved_out_of_stock_meals_still_consume_budget(generator):
    generator.menu_items.loc[0, "instock"] = 0
    with pytest.raises(BudgetExceededError):
        generate(generator, menu="[2026-10-11,1,3]", weekly_cap_cents=1999)


def test_zero_cap_allows_only_free_meals(generator):
    with pytest.raises(BudgetExceededError):
        generate(generator, weekly_cap_cents=0)
    generator.menu_items.loc[1, "price"] = 0
    generator.item_prices[2] = 0
    assert generate(generator, weekly_cap_cents=0, number_of_days=1) == "[2026-10-05,2,3]"
    assert generator.item_total_cents == 0


def test_variety_never_buys_past_the_cap(generator):
    # Item 1 ($10) is from another restaurant, so it is the most varied second meal...
    generator.menu_items.loc[0, "rtr_id"] = 2
    generator.restaurants.loc[1] = {"rtr_id": 2, "hours": generator.restaurants.loc[0, "hours"]}
    # ...and is chosen when the cap allows it,
    assert generate(generator, weekly_cap_cents=1500) == "[2026-10-05,2,3],[2026-10-06,1,3]"
    # but not when it would go over: the cheaper, less varied item is used instead.
    assert generate(generator, weekly_cap_cents=1100) == "[2026-10-05,2,3],[2026-10-06,3,3]"
    assert generator.item_total_cents == 1000


def test_unknown_saved_price_does_not_silently_become_zero(generator):
    with pytest.raises(ValueError, match="no longer in the catalog"):
        generate(generator, menu="[2026-10-11,999,3]")
