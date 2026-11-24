"""A new plan takes the three days before its start into account (LOOKBACK_DAYS)."""

import json
import sqlite3

import pytest

from proj2.Flask_app import _meal_at, order_meals
from proj2 import variety
from proj2.meal_budget import plan_entries
from proj2.menu_generation import LOOKBACK_DAYS, recent_repeats
from tests.unit.test_variety import make_generator

START = "2026-11-19"  # a Thursday; the lookback is Mon 16 - Wed 18


def new_meals(plan, start=START):
    return [(day, itm_id, meal) for day, itm_id, meal in plan_entries(plan) if day >= start]


def test_lookback_is_three_days():
    assert LOOKBACK_DAYS == 3


def test_dish_from_the_day_before_is_not_repeated():
    # Two identical-looking dishes: only the lookback can tell them apart.
    gen = make_generator([{"protein": "chicken"}, {"protein": "chicken"}])
    plan = gen.update_menu("[2026-11-18,1,3]", "", "", START, [3])
    assert new_meals(plan) == [(START, 2, 3)]


def test_dish_from_three_days_before_is_not_repeated():
    gen = make_generator([{"protein": "chicken"}, {"protein": "chicken"}])
    plan = gen.update_menu("[2026-11-16,1,3]", "", "", START, [3])
    assert new_meals(plan) == [(START, 2, 3)]


def test_a_recent_dish_may_return_after_three_days():
    # Eaten Wednesday: barred Thu-Sat, allowed again on Sunday.
    gen = make_generator([{"protein": "chicken"}, {"protein": "beef"}])
    plan = gen.update_menu("[2026-11-18,1,3]", "", "", START, [3], 4)
    by_day = {day: itm_id for day, itm_id, _ in new_meals(plan)}
    assert by_day["2026-11-19"] == 2
    assert by_day["2026-11-22"] in (1, 2)
    assert 1 not in (by_day["2026-11-19"], by_day["2026-11-21"])


def test_repeat_is_allowed_when_nothing_else_fits():
    gen = make_generator([{"protein": "chicken"}])
    plan = gen.update_menu("[2026-11-18,1,3]", "", "", START, [3])
    assert new_meals(plan) == [(START, 1, 3)]


def test_only_meals_within_three_days_count_as_recent_repeats():
    position = variety.slot_position(START, 3)
    for day, barred in [
        ("2026-11-15", False),
        ("2026-11-16", True),
        ("2026-11-22", True),
        ("2026-11-23", False),
    ]:
        repeats = recent_repeats([(variety.slot_position(day, 1), 7)], position)
        assert (7 in repeats) is barred, day


def test_only_meals_within_three_days_bar_a_dish():
    # The bar follows nutrition miss in the ranking key; variety scoring still sees older meals.
    gen = make_generator([{"protein": "chicken"}, {"protein": "beef"}])
    pool = gen.menu_items.assign(price_cents=gen.menu_items.price)
    position = variety.slot_position(START, 3)
    for day, barred in [("2026-11-15", False), ("2026-11-16", True), ("2026-11-22", True)]:
        recent = [(variety.slot_position(day, 3), 1)]
        keys = dict(
            (itm_id, key) for key, itm_id in gen._ranked(pool, position, [], "", recent=recent)
        )
        assert keys[1][1] is barred, day
        assert keys[2][1] is False


def test_ordered_meals_count_like_planned_ones():
    gen = make_generator([{"protein": "chicken", "price": 400}, {"protein": "chicken"}])
    plan = gen.update_menu("", "", "", START, [3], ordered_meals=[("2026-11-18", 1, 2)])
    assert new_meals(plan) == [(START, 2, 3)]


