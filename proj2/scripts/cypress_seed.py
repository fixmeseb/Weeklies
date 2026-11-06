"""
Recreate the Cypress E2E database with the demo data (see proj2/seed.py).

The database is $WEEKLIES_DATABASE if set (relative paths are from the repo root),
else proj2/instance/cypress.db. The Flask server under test must be started with the
same WEEKLIES_DATABASE. This
script refuses to touch the development database (proj2/CSC510_DB.db), so E2E
runs can no longer wipe local data.

    python proj2/scripts/cypress_seed.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from proj2.db import DATABASE_ENV, DEFAULT_DATABASE, database_path_from_env
from proj2.seed import seed_database

CYPRESS_DATABASE = os.path.join(ROOT, "proj2", "instance", "cypress.db")


def cypress_database_path(environ=os.environ):
    return database_path_from_env(environ, default=CYPRESS_DATABASE)


def main(environ=os.environ):
    path = cypress_database_path(environ)
    if os.path.normcase(path) == os.path.normcase(os.path.abspath(DEFAULT_DATABASE)):
        sys.exit(
            f"Refusing to reseed the development database {path}. "
            f"Point {DATABASE_ENV} at a separate file for Cypress."
        )
    seed_database(path)
    print(f"Database successfully seeded for Cypress tests: {path}")


if __name__ == "__main__":
    main()
