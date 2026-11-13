"""
Unit tests for the variety score (proj2/variety.py) and the planner that maximizes it
(proj2/menu_generation.py)
"""

import datetime
import itertools
import json
import random

import pandas as pd
import pytest

from proj2 import demo_menu, variety
from proj2.meal_budget import plan_entries
from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator
from proj2.plan_rules import item_rejection
from proj2.seed import menu_item_row

MONDAY = "2026-11-16"
ALL_DAY = json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK})


def demo_rows():
    rows = {}
    for itm_id, item in enumerate(demo_menu.MENU_ITEMS, start=1):
        rows[item["name"]] = dict(menu_item_row(item), itm_id=itm_id)
    return rows


DEMO = demo_rows()


def feat(name):
    return variety.features(DEMO[name])


def dist(a, b):
    return variety.distance(feat(a), feat(b))


# ---------------------------------------------------------------- features and distance


class TestFeatures:
    def test_reads_every_weighted_tag(self):
        f = feat("Chicken Tikka Masala")
        assert set(f) == set(variety.WEIGHTS)
        assert f["protein"] == {"chicken"}
        assert f["spice_level"] == 2
        assert f["heaviness"] == variety.HEAVINESS_ORDER["hearty"]
        assert f["temperature"] == "hot"

    def test_missing_and_empty_tags_are_unknown(self):
        f = variety.features({"itm_id": 1, "rtr_id": 2, "protein": "", "spice_level": float("nan")})
        assert f["protein"] is None and f["spice_level"] is None and f["cuisine"] is None
        assert f["restaurant"] == 2 and f["item"] == 1


class TestDistance:
    def test_same_meal_is_zero(self):
        assert dist("Margherita Pizza", "Margherita Pizza") == 0.0

    def test_symmetric_and_within_zero_to_one(self):
        names = list(DEMO)
        for a, b in itertools.combinations(names[:30], 2):
            d = dist(a, b)
            assert 0.0 <= d <= 1.0
            assert d == pytest.approx(dist(b, a))

    @pytest.mark.parametrize(
        "base, closer, further",
        [
            ("Margherita Pizza", "Penne Arrabbiata", "Jerk Chicken with Rice and Peas"),
            ("Chicken Tikka Masala", "Chicken Tinga Bowl", "Matcha Mochi Ice Cream"),
            ("Chana Masala", "Palak Paneer", "Smoked Brisket Plate"),
            ("Beef Pho", "Tonkotsu Ramen", "Greek Salad with Feta"),
        ],
    )
    def test_sensible_orderings(self, base, closer, further):
        """Locks in that the weights behave the way a person would expect."""
        assert dist(base, closer) < dist(base, further)

    def test_missing_tags_are_left_out_not_counted(self):
        a = {"itm_id": 1, "rtr_id": 1, "protein": "chicken", "cuisine": "thai"}
        b = {"itm_id": 2, "rtr_id": 1, "protein": "chicken"}  # cuisine unknown
        a_without_cuisine = {"itm_id": 1, "rtr_id": 1, "protein": "chicken"}
        # b's missing cuisine neither adds difference nor counts as a match
        assert variety.distance(variety.features(a), variety.features(b)) == pytest.approx(
            variety.distance(variety.features(a_without_cuisine), variety.features(b))
        )

    def test_untagged_items_still_differ_by_dish_and_restaurant(self):
        a, b, c = ({"itm_id": i, "rtr_id": r} for i, r in [(1, 1), (2, 1), (3, 2)])
        fa, fb, fc = map(variety.features, (a, b, c))
        assert variety.distance(fa, fa) == 0.0
        assert 0.0 < variety.distance(fa, fb) < variety.distance(fa, fc) == 1.0

    def test_shared_tags_explain_the_similarity(self):
        shared = variety.shared_tags(feat("Chana Masala"), feat("Palak Paneer"))
        assert "same restaurant" in shared
        assert "carb_base: rice" in shared
        assert variety.shared_tags(feat("Beef Pho"), feat("Beef Pho")) == ["same dish"]


# ---------------------------------------------------------------- closeness and plan score


