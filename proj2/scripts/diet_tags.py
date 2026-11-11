"""
Tag menu items with the diets they meet (vegetarian, vegan, halal, ...).

    python proj2/scripts/diet_tags.py export menu_tags.csv
    # fill in the diet_tags column, then check it:
    python proj2/scripts/diet_tags.py import menu_tags.csv
    # write it once the check is clean:
    python proj2/scripts/diet_tags.py import menu_tags.csv --apply

Uses WEEKLIES_DB_PATH or proj2/CSC510_DB.db unless --db is given. Import changes nothing
unless every row is valid; see proj2/diet_tags_io.py for the rules.
"""

import argparse
import os
import sqlite3
import sys

# Repo root on sys.path so `proj2` imports when run as `python scripts/<name>.py`.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from proj2 import config  # noqa: E402
from proj2.diet_tags_io import apply_import, export_csv, plan_import  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--db", help="database file (default: WEEKLIES_DB_PATH or the app's DB)")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write every menu item to a CSV for tagging")
    export.add_argument("csv", help="file to write, or - for standard output")
    imp = commands.add_parser("import", help="check a tagged CSV, and write it with --apply")
    imp.add_argument("csv", help="the tagged CSV")
    imp.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    return parser.parse_args(argv)


def _show(value: str) -> str:
    return value or "(none)"


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    args = parse_args(argv)
    path = os.path.abspath(args.db) if args.db else config.db_path()
    if not os.path.exists(path):
        print(f"No database at {path}", file=out)
        return 1

    conn = sqlite3.connect(path)
    try:
        if args.command == "export":
            if args.csv == "-":
                count = export_csv(conn, out)
            else:
                # utf-8-sig so the file opens cleanly in Excel
                with open(args.csv, "w", newline="", encoding="utf-8-sig") as handle:
                    count = export_csv(conn, handle)
                print(f"Wrote {count} items to {args.csv}", file=out)
            return 0

        with open(args.csv, newline="", encoding="utf-8-sig") as handle:
            plan = plan_import(conn, handle)
        if not plan.ok:
            print(f"{len(plan.errors)} problem(s); nothing was changed:", file=out)
            for error in plan.errors:
                print(f"  {error}", file=out)
            return 1

        for itm_id, name, old, new in plan.changes:
            print(f"  {itm_id:>5}  {name}: {_show(old)} -> {_show(new)}", file=out)
        summary = f"{len(plan.changes)} to change, {plan.unchanged} unchanged"
        if not args.apply:
            print(f"Dry run: {summary}. Run again with --apply to write.", file=out)
            return 0
        apply_import(conn, plan)
        print(f"Applied: {summary}.", file=out)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
