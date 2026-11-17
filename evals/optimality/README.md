# How good is the variety planner?

`MenuGenerator.update_menu` fills each slot with the best-scoring candidate next to what is
already planned, then improves it. That is a heuristic. It is fast and it is deterministic,
but nothing in the repository said how close its weeks are to the best week that was
actually available, and a heuristic nobody has measured is a heuristic nobody can defend in
a review.

Measuring it turned out to be worth the trouble: the planner was losing 4% of its variety
*and* several dollars a week to one arbitrary first pick. Both are fixed below, and the
harness is what proves it.

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
"Before" is the planner as it was: one greedy pass plus a single improvement pass.

| scenario | slots | before | after | optimum | gap now | proven |
|---|---|---|---|---|---|---|
| dinners, 3 days | 3 | 0.9286 | **0.9614** | 0.9667 | 0.0054 | yes |
| dinners, 5 days | 5 | 0.9337 | **0.9402** | 0.9402 | 0.0001 | yes |
| dinners, 5d, vegetarian | 5 | 0.9127 | 0.9127 | 0.9127 | 0.0001 | yes |
| dinners, 5d, nut+dairy allergy | 5 | 0.9340 | **0.9206** | 0.9206 | 0.0000 | yes |
| all meals, 3 days | 9 | 0.9069 | **0.9115** | ≤ 0.9682 | ≤ 0.0567 | bound only |

Three of the four scenarios that solve to proven optimality now **sit on the optimum**
(0.0001 is the integer scaling, not a real difference), and the worst proven shortfall
fell from 4.1% to 0.6%.

### What the gap was

The first slot has nothing planned around it, so every candidate scored the same zero
gain and the tie-break handed the slot to the cheapest item. That arbitrary pick shaped
the rest of the week, and re-picking one slot at a time could not undo it: the plan was
already a local optimum. Two changes, both in `proj2/menu_generation.py`:

- **Improve until nothing changes.** Re-picking a slot changes what its neighbours should
  be, so one pass leaves stale picks behind. Each accepted move strictly raises that
  slot's gain and leaves every pair not touching it alone, so the total rises monotonically
  and the loop settles on its own.
- **Restart from a spread of openings.** The whole fill-and-improve runs once per opening
  for the first slot, sampled evenly across its candidates, and the best plan wins. The
  default opening is tried first, so a restart can only improve on what the planner would
  have produced anyway.

### What it cost

Restarts multiply planning work, so the cost depends entirely on the per-request caching in
the speedup PR. Measured by [`scripts/bench_planner.py`](../../scripts/bench_planner.py),
one week of 21 slots, on top of that caching:

| catalog | 12 restarts | 4 | 1 | none |
|---|---|---|---|---|
| 76 items | 0.13 s | 0.06 s | 0.03 s | 0.03 s |
| 228 items | 0.25 s | 0.11 s | 0.07 s | 0.05 s |
| 1,596 items | **1.80 s** | 0.72 s | 0.36 s | 0.22 s |

At the largest catalog the full twelve restarts cost about 8x the planning time and still
finish in **1.8 s against the 5 s target**. Without that caching the same work would be
roughly an order of magnitude slower and would miss the target, so these two changes belong
in that order: the speedup first, this on top of it.

`RESTART_OPENINGS` is the dial if the catalog grows past this. The variety it buys falls off
quickly — 12 restarts beat 4 by 0.0009 on the 1,596-item catalog, because that catalog is
the demo menu repeated and has variety to spare.

### What it exposed

Measuring harder found a rule nobody had written down. With 10 items over 7 dinners, the
improved search produced a plan that repeated one dish three days apart and *scored
higher* for it: `closeness` has decayed to 0.16 at a nine-slot gap, so the objective barely
penalises a distant repeat. The old planner avoided repeats by accident, not by rule, and
`test_no_repeats_while_there_are_enough_different_meals` had been passing on that accident.

So "do not repeat a meal while an unused one is available" is now an explicit rule in the
ranking, ahead of the score, and the solver carries the same `AllDifferent` constraint so
the comparison stays fair. When no all-different plan exists the harness drops the rule on
both sides rather than calling the week impossible.

This is the useful kind of result: a better optimiser is also a test of whether the
objective says what the team meant.

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
