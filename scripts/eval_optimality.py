#!/usr/bin/env python3
"""How close the planner's weeks are to the best week that was available.

`MenuGenerator.update_menu` fills slots greedily -- for each slot in turn it takes the
candidate with the highest `variety.candidate_score` next to what is already planned --
and then makes one improvement pass. That is a heuristic. It is fast and deterministic,
but nothing in the repository says how much variety it leaves on the table, and a
heuristic nobody has measured is a heuristic nobody can defend.

This harness answers that. For each scenario it:

1. runs the real planner and scores the week with `variety.plan_variety`;
2. solves the same week exactly with CP-SAT, over the same candidate sets, maximising the
   same objective;
3. reports the gap.

The objective is exactly the one the product reports. `plan_variety` returns

    sum(closeness(i, j) * distance(i, j)) / sum(closeness(i, j))

over every pair of planned meals, and `variety`'s own docstring notes the key fact: the
closeness weights depend only on which slots are filled, never on what fills them. The
denominator is therefore a constant for a given set of slots, so maximising the reported
score is exactly maximising `sum(closeness * distance)` -- a linear objective over the
pairwise distances, which is what the model below maximises.

Two deliberate choices keep the comparison honest:

- Scenarios use no soft preferences. The greedy adds `PREFERENCE_WEIGHT * preference_match`
  to its per-slot score, but `plan_variety` -- the number shown to the user -- does not.
  With no soft preferences the two objectives coincide, so any gap is the heuristic's, not
  an artefact of comparing different targets.
- Candidate sets come from `MenuGenerator._eligible_candidates`, the planner's own filter,
  rather than being rebuilt here. A private call is the point: the exact solver must choose
  from precisely what the planner could have chosen, or the gap means nothing.

The harness also recomputes the greedy's score itself and checks it against the planner's
own `self.variety.score`. If those two disagree, this script is measuring the wrong thing
and says so instead of reporting a number.

Running it:

    python scripts/eval_optimality.py                  # the default scenarios
    python scripts/eval_optimality.py --days 7         # one week
    python scripts/eval_optimality.py --max-gap 0.02   # exit non-zero if any gap is larger

Needs `ortools`, which the app itself does not use:  pip install ortools
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from proj2 import seed, variety  # noqa: E402
from proj2.menu_generation import MenuGenerator, get_meal_and_order_time  # noqa: E402
from proj2.menu_generation import DAYS_OF_WEEK  # noqa: E402

try:
    from ortools.sat.python import cp_model
except ImportError:  # pragma: no cover - environment problem, not a logic branch
    sys.exit("This harness needs OR-Tools. Install it with:  pip install ortools")

## Distances and closeness weights are floats in [0, 1]; CP-SAT needs integers. Ten
## thousand steps is finer than any difference the tag weights can produce, and keeps the
## objective's coefficients small enough that the solver can close the bound quickly --
## at a millionth, proving optimality on a six-slot week timed out at 30 s.
SCALE = 10_000


@dataclass
class Scenario:
    name: str
    start: str
    days: int
    meals: tuple = (1, 2, 3)
    allergens: str = ""
    preferences: str = ""  # diets only; soft preferences would split the objectives
    cap_cents: int = None


@dataclass
class Outcome:
    scenario: str
    slots: int
    candidates_per_slot: float
    greedy_score: float
    best_score: float
    upper_bound: float
    gap: float
    proven_optimal: bool
    solver_status: str
    greedy_seconds: float
    exact_seconds: float
    agrees_with_planner: bool
    greedy_cents: int = 0
    best_cents: int = 0
    notes: list = field(default_factory=list)


def build_database(directory: str) -> str:
    """Seed the demo catalog (proj2/demo_menu.py) into a throwaway file."""
    path = os.path.join(directory, "optimality.db")
    seed.seed_database(path)
    return path


def plan_slots(scenario: Scenario) -> list:
    """(iso_date, weekday, meal, slot_position) for every slot the scenario plans."""
    start = datetime.date.fromisoformat(scenario.start)
    slots = []
    for offset in range(scenario.days):
        day = (start + datetime.timedelta(days=offset)).isoformat()
        weekday = DAYS_OF_WEEK[datetime.date.fromisoformat(day).weekday()]
        for meal in scenario.meals:
            slots.append((day, weekday, meal, variety.slot_position(day, meal)))
    return slots


def candidate_pools(generator: MenuGenerator, scenario: Scenario, slots: list) -> list:
    """The planner's own eligible items for each slot, as a list of itm_id lists.

    The price cap is left out here even when the scenario sets one: the greedy applies it
    per slot as a shrinking reserve, while the exact model carries the real constraint,
    that each week's chosen items must total at most the cap. Handing the solver the
    greedy's reserve would quietly impose the heuristic on the optimum.
    """
    pools = []
    for _, weekday, meal, _ in slots:
        _, order_time = get_meal_and_order_time(meal)
        pool = generator._eligible_candidates(
            scenario.allergens,
            weekday,
            order_time,
            preferences=scenario.preferences,
            meal=meal,
        )
        pools.append([int(itm_id) for itm_id in pool["itm_id"]])
    return pools


def score_entries(entries, items) -> float:
    """The product's own score for a set of planned meals."""
    report = variety.plan_variety(entries, items)
    return 0.0 if report.score is None else report.score


