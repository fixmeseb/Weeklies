"""
Database access for the Flask app.

Routes call ``get_db()``. It returns one connection per application context, stored
on ``flask.g`` and closed by a teardown hook, so routes never open or close
connections themselves.

All connections made here:
  * return ``sqlite3.Row`` rows, so columns can be read by name (``row["email"]``)
    as well as by position;
  * enforce foreign keys (``PRAGMA foreign_keys = ON``);
  * never create a database file: a missing or empty database raises
    ``DatabaseNotInitialisedError`` instead of looking like an empty table.

The database path comes from ``app.config["DATABASE"]``, which defaults to
``$WEEKLIES_DATABASE`` (relative paths are taken from the repo root, so the server and
scripts agree whatever directory they run in), else ``proj2/CSC510_DB.db``.
"""

import contextlib
import os
import sqlite3

from flask import current_app, g

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATABASE = os.path.join(REPO_ROOT, "proj2", "CSC510_DB.db")
DATABASE_ENV = "WEEKLIES_DATABASE"

# Tables every route expects. Checked once per database path, on first use.
REQUIRED_TABLES = frozenset({"User", "Restaurant", "MenuItem", "Order", "Review", "Analytics"})

_NOT_INITIALISED_HINT = "run `flask --app proj2.Flask_app init-db` (and `seed` for demo data)"


class DatabaseNotInitialisedError(RuntimeError):
    """The database file is missing or lacks the app's tables."""


class Connection(sqlite3.Connection):
    """sqlite3 connection that knows whether it is inside ``transaction()``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx_depth = 0


_verified_paths = set()


def connect(path, *, verify=True):
    """
    Open ``path`` with the app's connection settings.

    Args:
        path: SQLite database file. It must already exist.
        verify: Check that the app's tables exist (skipped by init-db, which creates them).
    Raises:
        DatabaseNotInitialisedError: the file is missing, or (with verify) lacks tables.
    """
    path = os.fspath(path)
    if not os.path.exists(path):
        raise DatabaseNotInitialisedError(f"Database not found at {path}: {_NOT_INITIALISED_HINT}.")
    conn = sqlite3.connect(path, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if verify and path not in _verified_paths:
        try:
            _check_tables(conn, path)
        except Exception:
            conn.close()
            raise
        _verified_paths.add(path)
    return conn


def _check_tables(conn, path):
    found = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = sorted(REQUIRED_TABLES - found)
    if missing:
        raise DatabaseNotInitialisedError(
            f"Database at {path} is missing tables {', '.join(missing)}: {_NOT_INITIALISED_HINT}."
        )


def get_db():
    """The current app context's connection, opened on first use."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextlib.contextmanager
def transaction(conn):
    """
    Group several writes so they commit together or not at all.

    ``sqlQueries.execute_query`` normally commits after each statement; inside this
    block it does not, and the whole block is committed on success or rolled back on
    any exception. Blocks may nest; only the outermost one commits.
    """
    conn.tx_depth = getattr(conn, "tx_depth", 0) + 1
    try:
        yield conn
    except BaseException:
        conn.tx_depth -= 1
        if conn.tx_depth == 0:
            conn.rollback()
        raise
    conn.tx_depth -= 1
    if conn.tx_depth == 0:
        conn.commit()


def database_path_from_env(environ=None, default=DEFAULT_DATABASE):
    """$WEEKLIES_DATABASE as an absolute path (relative to the repo root), else ``default``."""
    environ = os.environ if environ is None else environ
    value = (environ.get(DATABASE_ENV) or "").strip()
    if not value:
        return default
    return os.path.normpath(os.path.join(REPO_ROOT, os.path.expanduser(value)))


def init_app(app):
    """Register the database config, teardown hook and CLI commands on ``app``."""
    app.config.setdefault("DATABASE", database_path_from_env())
    app.teardown_appcontext(close_db)
    from proj2 import db_cli  # local import: db_cli imports this module

    db_cli.register(app)
