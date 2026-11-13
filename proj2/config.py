"""
Settings shared by the app, the meal generator and the maintenance scripts.

Each value has a default that works for local development and can be overridden with
an environment variable (`flask run` loads them from .env; see .env.example).
This module imports nothing beyond the standard library so scripts can use it cheaply.
"""

import os
import secrets

_PROJ_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------- Database ----------------------

DB_PATH_ENV = "WEEKLIES_DB_PATH"
DEFAULT_DB_PATH = os.path.join(_PROJ_DIR, "CSC510_DB.db")


def db_path(environ=None) -> str:
    """
    Path to the SQLite database.
    Args:
        environ (Mapping | None): Environment to read; defaults to os.environ.
    Returns:
        str: WEEKLIES_DB_PATH if set (made absolute), otherwise proj2/CSC510_DB.db.
    """
    environ = os.environ if environ is None else environ
    override = (environ.get(DB_PATH_ENV) or "").strip()
    return os.path.abspath(override) if override else DEFAULT_DB_PATH


# ---------------------- Order charges ----------------------
# The server computes the charges that are stored and billed; templates receive the same
# values through the `order_fees` context variable so the totals they preview match.

TAX_RATE = 0.0725
DELIVERY_FEE = 3.99
SERVICE_FEE = 1.49


def order_fees() -> dict:
    """
    The fee schedule as a JSON-friendly dict, for templates.
    Returns:
        dict: tax_rate, delivery_fee and service_fee.
    """
    return {"tax_rate": TAX_RATE, "delivery_fee": DELIVERY_FEE, "service_fee": SERVICE_FEE}


# ---------------------- Seed-script passwords ----------------------

SEED_PASSWORD_ENV = "WEEKLIES_SEED_PASSWORD"


def seed_password(environ=None) -> str:
    """
    Password for accounts created or reset by the seed scripts.
    Args:
        environ (Mapping | None): Environment to read; defaults to os.environ.
    Returns:
        str: WEEKLIES_SEED_PASSWORD if set; otherwise a new random password, which the
        calling script prints, so a seeded database never ships a guessable login.
    """
    environ = os.environ if environ is None else environ
    return (environ.get(SEED_PASSWORD_ENV) or "").strip() or secrets.token_urlsafe(12)