class TestCloseness:
    def test_neighbouring_slots_count_fully_and_halve_every_day(self):
        lunch = variety.slot_position(MONDAY, 2)
        assert variety.closeness(lunch, lunch + 1) == 1.0
        assert variety.closeness(lunch, lunch + 4) == pytest.approx(0.5)
        assert variety.closeness(lunch, lunch) == 0.0

    def test_window_ends_after_seven_days(self):
        p = variety.slot_position(MONDAY, 1)
        assert variety.closeness(p, p + 21) > 0
        assert variety.closeness(p, p + 22) == 0.0

    def test_positions_follow_dates_and_meals(self):
        assert variety.slot_position("2026-11-16", 3) + 1 == variety.slot_position("2026-11-17", 1)


def entries(*picks, start=MONDAY, meal=3):
    """One dinner a day, starting on start, for the named demo items."""
    day = datetime.date.fromisoformat(start)
    return [
        ((day + datetime.timedelta(days=i)).isoformat(), DEMO[name]["itm_id"], meal)
        for i, name in enumerate(picks)
    ]


ITEMS_BY_ID = {row["itm_id"]: row for row in DEMO.values()}


class TestPlanVariety:
    def test_same_meal_every_day_scores_zero(self):
        assert variety.plan_variety(entries(*["Beef Pho"] * 4), ITEMS_BY_ID).score == 0.0

    def test_varied_plan_scores_higher(self):
        dull = entries("Beef Pho", "Tonkotsu Ramen", "Beef Pho", "Tonkotsu Ramen")
        lively = entries("Beef Pho", "Greek Salad with Feta", "Chana Masala", "Carnitas Tacos")
        assert (
            variety.plan_variety(lively, ITEMS_BY_ID).score
            > variety.plan_variety(dull, ITEMS_BY_ID).score
        )

    def test_a_repeat_next_door_costs_more_than_a_repeat_days_later(self):
        soon = entries("Beef Pho", "Beef Pho", "Greek Salad with Feta", "Carnitas Tacos")
        later = entries("Beef Pho", "Greek Salad with Feta", "Carnitas Tacos", "Beef Pho")
        assert (
            variety.plan_variety(soon, ITEMS_BY_ID).score
            < variety.plan_variety(later, ITEMS_BY_ID).score
        )

    def test_one_meal_or_meals_far_apart_have_no_score(self):
        assert variety.plan_variety(entries("Beef Pho"), ITEMS_BY_ID).score is None
        far = entries("Beef Pho") + entries("Beef Pho", start="2026-12-01")
        assert variety.plan_variety(far, ITEMS_BY_ID).score is None

    def test_unknown_items_are_left_out(self):
        plan = entries("Beef Pho", "Carnitas Tacos") + [(MONDAY, 99999, 1)]
        assert variety.plan_variety(plan, ITEMS_BY_ID).score is not None

    def test_similar_pairs_name_the_closest_nearby_meals(self):
        plan = entries("Beef Pho", "Beef Pho", "Greek Salad with Feta")
        pairs = variety.plan_variety(plan, ITEMS_BY_ID).similar_pairs(1)
        assert pairs[0]["shared"] == ["same dish"]
        assert pairs[0]["similarity"] == 1.0
        report = variety.plan_variety(plan, ITEMS_BY_ID).as_json()
        assert set(report) == {"score", "similar_pairs"}


class TestPreferences:
    def test_soft_preferences_ignore_diets(self):
        assert variety.soft_preferences("Vegetarian, Italian, Spicy") == {"italian", "spicy"}

    @pytest.mark.parametrize(
        "name, preferences, share",
        [
            ("Margherita Pizza", "Italian", 1.0),
            ("Margherita Pizza", "Vegetarian, Italian, Spicy", 0.5),
            ("Kung Pao Chicken", "spicy, chicken", 1.0),
            ("Chicken Shawarma Plate", "Middle Eastern", 1.0),
            ("Beef Pho", "Italian", 0.0),
            ("Beef Pho", "", 0.0),
            ("Beef Pho", "Vegetarian", 0.0),
        ],
    )
    def test_preference_match(self, name, preferences, share):
        assert variety.preference_match(DEMO[name], preferences) == share

    def test_preference_breaks_ties_but_does_not_override_variety(self):
        assert variety.candidate_score(1, 2, 1.0) > variety.candidate_score(1, 2, 0.0)
        # A much more varied option still beats a preferred but repetitive one.
        assert variety.candidate_score(0.9, 1, 0.0) > variety.candidate_score(0.3, 1, 1.0)


