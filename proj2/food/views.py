"""Loads every module that adds routes to the food blueprint."""

from proj2.food import (  # noqa: F401  (imported for their routes)
    analytics,
    db_view,
    orders,
    owner,
    owner_auth,
    owner_menu,
    plan,
    restaurants,
    reviews,
)
from proj2.food.blueprint import bp  # noqa: F401
