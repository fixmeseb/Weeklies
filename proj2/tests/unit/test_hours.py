"""Unit tests for restaurant hours display (proj2/hours.py)."""

import json

import pytest

from proj2 import demo_menu
from proj2.hours import format_hours, format_time
from proj2.plan_rules import is_restaurant_open

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week(**days):
    return json.dumps({day: days.get(day, []) for day in DAYS})


@pytest.mark.parametrize(
    "hhmm, text",
    [
        (0, "12 am"),
        (630, "6:30 am"),
        (1100, "11 am"),
        (1200, "12 pm"),
        (2130, "9:30 pm"),
        (2359, "11:59 pm"),
    ],
)
def test_format_time(hhmm, text):
    assert format_time(hhmm) == text


def test_same_hours_every_day():
    assert format_hours(json.dumps({d: [1100, 2130] for d in DAYS})) == "Daily 11 am–9:30 pm"


def test_days_with_the_same_hours_are_grouped():
    hours = week(
        Mon=[600, 1500], Tue=[600, 1500], Wed=[600, 1500], Thu=[600, 1500], Fri=[600, 1500]
    )
    assert format_hours(hours) == "Mon–Fri 6 am–3 pm · Sat, Sun closed"


def test_split_shifts_and_shared_am_pm():
    hours = week(Mon=[1100, 1400, 1700, 2200], Tue=[1700, 2200])
    assert format_hours(hours) == "Mon 11 am–2 pm, 5–10 pm · Tue 5–10 pm · Wed–Sun closed"


def test_closed_all_week():
    assert format_hours(week()) == "Closed"


def test_missing_days_count_as_closed_like_the_planner():
    hours = json.dumps({"Mon": [900, 1700]})
    assert format_hours(hours) == "Mon 9 am–5 pm · Tue–Sun closed"
    assert not is_restaurant_open(hours, "Tue", 1200)


@pytest.mark.parametrize(
    "text, shown",
    [
        ("11:00 AM - 10:00 PM", "11:00 am–10:00 pm"),
        ("  Mon-Fri   9am-5pm ", "Mon-Fri 9 am–5 pm"),
        ("9-21", "9–21"),
    ],
)
def test_free_text_is_tidied_not_rewritten(text, shown):
    assert format_hours(text) == shown


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_hours(value):
    assert format_hours(value) == ""


@pytest.mark.parametrize("bad", ['{"Mon": [900]}', '{"Mon": ["9", "5"]}', "[1, 2]", "{bad json"])
def test_unreadable_json_is_shown_as_text(bad):
    assert format_hours(bad) == bad


def test_every_demo_restaurant_has_readable_hours():
    for restaurant in demo_menu.RESTAURANTS:
        shown = format_hours(restaurant["hours"])
        assert shown and "{" not in shown, restaurant["name"]