# ---------------------------------------------------------------- the planner


def make_generator(items, restaurants=None):
    """A MenuGenerator over an in-memory catalog (no database)."""
    gen = MenuGenerator.__new__(MenuGenerator)
    rows = []
    for itm_id, item in enumerate(items, start=1):
        row = {
            "itm_id": itm_id,
            "rtr_id": 1,
            "name": f"Meal {itm_id}",
            "description": "",
            "price": 500,
            "calories": 500,
            "instock": 1,
            "allergens": "",
        }
        row.update(item)
        rows.append(row)
    gen.menu_items = pd.DataFrame(rows)
    gen.catalog = gen.menu_items.copy()
    rtr_ids = sorted(set(gen.menu_items.rtr_id))
    gen.restaurants = pd.DataFrame(
        restaurants or [{"rtr_id": r, "hours": ALL_DAY} for r in rtr_ids]
    )
    gen.item_prices = dict(zip(gen.menu_items.itm_id, gen.menu_items.price))
    gen.variety = None
    return gen


PROTEINS = ["chicken", "beef", "tofu", "fish", "legumes"]
CUISINES = ["thai", "mexican", "italian", "indian"]
CARBS = ["rice", "bread", "noodles", "none"]


def random_items(rng, n):
    return [
        {
            "rtr_id": rng.randint(1, 3),
            "protein": rng.choice(PROTEINS),
            "cuisine": rng.choice(CUISINES),
            "carb_base": rng.choice(CARBS),
            "spice_level": rng.randint(0, 3),
            "price": rng.choice([400, 500, 700, 900]),
        }
        for _ in range(n)
    ]


def plan_score(gen, plan):
    rows = {int(r["itm_id"]): r for r in gen.catalog.to_dict("records")}
    return variety.plan_variety(list(plan_entries(plan)), rows).score


def best_possible(gen, days, meal=3, cap_cents=None):
    """The best plan score over every possible assignment (brute force)."""
    ids = list(gen.menu_items.itm_id)
    prices = gen.item_prices
    best = -1.0
    start = datetime.date.fromisoformat(MONDAY)
    for combo in itertools.product(ids, repeat=days):
        if cap_cents is not None and sum(prices[i] for i in combo) > cap_cents:
            continue
        plan = ",".join(
            f"[{(start + datetime.timedelta(days=d)).isoformat()},{i},{meal}]"
            for d, i in enumerate(combo)
        )
        best = max(best, plan_score(gen, plan))
    return best


