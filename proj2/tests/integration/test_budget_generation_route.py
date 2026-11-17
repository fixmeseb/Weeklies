import json
import sqlite3

import pytest

from proj2.menu_generation import DAYS_OF_WEEK, MenuGenerator


@pytest.fixture
def budget_catalog(app, temp_db_path, seed_minimal_data):
    """A temporary catalog with one priced, in-stock item; yields that item's ID."""
    snapshot = sqlite3.connect(":memory:")
    with sqlite3.connect(temp_db_path) as conn:
        conn.backup(snapshot)
        restaurant = seed_minimal_data["rtr_id"]
        conn.execute(
            'UPDATE Restaurant SET hours=?, status="Open" WHERE rtr_id=?',
            (json.dumps({day: [0, 2359] for day in DAYS_OF_WEEK}), restaurant),
        )
        conn.execute(
            'UPDATE "User" SET generated_menu="" WHERE usr_id=?', (seed_minimal_data["usr_id"],)
        )
        item = conn.execute(
            "SELECT itm_id FROM MenuItem WHERE rtr_id=? ORDER BY itm_id LIMIT 1", (restaurant,)
        ).fetchone()[0]
        conn.execute("UPDATE MenuItem SET instock=0")
        conn.execute(
            'UPDATE MenuItem SET price=500, instock=1, allergens="" WHERE itm_id=?', (item,)
        )
    yield item
    with sqlite3.connect(temp_db_path) as conn:
        snapshot.backup(conn)
    snapshot.close()


def test_generator_uses_supplied_catalog_and_keeps_prices_for_unavailable_items(
    budget_catalog, temp_db_path
):
    gen = MenuGenerator(database_path=temp_db_path)
    assert gen.menu_items.itm_id.tolist() == [budget_catalog]
    assert gen.item_prices[budget_catalog] == 500
    assert len(gen.item_prices) > len(gen.menu_items)


def payload(**overrides):
    data = {
        "start_date": "2026-10-05",
        "meal_numbers": [3],
        "number_of_days": 2,
        "weekly_cap": "10.00",
    }
    data.update(overrides)
    return data


def test_exact_limit_json_returns_totals_and_saves_plan(
    client, login_session, budget_catalog, temp_db_path
):
    response = client.post("/menu/generate", json=payload())
    assert response.status_code == 200
    data = response.get_json()
    assert data["weekly_cap_cents"] == data["item_total_cents"] == 1000
    assert data["weekly_item_totals_cents"] == {"2026-10-05": 1000}
    with sqlite3.connect(temp_db_path) as conn:
        saved = conn.execute(
            'SELECT generated_menu FROM "User" WHERE email="test@x.com"'
        ).fetchone()[0]
    assert saved == data["generated_menu"]


def test_impossible_budget_does_not_change_saved_plan(
    client, login_session, budget_catalog, temp_db_path
):
    item = budget_catalog
    existing = f"[2026-10-11,{item},3]"
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute('UPDATE "User" SET generated_menu=? WHERE email="test@x.com"', (existing,))
    with client.session_transaction() as session:
        session["GeneratedMenu"] = existing
    response = client.post("/menu/generate", json=payload(weekly_cap="14.99"))
    assert response.status_code == 422
    assert "$15.00" in response.get_json()["error"]
    with sqlite3.connect(temp_db_path) as conn:
        assert (
            conn.execute('SELECT generated_menu FROM "User" WHERE email="test@x.com"').fetchone()[0]
            == existing
        )
    with client.session_transaction() as session:
        assert session["GeneratedMenu"] == existing


@pytest.mark.parametrize("cap", ["-1", "NaN", "10.001", True])
def test_invalid_cap_returns_400(client, login_session, budget_catalog, cap):
    response = client.post("/menu/generate", json=payload(weekly_cap=cap))
    assert response.status_code == 400
    assert "Weekly cap" in response.get_json()["error"]


