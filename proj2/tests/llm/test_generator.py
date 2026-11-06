import pytest
import os
import pandas as pd
from unittest.mock import Mock, patch

import proj2.menu_generation as menu_generation
from proj2.sqlQueries import *
from proj2.Flask_app import parse_generated_menu, app as flask_app

# Skip all LLM tests on CI (GitHub Actions on Linux)
# These require a GPU or significant CPU resources and the LLM model to be available
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true",
    reason="LLM tests require model loading and are skipped on CI"
)

# Initialize generator - will be skipped anyway on CI
try:
    generator = menu_generation.MenuGenerator(database_path=flask_app.config["DATABASE"])
except Exception as e:
    # If generator fails to initialize (e.g., on CI), set to None
    # Tests will be skipped anyway due to pytestmark
    generator = None


# Module-level fixtures for test data
@pytest.fixture(scope="module")
def menu_items_data(seed_minimal_data):
    """Load menu items from the test database."""
    conn = create_connection(flask_app.config["DATABASE"])
    try:
        items = pd.read_sql_query("SELECT * FROM MenuItem WHERE instock == 1", conn)
        return items
    finally:
        close_connection(conn)


@pytest.fixture(scope="module")
def menugenerator_single_menus():
    menugenerator_single_menu1 = generator.update_menu(
        menu=None,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[2],
    )
    menugenerator_single_menu2 = generator.update_menu(
        menu=menugenerator_single_menu1,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[3],
    )
    menugenerator_single_menu3 = generator.update_menu(
        menu=menugenerator_single_menu2,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[1],
    )
    menugenerator_single_menu4 = generator.update_menu(
        menu=menugenerator_single_menu3,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[2],
    )
    menugenerator_single_menu5 = generator.update_menu(
        menu=menugenerator_single_menu4,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[3],
    )
    return (
        menugenerator_single_menu1,
        menugenerator_single_menu2,
        menugenerator_single_menu3,
        menugenerator_single_menu4,
        menugenerator_single_menu5,
    )


def test_MenuGenerator_single_no_regression(menugenerator_single_menus):
    (
        menugenerator_single_menu1,
        menugenerator_single_menu2,
        menugenerator_single_menu3,
        menugenerator_single_menu4,
        menugenerator_single_menu5,
    ) = menugenerator_single_menus
    parsed1 = parse_generated_menu(menugenerator_single_menu1)
    parsed2 = parse_generated_menu(menugenerator_single_menu2)
    parsed3 = parse_generated_menu(menugenerator_single_menu3)
    parsed4 = parse_generated_menu(menugenerator_single_menu4)
    parsed5 = parse_generated_menu(menugenerator_single_menu5)

    assert parsed1["2025-10-14"][0] == parsed2["2025-10-14"][0]
    assert parsed1["2025-10-14"][0] == parsed3["2025-10-14"][0]
    assert parsed1["2025-10-14"][0] == parsed4["2025-10-14"][0]
    assert parsed1["2025-10-14"][0] == parsed5["2025-10-14"][0]
    assert parsed2["2025-10-14"][1] == parsed3["2025-10-14"][1]
    assert parsed2["2025-10-14"][1] == parsed4["2025-10-14"][1]
    assert parsed2["2025-10-14"][1] == parsed5["2025-10-14"][1]
    assert parsed3["2025-10-15"][0] == parsed4["2025-10-15"][0]
    assert parsed3["2025-10-15"][0] == parsed5["2025-10-15"][0]
    assert parsed4["2025-10-15"][1] == parsed5["2025-10-15"][1]


