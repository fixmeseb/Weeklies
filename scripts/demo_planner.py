#!/usr/bin/env python3
"""Run the meeting examples and serve a fresh local Weeklies demo."""

import argparse
from contextlib import closing
from datetime import date
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from tempfile import TemporaryDirectory

from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proj2.seed import seed_database  # noqa: E402
from scripts.compare_planners import main as compare  # noqa: E402

DEMO_EMAIL = "testuser@example.com"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console-only", action="store_true", help="Run the examples and exit")
    parser.add_argument("--port", type=int, default=0, help="Use a specific local port")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    print("\nExample 1 — Three dinners and the cost–variety trade-off")
    compare(["--tradeoffs"])
    print("\nExample 2 — A full week of meals under a $245 item cap")
    compare(["--days", "7", "--meals", "1", "2", "3", "--cap", "245"])
    if args.console_only:
        return 0

    with TemporaryDirectory(prefix="weeklies-demo-") as directory:
        database = str(Path(directory) / "demo.db")
        password = secrets.token_urlsafe(9)
        seed_database(database, password)
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute('UPDATE "User" SET generated_menu = ? WHERE email = ?', ("", DEMO_EMAIL))

        os.environ["WEEKLIES_DB_PATH"] = database
        os.environ["WEEKLIES_SECRET_KEY"] = secrets.token_hex(32)
        from proj2.Flask_app import app

        with make_server("127.0.0.1", args.port, app, threaded=True) as server:
            url = f"http://127.0.0.1:{server.server_port}"
            print(f"\nLive demo at {url}/login")
            print(f"Email    {DEMO_EMAIL}")
            print(f"Password {password}")
            print(f"\nAfter login, open {url}/profile#optimization-preferences")
            print("Add and save priorities of 60 variety, 25 lower cost, and 15 preference match.")
            print(f"Then open {url}/#new-plan")
            print(f"Pick {date.today().isoformat()}, three days, and Dinner only.")
            print("Set a $45 weekly item cap.")
            print("Generate Plan to show the metrics, then open Insights for the saved week.")
            print("On Home, choose Seed Catalog & Almanac in the Style picker to show the almanac.")
            print("Press Ctrl-C to stop the demo.\n", flush=True)
            server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
