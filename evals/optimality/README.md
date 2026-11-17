# How good is the variety planner?

`MenuGenerator.update_menu` fills each slot with the best-scoring candidate next to what is
already planned, then makes one improvement pass. That is a heuristic. It is fast and it is
deterministic, but nothing in the repository said how close its weeks are to the best week
that was actually available, and a heuristic nobody has measured is a heuristic nobody can
defend in a review.

[`scripts/eval_optimality.py`](../../scripts/eval_optimality.py) measures it: for each
scenario it runs the real planner, then solves the same week exactly with CP-SAT over the
same candidate sets and the same objective, and reports the difference.

## Why the comparison is fair

- **Same objective.** `variety.plan_variety` reports
  `sum(closeness * distance) / sum(closeness)`, and `variety`'s own docstring notes that the
  closeness weights depend only on which slots are filled, never on what fills them. The
  denominator is a constant for a fixed set of slots, so maximising the reported score is
  exactly maximising `sum(closeness * distance)` — which is what the model maximises.
- **Same candidates.** Slot pools come from `MenuGenerator._eligible_candidates`, the
  planner's own filter, not from a reimplementation. The solver may only choose from what
  the planner could have chosen.
- **Same scorer.** Both plans are scored by `variety.plan_variety`. The harness also
  recomputes the greedy's score itself and checks it against the planner's own
  `self.variety.score`; if those disagree it refuses to report a gap.
- **No soft preferences.** The greedy adds `PREFERENCE_WEIGHT * preference_match` to its
  per-slot score, but the reported score does not include it. Scenarios use diets (hard
  rules) only, so both sides optimise the same thing.

`gap` is the **proven upper bound minus the greedy's score**: the most variety the planner
can be leaving on the table, not an estimate. The greedy's plan is always feasible in the
model, so the true optimum never sits below it.

## Results

Demo catalog (11 restaurants, 76 tagged dishes), week of 2026-11-23, 90 s solver limit.

| scenario | slots | greedy | optimum | gap | proven |
|---|---|---|---|---|---|
| dinners, 3 days | 3 | 0.9286 | 0.9667 | **0.0381** (4.1%) | yes |
| dinners, 5 days | 5 | 0.9337 | 0.9402 | 0.0065 (0.7%) | yes |
| dinners, 5d, vegetarian | 5 | 0.9127 | 0.9127 | 0.0001 | yes |
| dinners, 5d, nut+dairy allergy | 5 | 0.9340 | 0.9402 | 0.0062 | yes |
| all meals, 3 days | 9 | 0.9069 | ≤ 0.9733 | ≤ 0.0665 | bound only |

**The better plan is also the cheaper plan**, every time it exists:

| scenario | planner | optimum | |
|---|---|---|---|
| dinners, 3 days | $40.27 | $33.97 | $6.30 cheaper **and** more varied |
| dinners, 5 days | $64.95 | $56.45 | $8.50 cheaper **and** more varied |
| dinners, 5d, nut+dairy allergy | $62.95 | $56.45 | $6.50 cheaper **and** more varied |

That is the finding worth acting on. The planner's tie-break is `(-score, price, itm_id)`,
so price only decides a tie — yet in every proven case there was a plan that was better on
both axes at once. The shortfall is not the planner trading variety for thrift; it is
myopia, and it costs the user money as well as variety.

Where the pools are small the greedy is already optimal: the vegetarian week has 9
candidates per slot and the gap is 0.0001. The gap opens up when there is more to choose
from, which is the case the catalog is growing towards.

## Running it

```bash
pip install ortools            # the app itself does not use it
python scripts/eval_optimality.py
python scripts/eval_optimality.py --days 7 --seconds 300
python scripts/eval_optimality.py --max-gap 0.01    # exit non-zero if any gap is larger
```

Writes [`results.json`](results.json).

## Honest limitations

- **Proving optimality is exponential here.** The objective is quadratic — every pair of
  meals in the window contributes — so 3 slots close in about 3 s, 5 in about 18 s, and 7
  do not close in 90 s. The ladder of scenarios is sized so most report a proven optimum;
  the all-meals row reports a bound, which is still a true statement.
- **One catalog, one week.** Everything runs against the demo menu starting on a Monday.
  The gap on a real catalog, or one with many more items per slot, is not measured here.
- **Variety only.** The weekly cap can be modelled (`cap_cents` on a scenario) but the
  default scenarios run uncapped, so the cost column reports what each plan happens to
  cost rather than what either could achieve under a budget.
- **No claim about which plan a user prefers.** This measures the objective the product
  already chose to optimise. Whether that objective matches what people want is a
  different experiment, and needs people.
