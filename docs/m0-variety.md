# M0 (Project 3): How much variety does the planner leave on the table?

The Project 2 team's M0 asks whether Weeklies saves people time and keeps them in budget.
That instrument is still here, still in CI, and
[still reports its number](m0.md).

This is the M0 claim for **our** delta. It tests the thing Project 3's work rides on.

## The hypothesis

Weeklies' pitch is that among the plans satisfying every hard rule, it picks the one with
the **most variety**. That is the product's whole "so what". But `MenuGenerator.update_menu`
is a heuristic: it fills each slot with the best-scoring candidate next to what is already
there, then improves. A heuristic can be arbitrarily far from the best available week, and
until Project 3 nothing in the repository said how far.

If the planner is well short of the best plan that was actually available, the product does
not do what it claims. That is the risk this kills.

> **Claim.** On every scenario the solver proves to optimality, the plan Weeklies produces
> scores within **0.01** of the best plan available from the same candidates — and no
> scenario's *upper bound* on lost variety exceeds **0.08**.

### Metric

`variety.plan_variety`, the same number the product reports:

```
sum(closeness(i, j) * distance(i, j)) / sum(closeness(i, j))
```

over every pair of planned meals, on a 0–1 scale. The **gap** is the proven optimum minus
the planner's score, so it is the *most* variety the planner can be losing, never an
estimate.

### Baseline

The planner as it stood at the fork point, measured by this harness before any fix:

| scenario | greedy | optimum | gap |
|---|---|---|---|
| dinners, 3 days | 0.9286 | 0.9667 | **0.0381** (4.1% of its score) |

The better week was also **$6.30 cheaper**. Cause: the first slot has nothing planned
around it, so every candidate scored the same zero gain and the tie-break handed the slot
to the cheapest item; that pick shaped the rest of the week and single-slot re-picks could
not undo it. Filed as
[#29](https://github.com/fixmeseb/Weeklies/issues/29), fixed in
[#9](https://github.com/fixmeseb/Weeklies/pull/9).

### Threshold

**0.01** on scenarios that solve to proven optimality, and **0.08** on the worst bound
across all scenarios. The second number is the one CI enforces, because one scenario does
not finish solving (see below) and its gap is an upper bound rather than a measurement.

This eval can fail, and has. The pre-fix planner missed the 0.01 threshold by almost four
times on a three-slot scenario.

## The instrument

[`scripts/eval_optimality.py`](../scripts/eval_optimality.py). For each scenario it runs the
real planner, then solves the same week exactly with CP-SAT over the same candidate sets
and the same objective, and reports the difference.

Why the comparison is fair — same objective, same candidate pools from the planner's own
`_eligible_candidates`, same scorer, and the harness refuses to report a gap if its own
score for the greedy plan disagrees with the planner's — is set out in
[`evals/optimality/README.md`](../evals/optimality/README.md).

It needs OR-Tools, which the application itself does not use:

```bash
pip install ortools
python scripts/eval_optimality.py --days 3 --seconds 90 --max-gap 0.08
```

Wired into CI as the `m0-variety` job in
[`ci.yml`](../.github/workflows/ci.yml), on the same pinned configuration.

## Result

Demo catalog, `--days 3 --seconds 90`, run 2026-11-26:

| scenario | slots | greedy | best | bound | gap | proven |
|---|---|---|---|---|---|---|
| dinners, 3 days | 3 | 0.9667 | 0.9701 | 0.9701 | 0.0035 | yes |
| dinners, 5 days | 5 | 0.9426 | 0.9453 | 0.9453 | 0.0027 | yes |
| dinners, 5d, vegetarian | 5 | 0.9233 | 0.9233 | 0.9233 | 0.0001 | yes |
| dinners, 5d, nut+dairy allergy | 5 | 0.9349 | 0.9389 | 0.9389 | 0.0040 | yes |
| all meals, 3 days | 9 | 0.9179 | 0.9190 | 0.9794 | ≤ 0.0615 | no — time limit |

**Verdict: PASS.** Worst proven gap **0.0040**, against a threshold of 0.01. Worst bound
**0.0615**, against 0.08.

Four of the five scenarios solve to proven optimality and the planner is within half a
percent of the best week available in all four. The baseline shortfall of 0.0381 is gone.

### What this does not show

- **One scenario never proves.** "All meals, 3 days" is nine slots over 31 candidates each;
  CP-SAT hits the 90-second limit with a bound of 0.9794, so its 0.0615 is the most the
  planner *could* be losing, not what it *is* losing. Its real gap is somewhere at or below
  that. Raising the limit would narrow it; we pinned 90 seconds so the number is
  reproducible in CI rather than dependent on how fast the runner is.
- **Synthetic catalog, not real users.** This is the demo seed, not a restaurant anyone
  eats at. Real data would be the bonus the course offers; we do not have it.
- **Variety only.** Cost and nutrition are constraints here, not objectives. Turning
  nutrition targets on drops a week's variety materially, and that trade-off is
  [recorded as future work](milestones.md#-what-could-come-next), not measured by this
  instrument.

### One figure we do not trust

`evals/optimality/README.md` records the nut+dairy scenario as 0.9340 before the fix and
0.9206 after, where 0.9206 is also the proven optimum — a "before" score above a proven
optimum on the same candidate set should not be possible. The run above gives 0.9349 and
0.9389 for that scenario, which is self-consistent. The older row was most likely measured
against a different candidate pool. We have left it in place rather than quietly editing a
published number, and no claim here rests on it.
