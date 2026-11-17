"""
Small SQL helpers shared by the app, scripts and tests.

Errors are never swallowed: a failing statement raises ``sqlite3.Error`` so that
bugs show up as a 500 (or a failing test) instead of as an empty result.

Inside the app, get connections from ``proj2.db.get_db()``. ``create_connection``
is for scripts and tests that work on a database file directly.
"""

import sqlite3


def create_connection(db_file: str):
    """
    Open a plain connection to ``db_file`` (created if it does not exist).
    Args:
        db_file (str): Path to the SQLite database file.
    Returns:
        sqlite3.Connection
    Raises:
        sqlite3.Error: the file cannot be opened.
    """
    return sqlite3.connect(db_file)


def close_connection(conn):
    """
    Close an existing SQLite database connection.
    Args:
        conn (sqlite3.Connection): Connection object to close.
    Returns:
        None
    """
    if conn:
        conn.close()


def execute_query(conn, query: str, params=()):
    """
    Execute a single SQL statement with optional parameters.

    Commits immediately, unless the connection is inside ``proj2.db.transaction()``,
    in which case the transaction commits (or rolls back) as a whole.
    Args:
        conn (sqlite3.Connection): Active database connection.
        query (str): SQL statement to execute.
        params (tuple, optional): Parameters to safely substitute into the query.
    Returns:
        sqlite3.Cursor
    Raises:
        sqlite3.Error: the statement failed.
    """
    cur = conn.cursor()
    cur.execute(query, params)
    if not getattr(conn, "tx_depth", 0):
        conn.commit()
    return cur


def fetch_all(conn, query: str, params=()):
    """
    Execute a query and return all fetched rows (an empty list if there are none).
    Raises:
        sqlite3.Error: the query failed.
    """
    return execute_query(conn, query, params).fetchall()


def fetch_one(conn, query: str, params=()):
    """
    Execute a query and return the first row, or None if there are no rows.
    Raises:
        sqlite3.Error: the query failed.
    """
    return execute_query(conn, query, params).fetchone()