def test_ordered_meals_steer_variety_not_just_repeats():
    # A chicken order yesterday makes the beef dish the more varied pick.
    gen = make_generator(
        [
            {"protein": "chicken", "cuisine": "thai"},
            {"protein": "chicken", "cuisine": "thai", "price": 400},
            {"protein": "beef", "cuisine": "mexican", "price": 900},
        ]
    )
    without = gen.update_menu("", "", "", START, [3])
    assert new_meals(without) == [(START, 2, 3)]
    plan = gen.update_menu("", "", "", START, [3], ordered_meals=[("2026-11-18", 1, 3)])
    assert new_meals(plan) == [(START, 3, 3)]


def test_orders_outside_the_lookback_are_ignored():
    gen = make_generator([{"protein": "chicken", "price": 400}, {"protein": "chicken"}])
    later = [("2026-11-15", 1, 3), ("2026-11-19", 1, 3), ("2026-11-25", 1, 3)]
    plan = gen.update_menu("", "", "", START, [3], ordered_meals=later)
    assert new_meals(plan) == [(START, 1, 3)]


def test_unknown_items_in_orders_are_ignored():
    gen = make_generator([{"protein": "chicken", "price": 400}, {"protein": "chicken"}])
    plan = gen.update_menu("", "", "", START, [3], ordered_meals=[("2026-11-18", 99, 3)])
    assert new_meals(plan) == [(START, 1, 3)]


# ---------------------------------------------------------------- the user's orders


@pytest.mark.parametrize("hour, meal", [(7, 1), (10, 1), (11, 2), (15, 2), (16, 3), (22, 3)])
def test_meal_at(hour, meal):
    assert _meal_at(hour) == meal


@pytest.fixture
def orders_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        'CREATE TABLE "Order" (ord_id INTEGER PRIMARY KEY, usr_id INT, details TEXT, status TEXT)'
    )

    def add(details, status="Delivered", usr_id=1):
        text = details if isinstance(details, str) else json.dumps(details)
        conn.execute(
            'INSERT INTO "Order" (usr_id, details, status) VALUES (?, ?, ?)',
            (usr_id, text, status),
        )

    yield conn, add
    conn.close()


def test_order_meals_reads_plan_and_ad_hoc_orders(orders_db):
    conn, add = orders_db
    add(
        {
            "date": "2026-11-17",
            "meal": 2,
            "items": [{"itm_id": 4}],
            "placed_at": "2026-11-17T09:00:00",
        }
    )
    add({"placed_at": "2026-11-18T19:30:00-05:00", "items": [{"itm_id": 5}, {"itm_id": 6}]})
    add({"time": "2026-11-16T08:15:00", "items": [{"itm_id": 7}]})
    assert sorted(order_meals(conn, 1)) == [
        ("2026-11-16", 7, 1),
        ("2026-11-17", 4, 2),
        ("2026-11-18", 5, 3),
        ("2026-11-18", 6, 3),
    ]


def test_order_meals_skips_cancelled_unreadable_and_other_users(orders_db):
    conn, add = orders_db
    add({"placed_at": "2026-11-18T19:30:00", "items": [{"itm_id": 5}]}, status="Cancelled")
    add({"placed_at": "2026-11-18T19:30:00", "items": [{"itm_id": 5}]}, usr_id=2)
    add("not json")
    add({"placed_at": "yesterday", "items": [{"itm_id": 5}]})
    add({"placed_at": "2026-11-18T19:30:00", "items": [{"name": "no id"}]})
    add(None)
    assert order_meals(conn, 1) == []


# ---------------------------------------------------------------- the route


def test_generate_route_passes_the_users_orders(client, login_session, monkeypatch):
    from proj2.food import plan

    seen = {}
    real = plan.MenuGenerator.update_menu

    def spy(self, *args, **kwargs):
        seen["ordered_meals"] = kwargs.get("ordered_meals")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(plan, "order_meals", lambda conn, usr_id: [("2026-11-18", 1, 3)])
    monkeypatch.setattr(plan.MenuGenerator, "update_menu", spy)
    client.post("/menu/generate", json={"start_date": START, "meal_numbers": [3]})
    assert seen["ordered_meals"] == [("2026-11-18", 1, 3)]
