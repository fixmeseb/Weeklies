"""
Recreate the Cypress E2E database with the demo data (see proj2/seed.py).

The database is $WEEKLIES_DB_PATH if set, else proj2/instance/cypress.db. The Flask
server under test must be started with the same WEEKLIES_DB_PATH; use an absolute
path, because this script and the server run from different directories. This script
refuses to touch the development database (proj2/CSC510_DB.db), so E2E runs can no
longer wipe local data. Accounts get the Cypress password, password123.

    python proj2/scripts/cypress_seed.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from proj2 import config
from proj2.seed import seed_database

CYPRESS_DATABASE = os.path.join(ROOT, "proj2", "instance", "cypress.db")


def cypress_database_path(environ=os.environ):
    if (environ.get(config.DB_PATH_ENV) or "").strip():
        return config.db_path(environ)
    return CYPRESS_DATABASE


def main(environ=os.environ):
    path = cypress_database_path(environ)
    if os.path.normcase(path) == os.path.normcase(config.DEFAULT_DB_PATH):
        sys.exit(
            f"Refusing to reseed the development database {path}. "
            f"Point {config.DB_PATH_ENV} at a separate file for Cypress."
        )
    seed_database(path)
    print(f"Database successfully seeded for Cypress tests: {path}")


if __name__ == "__main__":
    main()
