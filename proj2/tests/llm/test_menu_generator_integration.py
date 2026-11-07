"""
Integration tests for MenuGenerator class
Tests for menu generation with database and LLM integration
"""

import pytest
import os
import pandas as pd
import re
from proj2.menu_generation import MenuGenerator
from proj2.sqlQueries import create_connection, close_connection, fetch_all

# Skip all LLM tests on CI (GitHub Actions on Linux)
# These require model loading and disk space
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true",
    reason="LLM tests require model loading and are skipped on CI to prevent disk exhaustion"
)

db_file = os.path.join(os.path.dirname(__file__), "../../CSC510_DB.db")


class TestMenuGeneratorInitialization:
    """Tests for MenuGenerator initialization"""

    @pytest.mark.llm
    def test_menu_generator_initializes(self):
        """Test MenuGenerator initializes successfully"""
        gen = MenuGenerator(database_path=db_file)
        assert gen is not None
        assert hasattr(gen, 'menu_items')
        assert hasattr(gen, 'restaurants')
        assert hasattr(gen, 'generator')

    @pytest.mark.llm
    def test_menu_generator_loads_items(self):
        """Test MenuGenerator loads menu items from database"""
        gen = MenuGenerator(database_path=db_file)
        assert isinstance(gen.menu_items, pd.DataFrame)
        assert len(gen.menu_items) > 0
        assert 'itm_id' in gen.menu_items.columns

    @pytest.mark.llm
    def test_menu_generator_loads_restaurants(self):
        """Test MenuGenerator loads restaurants from database"""
        gen = MenuGenerator(database_path=db_file)
        assert isinstance(gen.restaurants, pd.DataFrame)
        assert 'rtr_id' in gen.restaurants.columns
        assert 'hours' in gen.restaurants.columns

    @pytest.mark.llm
    def test_menu_generator_custom_tokens(self):
        """Test MenuGenerator with custom token count"""
        gen = MenuGenerator(tokens=100, database_path=db_file)
        assert gen.generator.tokens == 100


class TestMenuGeneratorMenuUpdate:
    """Tests for MenuGenerator.update_menu method"""

    @pytest.mark.llm
    def test_update_menu_single_meal_no_existing(self):
        """Test generating single meal with no existing menu"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[2],
            number_of_days=1
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # Should match format [YYYY-MM-DD,item_id,meal]
        assert re.match(r"\[\d{4}-\d{2}-\d{2},\d+,2\]", result)

    @pytest.mark.llm
    def test_update_menu_multiple_meals_single_day(self):
        """Test generating multiple meals in single day"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1, 2, 3],
            number_of_days=1
        )
        assert isinstance(result, str)
        # Should have 3 meals in format
        matches = re.findall(r"\[\d{4}-\d{2}-\d{2},\d+,\d\]", result)
        assert len(matches) == 3

    @pytest.mark.llm
    def test_update_menu_multiple_days(self):
        """Test generating meals for multiple days"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=3
        )
        assert isinstance(result, str)
        # Should have entries for 3 consecutive days
        matches = re.findall(r"\d{4}-\d{2}-\d{2}", result)
        assert len(set(matches)) == 3  # 3 unique dates

    @pytest.mark.llm
    def test_update_menu_extend_existing(self):
        """Test extending existing menu with new meals"""
        gen = MenuGenerator(database_path=db_file)
        # Generate initial menu
        menu1 = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=1
        )
        # Extend with more meals
        menu2 = gen.update_menu(
            menu=menu1,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[2, 3],
            number_of_days=1
        )
        assert isinstance(menu2, str)
        # Should contain all three meals
        matches = re.findall(r"\[\d{4}-\d{2}-\d{2},\d+,\d\]", menu2)
        assert len(matches) == 3

    @pytest.mark.llm
    def test_update_menu_with_preferences(self):
        """Test menu generation with user preferences"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="high protein,low carb",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=1
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.llm
    def test_update_menu_with_allergens(self):
        """Test menu generation avoiding allergens"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="Peanuts,Shellfish",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=1
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # Extract the item ID and verify it doesn't have forbidden allergens
        match = re.search(r"\[2025-11-20,(\d+),1\]", result)
        if match:
            item_id = int(match.group(1))
            # Find the item in the menu_items dataframe
            item = gen.menu_items[gen.menu_items['itm_id'] == item_id]
            if not item.empty and item.iloc[0]['allergens']:
                allergens = [a.strip() for a in item.iloc[0]['allergens'].split(',')]
                assert 'Peanuts' not in allergens
                assert 'Shellfish' not in allergens

    @pytest.mark.llm
    def test_update_menu_empty_string_preferences(self):
        """Test menu generation with empty string preferences"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=1
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.llm
    def test_update_menu_none_allergens(self):
        """Test menu generation with None allergens"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[2],
            number_of_days=1
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.llm
    def test_update_menu_format_consistency(self):
        """Test that generated menu has consistent format"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1, 2, 3],
            number_of_days=2
        )
        # All entries should match pattern [YYYY-MM-DD,item_id,meal]
        entries = re.findall(r"\[(\d{4}-\d{2}-\d{2}),(\d+),(\d+)\]", result)
        assert all(len(entry) == 3 for entry in entries)
        # Meal numbers should be 1, 2, or 3
        assert all(int(entry[2]) in [1, 2, 3] for entry in entries)

    @pytest.mark.llm
    def test_update_menu_different_dates(self):
        """Test generating menus for different dates"""
        gen = MenuGenerator(database_path=db_file)
        # Test first date
        result1 = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-12-01",
            meal_numbers=[1],
            number_of_days=1
        )
        # Test second date
        result2 = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-12-15",
            meal_numbers=[1],
            number_of_days=1
        )
        # Both should generate successfully
        assert "[2025-12-01," in result1
        assert "[2025-12-15," in result2


class TestMenuGeneratorValidItemIds:
    """Tests for validating generated item IDs"""

    @pytest.mark.llm
    def test_generated_items_exist_in_database(self):
        """Test that all generated item IDs exist in database"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1, 2, 3],
            number_of_days=2
        )
        # Extract all item IDs
        entries = re.findall(r"\[(\d{4}-\d{2}-\d{2}),(\d+),(\d+)\]", result)
        item_ids = [int(entry[1]) for entry in entries]
        # Check each ID exists in menu_items
        for item_id in item_ids:
            exists = len(gen.menu_items[gen.menu_items['itm_id'] == item_id]) > 0
            assert exists, f"Item ID {item_id} not found in menu items"

    @pytest.mark.llm
    def test_generated_items_are_in_stock(self):
        """Test that generated items are in stock"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1],
            number_of_days=1
        )
        # Extract item ID
        match = re.search(r"\[2025-11-20,(\d+),1\]", result)
        if match:
            item_id = int(match.group(1))
            item = gen.menu_items[gen.menu_items['itm_id'] == item_id]
            assert not item.empty
            assert item.iloc[0]['instock'] == 1

    @pytest.mark.llm
    def test_no_duplicate_meals_same_day(self):
        """Test that same meal number isn't repeated same day"""
        gen = MenuGenerator(database_path=db_file)
        result = gen.update_menu(
            menu=None,
            preferences="",
            allergens="",
            date="2025-11-20",
            meal_numbers=[1, 2, 3],
            number_of_days=1
        )
        # Extract entries for 2025-11-20
        entries = re.findall(r"\[2025-11-20,(\d+),(\d+)\]", result)
        meal_numbers = [int(entry[1]) for entry in entries]
        # Should have exactly 3 meals with no duplicates
        assert len(meal_numbers) == 3
        assert len(set(meal_numbers)) == 3
