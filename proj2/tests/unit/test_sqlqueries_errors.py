"""SQL errors must propagate (Phase 1): they used to be printed and turned into None/[]."""

import sqlite3

import pytest

from proj2.sqlQueries import (
    close_connection,
    create_connection,
    execute_query,
    fetch_all,
    fetch_one,
)


def test_execute_query_raises_on_sql_error(tmp_path):
    conn = create_connection((tmp_path / "bad.sqlite").as_posix())
    try:
        with pytest.raises(sqlite3.Error):
            execute_query(conn, "THIS IS NOT VALID SQL")
    finally:
        close_connection(conn)


def test_fetch_all_and_fetch_one_raise_on_missing_table(tmp_path):
    conn = create_connection((tmp_path / "bad2.sqlite").as_posix())
    try:
        with pytest.raises(sqlite3.OperationalError):
            fetch_all(conn, 'SELECT * FROM "DoesNotExist"')
        with pytest.raises(sqlite3.OperationalError):
            fetch_one(conn, 'SELECT * FROM "DoesNotExist"')
    finally:
        close_connection(conn)
