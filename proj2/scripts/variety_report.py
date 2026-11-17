"""
Show how the variety score sees the menu: each meal's nearest neighbours and the spread of distances.

    python proj2/scripts/variety_report.py                # every in-stock item
    python proj2/scripts/variety_report.py --item 12      # one item's nearest meals
    python proj2/scripts/variety_report.py --neighbours 5 --all

Uses WEEKLIES_DB_PATH or proj2/CSC510_DB.db unless --db is given. Use it after tagging
(proj2/scripts/menu_tags.py) or changing proj2/variety.WEIGHTS to check that the meals
called closest are ones a person would also call similar.
"""

import argparse
import os
import sqlite3
import sys

# Repo root on sys.path so `proj2` imports when run as `python scripts/<name>.py`.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from proj2 import config, variety  # noqa: E402

## Distance buckets for the histogram: [0, 0.1), [0.1, 0.2), ... [0.9, 1.0]
BUCKETS = 10
BAR_WIDTH = 40


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--db", help="database file (default: WEEKLIES_DB_PATH or the app's DB)")
    parser.add_argument("--item", type=int, help="only report this itm_id's neighbours")
    parser.add_argument(
        "--neighbours", type=int, default=3, help="nearest meals to list per item (default 3)"
    )
    parser.add_argument("--all", action="store_true", help="include out-of-stock items")
    return parser.parse_args(argv)


def nearest(itm_id, feats, count):
    """The count closest other items to itm_id, closest first, as (distance, other_id)."""
    others = [
        (variety.distance(feats[itm_id], feats[other]), other) for other in feats if other != itm_id
    ]
    return sorted(others)[:count]


def histogram(distances):
    """Counts of pairwise distances per bucket of width 1 / BUCKETS."""
    counts = [0] * BUCKETS
    for d in distances:
        counts[min(int(d * BUCKETS), BUCKETS - 1)] += 1
    return counts


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    args = parse_args(argv)
    path = os.path.abspath(args.db) if args.db else config.db_path()
    if not os.path.exists(path):
        print(f"No database at {path}", file=out)
        return 1

    conn = sqlite3.connect(path)
    try:
        rows = variety.catalog_rows(conn)
    finally:
        conn.close()
    if not args.all:
        rows = {i: r for i, r in rows.items() if r.get("instock") == 1}
    if args.item is not None and args.item not in rows:
        print(f"No item {args.item} (out-of-stock items need --all)", file=out)
        return 1
    if len(rows) < 2:
        print("Need at least two items to compare.", file=out)
        return 1

    feats = {i: variety.features(r) for i, r in rows.items()}

    def name(itm_id):
        return f"{rows[itm_id].get('name')} [{itm_id}]"

    targets = [args.item] if args.item is not None else sorted(rows)
    for itm_id in targets:
        print(name(itm_id), file=out)
        for d, other in nearest(itm_id, feats, args.neighbours):
            shared = "; ".join(variety.shared_tags(feats[itm_id], feats[other])) or "nothing shared"
            print(f"    {d:.2f}  {name(other)}  ({shared})", file=out)

    ids = sorted(rows)
    distances = [
        variety.distance(feats[a], feats[b]) for i, a in enumerate(ids) for b in ids[i + 1 :]
    ]
    counts = histogram(distances)
    peak = max(counts) or 1
    print(
        f"\nDistance between every pair of the {len(ids)} items ({len(distances)} pairs):", file=out
    )
    for bucket, count in enumerate(counts):
        low = bucket / BUCKETS
        bar = "#" * round(BAR_WIDTH * count / peak)
        print(f"  {low:.1f}-{low + 1 / BUCKETS:.1f}  {count:>6}  {bar}", file=out)
    ordered = sorted(distances)
    print(
        f"  min {ordered[0]:.2f}, median {ordered[len(ordered) // 2]:.2f}, max {ordered[-1]:.2f}",
        file=out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
