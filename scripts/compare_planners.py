#!/usr/bin/env python3
"""Compare search strategies with the same meal constraints, objectives, starts, and budget."""

import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proj2 import seed  # noqa: E402
from proj2.hill_climbing import (  # noqa: E402
    FINAL_TEMPERATURE,
    INITIAL_TEMPERATURE,
    LATE_ACCEPTANCE_HISTORY,
    PERTURBATION_STEPS,
    STRATEGIES,
    TABU_TENURE,
)
from proj2.meal_budget import parse_weekly_cap, plan_entries  # noqa: E402
from proj2.menu_generation import MenuGenerator  # noqa: E402
from proj2.plan_optimization import OBJECTIVES, VARIETY_ONLY, parse_weights  # noqa: E402
from scripts.bench_planner import grow  # noqa: E402

STRATEGY_LABELS = {
    "first": "First improvement",
    "best": "Best improvement",
    "stochastic": "Stochastic uphill",
    "sideways": "Best + sideways",
    "annealing": "Simulated annealing",
    "tabu": "Tabu search",
    "late-acceptance": "Late acceptance hill climbing",
    "iterated": "Iterated local search",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 15), default=3)
    parser.add_argument("--meals", type=int, choices=(1, 2, 3), nargs="+", default=[3])
    parser.add_argument("--cap", help="Weekly item cap in dollars")
    parser.add_argument("--diets", default="", help="Comma-separated required diets")
    parser.add_argument("--allergens", default="", help="Comma-separated allergens to avoid")
    parser.add_argument("--food-matches", default="", help="Comma-separated foods to favor")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help=f"Relative priority from 0 to 100. Names are {', '.join(OBJECTIVES)}. Repeat to mix.",
    )
    parser.add_argument("--evaluations", type=int, default=10_000, help="Total budget per run")
    parser.add_argument(
        "--starts", "--restarts", type=int, default=4, help="Total starts per strategy"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--catalog-copies", type=int, default=0, help="Extra copies of the catalog")
    parser.add_argument("--trace", action="store_true", help="Print best-so-far search points")
    parser.add_argument("--tradeoffs", action="store_true", help="Sweep cost and variety weights")
    args = parser.parse_args(argv)
    if args.evaluations < 1 or args.starts < 1 or args.catalog_copies < 0:
        parser.error("Evaluations and starts must be positive and catalog copies nonnegative.")
    try:
        cap = parse_weekly_cap(args.cap)
        raw_weights = dict(option.split("=", 1) for option in args.weight)
        if raw_weights.keys() - OBJECTIVES.keys():
            raise ValueError(f"Unknown objective. Choose from {', '.join(OBJECTIVES)}.")
        weights = parse_weights(tuple(raw_weights.get(name) for name in OBJECTIVES)) or VARIETY_ONLY
        if weights[2] and not args.food_matches.strip():
            raise ValueError("Supply --food-matches when using a positive preference weight.")
    except ValueError as exc:
        parser.error(str(exc))

    preferences = ", ".join(filter(None, (args.diets, args.food_matches)))
    with TemporaryDirectory() as directory:
        database = str(Path(directory) / "catalog.db")
        seed.seed_database(database)
        if args.catalog_copies:
            grow(database, args.catalog_copies)

        def run(label, strategy, priorities=weights, weekly_cap=cap, starts=args.starts):
            started = perf_counter()
            generator = MenuGenerator(database_path=database)
            menu = generator.update_menu(
                "",
                preferences,
                args.allergens,
                "2026-11-23",
                args.meals,
                args.days,
                weekly_cap_cents=weekly_cap,
                strategy=strategy,
                objective_weights=priorities if strategy else None,
                max_evaluations=args.evaluations,
                starts=starts,
                seed=args.seed,
            )
            elapsed = perf_counter() - started
            variety = generator.variety.score
            cost = sum(generator.item_prices[item] for _, item, _ in plan_entries(menu))
            result = generator.search_result
            variety_text = "n/a" if variety is None else f"{variety:.4f}"
            if result is None:
                search = f"{'-':>7} {'-':>7} {'-':>7} {'-':>7} {'-':>6} {'-':>12}"
            else:
                uphill = result.moves - result.sideways_moves - result.downhill_moves
                steps = f"{uphill}/{result.sideways_moves}/{result.downhill_moves}"
                search = (
                    f"{result.initial_score:>7.4f} {result.best_start_score:>7.4f} "
                    f"{result.best.score:>7.4f} {result.evaluations:>7} {result.starts:>6} {steps:>12}"
                )
            print(f"{label:<30} {elapsed:>7.3f} {variety_text:>8} ${cost / 100:>7.2f} {search}")
            if args.trace and result:
                for count, seconds, score in result.trace:
                    print(f"  {count:>8} eval   {seconds:>7.3f} s   {score:.6f}")
            return (variety or 0.0, cost)

        def print_columns():
            print(
                f"{'Method / scenario':<30} {'Seconds':>7} {'Variety':>8} {'Cost':>8} "
                f"{'Greedy':>7} {'Start':>7} {'Best':>7} {'Evals':>7} {'Starts':>6} {'Up/Flat/Down':>12}"
            )

        catalog_size = len(MenuGenerator(database_path=database).catalog)
        print(
            f"{catalog_size} dishes, {args.days} day(s), meal slots {args.meals} "
            "(1 breakfast, 2 lunch, 3 dinner)"
        )
        cap_label = f"${cap / 100:.2f}" if cap is not None else "none"
        print(
            f"Required diets {args.diets or 'none'} | Avoid {args.allergens or 'none'} | "
            f"Weekly cap {cap_label} | Food matches {args.food_matches or 'none'}"
        )
        padded = (*weights, *(0.0,) * (len(OBJECTIVES) - len(weights)))
        print(
            "Objective weights "
            + ", ".join(
                f"{label} {weight:.1%}" for label, weight in zip(OBJECTIVES.values(), padded)
            )
        )
        print(
            f"Seed {args.seed}, up to {args.starts} starts and {args.evaluations:,} scored plans per run. "
            f"Annealing cools from {INITIAL_TEMPERATURE} to {FINAL_TEMPERATURE} at each start."
        )
        print(
            f"Tabu tenure {TABU_TENURE} moves | Late acceptance history {LATE_ACCEPTANCE_HISTORY} scores | "
            f"Iterated local search uses {PERTURBATION_STEPS} random moves after a local optimum."
        )
        if args.catalog_copies:
            print("Extra catalog copies repeat the same foods at separate restaurant entries.")
        print(
            "Greedy is the first start's score. Start is the best starting score. "
            "Best is the highest score reached."
        )
        print(
            "Up/Flat/Down counts accepted moves. Starts and rejected proposals count only toward evaluations."
        )
        print("The default planner uses its built-in repeat, variety, and food-match rules.")
        print_columns()
        try:
            run("Default planner", None)
            if args.starts > 1:
                run("Best (greedy only)", "best", starts=1)
            for strategy in STRATEGIES:
                run(STRATEGY_LABELS[strategy], strategy)
            if args.tradeoffs:
                print("\nCost vs. variety trade-offs using best improvement")
                print("Weight rows use the displayed mix. Cap rows optimize variety alone.")
                print_columns()
                trials = []
                for weight in (0.0, 0.25, 0.50, 0.75, 1.0):
                    label = f"variety {weight:.0%} / cost {1 - weight:.0%}"
                    trials.append((label, run(label, "best", (weight, 1 - weight, 0.0))))
                low, high = sorted((trials[0][1][1], trials[-1][1][1]))
                for limit in sorted({low, (low + high) // 2, high}):
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