def run_greedy(generator: MenuGenerator, scenario: Scenario, items) -> tuple:
    """The planner's plan, its score, and the score the planner reported for itself."""
    started = time.perf_counter()
    menu = generator.update_menu(
        "",
        scenario.preferences,
        scenario.allergens,
        scenario.start,
        list(scenario.meals),
        number_of_days=scenario.days,
        weekly_cap_cents=scenario.cap_cents,
    )
    elapsed = time.perf_counter() - started
    entries = [(day, itm_id, meal) for day, itm_id, meal in _entries(menu)]
    reported = None if generator.variety is None else generator.variety.score
    return entries, score_entries(entries, items), reported, elapsed


def _entries(menu: str):
    from proj2.meal_budget import plan_entries

    return list(plan_entries(menu))


def solve_exactly(
    slots, pools, items, prices, scenario, seconds: float, hint=None, distinct=True
) -> tuple:
    """Maximise the reported variety score exactly, over the planner's candidate sets.

    Each slot gets an index variable over its own candidate list. For every pair of slots
    whose closeness weight is non-zero, a table constraint ties the two indices to the
    scaled distance between the items they select, and the objective is the closeness-
    weighted sum of those distances. The denominator of the reported score is a constant
    for a fixed set of slots, so this maximises the score itself.

    Returns (entries, score, upper_bound_score, status_name, seconds, notes).
    """
    model = cp_model.CpModel()
    notes = []

    features = {itm_id: variety.features(row) for itm_id, row in items.items()}
    choice = [model.NewIntVar(0, len(pool) - 1, f"slot_{s}") for s, pool in enumerate(pools)]

    # The planner will not repeat a meal while it still has an unused one, so the solver
    # must not either; without this the gap would credit the optimum with freedom the
    # planner does not have. Slots have different pools, so the choice indices cannot be
    # compared directly and the chosen item id is modelled explicitly.
    if distinct:
        chosen_item = []
        for s, pool in enumerate(pools):
            item_var = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(sorted(set(pool))), f"item_{s}"
            )
            model.AddAllowedAssignments(
                [choice[s], item_var], [(a, item) for a, item in enumerate(pool)]
            )
            chosen_item.append(item_var)
        model.AddAllDifferent(chosen_item)

    positions = [position for _, _, _, position in slots]
    weight_total = 0.0
    objective_terms = []

    for i in range(len(slots)):
        for j in range(i + 1, len(slots)):
            w = variety.closeness(positions[i], positions[j])
            if not w:
                continue
            weight_total += w
            distance_var = model.NewIntVar(0, SCALE, f"d_{i}_{j}")
            tuples = []
            for a, item_a in enumerate(pools[i]):
                for b, item_b in enumerate(pools[j]):
                    d = variety.distance(features[item_a], features[item_b])
                    tuples.append((a, b, int(round(d * SCALE))))
            model.AddAllowedAssignments([choice[i], choice[j], distance_var], tuples)
            objective_terms.append(int(round(w * SCALE)) * distance_var)

    if scenario.cap_cents is not None:
        weeks = {}
        for s, (day, _, _, _) in enumerate(slots):
            weeks.setdefault(_week_start(day), []).append(s)
        for week, members in weeks.items():
            spend = []
            for s in members:
                cost = model.NewIntVar(0, max(prices[i] for i in pools[s]), f"cost_{s}")
                model.AddAllowedAssignments(
                    [choice[s], cost],
                    [(a, prices[item]) for a, item in enumerate(pools[s])],
                )
                spend.append(cost)
            model.Add(sum(spend) <= scenario.cap_cents)
            notes.append(f"week of {week}: spend capped at {scenario.cap_cents}c")

    model.Maximize(sum(objective_terms))

    # Start from the greedy's own plan. The solver then spends its time proving how much
    # better a week could be, instead of rediscovering a decent one, and a timed-out run
    # still reports a bound that means something.
    if hint:
        for s, itm_id in enumerate(hint):
            if itm_id in pools[s]:
                model.AddHint(choice[s], pools[s].index(itm_id))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 8
    # The hint sets only the slot variables; the distance variables it implies are left to
    # the solver, so let it repair the partial hint rather than discard it.
    solver.parameters.repair_hint = True
    started = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - started

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], 0.0, 0.0, solver.StatusName(status), elapsed, notes

    entries = []
    for s, (day, _, meal, _) in enumerate(slots):
        entries.append((day, pools[s][solver.Value(choice[s])], meal))

    denominator = weight_total or 1.0
    best = solver.ObjectiveValue() / (SCALE * SCALE) / denominator
    bound = solver.BestObjectiveBound() / (SCALE * SCALE) / denominator
    return entries, best, bound, solver.StatusName(status), elapsed, notes


