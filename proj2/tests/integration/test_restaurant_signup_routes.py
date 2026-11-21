"""
The restaurant sign-up page and its JSON API.

The rules live in ``proj2.restaurant_signup`` and are tested there; these tests are about
the routes carrying them faithfully -- that a rejected form comes back with what was
typed, that a new restaurant is signed in and sent somewhere useful, that the password is
stored hashed and never echoed, and that the HTML form and the JSON API agree because
they share one validator.

Every test uses its own email address: the test database is shared across the session and
``Restaurant.email`` is UNIQUE, so a reused address would make a later test's failure
depend on an earlier test's success.
"""

import json
import re
from itertools import count

import pytest

from proj2 import restaurant_signup
from proj2.db import get_db
from proj2.hours import DAYS
from proj2.menu_generation import _hours_are_readable
from proj2.plan_rules import is_restaurant_open

_serial = count()


def unique_email():
    return f"owner{next(_serial)}@signup.test"


def form(**overrides):
    """A complete, valid submission with an address no other test will use."""
    submitted = {
        "name": "Wingstop",
        "description": "Wings, by the bucket.",
        "address": "12 Hillsborough St",
        "city": "Raleigh",
        "state": "NC",
        "zip": "27601",
        "phone": "(919) 555-0199",
        "email": unique_email(),
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


def stored(email):
    """The restaurant row for an address, as a dict; None if it was never written."""
    row = (
        get_db()
        .execute(
            """SELECT rtr_id, name, description, phone, email, password_HS,
                  address, city, state, zip, hours, status
           FROM Restaurant WHERE email = ?""",
            (email,),
        )
        .fetchone()
    )
    if row is None:
        return None
    return dict(
        zip(
            (
                "rtr_id",
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
            ),
            row,
        )
    )


# --- the page -------------------------------------------------------------------------


def test_the_signup_page_is_reachable_without_an_account(client):
    """A restaurant cannot be signed in before it exists, so this route takes no session."""
    response = client.get("/restaurant/register")
    assert response.status_code == 200
    assert b'name="name"' in response.data


def test_the_page_offers_a_time_field_for_every_day(client):
    body = client.get("/restaurant/register").data.decode()
    for day in DAYS:
        assert f'name="open_{day}"' in body
        assert f'name="{day}_open"' in body
        assert f'name="{day}_close"' in body


def test_the_page_offers_no_free_text_hours_box(client):
    """Prose hours render on every page and are never open to the planner, so the form
    must not collect them. See the restaurant_signup module docstring."""
    body = client.get("/restaurant/register").data.decode()
    assert 'name="hours"' not in body


def test_the_login_page_links_to_signup(client):
    """There was a /restaurant/login with no door behind it; this is the door."""
    assert b"/restaurant/register" in client.get("/restaurant/login").data


# --- signing up -----------------------------------------------------------------------


def test_a_valid_submission_creates_the_restaurant(client):
    submitted = form()
    response = client.post("/restaurant/register", data=submitted)
    assert response.status_code == 302
    row = stored(submitted["email"])
    assert row["name"] == "Wingstop"
    assert row["city"] == "Raleigh"
    assert row["status"] == "open"


def test_a_new_restaurant_lands_on_its_empty_menu(client):
    """A restaurant with no dishes cannot be planned from, so adding one is the only
    useful next step."""
    response = client.post("/restaurant/register", data=form())
    assert "/restaurant/menu" in response.headers["Location"]


def test_a_new_restaurant_is_signed_in(client):
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    with client.session_transaction() as sess:
        assert sess["restaurant_mode"] is True
        assert sess["RestaurantEmail"] == submitted["email"]
        assert sess["rtr_id"] == stored(submitted["email"])["rtr_id"]
    # and the session really opens the owner pages
    assert client.get("/restaurant/menu").status_code == 200


def test_the_new_restaurant_can_sign_in_again_afterwards(client):
    """The whole point: an account made here must work at the door it was made for."""
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    client.get("/restaurant/logout")
    response = client.post(
        "/restaurant/login",
        data={"email": submitted["email"], "password": submitted["password"]},
    )
    assert response.status_code == 302
    assert "/restaurant/orders" in response.headers["Location"]


def test_the_password_is_stored_hashed(client):
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    row = stored(submitted["email"])
    assert row["password_HS"] != submitted["password"]
    assert submitted["password"] not in row["password_HS"]
    assert row["password_HS"].startswith("pbkdf2:")


def test_the_wrong_password_is_still_refused_afterwards(client):
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    client.get("/restaurant/logout")
    response = client.post(
        "/restaurant/login", data={"email": submitted["email"], "password": "not-it"}
    )
    assert b"Invalid credentials" in response.data


def test_an_email_is_matched_case_insensitively_at_the_door(client):
    """The form lowercases, so a sign-up typed in capitals must still log in."""
    submitted = form(email="Owner.Caps@signup.test")
    client.post("/restaurant/register", data=submitted)
    client.get("/restaurant/logout")
    response = client.post(
        "/restaurant/login",
        data={"email": "Owner.Caps@signup.test", "password": submitted["password"]},
    )
    assert response.status_code == 302


# --- hours, through the route ---------------------------------------------------------


def test_hours_submitted_as_times_are_stored_as_the_planners_json(client):
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    hours = stored(submitted["email"])["hours"]
    assert json.loads(hours)["Mon"] == [1100, 2100]
    assert _hours_are_readable(hours)
    assert is_restaurant_open(hours, "Mon", 1200)


def test_a_new_restaurant_is_in_the_planners_candidate_pool(client):
    """A prose-hours restaurant is loaded and then silently never open. This asserts the
    one thing that distinguishes a restaurant that can be planned from one that cannot."""
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    rows = (
        get_db()
        .execute(
            "SELECT hours FROM Restaurant WHERE LOWER(TRIM(status)) = 'open' AND email = ?",
            (submitted["email"],),
        )
        .fetchall()
    )
    assert rows and _hours_are_readable(rows[0][0])


def test_a_restaurant_listed_closed_is_not_in_the_pool(client):
    submitted = form(status="closed")
    client.post("/restaurant/register", data=submitted)
    assert stored(submitted["email"])["status"] == "closed"


# --- rejection ------------------------------------------------------------------------


def test_a_rejected_submission_writes_nothing(client):
    submitted = form(zip="nope")
    response = client.post("/restaurant/register", data=submitted)
    assert response.status_code == 200
    assert stored(submitted["email"]) is None


def test_a_rejected_submission_keeps_what_was_typed(client):
    """Nobody should have to retype seven fields and a week of hours."""
    submitted = form(zip="nope", name="Keep This Name")
    body = client.post("/restaurant/register", data=submitted).data.decode()
    assert 'value="Keep This Name"' in body
    assert submitted["email"] in body


def test_a_rejected_submission_does_not_echo_the_password(client):
    body = client.post("/restaurant/register", data=form(zip="nope")).data.decode()
    assert "hunter2hunter" not in body


def test_a_rejected_submission_names_every_problem(client):
    body = client.post(
        "/restaurant/register", data=form(zip="nope", state="Carolina", phone="")
    ).data.decode()
    assert "ZIP code must be five digits" in body
    assert "two-letter" in body
    assert "Phone is required" in body


def test_each_message_links_to_the_field_it_is_about(client):
    """The summary is the only thing a screen reader reaches first, so its links must land."""
    body = client.post("/restaurant/register", data=form(zip="nope")).data.decode()
    targets = set(re.findall(r'<a href="#([^"]+)">', body))
    assert targets
    for target in targets:
        assert f'id="{target}"' in body


def test_a_rejected_day_keeps_the_rest_of_the_week(client):
    body = client.post("/restaurant/register", data=form(Mon_close="02:00")).data.decode()
    assert "later than the opening time" in body
    assert 'name="open_Fri"' in body and "checked" in body


def test_an_email_already_registered_is_refused(client):
    submitted = form()
    client.post("/restaurant/register", data=submitted)
    again = form(email=submitted["email"], name="Impostor")
    response = client.post("/restaurant/register", data=again)
    assert response.status_code == 200
    assert b"already has a restaurant account" in response.data
    rows = (
        get_db()
        .execute("SELECT COUNT(*) FROM Restaurant WHERE email = ?", (submitted["email"],))
        .fetchone()
    )
    assert rows[0] == 1


def test_a_restaurant_that_predates_this_page_cannot_have_its_email_taken_over(client):
    """Every restaurant used to come from proj2.seed. Sign-up must not let somebody claim
    one of those addresses and be handed its orders, menu and reviews."""
    existing = unique_email()
    get_db().execute(
        "INSERT INTO Restaurant (name, email, status) VALUES (?, ?, 'open')",
        ("Seeded Diner", existing),
    )
    response = client.post("/restaurant/register", data=form(email=existing))
    assert response.status_code == 200
    assert b"already has a restaurant account" in response.data
    assert stored(existing)["name"] == "Seeded Diner"


# --- the JSON API ---------------------------------------------------------------------


def test_the_schema_is_public(client):
    """A client cannot have an account yet, so the contract cannot need one."""
    response = client.get("/api/restaurant/register/schema")
    assert response.status_code == 200
    assert response.get_json() == restaurant_signup.schema()


def test_the_api_creates_a_restaurant(client):
    body = form()
    del body["confirm_password"]
    response = client.post("/api/restaurant/register", json=body)
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["rtr_id"] == stored(body["email"])["rtr_id"]
    assert payload["state"] == "NC"


def test_the_api_never_returns_the_password(client):
    body = form()
    del body["confirm_password"]
    response = client.post("/api/restaurant/register", json=body)
    assert "password" not in response.get_json()
    assert b"hunter2hunter" not in response.data


def test_the_api_reports_every_problem_at_once(client):
    response = client.post(
        "/api/restaurant/register", json={"name": "Nowhere", "email": "bad", "password": "short"}
    )
    assert response.status_code == 422
    errors = response.get_json()["errors"]
    assert {"address", "city", "email", "password", "phone", "state", "zip"} <= set(errors)


def test_the_api_refuses_an_email_already_registered(client):
    body = form()
    del body["confirm_password"]
    client.post("/api/restaurant/register", json=body)
    response = client.post("/api/restaurant/register", json=body)
    assert response.status_code == 422
    assert "email" in response.get_json()["errors"]


def test_the_api_refuses_a_body_that_is_not_an_object(client):
    assert client.post("/api/restaurant/register", json=["nope"]).status_code == 400


def test_the_api_refuses_a_body_that_is_not_json(client):
    response = client.post(
        "/api/restaurant/register", data="name=Nowhere", content_type="text/plain"
    )
    assert response.status_code == 400


def test_the_api_does_not_sign_the_caller_in(client):
    """A programmatic client posts to /restaurant/login for a session."""
    body = form()
    del body["confirm_password"]
    client.post("/api/restaurant/register", json=body)
    with client.session_transaction() as sess:
        assert "rtr_id" not in sess


@pytest.mark.parametrize("field", ["name", "address", "city", "state", "zip", "phone", "email"])
def test_the_api_and_the_form_refuse_the_same_submission(client, field):
    """One validator behind two encodings; a client must not find a way round the page."""
    body = form(**{field: ""})
    del body["confirm_password"]
    assert client.post("/api/restaurant/register", json=body).status_code == 422
    page = client.post("/restaurant/register", data=form(**{field: ""}))
    assert page.status_code == 200  # the form came back rather than redirecting