def test_MenuGenerator_single_valid_items(menugenerator_single_menus, menu_items_data):
    (
        menugenerator_single_menu1,
        menugenerator_single_menu2,
        menugenerator_single_menu3,
        menugenerator_single_menu4,
        menugenerator_single_menu5,
    ) = menugenerator_single_menus
    parsed5 = parse_generated_menu(menugenerator_single_menu5)

    assert menu_items_data[menu_items_data["itm_id"] == parsed5["2025-10-14"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed5["2025-10-14"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed5["2025-10-15"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed5["2025-10-15"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed5["2025-10-15"][2]["itm_id"]].shape[0] == 1


def test_MenuGenerator_single_correct_meals(menugenerator_single_menus):
    (
        menugenerator_single_menu1,
        menugenerator_single_menu2,
        menugenerator_single_menu3,
        menugenerator_single_menu4,
        menugenerator_single_menu5,
    ) = menugenerator_single_menus
    parsed5 = parse_generated_menu(menugenerator_single_menu5)

    assert parsed5["2025-10-14"][0]["meal"] == 2
    assert parsed5["2025-10-14"][1]["meal"] == 3
    assert parsed5["2025-10-15"][0]["meal"] == 1
    assert parsed5["2025-10-15"][1]["meal"] == 2
    assert parsed5["2025-10-15"][2]["meal"] == 3


@pytest.fixture(scope="module")
def menugenerator_multiple_meals_menus():
    menugenerator_multiple_meals_menu1 = generator.update_menu(
        menu=None,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[2, 3],
    )
    menugenerator_multiple_meals_menu2 = generator.update_menu(
        menu=menugenerator_multiple_meals_menu1,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[1, 2, 3],
    )
    return menugenerator_multiple_meals_menu1, menugenerator_multiple_meals_menu2


def test_MenuGenerator_multiple_meals_no_regression(menugenerator_multiple_meals_menus):
    menugenerator_multiple_meals_menu1, menugenerator_multiple_meals_menu2 = (
        menugenerator_multiple_meals_menus
    )
    parsed1 = parse_generated_menu(menugenerator_multiple_meals_menu1)
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_menu2)

    assert parsed1["2025-10-14"][0] == parsed2["2025-10-14"][0]
    assert parsed1["2025-10-14"][1] == parsed2["2025-10-14"][1]


def test_MenuGenerator_multiple_meals_valid_items(menugenerator_multiple_meals_menus, menu_items_data):
    menugenerator_multiple_meals_menu1, menugenerator_multiple_meals_menu2 = (
        menugenerator_multiple_meals_menus
    )
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_menu2)

    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-14"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-14"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][2]["itm_id"]].shape[0] == 1


def test_MenuGenerator_multiple_meals_correct_meals(menugenerator_multiple_meals_menus):
    menugenerator_multiple_meals_menu1, menugenerator_multiple_meals_menu2 = (
        menugenerator_multiple_meals_menus
    )
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_menu2)

    assert parsed2["2025-10-14"][0]["meal"] == 2
    assert parsed2["2025-10-14"][1]["meal"] == 3
    assert parsed2["2025-10-15"][0]["meal"] == 1
    assert parsed2["2025-10-15"][1]["meal"] == 2
    assert parsed2["2025-10-15"][2]["meal"] == 3


@pytest.fixture(scope="module")
def menugenerator_multiple_meals_oof_menus():
    menugenerator_multiple_meals_oof_menu1 = generator.update_menu(
        menu=None,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[3, 2],
    )
    menugenerator_multiple_meals_oof_menu2 = generator.update_menu(
        menu=menugenerator_multiple_meals_oof_menu1,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[2, 1, 3],
    )
    return menugenerator_multiple_meals_oof_menu1, menugenerator_multiple_meals_oof_menu2


def test_MenuGenerator_multiple_meals_out_of_order_no_regression(
    menugenerator_multiple_meals_oof_menus,
):
    menugenerator_multiple_meals_oof_menu1, menugenerator_multiple_meals_oof_menu2 = (
        menugenerator_multiple_meals_oof_menus
    )
    parsed1 = parse_generated_menu(menugenerator_multiple_meals_oof_menu1)
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_oof_menu2)

    assert parsed1["2025-10-14"][0] == parsed2["2025-10-14"][0]
    assert parsed1["2025-10-14"][1] == parsed2["2025-10-14"][1]


