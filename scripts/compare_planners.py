#!/usr/bin/env python3
"""Compare meal-planning strategies on the demo catalog. Run with --help for options."""

import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proj2 import seed  # noqa: E402
from proj2.hill_climbing import STRATEGIES  # noqa: E402
from proj2.meal_budget import parse_weekly_cap, plan_entries  # noqa: E402
from proj2.menu_generation import MenuGenerator  # noqa: E402
from proj2.plan_optimization import VARIETY_ONLY  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 8), default=3)
    parser.add_argument("--meals", type=int, choices=(1, 2, 3), nargs="+", default=[3])
    parser.add_argument("--cap", help="Weekly item cap in dollars")
    parser.add_argument("--evaluations", type=int, default=10_000)
    parser.add_argument("--restarts", type=int, default=4, help="Total starts for random-restart")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trace", action="store_true", help="Print best-so-far search points")
    parser.add_argument("--tradeoffs", action="store_true", help="Compare weights and cost caps")
    args = parser.parse_args(argv)
    if args.evaluations < 1 or args.restarts < 1:
        parser.error("--evaluations and --restarts must be positive")
    try:
        cap = parse_weekly_cap(args.cap)
    except ValueError as exc:
        parser.error(str(exc))

    with TemporaryDirectory() as directory:
        database = str(Path(directory) / "catalog.db")
        seed.seed_database(database)

        def run(label, strategy, weights=None, weekly_cap=cap, starts=1):
            generator = MenuGenerator(database_path=database)
            started = perf_counter()
            menu = generator.update_menu(
                "",
                "",
                "",
                "2026-11-23",
                args.meals,
                args.days,
                weekly_cap_cents=weekly_cap,
                strategy=strategy,
                objective_weights=weights,
                max_evaluations=args.evaluations,
                starts=starts,
                seed=args.seed,
            )
            elapsed = perf_counter() - started
            variety = generator.variety.score
            cost = sum(generator.item_prices[item] for _, item, _ in plan_entries(menu))
            result = generator.search_result
            evaluation_count = "-" if result is None else str(result.evaluations)
            moves = "-" if result is None else str(result.moves)
            starts_tried = "-" if result is None else str(result.starts)
            variety_text = "n/a" if variety is None else f"{variety:.4f}"
            print(
                f"{label:<24} {elapsed:>7.3f} {variety_text:>8} ${cost / 100:>7.2f} "
                f"{evaluation_count:>8} {moves:>6} {starts_tried:>6}"
            )
            if args.trace and result:
                for count, seconds, score in result.trace:
                    print(f"  {count:>8} eval   {seconds:>7.3f} s   {score:.6f}")
            return (variety or 0.0, cost)

        print(f"{args.days} day(s), meals {args.meals}, seed {args.seed}")
        print(
            f"{'Strategy / scenario':<24} {'Seconds':>7} {'Variety':>8} {'Cost':>8} "
            f"{'Evals':>8} {'Moves':>6} {'Starts':>6}"
        )
        try:
            run("current planner", None)
            for strategy in STRATEGIES:
                run(strategy, strategy)
            run("random-restart best", "best", starts=args.restarts)
            if args.tradeoffs:
                print("\nCost vs. variety trade-offs (higher variety and lower cost are better)")
                trials = []
                for weight in (0.0, 0.25, 0.50, 0.75, 1.0):
                    label = f"variety weight {weight:.0%}"
                    trials.append((label, run(label, "best", (weight, 1 - weight, 0.0))))
                low, high = sorted((trials[0][1][1], trials[-1][1][1]))
                caps = {low, (low + high) // 2, high}
                for limit in sorted(caps):
                    label = f"cap ${limit / 100:.2f}"
                    trials.append((label, run(label, "best", VARIETY_ONLY, limit)))
                print("\nNondominated outcomes found")
                for label, (variety, cost) in trials:
                    if not any(
                        other_v >= variety
                        and other_c <= cost
                        and (other_v > variety or other_c < cost)
                        for _, (other_v, other_c) in trials
                    ):
                        print(f"  {label:<23} variety {variety:.4f}, cost ${cost / 100:.2f}")
        except ValueError as exc:
            parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