class TestPlanner:
    def test_no_repeats_while_there_are_enough_different_meals(self):
        rng = random.Random(1)
        gen = make_generator(random_items(rng, 10))
        plan = gen.update_menu("", "", "", MONDAY, [3], 7)
        ids = [itm_id for _, itm_id, _ in plan_entries(plan)]
        assert len(ids) == len(set(ids)) == 7

    def test_same_request_gives_the_same_plan(self):
        gen = make_generator(random_items(random.Random(2), 12))
        first = gen.update_menu("", "", "", MONDAY, [1, 2, 3], 5)
        assert gen.update_menu("", "", "", MONDAY, [1, 2, 3], 5) == first

    def test_sets_a_variety_report_for_the_requested_days(self):
        gen = make_generator(random_items(random.Random(3), 8))
        gen.update_menu("[2026-11-01,1,3]", "", "", MONDAY, [3], 3)
        assert gen.variety.score is not None
        assert {e[0] for _, _, a, b in gen.variety.pairs for e in (a, b)} <= {
            "2026-11-16",
            "2026-11-17",
            "2026-11-18",
        }

    def test_existing_meals_are_kept_and_avoided(self):
        items = [{"protein": "chicken"}, {"protein": "chicken"}, {"protein": "beef"}]
        gen = make_generator(items)
        plan = gen.update_menu(f"[{MONDAY},1,2]", "", "", MONDAY, [2, 3])
        assert plan.startswith(f"[{MONDAY},1,2]")
        # Dinner next to Monday's chicken lunch: the beef dish is the most different.
        assert plan.endswith(f"[{MONDAY},3,3]")

    def test_soft_preference_breaks_a_tie(self):
        items = [{"cuisine": "thai"}, {"cuisine": "italian"}]
        gen = make_generator(items)
        assert gen.update_menu("", "", "", MONDAY, [3]) == f"[{MONDAY},1,3]"  # lower ID
        assert gen.update_menu("", "Italian", "", MONDAY, [3]) == f"[{MONDAY},2,3]"

    def test_cheaper_item_wins_a_variety_tie(self):
        gen = make_generator([{"price": 900}, {"price": 400}])
        assert gen.update_menu("", "", "", MONDAY, [3]) == f"[{MONDAY},2,3]"

    def test_every_planned_meal_passes_the_shared_rules(self):
        gen = make_generator(
            [
                {"allergens": "Peanuts", "diet_tags": "vegan"},
                {"diet_tags": "vegetarian", "course": "drink"},
                {"diet_tags": "vegetarian", "meal_type": "breakfast"},
                {"diet_tags": "vegan", "meal_type": "lunch-dinner"},
                {"diet_tags": "vegetarian", "course": "main"},
                {"diet_tags": None},
            ]
        )
        plan = gen.update_menu("", "Vegetarian", "peanuts", MONDAY, [1, 2, 3], 3)
        rows = {int(r["itm_id"]): r for r in gen.menu_items.to_dict("records")}
        for day, itm_id, meal in plan_entries(plan):
            weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(day).weekday()]
            _, order_time = {1: (0, 1000), 2: (0, 1400), 3: (0, 2000)}[meal]
            item = dict(rows[itm_id], restaurant_status="Open", hours=ALL_DAY)
            assert item_rejection(item, "peanuts", "Vegetarian", weekday, order_time, meal) is None

    @pytest.mark.parametrize("seed", range(12))
    def test_close_to_the_best_possible_plan(self, seed):
        """Against brute force on small random menus: the greedy pick plus one
        improvement pass stays within 5% of the best possible plan."""
        rng = random.Random(seed)
        gen = make_generator(random_items(rng, 5))
        plan = gen.update_menu("", "", "", MONDAY, [3], 4)
        assert plan_score(gen, plan) >= 0.95 * best_possible(gen, 4)

    @pytest.mark.parametrize("seed", range(6))
    def test_close_to_the_best_possible_plan_within_a_budget(self, seed):
        rng = random.Random(100 + seed)
        gen = make_generator(random_items(rng, 5))
        # Room for the cheapest item four times plus a little: feasible, but it binds.
        cap = 4 * min(gen.item_prices.values()) + 400
        plan = gen.update_menu("", "", "", MONDAY, [3], 4, weekly_cap_cents=cap)
        assert sum(gen.item_prices[i] for _, i, _ in plan_entries(plan)) <= cap
        assert plan_score(gen, plan) >= 0.95 * best_possible(gen, 4, cap_cents=cap)


# ---------------------------------------------------------------- swap options


