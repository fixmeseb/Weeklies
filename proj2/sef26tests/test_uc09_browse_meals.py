"""UC09: Browse Available Meals — tests.

Verified against Flask_app.py:2060-2137. GET /restaurants lists in-stock items.
Requires login (redirects otherwise).
"""
import pytest


def _login(client, seed_user):
    client.post("/login", data={"email": seed_user["email"], "password": seed_user["password"]})


def test_browse_meals_all(client, seed_user, seed_restaurant):
    """UC09 main: /restaurants returns 200 with items listed."""
    _login(client, seed_user)
    resp = client.get("/restaurants")
    assert resp.status_code == 200
    assert b"Pasta" in resp.data or b"Salad" in resp.data


def test_browse_meals_none(client, seed_user, temp_db_path):
    """UC09 ext 1a: no items → empty catalog still renders 200."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'DELETE FROM "MenuItem"')
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/restaurants")
    assert resp.status_code == 200


def test_browse_meals_stock_unset(client, seed_user, seed_restaurant, temp_db_path):
    """UC09 ext 1b: items with NULL instock still show (SQL: instock IS NULL OR instock=1)."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'UPDATE "MenuItem" SET instock=NULL')
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/restaurants")
    assert resp.status_code == 200


def test_browse_meals_missing_nutrition(client, seed_user, seed_restaurant, temp_db_path):
    """UC09 ext 2a: items with NULL calories/allergens still render."""
    from proj2.sqlQueries import create_connection, execute_query, close_connection
    conn = create_connection(temp_db_path)
    try:
        execute_query(conn, 'UPDATE "MenuItem" SET calories=NULL, allergens=NULL')
    finally:
        close_connection(conn)
    _login(client, seed_user)
    resp = client.get("/restaurants")
    assert resp.status_code == 200


def test_browse_meals_by_restaurant(client, seed_user, seed_restaurant):
    """UC09 variant: items include restaurant relation (both are passed to template)."""
    _login(client, seed_user)
    resp = client.get("/restaurants")
    assert resp.status_code == 200
    assert b"SEF Cafe" in resp.data