def _week_start(day: str) -> str:
    from proj2.meal_budget import week_start

    return week_start(day)


def evaluate(scenario: Scenario, database: str, seconds: float) -> Outcome:
    generator = MenuGenerator(database_path=database)
    conn = sqlite3.connect(database)
    try:
        items = variety.catalog_rows(conn)
    finally:
        conn.close()
    prices = {itm_id: int(row["price"]) for itm_id, row in items.items()}

    slots = plan_slots(scenario)
    pools = candidate_pools(generator, scenario, slots)

    greedy_entries, greedy_score, reported, greedy_seconds = run_greedy(generator, scenario, items)
    agrees = reported is None or abs(reported - greedy_score) < 1e-9

    by_slot = {(day, meal): itm_id for day, itm_id, meal in greedy_entries}
    hint = [by_slot.get((day, meal)) for day, _, meal, _ in slots]

    exact_entries, best, bound, status, exact_seconds, notes = solve_exactly(
        slots, pools, items, prices, scenario, seconds, hint=hint
    )
    if status == "INFEASIBLE":
        # Not enough different meals to fill the week, which is the one case where the
        # planner is allowed to repeat. Drop the rule on both sides rather than report
        # a week as impossible.
        exact_entries, best, bound, status, exact_seconds, extra = solve_exactly(
            slots, pools, items, prices, scenario, seconds, hint=hint, distinct=False
        )
        notes = extra + ["no all-different solution exists; repeats allowed, as the planner does"]
    # Score the solver's own plan through plan_variety too, so both numbers come from the
    # product's scorer rather than from the model's arithmetic.
    if exact_entries:
        rescored = score_entries(exact_entries, items)
        # The two differ only by the integer scaling of the distances; anything larger
        # would mean the model is not optimising the score the product reports.
        if abs(rescored - best) > 1.0 / SCALE:
            notes.append(f"model objective {best:.6f} vs plan_variety {rescored:.6f}")
        best = rescored

    # The greedy's plan is feasible in this model by construction, so the true optimum is
    # never below it. On a run that times out the solver can return something worse, which
    # says nothing about the planner; the honest statement is the distance to the proven
    # upper bound -- at most this much variety is being left on the table.
    if best < greedy_score:
        notes.append(
            f"solver's best ({best:.6f}) is below the greedy's own plan; "
            "reporting the greedy as the incumbent"
        )
        best = greedy_score
    bound = max(bound, best)

    return Outcome(
        scenario=scenario.name,
        slots=len(slots),
        candidates_per_slot=round(sum(len(p) for p in pools) / len(pools), 1),
        greedy_score=round(greedy_score, 6),
        best_score=round(best, 6),
        upper_bound=round(bound, 6),
        gap=round(bound - greedy_score, 6),
        greedy_cents=sum(prices[itm_id] for _, itm_id, _ in greedy_entries),
        best_cents=sum(prices[itm_id] for _, itm_id, _ in exact_entries) if exact_entries else 0,
        proven_optimal=status == "OPTIMAL",
        solver_status=status,
        greedy_seconds=round(greedy_seconds, 3),
        exact_seconds=round(exact_seconds, 2),
        agrees_with_planner=agrees,
        notes=notes,
    )


