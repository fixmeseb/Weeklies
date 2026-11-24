"""
One rule for how a restaurant joins Weeklies.

Until now nothing in the application wrote to ``Restaurant``. Every restaurant came from
``proj2.seed``, so the owner-facing half of the product -- the order queue, the analytics,
the reviews, and the menu editor added alongside this module -- could only ever be reached
by an account a developer had seeded. There was a ``/restaurant/login`` with no door
behind it. This module is the write path.

**Why the form writes per-day JSON rather than free text.**
``Restaurant.hours`` is read by two consumers that do not agree on a format.
``proj2.hours.format_hours`` renders either per-day JSON or free text, so prose hours look
perfectly fine on every page a person sees. ``proj2.plan_rules.is_restaurant_open`` parses
JSON only, and returns ``False`` for anything it cannot read -- so a restaurant whose hours
are prose is never open, is dropped from the planner's candidate pool, and says nothing
about it. ``menu_generation`` surfaces that mismatch only in the one case where *no*
restaurant is open at all; while any seeded restaurant still matches, a prose-hours
restaurant is simply invisible, with no error on any page.

``proj2.demo_menu`` seeds all 11 restaurants through ``_daily()``, so a freshly seeded
catalog is entirely JSON and the hazard is in the column's contract rather than in that
data. It is not hypothetical: a development database carried two prose rows left by a
seed predating ``_daily()``, and those two restaurants could never be planned from while
every page displayed their hours normally. Any database older than that change, or
hand-edited, holds the same silent rows.

A sign-up form that accepted "11am - 10pm" would have let every new restaurant join into
that same silence -- the worst kind of bug for somebody who has just signed up, because
the product looks like it is working. So the form collects an opening and closing time
per day and stores the JSON contract, and ``format_hours`` turns it back into prose for
display. The two formats stop being two contracts: JSON is what is written, prose is
only ever a rendering of it.

**Why a closing time must be after its opening time.** ``is_restaurant_open`` tests
``open <= time <= close`` against a single day with no wrap past midnight, so a window
such as 18:00-02:00 is not an overnight shift to it -- it is a window that no time
satisfies. Stored, it would read on the page as if the restaurant were open late while
the planner treated the day as closed. The form refuses it and says to leave the day
closed instead, because silently unplannable is the one outcome this module exists to
prevent. A restaurant that genuinely serves past midnight is a real gap, but it is a gap
in ``is_restaurant_open``, and it belongs with that function rather than behind a form
that would mis-store it.
"""

import json
import re
from dataclasses import dataclass, field

from werkzeug.security import generate_password_hash

from proj2.hours import DAYS
from proj2.sqlQueries import execute_query, fetch_one

## Columns the sign-up form writes. rtr_id is assigned by the database.
COLUMNS = (
    "name",
    "description",
    "phone",
    "email",
    "password_HS",
    "address",
    "city",
    "state",
    "zip",
    "hours",
    "status",
)

## What a restaurant may set its door to. The planner reads 'open' only
## (menu_generation: WHERE LOWER(TRIM(status)) = 'open').
STATUSES = ("open", "closed")

NAME_MAX = 120
DESCRIPTION_MAX = 1000
ADDRESS_MAX = 200
CITY_MAX = 80
EMAIL_MAX = 254
PASSWORD_MIN = 8

## Mirrors proj2.auth.views.register, which is the other door into the same product.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
## Five digits, or ZIP+4.
ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")
PHONE_DIGITS_MIN = 7
PHONE_DIGITS_MAX = 15  # E.164


@dataclass
class Validated:
    """A submitted restaurant, checked. ``values`` is only safe to store when ``ok``."""

    values: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)  # field name -> one message

    @property
    def ok(self) -> bool:
        return not self.errors


def _text(submitted, key, limit, *, required=True, label=None):
    """One trimmed text field, as ``(value, message)``; exactly one of the two is None."""
    raw = submitted.get(key)
    value = ("" if raw is None else str(raw)).strip()
    name = label or key.replace("_", " ").capitalize()
    if not value:
        return (None, f"{name} is required.") if required else ("", None)
    if len(value) > limit:
        return None, f"{name} must be at most {limit} characters."
    return value, None