def test_MenuGenerator_multiple_meals_out_of_order_valid_items(
    menugenerator_multiple_meals_oof_menus,
    menu_items_data,
):
    menugenerator_multiple_meals_oof_menu1, menugenerator_multiple_meals_oof_menu2 = (
        menugenerator_multiple_meals_oof_menus
    )
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_oof_menu2)

    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-14"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-14"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed2["2025-10-15"][2]["itm_id"]].shape[0] == 1


def test_MenuGenerator_multiple_meals_out_of_order_correct_meals(
    menugenerator_multiple_meals_oof_menus,
):
    menugenerator_multiple_meals_oof_menu1, menugenerator_multiple_meals_oof_menu2 = (
        menugenerator_multiple_meals_oof_menus
    )
    parsed2 = parse_generated_menu(menugenerator_multiple_meals_oof_menu2)

    assert parsed2["2025-10-14"][0]["meal"] == 3
    assert parsed2["2025-10-14"][1]["meal"] == 2
    assert parsed2["2025-10-15"][0]["meal"] == 2
    assert parsed2["2025-10-15"][1]["meal"] == 1
    assert parsed2["2025-10-15"][2]["meal"] == 3


@pytest.fixture(scope="module")
def menugenerator_multiple_days_menus():
    menugenerator_multiple_days_menu1 = generator.update_menu(
        menu=None,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-15",
        meal_numbers=[1],
        number_of_days=1,
    )
    menugenerator_multiple_days_menu2 = generator.update_menu(
        menu=menugenerator_multiple_days_menu1,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[2],
        number_of_days=2,
    )
    menugenerator_multiple_days_menu3 = generator.update_menu(
        menu=menugenerator_multiple_days_menu2,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[3],
        number_of_days=2,
    )
    return (
        menugenerator_multiple_days_menu1,
        menugenerator_multiple_days_menu2,
        menugenerator_multiple_days_menu3,
    )


def test_MenuGenerator_multiple_days_no_regression(menugenerator_multiple_days_menus):
    (
        menugenerator_multiple_days_menu1,
        menugenerator_multiple_days_menu2,
        menugenerator_multiple_days_menu3,
    ) = menugenerator_multiple_days_menus
    parsed1 = parse_generated_menu(menugenerator_multiple_days_menu1)
    parsed2 = parse_generated_menu(menugenerator_multiple_days_menu2)
    parsed3 = parse_generated_menu(menugenerator_multiple_days_menu3)

    assert parsed1["2025-10-15"][0] == parsed2["2025-10-15"][0]
    assert parsed1["2025-10-15"][0] == parsed3["2025-10-15"][0]
    assert parsed2["2025-10-14"][0] == parsed3["2025-10-14"][0]
    assert parsed2["2025-10-15"][1] == parsed3["2025-10-15"][1]


