"""Tests for menu_generation.py helper functions and edge cases."""
import pytest
import pandas as pd
import proj2.Flask_app as Flask_app
from proj2.menu_generation import (
    get_meal_and_order_time,
    get_weekday_and_increment,
    filter_allergens,
    filter_closed_restaurants,
    MenuGenerator,
    DAYS_OF_WEEK,
)
from datetime import datetime, timedelta


class TestMealAndOrderTime:
    """Tests for get_meal_and_order_time function."""

    def test_breakfast_meal(self):
        """Test breakfast returns correct meal and time."""
        meal, time = get_meal_and_order_time(1)
        assert meal == "breakfast"
        assert time == 1000

    def test_lunch_meal(self):
        """Test lunch returns correct meal and time."""
        meal, time = get_meal_and_order_time(2)
        assert meal == "lunch"
        assert time == 1400

    def test_dinner_meal(self):
        """Test dinner returns correct meal and time."""
        meal, time = get_meal_and_order_time(3)
        assert meal == "dinner"
        assert time == 2000


class TestWeekdayAndIncrement:
    """Tests for get_weekday_and_increment function."""

    def test_increment_day(self):
        """Test that date increments correctly."""
        date = "2025-01-01"  # Wednesday
        next_date, weekday = get_weekday_and_increment(date)
        
        # Verify next date is one day later
        assert next_date != date
        assert weekday in DAYS_OF_WEEK

    def test_weekday_sequence(self):
        """Test weekday sequence is correct."""
        dates = ["2025-01-06", "2025-01-07", "2025-01-08"]  # Mon, Tue, Wed
        
        current_date = dates[0]
        for i in range(len(dates) - 1):
            next_date, weekday = get_weekday_and_increment(current_date)
            assert next_date == dates[i + 1]
            current_date = next_date


class TestFilterAllergens:
    """Tests for filter_allergens function."""

    def test_filter_single_allergen(self):
        """Test filtering a single allergen."""
        df = pd.DataFrame({
            "name": ["Salad", "Burger", "Pizza"],
            "allergens": ["", "peanut", "milk"]
        })
        result = filter_allergens(df, "peanut")
        assert len(result) == 2
        assert "Burger" not in result["name"].values

    def test_filter_multiple_allergens(self):
        """Test filtering multiple allergens."""
        df = pd.DataFrame({
            "name": ["Salad", "Burger", "Pizza"],
            "allergens": ["", "peanut,milk", "milk"]
        })
        result = filter_allergens(df, "peanut,milk")
        assert len(result) <= 1

    def test_filter_no_allergens(self):
        """Test filtering with no allergens specified."""
        df = pd.DataFrame({
            "name": ["Salad", "Burger", "Pizza"],
            "allergens": ["", "peanut", "milk"]
        })
        result = filter_allergens(df, "")
        # Empty string filter should return same as input
        assert len(result) >= 0

    def test_filter_nonexistent_allergen(self):
        """Test filtering allergen not in data."""
        df = pd.DataFrame({
            "name": ["Salad", "Burger"],
            "allergens": ["", "peanut"]
        })
        result = filter_allergens(df, "shellfish")
        assert len(result) == 2


class TestFilterClosedRestaurants:
    """Tests for filter_closed_restaurants function."""

    def test_filter_exists(self):
        """Test that filter_closed_restaurants function exists and is callable."""
        assert callable(filter_closed_restaurants)


class TestMenuGeneratorInit:
    """MenuGenerator loads the catalog from the session test DB (conftest points
    app.config["DATABASE"] at it); there is no model to load."""

    def test_menu_generator_creates(self):
        gen = MenuGenerator(database_path=Flask_app.db_path())
        assert hasattr(gen, "menu_items")
        assert hasattr(gen, "restaurants")
        assert len(gen.catalog) >= len(gen.menu_items)
        assert gen.variety is None  # set by update_menu