def time_to_hhmm(value):
    """
    Convert a time as an ``<input type="time">`` sends it into the integer the planner reads

    Args:
        value (str | None): "HH:MM", or "HH:MM:SS" as some browsers send it

    Returns:
        int: The time as HHMM, e.g. "09:30" -> 930, "23:00" -> 2300

    Raises:
        ValueError: The value is missing or is not a real time of day
    """
    text = ("" if value is None else str(value)).strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if not match:
        raise ValueError("Enter a time as HH:MM, e.g. 09:30.")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("Enter a real time of day, between 00:00 and 23:59.")
    return hour * 100 + minute


def hhmm_to_time(hhmm):
    """
    Convert a stored HHMM integer back into the "HH:MM" an ``<input type="time">`` shows

    Args:
        hhmm (int | float | None): A time as HHMM, e.g. 930

    Returns:
        str: "HH:MM", or "" if there is no time
    """
    if hhmm is None or isinstance(hhmm, bool):
        return ""
    hours, minutes = divmod(int(hhmm), 100)
    return f"{hours % 24:02d}:{minutes:02d}"


def validate_hours(submitted) -> tuple:
    """
    Build the planner's per-day hours JSON from the form's per-day fields

    A day is open when ``open_<Day>`` is submitted, and carries ``<Day>_open`` and
    ``<Day>_close``. A day that is not ticked stores ``[]``, which ``is_restaurant_open``
    reads as closed. See the module docstring for why a closing time must be later than
    its opening time, and why this is JSON rather than the prose two seeded rows hold.

    Args:
        submitted (Mapping): The form, or a JSON body with the same field names

    Returns:
        Tuple[str | None, Dict[str, str]]: The JSON to store, and one message per bad day
            keyed by the field the message belongs to
    """
    week, errors = {}, {}
    for day in DAYS:
        if not submitted.get(f"open_{day}"):
            week[day] = []
            continue
        try:
            opens = time_to_hhmm(submitted.get(f"{day}_open"))
        except ValueError as problem:
            errors[f"{day}_open"] = f"{day}: {problem}"
            continue
        try:
            closes = time_to_hhmm(submitted.get(f"{day}_close"))
        except ValueError as problem:
            errors[f"{day}_close"] = f"{day}: {problem}"
            continue
        if closes <= opens:
            errors[f"{day}_close"] = (
                f"{day}: closing time must be later than the opening time. "
                "Weeklies cannot plan a day that ends before it starts; "
                "leave the day unticked to show as closed."
            )
            continue
        week[day] = [opens, closes]

    if errors:
        return None, errors
    if not any(week.values()):
        errors["open_Mon"] = (
            "Tick at least one day you are open. A restaurant that is never open "
            "cannot be planned from."
        )
        return None, errors
    return json.dumps(week), errors


def validate(submitted, *, conn=None) -> Validated:
    """
    Check a submitted restaurant, reporting every problem rather than the first

    Args:
        submitted (Mapping): The form, or a JSON body with the same field names
        conn (sqlite3.Connection | None): Checked for an email already registered. The
            database's UNIQUE constraint is still the authority (see ``create``); this
            only turns the common case into a field message instead of a failed insert.

    Returns:
        Validated: ``values`` ready for ``create``, or ``errors`` keyed by field name
    """
    values, errors = {}, {}

    for key, limit, required in (
        ("name", NAME_MAX, True),
        ("description", DESCRIPTION_MAX, False),
        ("address", ADDRESS_MAX, True),
        ("city", CITY_MAX, True),
    ):
        value, problem = _text(submitted, key, limit, required=required)
        if problem:
            errors[key] = problem
        else:
            values[key] = value

    # A generous limit so that "Carolina" is answered with the format rule below rather
    # than a length complaint that does not say what the field wants.
    state, problem = _text(submitted, "state", 32)
    if problem:
        errors["state"] = problem
    elif not re.fullmatch(r"[A-Za-z]{2}", state):
        errors["state"] = "State must be a two-letter abbreviation, e.g. NC."
    else:
        values["state"] = state.upper()

    postcode, problem = _text(submitted, "zip", 10, label="ZIP code")
    if problem:
        errors["zip"] = problem
    elif not ZIP_PATTERN.fullmatch(postcode):
        errors["zip"] = "ZIP code must be five digits, or ZIP+4 such as 27601-1234."
    else:
        values["zip"] = postcode

    phone, problem = _text(submitted, "phone", 32)
    if problem:
        errors["phone"] = problem
    else:
        # Stored as digits only, matching proj2.auth.views.register
        digits = re.sub(r"\D+", "", phone)
        if not PHONE_DIGITS_MIN <= len(digits) <= PHONE_DIGITS_MAX:
            errors["phone"] = "Enter a valid phone number."
        else:
            values["phone"] = digits

    email, problem = _text(submitted, "email", EMAIL_MAX)
    if problem:
        errors["email"] = problem
    else:
        email = email.lower()
        if not EMAIL_PATTERN.fullmatch(email):
            errors["email"] = "Enter a valid email address."
        elif conn is not None and email_taken(conn, email):
            errors["email"] = "That email already has a restaurant account. Log in instead."
        else:
            values["email"] = email

    password = submitted.get("password") or ""
    confirm = submitted.get("confirm_password")
    if len(password) < PASSWORD_MIN:
        errors["password"] = f"Password must be at least {PASSWORD_MIN} characters."
    elif confirm is not None and password != confirm:
        # A JSON client sends no confirm_password; the page always sends one.
        errors["confirm_password"] = "The two passwords do not match."
    else:
        values["password"] = password

    status = (submitted.get("status") or "open").strip().lower()
    if status not in STATUSES:
        errors["status"] = f"Status must be one of {', '.join(STATUSES)}."
    else:
        values["status"] = status

    hours, hour_errors = validate_hours(submitted)
    errors.update(hour_errors)
    if hours is not None:
        values["hours"] = hours

    return Validated(values=values, errors=errors)


