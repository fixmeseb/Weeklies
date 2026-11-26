# M0 (Project 3): can the planner stay fast as the catalog grows?

The Project 2 team's M0 asks whether Weeklies saves people time and keeps them in budget.
That instrument is untouched, still in CI, and [still reports its number](m0.md) — currently
FAIL, at a 24.7% median time reduction against their 30% target.

This is the M0 claim for **our** delta. It is the claim stated on the Project 3 poster.

## The hypothesis

Project 3 made the planner search harder. The variety fix in
[#9](https://github.com/fixmeseb/Weeklies/pull/9) replaced a single greedy pass with
*fill, improve until nothing changes, and restart from a spread of openings*. That closed a
real quality gap — but it multiplies the work per request, and restaurants can now sign
themselves up and add dishes, so the catalog grows without us controlling it.

The risk is simple: **the planner that produces better weeks becomes one nobody waits
for.** A meal planner that takes half a minute is not a product.

> **Claim.** On a 1,743-item catalog, Weeklies plans a full week — 21 meals — in **under
> 5 seconds**, and the restart search **matches or beats** the variety of the
> single-restart planner it replaced.

### Metric

Two numbers from one run:

- **Wall-clock seconds** for `MenuGenerator.update_menu` to fill 21 slots (3 meals × 7
  days), measured with `time.perf_counter()` around the call the web request makes.
- **`variety.plan_variety`**, the same 0–1 score the product reports, at 12 restarts
  against the same plan at 1 restart.

### Baseline

The single-restart planner — what the code did before the restart search landed. On the
same 1,743-item catalog: **0.69 s, variety 0.9050**.

The honest comparison is not "is it fast" but "what did the extra quality cost". PR #8
reported 11.14 s for a one-week plan on a 1,596-item catalog before its caching work and
1.53 s after; the restart search multiplies that, which is exactly why this needs
measuring rather than assuming.

### Threshold

**5 seconds**, and **no variety below the single-restart baseline**.

## The instrument

[`scripts/bench_planner.py`](../scripts/bench_planner.py). It seeds the demo catalog,
repeats every restaurant and its menu to reach the target size, then times a full week at
each restart count and records the variety score.

```bash
python scripts/bench_planner.py --copies 20 --restarts 12 1 \
    --max-seconds 5 --no-variety-loss
```

`--max-seconds` and `--no-variety-loss` make it exit non-zero when the claim breaks. Run in
CI as the `m0-project3` job.

## Result

Run 2026-11-26, `--copies 20` (83 seeded dishes × 21 restaurant copies = 1,743 items):

| catalog | 12 restarts | 1 restart (baseline) |
|---|---|---|
| 1,743 items | **2.37 s** / variety **0.9061** | 0.69 s / variety 0.9050 |

**Verdict: PASS.** Well inside the 5-second target, and the restart search scores above
the baseline rather than below it.

The poster reports 4.23 s and a 1.14 s baseline for the same configuration. Both are the
same instrument on the same catalog; the difference is the machine. The claim is about the
5-second threshold, which holds in both.

### Why the variety half is the weaker half

Be clear about this: restarts try the planner's own default opening **first**, so a
restart can only match or beat what the planner would have produced anyway. The variety
check is a guard against that property breaking, not a discovery.

**The speed half is the live risk**, and it is the one that can fail. Verified: re-run with
`--max-seconds 0.5` and the job exits 1 with `FAIL: slowest plan 2.34 s exceeds the 0.50 s
target`.

### Supporting evidence: the restarts are worth paying for

Speed only matters if the extra work buys something. It does, and that is measured
separately by [`scripts/eval_optimality.py`](../scripts/eval_optimality.py), which solves
the same week exactly with CP-SAT over the planner's own candidate sets and reports how
much variety the planner leaves on the table.

Before the restart fix, the planner sat **0.0381 below the proven optimum** on a three-day
scenario — 4.1% of its score, and the better week was **$6.30 cheaper**
([#29](https://github.com/fixmeseb/Weeklies/issues/29)). After it, on a run at
`--days 3 --seconds 90`:

| scenario | greedy | optimum | gap | proven |
|---|---|---|---|---|
| dinners, 3 days | 0.9667 | 0.9701 | 0.0035 | yes |
| dinners, 5 days | 0.9426 | 0.9453 | 0.0027 | yes |
| dinners, 5d, vegetarian | 0.9233 | 0.9233 | 0.0001 | yes |
| dinners, 5d, nut+dairy allergy | 0.9349 | 0.9389 | 0.0040 | yes |
| all meals, 3 days | 0.9179 | ≤ 0.9794 | ≤ 0.0615 | no — time limit |

Worst proven gap **0.0040**, down from 0.0381. This runs in CI as the
`planner-optimality` job with a `--max-gap` guard, and
[`evals/optimality/README.md`](../evals/optimality/README.md) sets out why the comparison
is fair.

Which scenarios prove optimal depends on machine speed — CI's runner proves three of five
where this machine proves four — which is why that job's gate is on the worst *bound*
rather than on proven gaps.

### What this does not show

- **A synthetic catalog.** 1,743 items is the demo seed repeated across more restaurants.
  Repeats make a catalog *easier* to plan well, not harder, so this measures work per
  request rather than plan quality at scale.
- **No real users.** Real evidence is the bonus the course offers; we do not have it.
- **One machine, one run per cell.** No percentiles, despite the target being written as
  p95. A slower machine would report larger times; the threshold has roughly a factor of
  two of headroom at this catalog size.
- **One scenario never proves optimal** in the supporting harness, so its gap is an upper
  bound rather than a measurement.

### One figure we do not trust

`evals/optimality/README.md` records the nut+dairy scenario as 0.9340 before the fix and
0.9206 after, where 0.9206 is also the proven optimum — a "before" score above a proven
optimum on the same candidate set should not be possible. The run above gives 0.9349 and
0.9389, which is self-consistent. We have left the published number in place rather than
quietly editing it, and no claim here rests on it.
