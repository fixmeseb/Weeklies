#!/usr/bin/env python3
"""Time a week of planning as the catalog grows, with and without restarts.

PR #8 reports 11.14 s for a one-week plan on a 1,596-item catalog before its caching and
1.53 s after. The restart search added for the optimality fix multiplies planning work, so
the question this answers is whether the two together still fit the 5 s target on a catalog
that size.

The large catalogs are the demo menu (11 restaurants, 76 dishes) repeated across more
restaurants, which is how 1,596 is reached: 76 x 21. Repeats make the catalog easier to
plan well, not harder, so these times are about the work per request rather than about
plan quality.

    python scripts/bench_planner.py
    python scripts/bench_planner.py --restarts 12 4 1
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from proj2 import menu_generation, seed  # noqa: E402
from proj2.menu_generation import MenuGenerator  # noqa: E402

MONDAY = "2026-11-23"


def grow(path: str, copies: int) -> int:
    """Repeat every restaurant and its menu `copies` extra times. Returns the item count."""
    conn = sqlite3.connect(path)
    try:
        restaurants = conn.execute(
            "SELECT rtr_id, name, description, phone, email, password_HS, address, city,"
            " state, zip, hours, status FROM Restaurant"
        ).fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM MenuItem LIMIT 1").description]
        carried = [c for c in columns if c != "itm_id"]
        placeholders = ", ".join("?" for _ in carried)

        for copy in range(1, copies + 1):
            for row in restaurants:
                old_id, name = row[0], row[1]
                conn.execute(
                    "INSERT INTO Restaurant (name, description, phone, email, password_HS,"
                    " address, city, state, zip, hours, status)"
                    f" VALUES ({', '.join('?' for _ in range(11))})",
                    # row is (rtr_id, name, description, phone, email, password_HS, ...);
                    # only the email carries a UNIQUE constraint.
                    (f"{name} #{copy}", row[2], row[3], f"c{copy}-{row[4]}", row[5], *row[6:]),
                )
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                items = conn.execute(
                    f"SELECT {', '.join(carried)} FROM MenuItem WHERE rtr_id = ?", (old_id,)
                ).fetchall()
                rtr_index = carried.index("rtr_id")
                for item in items:
                    values = list(item)
                    values[rtr_index] = new_id
                    conn.execute(
                        f"INSERT INTO MenuItem ({', '.join(carried)}) VALUES ({placeholders})",
                        values,
                    )
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM MenuItem").fetchone()[0]
    finally:
        conn.close()


def time_week(path: str, restarts: int) -> tuple:
    """Plan one week at a given restart count. Returns (seconds, variety score)."""
    generator = MenuGenerator(database_path=path)
    # Bound per instance rather than by setting the module constant, so the count really
    # reaches the planner whatever the constant was at import.
    unbound = type(generator)._restart_openings
    generator._restart_openings = lambda slots, limit=restarts: unbound(generator, slots, limit)
    started = time.perf_counter()
    generator.update_menu("", "", "", MONDAY, [1, 2, 3], 7)
    return time.perf_counter() - started, generator.variety.score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copies", type=int, nargs="+", default=[0, 2, 20])
    parser.add_argument("--restarts", type=int, nargs="+", default=[12, 4, 1])
    args = parser.parse_args()

    original = menu_generation.RESTART_OPENINGS
    print("\n  One week, 21 slots. Target: p95 at or under 5 s.\n")
    header = f"  {'catalog':>10}" + "".join(f"{f'{r} restarts':>16}" for r in args.restarts)
    print(header)
    print("  " + "-" * (len(header) - 2))
    try:
        for copies in args.copies:
            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "bench.db")
                seed.seed_database(path)
                items = grow(path, copies) if copies else _count(path)
                cells = []
                for restarts in args.restarts:
                    seconds, score = time_week(path, restarts)
                    flag = " " if seconds <= 5 else "!"
                    cells.append(f"{seconds:.2f} s{flag} / {score:.4f}")
                print(f"  {items:>7} items" + "".join(f"{c:>16}" for c in cells))
    finally:
        menu_generation.RESTART_OPENINGS = original
    print("\n  ! over the 5 s target\n")
    return 0


def _count(path: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM MenuItem").fetchone()[0]
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
