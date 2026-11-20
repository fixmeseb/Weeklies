"""
The rules a restaurant must satisfy to join.

The point of most of these is not the form but the planner. ``Restaurant.hours`` is read
by two consumers that disagree -- ``proj2.hours.format_hours`` renders prose or JSON,
``proj2.plan_rules.is_restaurant_open`` parses JSON only -- so a restaurant stored with
prose hours looks right on every page a person sees and is silently never planned from.
Several tests below assert the round trip through both consumers rather than the string
this module produces, because the string is only correct if both of them accept it.
"""

import json

import pytest

from proj2 import restaurant_signup
from proj2.hours import DAYS, format_hours
from proj2.menu_generation import _hours_are_readable
from proj2.plan_rules import is_restaurant_open


def form(**overrides):
    """A complete, valid submission, open Mon-Fri 11:00-21:00."""
    submitted = {
        "name": "Wingstop",
        "description": "Wings, by the bucket.",
        "address": "12 Hillsborough St",
        "city": "Raleigh",
        "state": "NC",
        "zip": "27601",
        "phone": "9195550199",
        "email": "owner@wingstop.test",
        "password": "hunter2hunter",
        "confirm_password": "hunter2hunter",
        "status": "open",
    }
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri"):
        submitted[f"open_{day}"] = "1"
        submitted[f"{day}_open"] = "11:00"
        submitted[f"{day}_close"] = "21:00"
    submitted.update(overrides)
    return submitted


# --- the whole submission -------------------------------------------------------------


def test_a_complete_submission_is_accepted():
    assert restaurant_signup.validate(form()).ok


def test_every_problem_is_reported_not_just_the_first():
    checked = restaurant_signup.validate(form(state="", zip="nope", phone="", email="bad"))
    assert set(checked.errors) == {"state", "zip", "phone", "email"}


def test_the_password_is_never_among_the_stored_values_in_the_clear():
    # create() hashes it; values carries the plaintext only as far as that call.
    values = restaurant_signup.validate(form()).values
    assert values["password"] == "hunter2hunter"
    assert "password_HS" not in values


# --- hours: the reason this module exists ---------------------------------------------


def test_hours_are_stored_as_the_json_the_planner_reads():
    hours = restaurant_signup.validate(form()).values["hours"]
    assert json.loads(hours) == {
        "Mon": [1100, 2100],
        "Tue": [1100, 2100],
        "Wed": [1100, 2100],
        "Thu": [1100, 2100],
        "Fri": [1100, 2100],
        "Sat": [],
        "Sun": [],
    }


def test_stored_hours_satisfy_both_consumers_that_read_the_column():
    """The two-contract check: the planner must parse it and the page must render it."""
    hours = restaurant_signup.validate(form()).values["hours"]
    assert _hours_are_readable(hours)  # not dropped from the planner's candidate pool
    assert is_restaurant_open(hours, "Mon", 1200)
    assert not is_restaurant_open(hours, "Mon", 2200)
    assert not is_restaurant_open(hours, "Sat", 1200)
    assert format_hours(hours) == "Mon–Fri 11 am–9 pm · Sat, Sun closed"


def test_a_day_that_is_not_ticked_is_stored_closed_rather_than_omitted():
    """is_restaurant_open returns False for a missing key too, but an explicit [] is what
    format_hours needs to say "closed" instead of falling back to tidied text."""
    week = json.loads(restaurant_signup.validate(form()).values["hours"])
    assert set(week) == set(DAYS)
    assert week["Sun"] == []


@pytest.mark.parametrize("close", ["11:00", "02:00", "10:59"])
def test_a_closing_time_not_after_the_opening_time_is_refused(close):
    """is_restaurant_open tests open <= t <= close on one day with no wrap past midnight,
    so such a window matches no time at all: the day would read as open and never plan."""
    checked = restaurant_signup.validate(form(Mon_close=close))
    assert "Mon_close" in checked.errors
    assert "later than the opening time" in checked.errors["Mon_close"]


def test_a_restaurant_open_no_day_is_refused():
    submitted = form()
    for day in DAYS:
        submitted.pop(f"open_{day}", None)
    checked = restaurant_signup.validate(submitted)
    assert not checked.ok
    assert "at least one day" in " ".join(checked.errors.values())


def test_hours_are_free_text_nowhere_in_the_accepted_values():
    """A submission cannot smuggle prose past the per-day fields."""
    checked = restaurant_signup.validate(form(hours="11am - 10pm"))
    assert checked.ok
    assert json.loads(checked.values["hours"])["Mon"] == [1100, 2100]


@pytest.mark.parametrize("bad", ["", "25:00", "11:60", "eleven", "11", "11:0"])
def test_an_unreadable_time_is_refused(bad):
    assert "Mon_open" in restaurant_signup.validate(form(Mon_open=bad)).errors


