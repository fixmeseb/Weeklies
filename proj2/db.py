"""
Database access for the Flask app.

Routes call ``get_db()``. It returns one connection per application context, stored
on ``flask.g`` and closed by a teardown hook, so routes never open or close
connections themselves.

All connections made here:
  * return ``sqlite3.Row`` rows, so columns can be read by name (``row["email"]``)
    as well as by position;
  * enforce foreign keys (``PRAGMA foreign_keys = ON``);
  * never create a database file, and check the schema version
    (``PRAGMA user_version``, set by the migrations): a database that is missing,
    empty, made by the old scripts, or not yet migrated raises
    ``DatabaseNotInitialisedError`` with the command that fixes it, instead of
    failing later as an empty table or "no such table".

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

_FLASK = "flask --app proj2.Flask_app"


class DatabaseNotInitialisedError(RuntimeError):
    """The database is missing, empty, or not at the schema version this code needs."""


class Connection(sqlite3.Connection):
    """sqlite3 connection that knows whether it is inside ``transaction()``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx_depth = 0


def connect(path, *, verify=True):
    """
    Open ``path`` with the app's connection settings.

    Args:
        path: SQLite database file. It must already exist.
        verify: Check the schema version (skipped by the migration code itself).
    Raises:
        DatabaseNotInitialisedError: the file is missing, or (with verify) is not at the
            latest schema version.
    """
    path = os.fspath(path)
    if not os.path.exists(path):
        raise DatabaseNotInitialisedError(
            f"Database not found at {path}: run `{_FLASK} init-db` (or `seed` for demo data)."
        )
    conn = sqlite3.connect(path, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if verify:
        try:
            check_schema_version(conn, path)
        except Exception:
            conn.close()
            raise
    return conn


def check_schema_version(conn, path="the database"):
    """Raise DatabaseNotInitialisedError unless ``conn`` is at the latest migration."""
    from proj2.db_cli import latest_version  # local import: db_cli is the CLI layer

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    latest = latest_version()
    if version == latest:
        return
    if version == 0:
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        if not has_tables:
            problem = f"is empty: run `{_FLASK} init-db` (or `seed` for demo data)"
        else:
            problem = (
                "was made by the old setup scripts and has no schema version: "
                f"recreate it with `{_FLASK} seed` (this deletes its data)"
            )
    elif version < latest:
        problem = (
            f"is at schema version {version}, this code needs {latest}: run `{_FLASK} migrate`"
        )
    else:
        problem = (
            f"is at schema version {version}, newer than this code ({latest}): update the code"
        )
    raise DatabaseNotInitialisedError(f"Database at {path} {problem}.")


def db_path():
    """Path of the current app's database, for code that opens its own connection."""
    return current_app.config["DATABASE"]


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
