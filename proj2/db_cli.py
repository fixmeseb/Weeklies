"""
Schema migrations and the ``flask init-db`` / ``migrate`` / ``seed`` commands.

Migrations are the numbered ``proj2/migrations/NNN_name.sql`` files. A database's
``PRAGMA user_version`` records the number of the last one applied, so ``migrate``
applies only the newer files, each in its own transaction.

    flask --app proj2.Flask_app init-db           # new, empty database
    flask --app proj2.Flask_app init-db --force   # delete and recreate it
    flask --app proj2.Flask_app migrate           # bring an existing database up to date
    flask --app proj2.Flask_app seed              # recreate it with the demo data

All commands act on ``app.config["DATABASE"]`` (set ``WEEKLIES_DATABASE`` to change it).
"""

import os
import re
import sqlite3

import click

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
_MIGRATION_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    pass


def migrations(directory=MIGRATIONS_DIR):
    """[(version, path)] for every migration file, in order."""
    found = []
    for name in os.listdir(directory):
        m = _MIGRATION_NAME.match(name)
        if m:
            found.append((int(m.group(1)), os.path.join(directory, name)))
        elif name.endswith(".sql"):
            raise MigrationError(f"Badly named migration {name!r}: use NNN_lower_snake.sql")
    found.sort()
    versions = [v for v, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(
            f"Migration numbers must run 1, 2, 3... without gaps; found {versions}"
        )
    return found


def latest_version(directory=MIGRATIONS_DIR):
    found = migrations(directory)
    return found[-1][0] if found else 0


def apply_migrations(conn, directory=MIGRATIONS_DIR):
    """
    Apply every migration newer than the database's user_version.

    Returns:
        list[int]: the versions applied (empty if already up to date).
    Raises:
        MigrationError: the database has tables but no version (made by the old scripts),
            or is newer than this code.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    found = migrations(directory)
    latest = found[-1][0] if found else 0
    if current > latest:
        raise MigrationError(f"Database is at version {current}, newer than this code ({latest}).")
    if current == 0:
        tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        if tables:
            raise MigrationError(
                "Database has tables but no schema version: it was made by the old setup scripts. "
                "Recreate it with `init-db --force` (or `seed`)."
            )

    applied = []
    for version, path in found:
        if version <= current:
            continue
        with open(path, encoding="utf-8") as fh:
            sql = fh.read()
        # executescript() commits first and runs outside the sqlite3 module's implicit
        # transactions, so wrap each file in an explicit one.
        try:
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
        except sqlite3.Error as exc:
            conn.rollback()
            raise MigrationError(f"{os.path.basename(path)} failed: {exc}") from exc
        applied.append(version)
    return applied


def init_database(path, *, force=False):
    """Create a database at ``path`` with the full schema. Returns the schema version."""
    path = os.fspath(path)
    if os.path.exists(path):
        if not force:
            raise MigrationError(f"{path} already exists; use --force to delete and recreate it.")
        os.remove(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        apply_migrations(conn)
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def register(app):
    @app.cli.command("init-db")
    @click.option("--force", is_flag=True, help="Delete an existing database first.")
    def init_db_command(force):
        """Create an empty database with the current schema."""
        path = app.config["DATABASE"]
        try:
            version = init_database(path, force=force)
        except MigrationError as exc:
            raise click.ClickException(str(exc))
        click.echo(f"Created {path} (schema version {version}).")

    @app.cli.command("migrate")
    def migrate_command():
        """Apply any migrations the database does not have yet."""
        path = app.config["DATABASE"]
        if not os.path.exists(path):
            raise click.ClickException(f"{path} does not exist; run init-db first.")
        conn = sqlite3.connect(path)
        try:
            applied = apply_migrations(conn)
        except MigrationError as exc:
            raise click.ClickException(str(exc))
        finally:
            conn.close()
        click.echo(f"Applied migrations {applied}." if applied else "Already up to date.")

    @app.cli.command("seed")
    def seed_command():
        """Delete the database and recreate it with the demo data."""
        from proj2.seed import seed_database

        path = app.config["DATABASE"]
        seed_database(path)
        click.echo(f"Seeded {path}.")