class TestSwapRanking:
    CATALOG = {
        1: {"itm_id": 1, "rtr_id": 1, "price": 500, "protein": "chicken", "cuisine": "thai"},
        2: {"itm_id": 2, "rtr_id": 1, "price": 500, "protein": "chicken", "cuisine": "thai"},
        3: {"itm_id": 3, "rtr_id": 2, "price": 900, "protein": "beef", "cuisine": "mexican"},
        4: {"itm_id": 4, "rtr_id": 2, "price": 400, "protein": "beef", "cuisine": "mexican"},
        5: {"itm_id": 5, "rtr_id": 3, "price": 500, "protein": "tofu", "cuisine": "italian"},
    }

    def rank(self, option_ids, menu, preferences=""):
        from proj2.meal_swap import rank_swap_options

        options = [{"itm_id": i} for i in option_ids]
        return rank_swap_options(options, self.CATALOG, menu, MONDAY, 3, preferences)

    def test_most_different_from_nearby_meals_first(self):
        # Monday lunch is chicken Thai; the slot being swapped is Monday dinner.
        ranked = self.rank([2, 3, 5], f"[{MONDAY},1,2],[{MONDAY},2,3]")
        assert ranked[0]["itm_id"] in {3, 5}
        assert ranked[-1]["itm_id"] == 2
        assert all("variety" in o for o in ranked)
        scores = [o["variety"] for o in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_the_slot_itself_is_not_its_own_neighbour(self):
        # Only the dinner being replaced is planned, so every option scores the same 0.
        ranked = self.rank([2, 3], f"[{MONDAY},1,3]")
        assert [o["variety"] for o in ranked] == [0.0, 0.0]

    def test_ties_go_to_the_cheaper_item_then_lower_id(self):
        ranked = self.rank([3, 4], f"[{MONDAY},1,2]")
        assert [o["itm_id"] for o in ranked] == [4, 3]

    def test_soft_preference_lifts_a_matching_option(self):
        menu = f"[{MONDAY},1,2]"
        plain = [o["itm_id"] for o in self.rank([3, 5], menu)]
        preferred = [o["itm_id"] for o in self.rank([3, 5], menu, "Italian")]
        assert preferred[0] == 5
        assert set(plain) == set(preferred)


# ---------------------------------------------------------------- scripts/variety_report.py


def test_variety_report_script(tmp_path):
    import io

    from proj2.scripts import variety_report
    from proj2.seed import seed_database

    path = str(tmp_path / "seed.db")
    seed_database(path, password="pw-for-tests")
    out = io.StringIO()
    assert variety_report.main(["--db", path, "--item", "3", "--neighbours", "2"], out) == 0
    text = out.getvalue()
    assert text.startswith("Penne Arrabbiata [3]") or "[3]" in text.splitlines()[0]
    assert "pairs):" in text and "median" in text
    assert variety_report.main(["--db", path, "--item", "99999"], io.StringIO()) == 1
    assert variety_report.main(["--db", str(tmp_path / "missing.db")], io.StringIO()) == 1


# ---------------------------------------------------------------- why a slot has no candidates


class TestEmptySlotReason:
    def plan(self, gen, **kw):
        from proj2.menu_generation import NoEligibleMealError

        with pytest.raises(NoEligibleMealError) as caught:
            gen.update_menu("", "", kw.get("allergens", ""), MONDAY, [kw.get("meal", 1)])
        return str(caught.value)

    def test_unreadable_hours_are_named(self):
        gen = make_generator([{}], restaurants=[{"rtr_id": 1, "hours": "11:00 AM - 10:00 PM"}])
        message = self.plan(gen)
        assert message.startswith("No menu item can be planned for breakfast on 2026-11-16:")
        assert "no restaurant is open at 10:00 on Mon" in message
        assert '"11:00 AM - 10:00 PM"' in message and "flask seed" in message

    def test_closed_at_that_hour(self):
        hours = json.dumps({day: [1700, 2200] for day in DAYS_OF_WEEK})
        gen = make_generator([{}], restaurants=[{"rtr_id": 1, "hours": hours}])
        message = self.plan(gen)
        assert message.endswith("no restaurant is open at 10:00 on Mon.")

    def test_no_main_for_the_meal(self):
        gen = make_generator([{"meal_type": "lunch-dinner", "course": "main"}, {"course": "drink"}])
        assert "serves a main dish for breakfast" in self.plan(gen)

    def test_allergens_rule_everything_out(self):
        gen = make_generator([{"allergens": "Peanuts"}])
        assert "contains one of your allergens (peanuts)" in self.plan(gen, allergens="peanuts")

    def test_nothing_in_stock(self):
        gen = make_generator([{"instock": 0}])
        assert "no open restaurant has any item in stock" in self.plan(gen)
