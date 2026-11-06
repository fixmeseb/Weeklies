"""UC01: Register Account — tests.

Verified against Flask_app.py:1176-1235. The form uses fields
`fname`, `lname`, `email`, `phone`, `password`, `confirm_password`,
`preferences`, `allergies`. Success = 302 redirect to /login.
Validation errors re-render the register page (status 200).
"""
import pytest
from proj2.sqlQueries import create_connection, fetch_one, close_connection


def _base_form(**overrides):
    data = {
        "fname": "John", "lname": "Doe",
        "email": "uniq@test.com", "phone": "5551234567",
        "password": "secret123", "confirm_password": "secret123",
        "preferences": "", "allergies": "",
    }
    data.update(overrides)
    return data


def test_register_valid_user(client, temp_db_path):
    """UC01 main: valid registration creates account and redirects to /login."""
    resp = client.post("/register", data=_base_form(email="uc01_valid@test.com"),
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    # Verify DB row exists
    conn = create_connection(temp_db_path)
    try:
        row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email=?', ("uc01_valid@test.com",))
    finally:
        close_connection(conn)
    assert row is not None


def test_register_missing_first_name(client):
    """UC01 ext 2a: first-name-only rejected (page re-rendered)."""
    resp = client.post("/register", data=_base_form(fname="", email="uc01_nofname@test.com"))
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"first" in resp.data.lower()


def test_register_missing_last_name(client):
    """UC01 ext 2a: missing last name rejected."""
    resp = client.post("/register", data=_base_form(lname="", email="uc01_nolname@test.com"))
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"last" in resp.data.lower()


def test_register_password_mismatch(client):
    """UC01 ext 2b: mismatched passwords rejected."""
    resp = client.post("/register", data=_base_form(
        email="uc01_mismatch@test.com", password="secret123", confirm_password="different"))
    assert resp.status_code == 200
    assert b"match" in resp.data.lower() or b"password" in resp.data.lower()


def test_register_password_too_short(client):
    """UC01 ext 2c: password shorter than 6 chars is rejected."""
    resp = client.post("/register", data=_base_form(
        email="uc01_short@test.com", password="abc", confirm_password="abc"))
    assert resp.status_code == 200
    assert b"6" in resp.data or b"characters" in resp.data.lower()


def test_register_invalid_phone(client):
    """UC01 ext 2d: phone with < 7 digits rejected."""
    resp = client.post("/register", data=_base_form(
        email="uc01_badphone@test.com", phone="abc12"))
    assert resp.status_code == 200
    assert b"phone" in resp.data.lower()


def test_register_duplicate_email(client, seed_user):
    """UC01 ext 2e: duplicate email rejected."""
    resp = client.post("/register", data=_base_form(email=seed_user["email"]))
    assert resp.status_code == 200
    assert b"already" in resp.data.lower() or b"registered" in resp.data.lower()


def test_register_db_failure(client, monkeypatch):
    """UC01 ext 3a: IntegrityError from DB caught and rendered as email-registered error."""
    from sqlite3 import IntegrityError
    from proj2 import Flask_app
    def boom(*a, **k):
        raise IntegrityError("simulated")
    monkeypatch.setattr("proj2.auth.views.execute_query", boom, raising=True)
    resp = client.post("/register", data=_base_form(email="uc01_dbfail@test.com"))
    assert resp.status_code == 200
    assert b"already" in resp.data.lower() or b"registered" in resp.data.lower()
