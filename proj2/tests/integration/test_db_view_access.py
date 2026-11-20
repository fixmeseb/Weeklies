"""/db is a developer tool: served only when WEEKLIES_ENABLE_DB_VIEW is set.

It shows every user's email and phone, so a normal deployment must 404.
"""
import pytest

import proj2.Flask_app as Flask_app
from proj2.Flask_app import DB_VIEW_ENV, env_flag


@pytest.fixture()
def viewer_disabled(monkeypatch):
    """Simulate a normal (non-test) server without the env var."""
    monkeypatch.setitem(Flask_app.app.config, "DB_VIEW_ENABLED", False)
    monkeypatch.setitem(Flask_app.app.config, "TESTING", False)


@pytest.fixture()
def viewer_enabled(monkeypatch):
    monkeypatch.setitem(Flask_app.app.config, "DB_VIEW_ENABLED", True)
    monkeypatch.setitem(Flask_app.app.config, "TESTING", False)


# ---- env_flag ----

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", " 1 ", "true\n"])
def test_env_flag_truthy(value):
    assert env_flag(DB_VIEW_ENV, {DB_VIEW_ENV: value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", "  "])
def test_env_flag_falsy(value):
    assert env_flag(DB_VIEW_ENV, {DB_VIEW_ENV: value}) is False


def test_env_flag_missing_is_false():
    assert env_flag(DB_VIEW_ENV, {}) is False


def test_env_flag_reads_os_environ(monkeypatch):
    monkeypatch.setenv(DB_VIEW_ENV, "1")
    assert env_flag(DB_VIEW_ENV) is True


# ---- disabled (the default outside tests) ----

@pytest.mark.parametrize("table", ["User", "Restaurant", "MenuItem", "Order", "Review"])
def test_disabled_viewer_404s_for_logged_in_customer(
    client, seed_minimal_data, login_session, viewer_disabled, table
):
    resp = client.get(f"/db?t={table}")
    assert resp.status_code == 404
    assert seed_minimal_data["usr_email"] not in resp.get_data(as_text=True)


def test_disabled_viewer_404s_when_logged_out(client, viewer_disabled):
    """No redirect to /login, which would reveal the page exists."""
    with client.session_transaction() as sess:
        sess.clear()
    assert client.get("/db").status_code == 404


# ---- enabled ----

def test_enabled_viewer_serves_logged_in_user(client, seed_minimal_data, login_session, viewer_enabled):
    resp = client.get("/db?t=User")
    assert resp.status_code == 200
    assert seed_minimal_data["usr_email"] in resp.get_data(as_text=True)


def test_enabled_viewer_still_requires_login(client, viewer_enabled):
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/db")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_test_mode_keeps_viewer_enabled(monkeypatch):
    monkeypatch.setitem(Flask_app.app.config, "DB_VIEW_ENABLED", False)
    monkeypatch.setitem(Flask_app.app.config, "TESTING", True)
    assert Flask_app.db_view_enabled() is True


# ---- nav link follows the flag ----

NAV_PAGES = ["/", "/insights", "/profile", "/orders", "/restaurants"]
DB_LINK = 'href="/db"'


@pytest.mark.parametrize("path", NAV_PAGES)
def test_nav_hides_db_link_when_disabled(client, seed_minimal_data, login_session, viewer_disabled, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert DB_LINK not in resp.get_data(as_text=True)


@pytest.mark.parametrize("path", NAV_PAGES)
def test_nav_shows_db_link_when_enabled(client, seed_minimal_data, login_session, viewer_enabled, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert DB_LINK in resp.get_data(as_text=True)


def test_context_processor_reports_flag(viewer_disabled):
    with Flask_app.app.test_request_context():
        assert Flask_app.inject_db_view_enabled() == {"db_view_enabled": False}
