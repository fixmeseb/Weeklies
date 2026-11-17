"""
Unit tests for menu_generation.py helper functions.
Tests for: get_meal_and_order_time, get_weekday_and_increment,
filter_allergens, filter_closed_restaurants
"""

import pytest
import pandas as pd
import json
import datetime

from proj2.menu_generation import (
    get_meal_and_order_time,
    get_weekday_and_increment,
    filter_allergens,
    filter_closed_restaurants,
    DAYS_OF_WEEK,
)


class TestGetMealAndOrderTime:
    """Tests for get_meal_and_order_time function"""

    def test_breakfast_meal(self):
        """Test breakfast (meal 1) returns correct name and time"""
        meal, order_time = get_meal_and_order_time(1)
        assert meal == "breakfast"
        assert order_time == 1000

    def test_lunch_meal(self):
        """Test lunch (meal 2) returns correct name and time"""
        meal, order_time = get_meal_and_order_time(2)
        assert meal == "lunch"
        assert order_time == 1400

    def test_dinner_meal(self):
        """Test dinner (meal 3) returns correct name and time"""
        meal, order_time = get_meal_and_order_time(3)
        assert meal == "dinner"
        assert order_time == 2000

    def test_invalid_meal_number(self):
        """Test that invalid meal numbers raise ValueError"""
        with pytest.raises(ValueError):
            get_meal_and_order_time(0)

        with pytest.raises(ValueError):
            get_meal_and_order_time(4)

        with pytest.raises(ValueError):
            get_meal_and_order_time(-1)


class TestGetWeekdayAndIncrement:
    """Tests for get_weekday_and_increment function"""

    def test_valid_date_parsing(self):
        """Test valid date parsing returns correct weekday"""
        next_date, weekday = get_weekday_and_increment("2025-11-20")
        assert weekday == "Thu"  # November 20, 2025 is Thursday
        assert next_date == "2025-11-21"

    def test_monday_increment(self):
        """Test Monday increments to Tuesday"""
        next_date, weekday = get_weekday_and_increment("2025-11-17")
        assert weekday == "Mon"  # November 17, 2025 is Monday
        assert next_date == "2025-11-18"

    def test_sunday_increment_wraps_to_next_week(self):
        """Test Sunday increments to Monday of next week"""
        next_date, weekday = get_weekday_and_increment("2025-11-23")
        assert weekday == "Sun"  # November 23, 2025 is Sunday
        assert next_date == "2025-11-24"  # Monday

    def test_year_boundary_increment(self):
        """Test date increment across year boundary"""
        next_date, weekday = get_weekday_and_increment("2025-12-31")
        assert next_date == "2026-01-01"

    def test_leap_year_february(self):
        """Test February 29 in leap year"""
        next_date, weekday = get_weekday_and_increment("2024-02-29")
        assert next_date == "2024-03-01"

    def test_invalid_date_format(self):
        """Test invalid date formats raise ValueError"""
        with pytest.raises(ValueError):
            get_weekday_and_increment("11-20-2025")  # Wrong format

        with pytest.raises(ValueError):
            get_weekday_and_increment("2025/11/20")  # Wrong format

        with pytest.raises(ValueError):
            get_weekday_and_increment("not-a-date")  # Invalid

    def test_invalid_date_values(self):
        """Test invalid date values raise ValueError"""
        with pytest.raises(ValueError):
            get_weekday_and_increment("2025-13-01")  # Invalid month

        with pytest.raises(ValueError):
            get_weekday_and_increment("2025-02-30")  # Invalid day for month


class TestFilterAllergens:
    """Tests for filter_allergens function"""

    def test_filter_single_allergen(self):
        """Test filtering items with single allergen"""
        items = pd.DataFrame({
            "name": ["Item1", "Item2", "Item3"],
            "allergens": ["Peanuts", None, "Shellfish"]
        })
        filtered = filter_allergens(items, "Peanuts")
        assert len(filtered) == 2
        assert "Item1" not in filtered["name"].values

    def test_filter_multiple_allergens(self):
        """Test filtering items with multiple allergens"""
        items = pd.DataFrame({
            "name": ["Item1", "Item2", "Item3", "Item4"],
            "allergens": ["Peanuts", "Shellfish", "Dairy", None]
        })
        filtered = filter_allergens(items, "Peanuts,Shellfish")
        assert len(filtered) == 2
        assert set(filtered["name"].values) == {"Item3", "Item4"}

    def test_filter_no_allergens_to_filter(self):
        """Test filtering when no allergens specified"""
        items = pd.DataFrame({
            "name": ["Item1", "Item2"],
            "allergens": ["Peanuts", "Shellfish"]
        })
        filtered = filter_allergens(items, "")
        assert len(filtered) == 2

    def test_filter_all_items_contain_allergen(self):
        """Test when all items contain specified allergen"""
        items = pd.DataFrame({
            "name": ["Item1", "Item2"],
            "allergens": ["Peanuts", "Peanuts"]
        })
        filtered = filter_allergens(items, "Peanuts")
        assert len(filtered) == 0

    def test_filter_none_allergens(self):
        """Test filtering with None allergen values"""
        items = pd.DataFrame({
            "name": ["Item1", "Item2", "Item3"],
            "allergens": [None, None, "Shellfish"]
        })
        filtered = filter_allergens(items, "Peanuts")
        assert len(filtered) == 3  # All items pass since Peanuts not found


class TestFilterClosedRestaurants:
    """Tests for filter_closed_restaurants function"""

    def test_restaurant_open_during_time(self):
        """Test restaurant open during specified time"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 2000]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1200)
        assert len(filtered) == 1

    def test_restaurant_closed_during_time(self):
        """Test restaurant closed during specified time"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 1100]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1200)
        assert len(filtered) == 0

    def test_restaurant_multiple_opening_times(self):
        """Test restaurant with multiple opening periods"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 1200, 1400, 2000]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1500)
        assert len(filtered) == 1  # Open in afternoon

    def test_restaurant_gap_between_periods(self):
        """Test restaurant closed during gap between opening periods"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 1100, 1400, 2000]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1200)
        assert len(filtered) == 0  # Closed during gap

    def test_restaurant_odd_number_times(self):
        """Test restaurant with odd number of times (malformed)"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 1100, 1400]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1200)
        assert len(filtered) == 0  # Removed due to malformed data

    def test_restaurant_edge_case_opening_time(self):
        """Test time exactly at opening"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 2000]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1000)
        assert len(filtered) == 1

    def test_restaurant_edge_case_closing_time(self):
        """Test time exactly at closing"""
        restaurants = pd.DataFrame({
            "rtr_id": [1],
            "hours": [json.dumps({"Mon": [1000, 2000]})]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 2000)
        assert len(filtered) == 1

    def test_multiple_restaurants_mixed_status(self):
        """Test filtering multiple restaurants with mixed open/closed status"""
        restaurants = pd.DataFrame({
            "rtr_id": [1, 2, 3],
            "hours": [
                json.dumps({"Mon": [1000, 2000]}),
                json.dumps({"Mon": [800, 900]}),
                json.dumps({"Mon": [1400, 2200]})
            ]
        })
        filtered = filter_closed_restaurants(restaurants, "Mon", 1500)
        assert len(filtered) == 2  # Restaurants 1 and 3 open at 1500