@pytest.mark.parametrize(
    "text,expected", [("09:30", 930), ("00:00", 0), ("23:59", 2359), ("09:30:00", 930)]
)
def test_time_to_hhmm(text, expected):
    assert restaurant_signup.time_to_hhmm(text) == expected


@pytest.mark.parametrize("hhmm,expected", [(930, "09:30"), (0, "00:00"), (2359, "23:59")])
def test_hhmm_to_time_round_trips(hhmm, expected):
    assert restaurant_signup.hhmm_to_time(hhmm) == expected
    assert restaurant_signup.time_to_hhmm(expected) == hhmm


def test_hhmm_to_time_has_no_value_for_nothing():
    assert restaurant_signup.hhmm_to_time(None) == ""


# --- the ordinary fields --------------------------------------------------------------


@pytest.mark.parametrize("field", ["name", "address", "city", "state", "zip", "phone", "email"])
def test_a_required_field_left_blank_is_refused(field):
    assert field in restaurant_signup.validate(form(**{field: "  "})).errors


def test_a_description_is_optional():
    assert restaurant_signup.validate(form(description="")).ok


def test_a_state_is_two_letters_and_is_stored_uppercase():
    assert restaurant_signup.validate(form(state="nc")).values["state"] == "NC"


@pytest.mark.parametrize("bad", ["Carolina", "N", "N1", "北"])
def test_a_state_that_is_not_two_letters_is_refused(bad):
    checked = restaurant_signup.validate(form(state=bad))
    assert "two-letter" in checked.errors["state"]


@pytest.mark.parametrize("good", ["27601", "27601-1234"])
def test_a_zip_may_be_five_digits_or_zip_plus_four(good):
    assert restaurant_signup.validate(form(zip=good)).values["zip"] == good


@pytest.mark.parametrize("bad", ["2760", "276011", "abcde", "27601-12"])
def test_a_malformed_zip_is_refused(bad):
    assert "zip" in restaurant_signup.validate(form(zip=bad)).errors


def test_a_phone_is_stored_as_digits_only():
    """Matches proj2.Flask_app.register, so the two doors store the column the same way."""
    assert restaurant_signup.validate(form(phone="(919) 555-0199")).values["phone"] == "9195550199"


@pytest.mark.parametrize("bad", ["12345", "1" * 16])
def test_a_phone_of_the_wrong_length_is_refused(bad):
    assert "phone" in restaurant_signup.validate(form(phone=bad)).errors


def test_an_email_is_stored_lowercase():
    assert restaurant_signup.validate(form(email="Owner@WINGSTOP.test")).values["email"] == (
        "owner@wingstop.test"
    )


@pytest.mark.parametrize("bad", ["owner", "owner@", "@wingstop.test", "owner@wingstop", "a b@c.d"])
def test_a_malformed_email_is_refused(bad):
    assert "email" in restaurant_signup.validate(form(email=bad)).errors


def test_a_short_password_is_refused():
    checked = restaurant_signup.validate(form(password="short", confirm_password="short"))
    assert str(restaurant_signup.PASSWORD_MIN) in checked.errors["password"]


def test_passwords_that_do_not_match_are_refused():
    assert "confirm_password" in restaurant_signup.validate(form(confirm_password="other")).errors


def test_a_client_that_sends_no_confirmation_is_not_asked_for_one():
    """The page always sends confirm_password; a JSON client has nothing to confirm."""
    submitted = form()
    del submitted["confirm_password"]
    assert restaurant_signup.validate(submitted).ok


def test_status_defaults_to_open():
    submitted = form()
    del submitted["status"]
    assert restaurant_signup.validate(submitted).values["status"] == "open"


def test_a_restaurant_may_list_itself_closed():
    assert restaurant_signup.validate(form(status="closed")).values["status"] == "closed"


def test_an_unknown_status_is_refused():
    assert "status" in restaurant_signup.validate(form(status="paused")).errors


def test_a_field_over_its_limit_is_refused():
    long_name = "x" * (restaurant_signup.NAME_MAX + 1)
    assert "name" in restaurant_signup.validate(form(name=long_name)).errors


# --- the published contract -----------------------------------------------------------


def test_the_schema_describes_every_field_the_validator_requires():
    """A published contract that drifts from the server is worse than none."""
    schema = restaurant_signup.schema()
    blank = restaurant_signup.validate({})
    required = {name for name, spec in schema["fields"].items() if spec["required"]}
    # Every field the schema calls required is one a blank submission is refused for.
    assert required <= set(blank.errors)


def test_the_schema_names_the_days_and_the_hours_fields():
    schema = restaurant_signup.schema()
    assert schema["hours"]["days"] == list(DAYS)
    assert set(schema["hours"]["fields"]) == {"open_<Day>", "<Day>_open", "<Day>_close"}


def test_the_schema_offers_only_the_statuses_the_validator_accepts():
    assert restaurant_signup.schema()["fields"]["status"]["values"] == list(
        restaurant_signup.STATUSES
    )