def test_form_can_request_json_and_receive_budget_errors(client, login_session, budget_catalog):
    response = client.post(
        "/menu/generate",
        data={"start_date": "2026-10-05", "days": "2", "meal3": "on", "weekly_cap": "9.99"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 422
    assert "weekly cap" in response.get_json()["error"]


def test_omitted_cap_keeps_generation_optional(client, login_session, budget_catalog):
    response = client.post("/menu/generate", json=payload(weekly_cap=None))
    assert response.status_code == 200
    assert response.get_json()["weekly_cap_cents"] is None
    assert response.get_json()["item_total_cents"] == 1000


@pytest.mark.parametrize("transport", ["json", "form"])
@pytest.mark.parametrize("cap", [None, "", "   "])
@pytest.mark.parametrize("problem", ["missing_item", "invalid_price"])
def test_uncapped_generation_saves_plan_when_saved_meals_cannot_be_priced(
    client, login_session, budget_catalog, temp_db_path, transport, cap, problem
):
    item = budget_catalog
    with sqlite3.connect(temp_db_path) as conn:
        saved_item = 999999
        if problem == "invalid_price":
            saved_item = conn.execute(
                "SELECT itm_id FROM MenuItem WHERE itm_id != ? LIMIT 1", (item,)
            ).fetchone()[0]
            conn.execute("UPDATE MenuItem SET price=-1 WHERE itm_id=?", (saved_item,))
        existing = f"[2026-10-11,{saved_item},3]"
        conn.execute('UPDATE "User" SET generated_menu=? WHERE email="test@x.com"', (existing,))
    if transport == "json":
        data = payload()
        data.pop("weekly_cap")
        if cap is not None:
            data["weekly_cap"] = cap
        response = client.post("/menu/generate", json=data)
    else:
        data = {"start_date": "2026-10-05", "days": "2", "meal3": "on"}
        if cap is not None:
            data["weekly_cap"] = cap
        response = client.post("/menu/generate", data=data)
    expected = f"{existing},[2026-10-05,{item},3],[2026-10-06,{item},3]"
    if transport == "json":
        assert response.status_code == 200
        result = response.get_json()
        assert result["generated_menu"] == expected
        assert result["weekly_cap_cents"] is None
        assert result["item_total_cents"] is None
        assert result["weekly_item_totals_cents"] is None
    else:
        assert response.status_code == 302
        assert response.headers["Location"] == "/"
    with sqlite3.connect(temp_db_path) as conn:
        assert (
            conn.execute('SELECT generated_menu FROM "User" WHERE email="test@x.com"').fetchone()[0]
            == expected
        )
    with client.session_transaction() as session:
        assert session["GeneratedMenu"] == expected


def test_capped_generation_rejects_missing_saved_items_without_saving(
    client, login_session, budget_catalog, temp_db_path
):
    existing = "[2026-10-11,999999,3]"
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute('UPDATE "User" SET generated_menu=? WHERE email="test@x.com"', (existing,))
    with client.session_transaction() as session:
        session["GeneratedMenu"] = existing
    response = client.post("/menu/generate", json=payload())
    assert response.status_code == 400
    assert "no longer in the catalog" in response.get_json()["error"]
    with sqlite3.connect(temp_db_path) as conn:
        assert (
            conn.execute('SELECT generated_menu FROM "User" WHERE email="test@x.com"').fetchone()[0]
            == existing
        )
    with client.session_transaction() as session:
        assert session["GeneratedMenu"] == existing


@pytest.mark.parametrize("transport", ["json", "form"])
def test_unexpected_generation_errors_are_logged_without_exposing_details(
    client, login_session, budget_catalog, temp_db_path, caplog, transport, monkeypatch
):
    details = "Private planner state: /internal/planner/config"

    def broken(*args, **kwargs):
        raise RuntimeError(details)

    monkeypatch.setattr(MenuGenerator, "update_menu", broken)
    with client.session_transaction() as session:
        session["GeneratedMenu"] = ""
    message = "Menu generation failed. Please try again."
    if transport == "json":
        response = client.post("/menu/generate", json=payload())
        assert response.status_code == 500
        assert response.get_json() == {"ok": False, "error": message}
    else:
        response = client.post(
            "/menu/generate",
            data={"start_date": "2026-10-05", "days": "2", "meal3": "on"},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/profile"
        page = client.get(response.headers["Location"]).get_data(as_text=True)
        assert message in page
        assert details not in page
    assert details not in response.get_data(as_text=True)
    assert "Menu generation failed" in caplog.text
    assert details in caplog.text
    assert any(record.exc_info for record in caplog.records)
    with sqlite3.connect(temp_db_path) as conn:
        assert (
            conn.execute('SELECT generated_menu FROM "User" WHERE email="test@x.com"').fetchone()[0]
            == ""
        )
    with client.session_transaction() as session:
        assert session["GeneratedMenu"] == ""


def test_profile_ignores_url_error_text_and_consumes_real_form_errors_once(
    client, login_session, budget_catalog
):
    injected = "Send your password to the attacker"
    html = client.get("/profile", query_string={"gen_error": injected}).get_data(as_text=True)
    assert injected not in html
    assert 'role="alert" hidden' in html
    response = client.post("/menu/generate", data={"weekly_cap": "-1"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    html = client.get("/profile", query_string={"gen_error": injected}).get_data(as_text=True)
    assert "Weekly cap must be a nonnegative dollar amount" in html
    assert injected not in html
    html = client.get("/profile").get_data(as_text=True)
    assert "Weekly cap must be a nonnegative dollar amount" not in html
    assert 'role="alert" hidden' in html


def test_profile_offers_cap_and_shows_budget_error_for_regular_form(
    client, login_session, budget_catalog
):
    response = client.post(
        "/menu/generate",
        data={"start_date": "2026-10-05", "days": "2", "meal3": "on", "weekly_cap": "9.99"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="weekly_cap"' in html
    assert "needs at least $10.00" in html
    assert 'id="menuError"' in html


def test_calendar_displays_weekly_item_total(client, login_session, budget_catalog):
    assert client.post("/menu/generate", json=payload()).status_code == 200
    response = client.get("/2026/10")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Weekly item totals" in html
    assert "<td>2026-10-05</td><td>$10.00</td>" in html
    assert "Taxes, delivery fees, and tips are extra" in html


def test_calendar_total_includes_saved_meals_just_outside_the_month(
    client, login_session, budget_catalog, temp_db_path
):
    item = budget_catalog
    with sqlite3.connect(temp_db_path) as conn:
        other = conn.execute(
            "SELECT itm_id FROM MenuItem WHERE itm_id != ? LIMIT 1", (item,)
        ).fetchone()[0]
        conn.execute("UPDATE MenuItem SET price=9000 WHERE itm_id=?", (other,))
        conn.execute(
            'UPDATE "User" SET generated_menu=? WHERE email="test@x.com"',
            (f"[2026-10-31,{other},3]",),
        )
    response = client.post(
        "/menu/generate",
        json=payload(start_date="2026-11-01", number_of_days=1, weekly_cap="100.00"),
    )
    assert response.status_code == 200
    assert response.get_json()["weekly_item_totals_cents"] == {"2026-10-26": 9500}
    page = client.get("/2026/11")
    assert "<td>2026-10-26</td><td>$95.00</td>" in page.get_data(as_text=True)


def test_calendar_does_not_claim_zero_total_for_missing_items(
    client, login_session, budget_catalog, temp_db_path
):
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute(
            'UPDATE "User" SET generated_menu=? WHERE email="test@x.com"',
            ("[2026-10-05,999999,3]",),
        )
    response = client.get("/2026/10")
    assert response.status_code == 200
    assert "Item totals are unavailable" in response.get_data(as_text=True)