def schema() -> dict:
    """
    The sign-up contract, generated from this module so a client cannot drift from it

    Returns:
        dict: Every field, whether it is required, and its vocabulary or limit
    """
    return {
        "fields": {
            "name": {"required": True, "max_length": NAME_MAX},
            "description": {"required": False, "max_length": DESCRIPTION_MAX},
            "address": {"required": True, "max_length": ADDRESS_MAX},
            "city": {"required": True, "max_length": CITY_MAX},
            "state": {"required": True, "pattern": "[A-Za-z]{2}"},
            "zip": {"required": True, "pattern": ZIP_PATTERN.pattern},
            "phone": {
                "required": True,
                "digits_min": PHONE_DIGITS_MIN,
                "digits_max": PHONE_DIGITS_MAX,
            },
            "email": {"required": True, "max_length": EMAIL_MAX, "unique": True},
            "password": {"required": True, "min_length": PASSWORD_MIN},
            "status": {"required": False, "default": "open", "values": list(STATUSES)},
        },
        "hours": {
            "days": list(DAYS),
            "fields": {
                "open_<Day>": "present when the restaurant is open that day",
                "<Day>_open": "opening time as HH:MM",
                "<Day>_close": "closing time as HH:MM, later than the opening time",
            },
            "stored_as": 'per-day JSON, e.g. {"Mon": [1100, 2200], "Sun": []}',
            "note": (
                "Stored as the JSON proj2.plan_rules.is_restaurant_open reads. Free text "
                "renders on the page but is never open to the planner."
            ),
        },
    }


def email_taken(conn, email) -> bool:
    """
    Whether a restaurant account already uses this email

    Args:
        conn (sqlite3.Connection): An open database connection
        email (str): The address, already lowercased

    Returns:
        bool: True if the address is taken
    """
    return (
        fetch_one(conn, "SELECT 1 FROM Restaurant WHERE LOWER(email) = ?", ((email or "").lower(),))
        is not None
    )


def create(conn, values) -> int:
    """
    Insert a checked restaurant and return its new id

    The password is hashed here rather than by the caller, so no route can store one in
    the clear. ``Restaurant.email`` is UNIQUE, so a second sign-up racing the first raises
    ``sqlite3.IntegrityError`` and the caller reports the address as taken: the check in
    ``validate`` is a courtesy, this constraint is the guarantee.

    Args:
        conn (sqlite3.Connection): An open database connection
        values (dict): ``Validated.values`` from a successful ``validate``

    Returns:
        int: The new ``rtr_id``

    Raises:
        sqlite3.IntegrityError: The email is already registered
    """
    cursor = execute_query(
        conn,
        """
        INSERT INTO Restaurant
            (name, description, phone, email, password_HS, address, city, state, zip, hours, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            values["name"],
            values.get("description") or None,
            values["phone"],
            values["email"],
            generate_password_hash(values["password"]),
            values["address"],
            values["city"],
            values["state"],
            values["zip"],
            values["hours"],
            values["status"],
        ),
    )
    return cursor.lastrowid
