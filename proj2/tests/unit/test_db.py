"""proj2/db.py: request-scoped connections, fail-fast on missing DBs, transactions."""

import os
import shutil
import sqlite3

import pytest

from proj2 import db, db_cli
from proj2.db_cli import init_database
from proj2.sqlQueries import execute_query, fetch_one


@pytest.fixture()
def fresh_db(tmp_path):
    path = str(tmp_path / "fresh.db")
    init_database(path)
    return path


def test_connect_missing_file_raises_and_creates_nothing(tmp_path):
    path = tmp_path / "nope.db"
    with pytest.raises(db.DatabaseNotInitialisedError, match="not found"):
        db.connect(path)
    assert not path.exists()


def test_connect_empty_file_says_run_init_db(tmp_path):
    path = tmp_path / "empty.db"
    path.touch()
    with pytest.raises(db.DatabaseNotInitialisedError, match="is empty: run .*init-db"):
        db.connect(path)


def test_connect_legacy_unversioned_database_says_reseed(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "User" (usr_id INTEGER PRIMARY KEY)')
    conn.close()
    with pytest.raises(db.DatabaseNotInitialisedError, match="old setup scripts.*seed"):
        db.connect(path)


def test_connect_outdated_database_says_migrate(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    db_cli.apply_migrations(conn, _migrations_upto(tmp_path, 1))
    conn.close()
    with pytest.raises(db.DatabaseNotInitialisedError, match="version 1, .*needs .*migrate"):
        db.connect(path)
    conn = sqlite3.connect(path)
    db_cli.apply_migrations(conn)  # what `flask migrate` does
    conn.close()
    db.connect(path).close()


def test_connect_database_newer_than_code_is_refused(fresh_db):
    conn = sqlite3.connect(fresh_db)
    conn.execute(f"PRAGMA user_version = {db_cli.latest_version() + 1}")
    conn.close()
    with pytest.raises(db.DatabaseNotInitialisedError, match="newer than this code"):
        db.connect(fresh_db)


def _migrations_upto(tmp_path, version):
    """A copy of the real migrations directory holding only files 1..version."""
    target = tmp_path / f"migrations_upto_{version}"
    target.mkdir()
    for v, path in db_cli.migrations():
        if v <= version:
            shutil.copy(path, target)
    return target


def test_connect_rows_by_name_and_foreign_keys_on(fresh_db):
    conn = db.connect(fresh_db)
    try:
        execute_query(
            conn, 'INSERT INTO "User"(email, first_name) VALUES (?, ?)', ("a@x.com", "Ann")
        )
        row = fetch_one(conn, 'SELECT usr_id, first_name FROM "User"')
        assert row["first_name"] == "Ann" and row[1] == "Ann"
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            execute_query(
                conn, 'INSERT INTO "MenuItem"(rtr_id, name, price) VALUES (999, ?, 1)', ("x",)
            )
    finally:
        conn.close()


def test_get_db_reuses_one_connection_per_context_and_closes_it(app, fresh_db, monkeypatch):
    monkeypatch.setitem(app.config, "DATABASE", fresh_db)
    with app.app_context():
        first = db.get_db()
        assert db.get_db() is first
    with pytest.raises(sqlite3.ProgrammingError):  # closed by the teardown hook
        first.execute("SELECT 1")


def _count_users(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute('SELECT COUNT(*) FROM "User"').fetchone()[0]
    finally:
        conn.close()


def test_transaction_commits_together(fresh_db):
    conn = db.connect(fresh_db)
    try:
        with db.transaction(conn):
            execute_query(conn, 'INSERT INTO "User"(email) VALUES (?)', ("a@x.com",))
            # execute_query must not commit inside a transaction
            assert _count_users(fresh_db) == 0
            execute_query(conn, 'INSERT INTO "User"(email) VALUES (?)', ("b@x.com",))
        assert _count_users(fresh_db) == 2
    finally:
        conn.close()


def test_transaction_rolls_back_everything_on_error(fresh_db):
    conn = db.connect(fresh_db)
    try:
        with pytest.raises(sqlite3.IntegrityError), db.transaction(conn):
            execute_query(conn, 'INSERT INTO "User"(email) VALUES (?)', ("a@x.com",))
            execute_query(conn, 'INSERT INTO "User"(email) VALUES (?)', ("a@x.com",))  # UNIQUE
        assert _count_users(fresh_db) == 0
        assert conn.tx_depth == 0
    finally:
        conn.close()


def test_nested_transaction_commits_only_at_outermost(fresh_db):
    conn = db.connect(fresh_db)
    try:
        with db.transaction(conn):
            with db.transaction(conn):
                execute_query(conn, 'INSERT INTO "User"(email) VALUES (?)', ("a@x.com",))
            assert _count_users(fresh_db) == 0
        assert _count_users(fresh_db) == 1
    finally:
        conn.close()


def test_database_path_from_env():
    assert db.database_path_from_env({}) == db.DEFAULT_DATABASE
    assert db.database_path_from_env({"WEEKLIES_DATABASE": "  "}) == db.DEFAULT_DATABASE
    rel = db.database_path_from_env({"WEEKLIES_DATABASE": "proj2/instance/x.db"})
    assert rel == os.path.normpath(os.path.join(db.REPO_ROOT, "proj2", "instance", "x.db"))
    absolute = os.path.abspath(os.path.join(os.sep, "data", "w.db"))
    assert db.database_path_from_env({"WEEKLIES_DATABASE": absolute}) == absolute


def test_sql_error_in_route_is_logged_and_returns_500(app, monkeypatch, caplog):
    """The app-wide handler: a failing query is a logged 500, not a silent empty page."""

    def broken_fetch(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated failure")

    monkeypatch.setattr("proj2.auth.views.fetch_one", broken_fetch)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)
    with app.test_client() as c:
        resp = c.post("/login", data={"email": "a@x.com", "password": "pw"})
    assert resp.status_code == 500
    assert b"Internal Server Error" in resp.data
    assert "simulated failure" in caplog.text
