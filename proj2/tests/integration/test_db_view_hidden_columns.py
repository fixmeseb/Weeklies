"""/db must never send password hashes to the browser.

Any logged-in customer can open the viewer, so credential columns are
excluded from the query itself (DB_VIEW_HIDDEN_COLUMNS).
"""
import re

from werkzeug.security import generate_password_hash

import proj2.Flask_app as Flask_app
from proj2.sqlQueries import close_connection, create_connection, execute_query

HASH_PATTERN = re.compile(r"(pbkdf2|scrypt):[\w:$]+")


def _headers(html):
    return re.findall(r"<th>(.*?)</th>", html)


def _get(client, table):
    resp = client.get(f"/db?t={table}")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


# ---- expected cases ----

def test_user_table_hides_password_hash(client, seed_minimal_data, login_session):
    html = _get(client, "User")
    assert "password_HS" not in _headers(html)
    assert not HASH_PATTERN.search(html)


def test_user_table_still_shows_other_columns(client, seed_minimal_data, login_session):
    html = _get(client, "User")
    assert {"usr_id", "email", "first_name"} <= set(_headers(html))
    assert seed_minimal_data["usr_email"] in html


def test_restaurant_table_hides_password_hash(client, seed_minimal_data, login_session, temp_db_path):
    conn = create_connection(temp_db_path)
    try:
        execute_query(
            conn,
            'UPDATE "Restaurant" SET password_HS=? WHERE rtr_id=?',
            (generate_password_hash("ownerpass"), seed_minimal_data["rtr_id"]),
        )
    finally:
        close_connection(conn)
    html = _get(client, "Restaurant")
    assert "password_HS" not in _headers(html)
    assert not HASH_PATTERN.search(html)


def test_tables_without_secrets_show_every_column(client, seed_minimal_data, login_session):
    html = _get(client, "MenuItem")
    assert {"itm_id", "rtr_id", "name", "price"} <= set(_headers(html))


def test_row_cells_line_up_with_headers(client, seed_minimal_data, login_session):
    """Selecting an explicit column list must keep every row the same width as the header."""
    html = _get(client, "User")
    header_count = len(_headers(html))
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        assert len(re.findall(r"<td>", row)) == header_count


def test_password_hs_is_in_hidden_set():
    assert "password_HS" in Flask_app.DB_VIEW_HIDDEN_COLUMNS


# ---- failure / edge cases ----

def test_quote_ident_escapes_double_quotes():
    assert Flask_app._quote_ident("name") == '"name"'
    assert Flask_app._quote_ident('we"ird') == '"we""ird"'


def test_table_with_every_column_hidden_renders_empty(
    client, seed_minimal_data, login_session, monkeypatch
):
    """If nothing is left to show, the page renders 'No rows.' instead of erroring."""
    review_cols = {"rev_id", "rtr_id", "usr_id", "title", "rating", "description", "ord_id",
                   "created_at"}
    monkeypatch.setattr("proj2.food.views.DB_VIEW_HIDDEN_COLUMNS", frozenset(review_cols))
    html = _get(client, "Review")
    assert _headers(html) == []
    assert "No rows." in html


def test_logged_out_user_redirected(client):
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get("/db?t=User")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
