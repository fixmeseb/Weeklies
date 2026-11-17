"""Migrations, the init-db / migrate / seed commands, and the Cypress seed wrapper."""

import os
import sqlite3

import pytest
from werkzeug.security import check_password_hash

from proj2 import config, db, db_cli
from proj2.scripts import cypress_seed
from proj2.seed import seed_database


def _version(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _write(directory, name, sql):
    (directory / name).write_text(sql, encoding="utf-8")


# ---------------------------------------------------------------- migrations


def test_init_database_applies_all_migrations(tmp_path):
    path = str(tmp_path / "a.db")
    assert db_cli.init_database(path) == db_cli.latest_version() >= 1
    db.connect(path).close()  # has every table the app needs


def test_apply_migrations_is_idempotent(tmp_path):
    path = str(tmp_path / "a.db")
    db_cli.init_database(path)
    conn = sqlite3.connect(path)
    try:
        assert db_cli.apply_migrations(conn) == []
    finally:
        conn.close()


def test_apply_migrations_only_runs_newer_files(tmp_path):
    mig = tmp_path / "migrations"
    mig.mkdir()
    _write(mig, "001_first.sql", "CREATE TABLE a (x INTEGER);")
    conn = sqlite3.connect(":memory:")
    assert db_cli.apply_migrations(conn, mig) == [1]
    _write(mig, "002_second.sql", "ALTER TABLE a ADD COLUMN y TEXT;")
    assert db_cli.apply_migrations(conn, mig) == [2]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert [r[1] for r in conn.execute("PRAGMA table_info(a)")] == ["x", "y"]


def test_failed_migration_rolls_back_and_keeps_version(tmp_path):
    mig = tmp_path / "migrations"
    mig.mkdir()
    _write(mig, "001_ok.sql", "CREATE TABLE a (x INTEGER);")
    _write(mig, "002_broken.sql", "CREATE TABLE b (x INTEGER);\nNOT VALID SQL;")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(db_cli.MigrationError, match="002_broken.sql"):
        db_cli.apply_migrations(conn, mig)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"a"}  # table b from the failed file was rolled back


def test_legacy_unversioned_database_is_refused(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "User" (usr_id INTEGER PRIMARY KEY)')
    with pytest.raises(db_cli.MigrationError, match="no schema version"):
        db_cli.apply_migrations(conn)
    conn.close()


def test_database_newer_than_code_is_refused():
    conn = sqlite3.connect(":memory:")
    conn.execute(f"PRAGMA user_version = {db_cli.latest_version() + 1}")
    with pytest.raises(db_cli.MigrationError, match="newer than this code"):
        db_cli.apply_migrations(conn)


@pytest.mark.parametrize(
    "names, message",
    [(["001_a.sql", "003_c.sql"], "without gaps"), (["1_bad.sql"], "Badly named")],
)
def test_migration_files_must_be_numbered_in_sequence(tmp_path, names, message):
    for name in names:
        _write(tmp_path, name, "SELECT 1;")
    with pytest.raises(db_cli.MigrationError, match=message):
        db_cli.migrations(tmp_path)


def test_init_database_needs_force_to_overwrite(tmp_path):
    path = str(tmp_path / "a.db")
    db_cli.init_database(path)
    with pytest.raises(db_cli.MigrationError, match="already exists"):
        db_cli.init_database(path)
    assert db_cli.init_database(path, force=True) == db_cli.latest_version()


def test_review_is_unique_per_order_and_rating_checked(tmp_path):
    path = str(tmp_path / "a.db")
    seed_database(path)
    conn = db.connect(path)
    try:
        insert = 'INSERT INTO "Review"(rtr_id, usr_id, rating, ord_id) VALUES (1, 1, ?, ?)'
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conn.execute(insert, (5, 1))  # order 1 is already reviewed in the seed
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(insert, (6, 4))
    finally:
        conn.close()


# ---------------------------------------------------------------- seed


def test_seed_creates_the_documented_demo_data(tmp_path):
    path = str(tmp_path / "seeded.db")
    seed_database(path)
    seed_database(path)  # reseeding replaces rather than duplicates
    conn = db.connect(path)
    try:
        counts = {
            t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in ["User", "Restaurant", "MenuItem", "Order", "Review", "Analytics"]
        }
        assert counts == {
            "User": 2,
            "Restaurant": 11,
            "MenuItem": 76,
            "Order": 4,
            "Review": 1,
            "Analytics": 2,
        }
        pw = conn.execute(
            'SELECT password_HS FROM "User" WHERE email=?', ("testuser@example.com",)
        ).fetchone()[0]
        assert check_password_hash(pw, "password123")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    assert _version(path) == db_cli.latest_version()


# ---------------------------------------------------------------- CLI


@pytest.fixture()
def cli(app, tmp_path, monkeypatch):
    path = str(tmp_path / "cli.db")
    monkeypatch.setitem(app.config, "DATABASE", path)
    return app.test_cli_runner(), path


def test_cli_init_db_then_migrate(cli):
    runner, _ = cli
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    assert f"schema version {db_cli.latest_version()}" in result.output
    result = runner.invoke(args=["migrate"])
    assert result.exit_code == 0 and "Already up to date" in result.output
    result = runner.invoke(args=["init-db"])
    assert result.exit_code != 0 and "--force" in result.output


def test_cli_migrate_without_database(cli):
    runner, path = cli
    result = runner.invoke(args=["migrate"])
    assert result.exit_code != 0 and "run init-db first" in result.output
    assert not os.path.exists(path)


def test_cli_seed(cli):
    runner, path = cli
    result = runner.invoke(args=["seed"])
    assert result.exit_code == 0, result.output
    conn = db.connect(path)
    try:
        assert conn.execute('SELECT COUNT(*) FROM "User"').fetchone()[0] == 2
    finally:
        conn.close()


# ---------------------------------------------------------------- cypress_seed.py


def test_cypress_seed_defaults_to_its_own_database():
    assert cypress_seed.cypress_database_path({}) == cypress_seed.CYPRESS_DATABASE
    assert cypress_seed.CYPRESS_DATABASE != config.DEFAULT_DB_PATH


def test_cypress_seed_refuses_the_development_database(monkeypatch):
    called = []
    monkeypatch.setattr(cypress_seed, "seed_database", called.append)
    with pytest.raises(SystemExit, match="Refusing"):
        cypress_seed.main({config.DB_PATH_ENV: config.DEFAULT_DB_PATH})
    assert called == []


def test_cypress_seed_uses_weeklies_database(tmp_path, capsys):
    path = str(tmp_path / "e2e.db")
    cypress_seed.main({config.DB_PATH_ENV: path})
    assert "successfully seeded" in capsys.readouterr().out
    assert _version(path) == db_cli.latest_version()
