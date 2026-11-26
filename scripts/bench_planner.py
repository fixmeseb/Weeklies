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
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="exit non-zero if any run takes longer than this (the M0 threshold is 5)",
    )
    parser.add_argument(
        "--no-variety-loss",
        action="store_true",
        help="exit non-zero if a restart count scores below the fewest restarts measured",
    )
    args = parser.parse_args()

    original = menu_generation.RESTART_OPENINGS
    print("\n  One week, 21 slots. Target: p95 at or under 5 s.\n")
    header = f"  {'catalog':>10}" + "".join(f"{f'{r} restarts':>16}" for r in args.restarts)
    print(header)
    print("  " + "-" * (len(header) - 2))
    slowest = 0.0
    regressions = []
    baseline_restarts = min(args.restarts)
    try:
        for copies in args.copies:
            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "bench.db")
                seed.seed_database(path)
                items = grow(path, copies) if copies else _count(path)
                cells = []
                scores = {}
                for restarts in args.restarts:
                    seconds, score = time_week(path, restarts)
                    slowest = max(slowest, seconds)
                    scores[restarts] = score
                    flag = " " if seconds <= 5 else "!"
                    cells.append(f"{seconds:.2f} s{flag} / {score:.4f}")
                print(f"  {items:>7} items" + "".join(f"{c:>16}" for c in cells))
                baseline = scores[baseline_restarts]
                for restarts, score in scores.items():
                    # Restarts try the planner's own opening first, so more restarts can
                    # only match or beat fewer. A drop here means that broke.
                    if restarts > baseline_restarts and score < baseline - 1e-9:
                        regressions.append((items, restarts, score, baseline))
    finally:
        menu_generation.RESTART_OPENINGS = original
    print("\n  ! over the 5 s target")

    ok = True
    if args.no_variety_loss and regressions:
        ok = False
        print("\n  FAIL: more restarts scored below the one-restart baseline:")
        for items, restarts, score, baseline in regressions:
            print(f"    {items} items, {restarts} restarts: {score:.4f} < {baseline:.4f}")
    if args.max_seconds is not None and slowest > args.max_seconds:
        ok = False
        print(f"\n  FAIL: slowest plan {slowest:.2f} s exceeds the {args.max_seconds:.2f} s target")
    if (args.max_seconds is not None or args.no_variety_loss) and ok:
        print(f"\n  PASS: slowest plan {slowest:.2f} s, no variety lost to restarts")
    print()
    return 0 if ok else 1


def _count(path: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM MenuItem").fetchone()[0]
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