def test_MenuGenerator_multiple_days_valid_items(menugenerator_multiple_days_menus, menu_items_data):
    (
        menugenerator_multiple_days_menu1,
        menugenerator_multiple_days_menu2,
        menugenerator_multiple_days_menu3,
    ) = menugenerator_multiple_days_menus
    parsed3 = parse_generated_menu(menugenerator_multiple_days_menu3)

    assert menu_items_data[menu_items_data["itm_id"] == parsed3["2025-10-14"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed3["2025-10-14"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed3["2025-10-15"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed3["2025-10-15"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed3["2025-10-15"][2]["itm_id"]].shape[0] == 1


def test_MenuGenerator_multiple_days_correct_meals(menugenerator_multiple_days_menus):
    (
        menugenerator_multiple_days_menu1,
        menugenerator_multiple_days_menu2,
        menugenerator_multiple_days_menu3,
    ) = menugenerator_multiple_days_menus
    parsed3 = parse_generated_menu(menugenerator_multiple_days_menu3)

    assert parsed3["2025-10-14"][0]["meal"] == 2
    assert parsed3["2025-10-14"][1]["meal"] == 3
    assert parsed3["2025-10-15"][0]["meal"] == 1
    assert parsed3["2025-10-15"][1]["meal"] == 2
    assert parsed3["2025-10-15"][2]["meal"] == 3


@pytest.fixture(scope="module")
def menugenerator_multiple_days_multiple_meals_menu():
    menu = generator.update_menu(
        menu=None,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[1, 2, 3],
        number_of_days=2,
    )
    return menu


@pytest.fixture(scope="module")
def menugenerator_partial_duplicate(menugenerator_multiple_days_multiple_meals_menu):
    menu = generator.update_menu(
        menu=menugenerator_multiple_days_multiple_meals_menu,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[2, 3],
        number_of_days=3,
    )
    return menu


def test_MenuGenerator_multiple_days_multiple_meals_valid_items(
    menugenerator_multiple_days_multiple_meals_menu,
    menu_items_data,
):
    parsed = parse_generated_menu(menugenerator_multiple_days_multiple_meals_menu)

    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-14"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-14"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-14"][2]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-15"][0]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-15"][1]["itm_id"]].shape[0] == 1
    assert menu_items_data[menu_items_data["itm_id"] == parsed["2025-10-15"][2]["itm_id"]].shape[0] == 1


def test_MenuGenerator_multiple_days_multiple_meals_correct_meals(
    menugenerator_multiple_days_multiple_meals_menu,
):
    parsed = parse_generated_menu(menugenerator_multiple_days_multiple_meals_menu)

    assert parsed["2025-10-14"][0]["meal"] == 1
    assert parsed["2025-10-14"][1]["meal"] == 2
    assert parsed["2025-10-14"][2]["meal"] == 3
    assert parsed["2025-10-15"][0]["meal"] == 1
    assert parsed["2025-10-15"][1]["meal"] == 2
    assert parsed["2025-10-15"][2]["meal"] == 3


def test_MenuGenerator_full_duplicate(menugenerator_multiple_days_multiple_meals_menu):
    attempt_duplicate = generator.update_menu(
        menu=menugenerator_multiple_days_multiple_meals_menu,
        preferences="high protein,low carb",
        allergens="Peanuts,Shellfish",
        date="2025-10-14",
        meal_numbers=[1, 2, 3],
        number_of_days=2,
    )
    assert attempt_duplicate == menugenerator_multiple_days_multiple_meals_menu


def test_MenuGenerator_partial_duplicate_no_regression(
    menugenerator_multiple_days_multiple_meals_menu, menugenerator_partial_duplicate
):
    parse_original = parse_generated_menu(menugenerator_multiple_days_multiple_meals_menu)
    parse_partial_duplicate = parse_generated_menu(menugenerator_partial_duplicate)

    assert parse_original["2025-10-14"][0] == parse_partial_duplicate["2025-10-14"][0]
    assert parse_original["2025-10-14"][1] == parse_partial_duplicate["2025-10-14"][1]
    assert parse_original["2025-10-14"][2] == parse_partial_duplicate["2025-10-14"][2]
    assert parse_original["2025-10-15"][0] == parse_partial_duplicate["2025-10-15"][0]
    assert parse_original["2025-10-15"][1] == parse_partial_duplicate["2025-10-15"][1]
    assert parse_original["2025-10-15"][2] == parse_partial_duplicate["2025-10-15"][2]


def test_MenuGenerator_partial_duplicate_valid_items(menugenerator_partial_duplicate, menu_items_data):
    parse_partial_duplicate = parse_generated_menu(menugenerator_partial_duplicate)

    assert (
        menu_items_data[
            menu_items_data["itm_id"] == parse_partial_duplicate["2025-10-16"][0]["itm_id"]
        ].shape[0]
        == 1
    )
    assert (
        menu_items_data[
            menu_items_data["itm_id"] == parse_partial_duplicate["2025-10-16"][1]["itm_id"]
        ].shape[0]
        == 1
    )


def test_MenuGenerator_partial_duplicate_correct_meals(menugenerator_partial_duplicate):
    parse_partial_duplicate = parse_generated_menu(menugenerator_partial_duplicate)

    assert parse_partial_duplicate["2025-10-16"][0]["meal"] == 2
    assert parse_partial_duplicate["2025-10-16"][1]["meal"] == 3
