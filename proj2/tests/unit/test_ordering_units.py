"""Unit tests for proj2/ordering.py, proj2/meal_times.py and proj2/plan_edit.py."""

import datetime
import json

import pytest

from proj2 import meal_times, plan_edit
from proj2.ordering import (
    OrderError,
    daily_order_counts,
    delivery_address,
    item_order_rejection,
    parse_tip,
    restaurant_metrics,
    when_due,
)

ALL_DAY = json.dumps({d: [0, 2359] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]})
LUNCH_ONLY = json.dumps(
    {d: [1100, 1500] for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
)


def item(**over):
    base = {
        "itm_id": 1,
        "name": "Soup",
        "instock": 1,
        "allergens": "",
        "restaurant_name": "Cafe",
        "restaurant_status": "open",
        "hours": ALL_DAY,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------- meal times


class TestMealTimes:
    def test_defaults_when_unset(self):
        assert meal_times.times_for(None) == {1: 1000, 2: 1400, 3: 2000}
        assert meal_times.times_for({"breakfast_time": None, "lunch_time": ""}) == {
            1: 1000,
            2: 1400,
            3: 2000,
        }

    def test_saved_times_win(self):
        row = {"breakfast_time": 730, "lunch_time": 1215, "dinner_time": 1845}
        assert meal_times.times_for(row) == {1: 730, 2: 1215, 3: 1845}

    @pytest.mark.parametrize(
        "text, value", [("8:30", 830), ("08:30", 830), ("0830", 830), ("23:59", 2359), ("0:00", 0)]
    )
    def test_parse_time(self, text, value):
        assert meal_times.parse_time(text) == value

    @pytest.mark.parametrize("text", ["", "24:00", "7:60", "noon", "7", "12:3", "-1:00"])
    def test_parse_time_rejects(self, text):
        with pytest.raises(meal_times.MealTimeError):
            meal_times.parse_time(text)

    def test_order_must_be_breakfast_lunch_dinner(self):
        meal_times.check_order({1: 700, 2: 1200, 3: 1800})
        with pytest.raises(meal_times.MealTimeError):
            meal_times.check_order({1: 1200, 2: 1200, 3: 1800})

    @pytest.mark.parametrize(
        "hhmm, text", [(1930, "7:30 pm"), (1000, "10 am"), (0, "12 am"), (1200, "12 pm")]
    )
    def test_display(self, hhmm, text):
        assert meal_times.as_display(hhmm) == text
        assert meal_times.as_text(1930) == "19:30"

    @pytest.mark.parametrize("hhmm, meal", [(600, 1), (1159, 1), (1200, 2), (1659, 2), (1700, 3)])
    def test_meal_at_splits_halfway(self, hhmm, meal):
        assert meal_times.meal_at(meal_times.DEFAULT_TIMES, hhmm) == meal


# ---------------------------------------------------------------- plan editing


class TestPlanEdit:
    MENU = "[2026-11-19,1,1],[2026-11-19,2,3],[2026-11-20,3,2],[2026-11-21,4,3]"

    def test_remove_meal_keeps_everything_else_in_order(self):
        menu, removed = plan_edit.remove_meal(self.MENU, "2026-11-19", 3)
        assert removed == [("2026-11-19", 2, 3)]
        assert menu == "[2026-11-19,1,1],[2026-11-20,3,2],[2026-11-21,4,3]"

    def test_remove_empty_slot_changes_nothing(self):
        menu, removed = plan_edit.remove_meal(self.MENU, "2026-11-19", 2)
        assert removed == [] and menu == self.MENU

    def test_clear_days_inclusive_and_by_meal(self):
        menu, removed = plan_edit.clear_days(self.MENU, "2026-11-19", "2026-11-20")
        assert len(removed) == 3 and menu == "[2026-11-21,4,3]"
        menu, removed = plan_edit.clear_days(self.MENU, "2026-11-19", "2026-11-21", meals=[3])
        assert [e[1] for e in removed] == [2, 4]

    def test_legacy_entries_without_a_meal_are_dinners(self):
        menu, removed = plan_edit.remove_meal("[2026-11-19,5]", "2026-11-19", 3)
        assert removed == [("2026-11-19", 5, 3)] and menu == ""

    @pytest.mark.parametrize(
        "call",
        [
            lambda: plan_edit.remove_meal("", "19-11-2026", 1),
            lambda: plan_edit.remove_meal("", "2026-11-19", 4),
            lambda: plan_edit.clear_days("", "2026-11-20", "2026-11-19"),
            lambda: plan_edit.clear_days("", "2026-11-19", "2026-11-20", meals=[]),
        ],
    )
    def test_bad_requests(self, call):
        with pytest.raises(plan_edit.PlanEditError):
            call()

    def test_days_range(self):
        assert plan_edit.days_range("2026-11-30", 3) == ("2026-11-30", "2026-12-02")


# ---------------------------------------------------------------- ordering checks


class TestOrderChecks:
    def test_allowed(self):
        assert item_order_rejection(item(), "", "Mon", 1200) is None

    def test_out_of_stock(self):
        assert item_order_rejection(item(instock=0), "", "Mon", 1200)[0] == "out_of_stock"

    def test_restaurant_not_open_for_business(self):
        rejection = item_order_rejection(item(restaurant_status="closed"), "", "Mon", 1200)
        assert rejection[0] == "restaurant_unavailable"

    def test_closed_at_that_time(self):
        rejection = item_order_rejection(item(hours=LUNCH_ONLY), "", "Mon", 2000)
        assert rejection[0] == "restaurant_closed"
        assert "8 pm" in rejection[1]
        assert item_order_rejection(item(hours=LUNCH_ONLY), "", "Mon", 1200) is None

    def test_unreadable_hours_do_not_block(self):
        assert item_order_rejection(item(hours="9-21"), "", "Mon", 300) is None
        assert item_order_rejection(item(hours=None), "", "Mon", 300) is None

    def test_allergen_from_the_account(self):
        rejection = item_order_rejection(item(allergens="peanuts"), "Peanuts", "Mon", 1200)
        assert rejection[0] == "allergen"

    @pytest.mark.parametrize("value, tip", [(None, 0.0), ("", 0.0), ("2.5", 2.5), (3, 3.0)])
    def test_tip(self, value, tip):
        assert parse_tip(value) == tip

    @pytest.mark.parametrize("value", [-1, "-0.01", "lots", float("nan"), 5000])
    def test_bad_tip(self, value):
        with pytest.raises(OrderError) as err:
            parse_tip(value)
        assert err.value.code == "bad_tip"

    def test_delivery_address(self):
        user = {"address": "1 Main St", "city": "Raleigh", "state": "NC", "zip": "27606"}
        assert delivery_address(user) == "1 Main St, Raleigh, NC 27606"
        assert delivery_address({"address": " ", "city": "Raleigh"}) == ""
        assert delivery_address({}) == ""


class TestWhenDue:
    NOW = datetime.datetime(2026, 11, 19, 12, 30)  # a Thursday

    def test_asap_is_now_and_the_meal_of_that_time(self):
        assert when_due(meal_times.DEFAULT_TIMES, now=self.NOW) == (
            "2026-11-19",
            2,
            "Thu",
            1230,
            True,
        )

    def test_planned_meal_uses_the_users_time(self):
        times = {1: 730, 2: 1215, 3: 1845}
        assert when_due(times, "2026-11-21", 3, self.NOW) == ("2026-11-21", 3, "Sat", 1845, False)

    @pytest.mark.parametrize(
        "day, meal, code",
        [
            ("2026-11-18", 3, "past_date"),
            ("tomorrow", 3, "bad_date"),
            ("2026-11-20", 7, "bad_meal"),
        ],
    )
    def test_bad(self, day, meal, code):
        with pytest.raises(OrderError) as err:
            when_due(meal_times.DEFAULT_TIMES, day, meal, self.NOW)
        assert err.value.code == code


# ---------------------------------------------------------------- analytics


def order(status, total, usr=1, placed="2026-11-19T12:00:00", items=((7, 1),)):
    details = {
        "placed_at": placed,
        "charges": {"total": total},
        "items": [{"itm_id": i, "qty": q} for i, q in items],
    }
    return (status, usr, json.dumps(details))


class TestMetrics:
    def test_cancelled_orders_earn_nothing(self):
        m = restaurant_metrics(
            [order("Delivered", 10.0), order("Cancelled", 20.0), order("Ordered", 5.5, usr=2)]
        )
        assert m["total_orders"] == 2
        assert m["cancelled"] == 1
        assert m["total_revenue_cents"] == 1550
        assert m["avg_order_value_cents"] == 775
        assert m["total_customers"] == 2
        assert m["order_completion_rate"] == pytest.approx(1 / 3)

    def test_popular_item_by_quantity(self):
        m = restaurant_metrics(
            [order("Delivered", 1, items=((1, 1), (2, 3))), order("Delivered", 1, items=((1, 1),))]
        )
        assert m["most_popular_item_id"] == 2

    def test_no_orders(self):
        m = restaurant_metrics([])
        assert m["total_orders"] == 0 and m["avg_order_value_cents"] == 0
        assert m["most_popular_item_id"] is None

    def test_unreadable_details_are_skipped(self):
        assert restaurant_metrics([("Delivered", 1, "not json")])["total_revenue_cents"] == 0

    def test_daily_counts_cover_every_day(self):
        days, counts = daily_order_counts(
            [
                order("Delivered", 1, placed="2026-11-19T09:00:00"),
                order("Ordered", 1, placed="2026-11-19T19:00:00-05:00"),
                order("Cancelled", 1, placed="2026-11-19T10:00:00"),
                order("Delivered", 1, placed="2026-11-17T10:00:00"),
                order("Delivered", 1, placed="2026-10-01T10:00:00"),
            ],
            datetime.date(2026, 11, 19),
            days=3,
        )
        assert days == ["2026-11-17", "2026-11-18", "2026-11-19"]
        assert counts == [1, 0, 2]