def default_scenarios(days: int) -> list:
    """A ladder of sizes, Monday-started so the days line up with the budget week.

    Proving optimality on this objective gets hard quickly: 3 slots closes in about 3 s,
    5 in about 18 s, and 7 does not close in 90 s. The dinner-only scenarios are therefore
    sized to finish with a proven optimum, and the all-meals one is included knowing it
    will usually report a bound instead -- a bound is still a true statement about how
    much the planner can be losing.
    """
    monday = "2026-11-23"
    return [
        Scenario("dinners, 3 days", monday, 3, meals=(3,)),
        Scenario("dinners, 5 days", monday, 5, meals=(3,)),
        Scenario("dinners, 5d, vegetarian", monday, 5, meals=(3,), preferences="vegetarian"),
        Scenario(
            "dinners, 5d, nut+dairy allergy",
            monday,
            5,
            meals=(3,),
            allergens="Peanuts, Milk",
        ),
        Scenario(f"all meals, {days} days", monday, days),
    ]


def report(outcomes: list, max_gap: float) -> bool:
    print("\nOptimality of the variety planner\n")
    header = (
        f"  {'scenario':<34}{'slots':>6}{'cand':>6}{'greedy':>9}{'best':>9}"
        f"{'bound':>9}{'gap':>9}  {'proven':<9}{'exact s':>9}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for o in outcomes:
        print(
            f"  {o.scenario:<34}{o.slots:>6}{o.candidates_per_slot:>6}"
            f"{o.greedy_score:>9.4f}{o.best_score:>9.4f}{o.upper_bound:>9.4f}{o.gap:>9.4f}  "
            f"{('yes' if o.proven_optimal else o.solver_status.lower()):<9}{o.exact_seconds:>9.2f}"
        )
    print()
    print("  gap = proven upper bound - greedy, so it is the most variety the planner")
    print("  can be leaving on the table, not an estimate.\n")

    cheaper = [o for o in outcomes if o.best_cents and o.best_cents < o.greedy_cents]
    if cheaper:
        print("  Where the better plan also costs less:")
        for o in cheaper:
            saved = (o.greedy_cents - o.best_cents) / 100
            print(
                f"    {o.scenario:<34} ${o.greedy_cents / 100:.2f} -> "
                f"${o.best_cents / 100:.2f}  (${saved:.2f} cheaper, and more varied)"
            )
        print()

    mismatched = [o for o in outcomes if not o.agrees_with_planner]
    if mismatched:
        print("  SCORING MISMATCH: this harness and the planner disagree on the greedy's own")
        print("  score, so the gaps above are not trustworthy:")
        for o in mismatched:
            print(f"    {o.scenario}")
        return False

    worst = max(outcomes, key=lambda o: o.gap)
    print(f"  Largest gap: {worst.gap:.4f} on {worst.scenario!r}", end="")
    if worst.greedy_score:
        print(f"  ({worst.gap / worst.greedy_score:.1%} of its score)")
    else:
        print()

    unproven = [o for o in outcomes if not o.proven_optimal]
    if unproven:
        print(
            f"  {len(unproven)} scenario(s) hit the time limit; their 'best' is the best found,"
            " not a proven optimum."
        )

    if max_gap is not None and worst.gap > max_gap:
        print(f"\n  FAIL: gap {worst.gap:.4f} exceeds the --max-gap of {max_gap:.4f}")
        return False
    print("\n  PASS")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=3, help="days per scenario (default 3)")
    parser.add_argument(
        "--seconds", type=float, default=60.0, help="CP-SAT time limit per scenario"
    )
    parser.add_argument(
        "--max-gap",
        type=float,
        default=None,
        help="exit non-zero if any scenario's gap exceeds this",
    )
    parser.add_argument(
        "--json",
        default=os.path.join(REPO_ROOT, "evals", "optimality", "results.json"),
        help="where to write the machine-readable report",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        database = build_database(directory)
        outcomes = []
        for scenario in default_scenarios(args.days):
            print(f"  solving {scenario.name!r} ...", flush=True)
            outcomes.append(evaluate(scenario, database, args.seconds))

    ok = report(outcomes, args.max_gap)

    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    with open(args.json, "w") as handle:
        json.dump(
            {
                "question": "How much variety does the greedy planner leave on the table?",
                "objective": "plan_variety: sum(closeness*distance)/sum(closeness)",
                "days_per_scenario": args.days,
                "scenarios": [o.__dict__ for o in outcomes],
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    print(f"  wrote {os.path.relpath(args.json, REPO_ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
