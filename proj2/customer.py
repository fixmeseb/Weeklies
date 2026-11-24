"""The customer's account row, and the diet and planner settings saved on it."""

import json

from flask import request

from proj2 import variety
from proj2.dietary import KNOWN_DIETS
from proj2.plan_optimization import OBJECTIVES, parse_weights
from proj2.plan_rules import parse_allergens
from proj2.sqlQueries import fetch_all, fetch_one

USER_ACCOUNT_COLUMNS = (
    "usr_id, first_name, last_name, email, phone, wallet, preferences, allergies, "
    "generated_menu, address, city, state, zip, breakfast_time, lunch_time, dinner_time, "
    "optimization_weights, weekly_cap_cents, nutrition_targets, strict_targets"
)


def account(conn, email=None, usr_id=None):
    """The logged-in user's "User" row (as sqlite3.Row), by email or id; None if gone."""
    if usr_id:
        return fetch_one(
            conn, f'SELECT {USER_ACCOUNT_COLUMNS} FROM "User" WHERE usr_id = ?', (usr_id,)
        )
    return fetch_one(conn, f'SELECT {USER_ACCOUNT_COLUMNS} FROM "User" WHERE email = ?', (email,))


def _csv_list(value) -> list:
    """The non-empty, stripped entries of a comma-separated string."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


DIET_OPTIONS = {tag: tag.title() for tag in sorted(KNOWN_DIETS)}


def submitted_diet_constraints():
    """Read the checkbox editor or the existing CSV fields used by older clients."""
    if "diet_constraints" not in request.form:
        return tuple(
            (request.form.get(name) or "").strip() for name in ("allergies", "preferences")
        )
    allergies = ", ".join(request.form.getlist("allergies[]"))
    diets = ", ".join(sorted(KNOWN_DIETS.intersection(request.form.getlist("diets[]"))))
    return allergies, diets


def profile_weights(stored, preferences):
    """Give legacy food tags a weight when the account has never set any sliders."""
    weights = json.loads(stored)
    if not variety.soft_preferences(preferences):
        weights.pop("preference", None)
    elif not weights:
        return {"variety": 100, "preference": round(100 * variety.PREFERENCE_WEIGHT)}
    return weights


def configured_weights(stored, preferences):
    weights = profile_weights(stored, preferences)
    return parse_weights(tuple(weights.get(name) or None for name in OBJECTIVES))


def submitted_weights():
    """Read whole-number priorities. An all-zero set selects the default planner."""
    weights = {}
    for name in OBJECTIVES:
        value = request.form.get(f"{name}_weight")
        if value in (None, ""):
            continue
        try:
            weight = int(value)
            if not 0 <= weight <= 100:
                raise ValueError
        except ValueError:
            raise ValueError("Use whole-number weights from 0 to 100.") from None
        weights[name] = weight
    return weights


def diet_summary(conn, allergies, preferences) -> dict:
    """
    What the Profile's Diet chapter says about the user's allergies and preferences.
    Args:
        conn: Open database connection.
        allergies (str): The user's comma-separated allergies.
        preferences (str): The user's comma-separated preferences.
    Returns:
        dict: allergies and preferences as lists, plus how many in-stock dishes the
        allergies set aside ("set_aside") out of how many there are ("dishes"). Matching
        is the meal planner's (proj2.plan_rules.parse_allergens).
    """
    banned = parse_allergens(allergies)
    rows = fetch_all(conn, 'SELECT allergens FROM "MenuItem" WHERE instock IS NULL OR instock = 1')
    return {
        "allergies": _csv_list(allergies),
        "preferences": _csv_list(preferences),
        "set_aside": sum(1 for (tags,) in rows if banned & parse_allergens(tags)),
        "dishes": len(rows),
    }
