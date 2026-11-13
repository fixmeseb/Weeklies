"""
Hard dietary rules (vegetarian, vegan, halal, ...) for meal generation and swaps.

A user's diet is read from the known diet words in their comma-separated preferences,
e.g. "Vegetarian, Italian" requires "vegetarian"; "Italian" stays a soft preference
(proj2.variety.preference_match). Each menu item declares the diets it satisfies in MenuItem.diet_tags.

The check fails closed: an item without a tag does not satisfy that diet, the same way
a missing price is never treated as free. Allergens remain a separate filter, but
requests may not drop the account's allergies either (with_account_allergies).
"""

import pandas as pd

## Diets enforced as hard rules. Any other preference word is a soft preference.
KNOWN_DIETS = frozenset({"vegetarian", "vegan", "pescatarian", "halal", "kosher", "gluten-free"})

## A tag also satisfies every diet it implies (vegan food is vegetarian, and so on)
IMPLIED_DIETS = {
    "vegan": {"vegetarian", "pescatarian"},
    "vegetarian": {"pescatarian"},
}

DIET_TAGS_COLUMN = "diet_tags"


class DietaryConstraintError(ValueError):
    """No menu item satisfies the user's dietary requirements for a meal slot."""


def normalize_tag(value: str) -> str:
    """Casefold a tag and join its words with hyphens ("Gluten Free" -> "gluten-free")."""
    return "-".join(str(value).replace("_", " ").replace("-", " ").casefold().split())


def _split_tags(value) -> set:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return set()
    return {normalize_tag(tag) for tag in str(value).split(",") if tag.strip()}


def required_diets(preferences) -> set:
    """
    Returns the diets a user must be held to

    Args:
        preferences (str | None): The user's comma-separated preferences

    Returns:
        set: The normalized KNOWN_DIETS named in the preferences
    """
    return _split_tags(preferences) & KNOWN_DIETS


def satisfied_diets(diet_tags) -> set:
    """
    Returns every diet a menu item satisfies, including implied ones

    Args:
        diet_tags (str | None): The item's comma-separated MenuItem.diet_tags

    Returns:
        set: The normalized diets the item satisfies
    """
    tags = _split_tags(diet_tags) & KNOWN_DIETS
    for tag in list(tags):
        tags |= IMPLIED_DIETS.get(tag, set())
    return tags


def missing_diets(diet_tags, required: set) -> set:
    """Returns the required diets that an item with these tags does not satisfy."""
    return set(required) - satisfied_diets(diet_tags)


def filter_diets(menu_items: pd.DataFrame, preferences) -> pd.DataFrame:
    """
    Keeps only the menu items that satisfy every diet named in the preferences

    Args:
        menu_items (pd.DataFrame): Menu items; a missing diet_tags column means no item is tagged
        preferences (str | None): The user's comma-separated preferences

    Returns:
        pd.DataFrame: The items that satisfy every required diet
    """
    required = required_diets(preferences)
    if not required:
        return menu_items.copy()
    if DIET_TAGS_COLUMN not in menu_items.columns:
        return menu_items.iloc[0:0].copy()
    keep = menu_items[DIET_TAGS_COLUMN].map(lambda tags: not missing_diets(tags, required))
    return menu_items.loc[keep.astype(bool)].copy()


def has_diet_tags_column(conn) -> bool:
    """Whether the MenuItem table has a diet_tags column (older databases do not)."""
    columns = conn.execute('PRAGMA table_info("MenuItem")').fetchall()
    return any(column[1] == DIET_TAGS_COLUMN for column in columns)


def ensure_diet_tags_column(conn) -> bool:
    """
    Adds MenuItem.diet_tags to an older database; safe to run more than once

    Args:
        conn (sqlite3.Connection): An open database connection

    Returns:
        bool: True if the column was added, False if it already existed
    """
    if has_diet_tags_column(conn):
        return False
    if conn.execute("PRAGMA user_version").fetchone()[0] > 0:
        # Made by init-db: add the column through the migrations, so a later
        # `flask migrate` does not try to add it a second time.
        from proj2.db_cli import apply_migrations

        apply_migrations(conn)
        return True
    conn.execute(f'ALTER TABLE "MenuItem" ADD COLUMN {DIET_TAGS_COLUMN} TEXT')
    conn.commit()
    return True


def with_account_diets(preferences, account_preferences) -> str:
    """
    Adds the diets on the user's account to preferences supplied with a request

    A request may change the soft preferences used for ranking, but it cannot drop a
    diet the account requires.

    Args:
        preferences (str | None): Preferences sent with the request
        account_preferences (str | None): Preferences stored on the user's account

    Returns:
        str: The request preferences followed by any account diets they did not name
    """
    preferences = (preferences or "").strip()
    extra = sorted(required_diets(account_preferences) - required_diets(preferences))
    return ", ".join([part for part in [preferences, *extra] if part])


def with_account_allergies(allergies, account_allergies) -> str:
    """
    Adds the allergies on the user's account to allergens supplied with a request

    A request may add allergens to avoid, but it cannot drop one the account lists.
    Matching ignores case and surrounding spaces, like menu_generation.filter_allergens.

    Args:
        allergies (str | None): Comma-separated allergens sent with the request
        account_allergies (str | None): Comma-separated allergies stored on the account

    Returns:
        str: The request allergens followed by any account allergies they did not name
    """
    parts = [tag.strip() for tag in (allergies or "").split(",") if tag.strip()]
    named = {tag.casefold() for tag in parts}
    for tag in (account_allergies or "").split(","):
        tag = tag.strip()
        if tag and tag.casefold() not in named:
            parts.append(tag)
            named.add(tag.casefold())
    return ", ".join(parts)
