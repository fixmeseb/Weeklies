# 🎯 Project 3 Milestones

**Project 3 is the maintenance project**: take another team's Project 2 and make it do new
things without breaking the old things. This page is the before and the after.

- **Upstream:** [rdpatel2/Weeklies](https://github.com/rdpatel2/Weeklies) — Projects 1 and 2.
- **This fork:** [fixmeseb/Weeklies](https://github.com/fixmeseb/Weeklies) — Project 3.
- **Fork point:** `b951f60` (2026-10-21). Everything before it is theirs; everything after
  `064241c` (2026-11-02) is ours.

For the Project 2 team's own milestones, and the roadmap they proposed for whoever
inherited their code, see
[their repository](https://github.com/rdpatel2/Weeklies/blob/main/docs/milestones.md). We
took one item from that roadmap (nutrition) and went our own way on the rest.

---

## 📦 What we inherited

A working Flask meal planner: accounts, restaurants and menus, a weekly calendar, budget
caps, single-meal swaps, an order lifecycle with a progress stepper, reviews, a restaurant
dashboard, a Cypress suite of 15 specs, and an M0 evaluation instrument.

What it could not do, and what shaped our four milestones:

- **Restaurants could not join.** The catalog was a seed script. There was no sign-up, and
  nothing to record opening hours in a form the planner could read.
- **Restaurants could not manage a menu.** Dishes were seed data. No owner-facing editing,
  no API.
- **Plans knew prices, not nutrition.** Budget caps existed; calories and macros did not.
- **Everything lived in one file.** `proj2/Flask_app.py` was 2,793 lines at the fork point
  and still growing.

---

## 🏆 The milestones we delivered

### M1 — Restaurant self-registration, with hours the planner can read

Restaurants sign themselves up and record opening hours as structured JSON rather than
prose, so `is_restaurant_open` can answer for a given weekday and time instead of
rendering a string nobody can parse.

New: `proj2/restaurant_signup.py`, `proj2/hours.py`,
`proj2/templates/restaurant_register.html`. Pull request
[#16](https://github.com/fixmeseb/Weeklies/pull/16).

The hazard this closed is on the record: the column's contract (`format_hours` renders
prose, `is_restaurant_open` refuses it) had already cost a real database two restaurants
that displayed perfectly and could never be planned — see
[#34](https://github.com/fixmeseb/Weeklies/issues/34).

### M2 — Restaurant menu management, over a UI and a JSON API

Owners add, edit and delete their own dishes, with diet and descriptive tags. The JSON
API's field contract is generated from the validator, so the documentation cannot drift
from what the code accepts.

New: `proj2/food/owner_menu.py`, `proj2/menu_items.py`, `proj2/menu_tags_io.py`,
`proj2/templates/restaurant_menu.html`. Pull request
[#13](https://github.com/fixmeseb/Weeklies/pull/13).

### M3 — Daily nutrition targets from USDA FoodData Central

A day can be aimed at calorie, protein, carb, fat and sodium ranges. Per-dish nutrients are
estimated from the USDA FNDDS 2024-10-31 release, public domain. Soft targets rank meals by
how far they leave the day from its ranges; when targets conflict, an exact search decides.

New: `proj2/nutrition.py`, `proj2/fndds_foods.py`, `proj2/demo_nutrition.py`,
`scripts/build_fndds_snapshot.py`, migrations `005` and `006`. Pull request
[#15](https://github.com/fixmeseb/Weeklies/pull/15), integrated by `002241d`.

### M4 — A blueprint split behind an application factory

`proj2/Flask_app.py` went from **2,793 lines to 76**. Routes now live in four blueprints —
`auth`, `account`, `planner`, `food` — built by `create_app()`. `auth`, `account` and
`planner` do not import `food`; what they share lives outside the blueprints.

New: `proj2/__init__.py` (the factory), `proj2/auth/`, `proj2/account/`, `proj2/planner/`,
`proj2/food/`. Pull request [#23](https://github.com/fixmeseb/Weeklies/pull/23).

This is a systems milestone: no user sees it. It is what made M1, M2 and M5 possible
without three teams editing the same file.

### M5 — Insights, themes, and a schema that can move

An Insights tab, the Almanac theme system, and ten numbered migrations (`001`–`010`) with a
startup check that compares `PRAGMA user_version` against the latest migration and names
the command that fixes a mismatch — instead of failing later with `no such table`.

New: `proj2/templates/insights.html`, `proj2/almanac.py`, `proj2/migrations/`,
`proj2/db.py`. Pull requests [#6](https://github.com/fixmeseb/Weeklies/pull/6) and
[#20](https://github.com/fixmeseb/Weeklies/pull/20), plus `590c24a`.

---

## 📐 M0: the evaluation instruments

### The inherited eval still runs

The Project 2 team's time-and-budget instrument
([`docs/m0.md`](m0.md), [`scripts/eval_m0.py`](../scripts/eval_m0.py)) is untouched and runs
in CI on every push, as the `m0-evaluation` job.

Its current verdict is **FAIL**: a median time reduction of **24.7%** against their stated
**30%** target. The budget checks pass — 90% of Weeklies sessions finish within budget
against 70% for the manual baseline, clearing their 20-point lift. Only the time threshold
misses.

We did not move their threshold to make it pass. A failing eval honestly reported is a
spiral review, which is what the instrument is for.

### The new claim for our delta

[`docs/m0-variety.md`](m0-variety.md) states it in full: **how much variety the planner
leaves on the table, measured against a proven optimum**, with
[`scripts/eval_optimality.py`](../scripts/eval_optimality.py) as the instrument and a CI job
that fails when the gap grows.

---

## 🔬 The delta, in numbers

Measured from the fork point `b951f60` to `main`:

- **122 files added, 89 modified, 22 deleted** — +30,236 / −12,315 lines.
- **39 new test files, 735 new test functions.** The course asks for 50, and calls 100
  better.
- **Cypress specs: 15 → 19.**
- **2,311 tests passing at 98% line coverage**, on every push.
- **`proj2/Flask_app.py`: 2,793 lines → 76.**
- Every inherited test still passes.

---

## 🔭 What could come next

Real gaps we found and did not close. Each is recorded where it was found, so a fourth team
does not have to rediscover it.

| Next | Why it matters | Where to start |
|---|---|---|
| **Nutrition targets cost variety** | Turning targets on drops a week's variety score from 0.84 to 0.57. The planner satisfies the ranges by narrowing the menu. | `proj2/nutrition.py` ranking, against `scripts/eval_optimality.py` |
| **Nutrient estimates are rough** | Macros are scaled to each dish's stated calories, so `4p + 4c + 9f` does not reconstruct them. Fine for ranking, wrong for anyone counting. | `nutrition.estimate_macros` |
| **The optimality harness measures an old catalog** | Its numbers were taken on the 76-dish catalog; the seed is now 83 dishes plus restaurant-added ones. | `evals/optimality/` |
| **Two scenarios never prove optimal** | "5 days" and "all meals" hit the solver limit, so their gaps are upper bounds, not measurements. | `scripts/eval_optimality.py` |
| **The planner is single-objective at heart** | Variety is maximised; cost and nutrition are constraints. A real multi-objective search would expose the trade-off instead of hiding it. | `proj2/hill_climbing.py` — six strategies already live there |

---

## 🛠️ Inheriting this codebase

- [Installation & Quickstart](../INSTALL.md)
- [Contributing](../CONTRIBUTING.md)
- [Architecture](../proj2/docs/architecture.md)
- [Code of Conduct](../CODE-OF-CONDUCT.md)
- [Third-party licenses](../THIRD_PARTY_LIBRARIES.md)
