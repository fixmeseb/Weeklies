"""The Seed Catalog & Almanac calendar style's week data (proj2/almanac.py)."""

import datetime

import pytest

from proj2 import almanac


@pytest.mark.parametrize(
    "day, text",
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (23, "23rd"),
        (30, "30th"),
    ],
)
def test_ordinal(day, text):
    assert almanac.ordinal(day) == text


def test_roman():
    assert almanac.roman(2026) == "MMXXVI"
    assert almanac.roman(1994) == "MCMXCIV"


@pytest.mark.parametrize(
    "score, word",
    [
        (100, "Very varied"),
        (90, "Very varied"),
        (89, "Fair and varied"),
        (80, "Fair and varied"),
        (79, "Changeable"),
        (65, "Changeable"),
        (64, "Monotonous"),
        (0, "Monotonous"),
        (None, "Too few meals to judge"),
    ],
)
def test_forecast(score, word):
    assert almanac.forecast(score) == word


@pytest.mark.parametrize(
    "start, title",
    [
        ("2026-11-16", "the 16th to the 22nd of November, 2026"),
        ("2026-11-30", "the 30th of November to the 6th of December, 2026"),
        ("2026-12-28", "the 28th of December, 2026 to the 3rd of January, 2027"),
    ],
)
def test_week_title(start, title):
    assert almanac.week_title(datetime.date.fromisoformat(start)) == title


ITEMS = {
    1: {"name": "Oatmeal", "price": 650, "calories": 300, "rtr_id": 10, "restaurant_name": "Grind"},
    2: {
        "name": "Chicken Bowl",
        "price": 1200,
        "calories": 700,
        "rtr_id": 11,
        "restaurant_name": "Bowl Co",
    },
    3: {
        "name": "Fish Tacos",
        "price": 1100,
        "calories": 600,
        "rtr_id": 12,
        "restaurant_name": "Casa",
    },
}
CATALOG = {
    1: {"protein": "none"},
    2: {"protein": "chicken, legumes"},
    3: {"protein": "fish"},
}
## Mon 2026-11-16: oatmeal, chicken lunch; Tue: chicken lunch again, fish dinner; Thu: fish dinner
ENTRIES = [
    ("2026-11-16", 1, 1),
    ("2026-11-16", 2, 2),
    ("2026-11-17", 2, 2),
    ("2026-11-17", 3, 3),
    ("2026-11-19", 3, 3),
    ("2026-11-24", 1, 1),  # the next week, which the variety report does not name: not drawn
]
SIMILAR = ["Chicken Bowl (Mon lunch) and Chicken Bowl (Tue lunch): same dish"]
VARIETY = {"2026-11-16": {"score": 72, "similar": SIMILAR}}


@pytest.fixture()
def week():
    weeks = almanac.build_weeks(ENTRIES, ITEMS, CATALOG, VARIETY)
    assert len(weeks) == 1
    return weeks[0]


def test_week_heading(week):
    assert week["start"] == "2026-11-16"
    assert week["title"] == "the 16th to the 22nd of November, 2026"
    assert (week["volume"], week["number"]) == ("MMXXVI", 47)


def test_week_counts_and_totals(week):
    assert week["meal_count"] == 5
    assert week["distinct"] == 3
    assert week["kitchens"] == 3
    assert week["total"] == 650 + 1200 + 1200 + 1100 + 1100
    assert [d["total"] for d in week["days"]] == [1850, 2300, 0, 1100, 0, 0, 0]


def test_days_hold_meals_by_slot(week):
    days = week["days"]
    assert [d["weekday"] for d in days] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert sorted(days[0]["meals"]) == [1, 2]
    assert days[2]["meals"] == {}
    lunch = days[0]["meals"][2]
    assert lunch["name"] == "Chicken Bowl" and lunch["restaurant"] == "Bowl Co"
    assert lunch["date"] == "2026-11-16" and lunch["meal"] == 2


def test_repeats_are_flagged_with_their_other_days(week):
    assert week["days"][0]["meals"][2]["again"] == ["Tue"]
    assert week["days"][1]["meals"][3]["again"] == ["Thu"]
    assert week["days"][0]["meals"][1]["again"] == []


def test_crop_rotation(week):
    rows = {row["bed"]: row["cells"] for row in week["rotation"]}
    # "none" is not a bed; most planted first, then by name
    assert [row["bed"] for row in week["rotation"]] == ["chicken", "fish", "legumes"]
    assert rows["chicken"] == ["on", "twice", "", "", "", "", ""]
    assert rows["fish"] == ["", "on", "", "on", "", "", ""]


def test_notes_come_from_the_variety_report(week):
    assert week["score"] == 72
    assert week["forecast"] == "Changeable"
    assert week["similar"] == SIMILAR


def test_rotation_rows_are_capped():
    catalog = {1: {"protein": ", ".join(f"p{i}" for i in range(10))}}
    weeks = almanac.build_weeks(
        [("2026-11-16", 1, 1)], {1: ITEMS[1]}, catalog, {"2026-11-16": {"score": None}}
    )
    assert len(weeks[0]["rotation"]) == almanac.ROTATION_ROWS
    assert weeks[0]["forecast"] == "Too few meals to judge"


def test_items_missing_from_the_catalog_are_left_out():
    weeks = almanac.build_weeks(
        [("2026-11-16", 99, 1)], ITEMS, CATALOG, {"2026-11-16": {"score": None}}
    )
    assert weeks[0]["meal_count"] == 0
    assert weeks[0]["days"][0]["meals"] == {}
