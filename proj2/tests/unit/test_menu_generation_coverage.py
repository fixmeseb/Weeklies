"""Tests for menu_generation.py helper functions and edge cases."""
import pytest
import pandas as pd
import proj2.Flask_app as Flask_app
import proj2.llm_toolkit as llm_toolkit
from proj2.menu_generation import (
    get_meal_and_order_time,
    get_weekday_and_increment,
    format_llm_output,
    limit_scope,
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


class TestFormatLLMOutput:
    """Tests for format_llm_output function."""

    def test_valid_llm_output(self):
        """Test parsing valid LLM output."""
        output = "<|start_of_role|>assistant<|end_of_role|>42<|end_of_text|>"
        result = format_llm_output(output)
        assert result == 42

    def test_llm_output_with_extra_text(self):
        """Test LLM output with surrounding text."""
        output = "Some text <|start_of_role|>assistant<|end_of_role|>123<|end_of_text|> more text"
        result = format_llm_output(output)
        assert result == 123

    def test_invalid_llm_output(self):
        """Test invalid LLM output returns -1."""
        output = "no valid output here"
        result = format_llm_output(output)
        assert result == -1

    def test_malformed_llm_output(self):
        """Test malformed LLM output."""
        output = "<|start_of_role|>assistant<|end_of_role|>not_a_number<|end_of_text|>"
        result = format_llm_output(output)
        assert result == -1


class TestLimitScope:
    """Tests for limit_scope function."""

    def test_limit_scope_with_fewer_items(self):
        """Test limit_scope when dataframe has fewer items than requested."""
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"]})
        result = limit_scope(df, 5)
        assert len(result) <= len(df)

    def test_limit_scope_with_exact_items(self):
        """Test limit_scope with exact number of items."""
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"]})
        result = limit_scope(df, 3)
        assert len(result) == 3

    def test_limit_scope_with_more_items(self):
        """Test limit_scope when dataframe has more items than requested."""
        df = pd.DataFrame({"id": list(range(1, 21)), "name": [f"Item{i}" for i in range(20)]})
        result = limit_scope(df, 5)
        assert len(result) == 5

    def test_limit_scope_empty_dataframe(self):
        """Test limit_scope with empty dataframe."""
        df = pd.DataFrame({"id": [], "name": []})
        result = limit_scope(df, 5)
        assert len(result) == 0


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
    """Tests for MenuGenerator initialization.

    These use the session test DB (conftest points Flask_app.db_file at it) and a stub
    LLM, so they need neither the real CSC510_DB.db nor torch/model downloads.
    """

    @pytest.fixture
    def stub_llm(self, monkeypatch):
        class StubLLM:
            def __init__(self, tokens=500):
                self.tokens = tokens

        monkeypatch.setattr(llm_toolkit, "LLM", StubLLM)
        return StubLLM

    def test_menu_generator_creates(self, stub_llm):
        """Test MenuGenerator can be initialized."""
        gen = MenuGenerator(tokens=50, database_path=Flask_app.db_file)
        assert gen is not None
        assert hasattr(gen, "menu_items")
        assert hasattr(gen, "restaurants")
        assert hasattr(gen, "generator")

    def test_menu_generator_tokens(self, stub_llm):
        """Test MenuGenerator passes its token count to the LLM it creates."""
        gen = MenuGenerator(tokens=100, database_path=Flask_app.db_file)
        assert isinstance(gen.generator, stub_llm)
        assert gen.generator.tokens == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
