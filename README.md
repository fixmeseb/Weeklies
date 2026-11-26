
# 🍽️ WEEKLIES — Intelligent Meal Planning and Delivery System

[![CI](https://github.com/fixmeseb/Weeklies/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fixmeseb/Weeklies/actions/workflows/ci.yml)
[![Docs](https://github.com/fixmeseb/Weeklies/actions/workflows/docs.yml/badge.svg?branch=main)](https://fixmeseb.github.io/Weeklies/)
[![Tests](https://img.shields.io/badge/tests-2311%20passing-brightgreen.svg)](https://github.com/fixmeseb/Weeklies/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen.svg)](https://github.com/fixmeseb/Weeklies/actions/workflows/ci.yml)
[![Cypress specs](https://img.shields.io/badge/cypress-19%20specs-brightgreen?logo=cypress&logoColor=white)](proj2/cypress/e2e)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)](INSTALL.md)
[![Flask](https://img.shields.io/badge/Flask-2.3.3-lightgrey?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](pyproject.toml)
[![Lint: ruff](https://img.shields.io/badge/lint-ruff-46a2f1?logo=ruff&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Last commit](https://img.shields.io/github/last-commit/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/commits/main)
[![Open issues](https://img.shields.io/github/issues/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/issues)
[![Open pull requests](https://img.shields.io/github/issues-pr/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/pulls)
[![Closed pull requests](https://img.shields.io/github/issues-pr-closed/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/pulls?q=is%3Apr+is%3Aclosed)
[![Contributors](https://img.shields.io/github/contributors/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/graphs/contributors)
[![Commit activity](https://img.shields.io/github/commit-activity/m/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies/pulse)
[![Repo size](https://img.shields.io/github/repo-size/fixmeseb/Weeklies.svg)](https://github.com/fixmeseb/Weeklies)
<!-- DOI badge: add it here once the first release is archived. The previous badge pointed at 10.5281/zenodo.23535676, which is rdpatel2/Weeklies' Project 2 archive and lists none of this team. See CITATION.cff for the steps. -->

> 🎬 **Project 3 videos** — [Teaser](https://drive.google.com/file/d/1XasLGLjjncoXMDLWJ_P6k2x5bvojpNE3/view?usp=drive_link) · [Feature walk-through](https://drive.google.com/file/d/10ITcMl-MdByPu8lPa5-JHT4FHdOK5q2v/view?usp=drive_link) (both need an NC State account)

---

## 🧠 Project Overview

**Weeklies** is a **full-stack Flask web application** developed as part of *CSC 510: Software Engineering (Fall 2026, NC State University)*.  
It models a modern food-delivery system where users can register, browse restaurants and menus, tag preferences, and schedule future meal orders via an integrated calendar.  
The project demonstrates **modular backend design**, **frontend interaction**, **variety-driven meal planning**, and **continuous documentation & testing pipelines**.

---

## ⚙️ Tech Stack

| Layer | Technologies | Key Focus |
|-------|---------------|-----------|
| **Frontend** | HTML, CSS, JavaScript (templated views) | Dynamic forms, order interaction, user calendar |
| **Backend** | Python 3.11+, Flask 2.x | RESTful routes, modular blueprints, DB logic |
| **Database** | SQLite | Lightweight persistence for menus, users, orders |
| **Automation** | GitHub Actions, pdoc, pytest, ruff, black | CI/CD, linting, testing, documentation |
| **Meal Planner** | pandas, tag-based variety score | Rule-checked, budget-aware plans chosen for variety |
| **PDF Service** | ReportLab | Automated PDF receipt generation |
| **E2E Testing** | Cypress 16 | Browser-based end-to-end UI testing |

---

## 🧩 Core Features

- 👤 **User registration & authentication**
- 🍱 **Menu and restaurant search** with allergen + cuisine tagging
- 🧭 **User preference tagging** and filtering
- 📅 **Calendar-based scheduling** (order-on-selected-date logic)
- 🧾 **Dynamic PDF receipt generation**
- 🎲 **Variety-scored meal plans**: meals are tagged (cuisine, protein, carb base, cooking method, ...) and the planner picks the most varied plan that passes every rule; the calendar shows each week's variety score
- 🔄 **End-to-end order workflow** from cart → checkout → payment → fulfillment
- ⭐ **Restaurant reviews & ratings** with user-generated feedback
- 📊 **Restaurant analytics dashboard** for orders, customer behavior, and performance insights
- 🥗 **Dynamic meal generation** based on user preferences, allergens, and dietary constraints
- 🧪 **Automated test suite** with `pytest` (unit, integration, e2e) and Cypress (UI e2e)
- 🧰 **CI/CD workflows** for tests, linting, and documentation deployment
- 🏪 **Restaurant sign-up** — a restaurant lists itself at `/restaurant/register` and lands on its own empty menu to add the first dish, instead of being added by hand to a seed script. Opening hours are collected a day at a time and stored in the per-day format the planner reads, because free-text hours render fine on every page and are silently never open to the planner
- 🍜 **Restaurant menu management** — restaurant owners list, edit and withdraw their own dishes from a Menu tab, or over a JSON API whose field contract (`GET /api/restaurant/menu/schema`) is generated from the validator that checks submissions, so the two cannot drift. Tags are checked against their vocabularies, a dish is refused if it contradicts itself (vegan with a beef protein), and a dish a saved plan still names can be taken off the menu but not deleted
- 🔁 **Single-meal swaps** — replace one date/meal slot from the calendar; the server checks stock, restaurant hours, and the account's allergies, and leaves the rest of the plan untouched (`POST /menu/swap`, `GET /menu/swap/options`)

---

## 🎯 Milestones & Project 3 Roadmap

Weeklies delivers **5 completed milestones** for Project 2 and an architectural roadmap for Project 3:
- **[M0: Risk-Killer Eval](./docs/m0.md)** — Runnable hypothesis evaluation instrument with synthetic simulation and CI reporting.
- **[M1: Dynamic Single-Meal Swaps](./docs/milestones.md#milestone-1-m1-dynamic-single-meal-swaps-uc29)** — Calendar slot replacement with allergen and operating-hours checks.
- **[M2: Budget-Aware Plan Generation](./docs/milestones.md#milestone-2-m2-budget-constrained-meal-plan-generation)** — Exact-cents budget caps, candidate ranking, and weekly totals.
- **[M3: Order Progress Stepper](./docs/milestones.md#milestone-3-m3-order-lifecycle--visual-progress-stepper-uc13)** — 5-stage visual lifecycle tracker on `/profile`.
- **[M4: Cypress E2E UI Test Harness](./docs/milestones.md#milestone-4-m4-comprehensive-cypress-e2e-ui-test-harness)** — Automated browser E2E test suite running 19 specs in CI.
- ➡️ **[See Full Milestones & Project 3 Roadmap →](./docs/milestones.md)**

---

## 🧱 Architecture

```
Weeklies/
│
├── 📁 proj2/                          # Main Flask Application
│   ├── 🐍 Flask_app.py                # Entry point: builds the app
│   ├── 🏭 __init__.py                 # create_app(): settings, error pages, blueprints
│   ├── 📁 auth/                       # Login, logout and registration
│   ├── 📁 account/                    # Profile, diet settings, password
│   ├── 📁 planner/                    # Calendar and insights pages
│   ├── 📁 food/                       # Restaurants, orders, plan changes, owner pages, /db
│   ├── 🥗 menu_generation.py          # Meal planner (rules + variety)
│   ├── 🎲 variety.py                  # Variety score between meals and plans
│   ├── 🧮 nutrition.py                # Daily calorie/protein/carb/fat/sodium targets
│   ├── 📊 fndds_foods.py              # USDA FoodData Central snapshot (generated)
│   ├── 🏪 restaurant_signup.py        # Restaurant self-registration rules
│   ├── 🕒 hours.py                    # Opening hours: render and parse
│   ├── 📄 pdf_receipt.py              # PDF generation service
│   ├── 💾 sqlQueries.py               # Database helper functions
│   │
│   ├── 📁 templates/                  # HTML Templates
│   │   ├── index.html                 # Home / calendar view, Today's Menu, plan form
│   │   ├── insights.html              # Weekly item totals and plan variety
│   │   ├── login.html                 # User login
│   │   ├── register.html              # User registration
│   │   ├── profile.html               # Account as chapters: particulars, diet, wallet, password
│   │   ├── orders.html                # My Orders: order history and tracking
│   │   ├── restaurants.html           # Restaurant browsing, cart and checkout
│   │   ├── review.html                # Write, then view, an order's review
│   │   ├── restaurant_orders.html     # Restaurant owner home: order management
│   │   ├── restaurant_analytics.html  # Analytics dashboard
│   │   ├── _owner_header.html         # Owner banner with Orders/Analytics/Reviews tabs
│   │   ├── _diet_editor.html          # Allergy and preference picker (register, profile)
│   │   └── ...                        # Reviews, login, etc.
│   │
│   ├── 📁 static/                     # Frontend Assets
│   │   ├── style.css
│   │   └── script.js
│   │
│   ├── 📁 tests/                      # Python Test Suite
│   │   ├── e2e/                       # End-to-end tests
│   │   ├── integration/               # Integration tests
│   │   ├── unit/                      # Unit tests
│   │   └── smoke/                     # Smoke tests
│   │
│   ├── 📁 cypress/                    # Cypress E2E UI Tests
│   │   ├── e2e/                       # Test specs by feature area
│   │   ├── fixtures/                  # Test data (JSON)
│   │   └── support/                   # Custom commands & setup
│   │
│   └── 📋 requirements.txt           # Python dependencies
│
├── 🔄 .github/workflows/
│   ├── ci.yml                         # Automated testing & linting
│   └── docs.yml                       # Documentation build & deploy
│
├── 📁 scripts/                        # Utility Scripts
│   ├── build_docs.py
│   ├── cypress_seed.py                # Database seeder for Cypress tests
│   └── ...
│
├── 🎯 Configuration Files
│   ├── pytest.ini                     # Test configuration
│   ├── pyproject.toml                 # Black / Ruff config
│   ├── pdoc.toml                      # Documentation config
│   ├── cypress.config.js              # Cypress E2E config
│   └── .coderabbit.yaml               # CodeRabbit PR review bot config
│
└── 📖 Documentation
    ├── README.md                      # This file
    ├── INSTALL.md                      # Setup guide
    ├── CONTRIBUTING.md                # Contribution guidelines
    ├── CODE-OF-CONDUCT.md             # Community standards
    ├── THIRD_PARTY_LIBRARIES.md       # Dependency licenses
    ├── AI_DISCLOSURE.md               # AI use & verification disclosure
    ├── RUBRIC.md                      # Self-assessed repository rubric
    ├── CITATION.cff                   # How to cite this software
    ├── .zenodo.json                   # Archive metadata for the Zenodo DOI
    └── LICENSE.md                     # MIT License
```

---

## 🧪 Continuous Integration

Every push to any branch, and every pull request into `main` or `dev-branch`, runs
[`ci.yml`](./.github/workflows/ci.yml):

1. **Static analysis** — `black` and `ruff` over the Python files the branch changed
   (scoped rather than whole-tree, so new code is gated without a repo-wide reformat)
2. **M0 evaluation** — the hypothesis instrument is verified and the synthetic sample
   reproduced, with the verdict written to the run summary
3. **Unit, integration and e2e tests** — `pytest` with `coverage`, uploaded to Codecov
4. **Cypress** — 19 browser specs against a live Flask server on a seeded database

[`docs.yml`](./.github/workflows/docs.yml) runs when a push or a pull request into `main`
touches `proj2/`, `scripts/`, `pdoc.toml` or the workflow itself. It builds the pdoc site and
attaches it as an artifact on pull requests, and publishes it to the `gh-pages` branch when
`main` moves.

You can view live status from the badges above.

---

## 📚 Documentation

Auto-generated API documentation is available through **pdoc** and deployed automatically.  
You can view it online (via GitHub Pages) or build it locally:

🔗 **Live Docs:** [Weeklies Documentation](https://fixmeseb.github.io/Weeklies/)  
🧰 **Local Build:** See [INSTALL.md](./INSTALL.md#documentation)

---

## 🚀 Installation & Usage

Setup, environment creation, and execution instructions have been moved to a dedicated guide:  
➡️ **[See Installation Guide →](./INSTALL.md)**

---

### Planner experiments

From the repository root on macOS, run the meeting demo with the project virtual environment.

```sh
.venv/bin/python scripts/demo_planner.py
```

The demo first compares cost and variety for three dinners, then compares search methods on a
full week of vegetarian meals with a peanut allergy, a $245 weekly cap, and all six objectives.
It prints the active settings and normalized weights before each comparison. The final example
saves each slider through **Profile → II. Diet**, compares the same five dinners under a $60 cap,
and shows the planner rejecting an infeasible $1 cap.

The printed URL opens the demo account with the combined settings already saved. Generate the
suggested dinners from the calendar to see the applied priorities and results. Press Ctrl+C
to stop, or pass `--console-only` to run the examples without starting the server.
For an existing development database, run `flask migrate` to add the saved weekly cap.

To configure a comparison directly, run it from the activated project environment.

```sh
python scripts/compare_planners.py --trace --tradeoffs
python scripts/compare_planners.py --days 7 --meals 1 2 3 --cap 245 --starts 8 --seed 7
python scripts/compare_planners.py --days 7 --meals 1 2 3 --catalog-copies 2 \
  --diets vegetarian --allergens Peanuts --food-matches Italian --cap 245 \
  --weight variety=60 --weight cost=25 --weight preference=35
```

Each search method gets the same seeded starting plans and evaluation budget. The first
start is greedy. Additional starts build randomized feasible plans across all slots. The table
compares the greedy score, best start, and best score reached, alongside the number of scored
plans and accepted uphill, flat, and downhill moves. Alongside the hill-climbing variants
and simulated annealing, the demo compares tabu search (blocks recent reversals), late
acceptance hill climbing (uses recent scores to accept proposals), and iterated local
search (perturbs plans between climbs). Extra catalog copies repeat the same dishes under
new restaurant entries, so those runs measure search effort with larger pools.
Use the [CP-SAT harness](evals/optimality/README.md) to check small variety-only cases
against the solver's integer-scaled objective.

---

## 📹 Project Demonstration Videos

These are the **Project 3** videos. The walk-through is the one linked from the project poster.

- ⚡ **Teaser**: a short tour of the application.  
  ➡️ **[Watch the teaser](https://drive.google.com/file/d/1XasLGLjjncoXMDLWJ_P6k2x5bvojpNE3/view?usp=drive_link)**
- 🔍 **Feature walk-through**: a longer demonstration of the Project 3 work.  
  ➡️ **[Watch the walk-through](https://drive.google.com/file/d/10ITcMl-MdByPu8lPa5-JHT4FHdOK5q2v/view?usp=drive_link)**

Both are hosted on Google Drive and open for anyone signed in with an NC State account; a
personal Google account is refused.

The Project 1 and Project 2 videos are not listed here. They belong to the
[upstream repository](https://github.com/rdpatel2/Weeklies) and were still linked from this
README, which read as though they showed this team's work.

---

## 👥 Team & Contributors

### Project 3 — Fall 2026 (Current Team)

| Member | GitHub Handle | Key Contributions |
|---------|----------------|-------------------|
| **Sebastian Polge** | [@fixmeseb](https://github.com/fixmeseb) | Blueprint split behind `create_app()`, ordering rules and delivery details, Insights tab, Almanac theme system, schema versioning |
| **Karthik Panicker** | [@KarthikPanicker2000](https://github.com/KarthikPanicker2000) | Restaurant sign-up and menu management (UI + JSON API), variety-score correction, planner restarts and optimality evals, Cypress specs |
| **Carlos** | [@ccast44](https://github.com/ccast44) | Daily calorie/protein/carb/fat/sodium targets from USDA FoodData Central, allergen label rules, wallet and dish-refusal fixes |
| **Cameron** | [@Tacho2](https://github.com/Tacho2) | Local-search strategy comparison in the planner demo, diet settings unified with plan optimization |

### Project 2 — Fall 2026 (Upstream Team)

| Member | GitHub Handle | Key Contributions |
|---------|----------------|-------------------|
| **Rohan Patel** | [@rrpatel7](https://github.com/rrpatel7) | — |
| **Srikar Desemsetti** | [@spdesems](https://github.com/spdesems) | — |
| **Alex Tanton** | [@actanton](https://github.com/actanton) | — |
| **Kushal Upreti** | [@kupreti](https://github.com/kupreti) | — |

### Project 1 — Fall 2025 (Original Team)

| Member | GitHub Handle | Key Contributions |
|---------|----------------|-------------------|
| **Taylor J. Brown** | [@TaylorBrown96](https://github.com/TaylorBrown96) | User authentication, preference management, PDF receipts, calendar integration |
| **Kunal Jindal** | [@devkunal2002](https://github.com/devkunal2002) | Documentation pipeline, CI/CD workflows, repository structure |
| **Ashritha Bugada** | — | Restaurant search, menu browsing, ordering flow |
| **Daniel Dong** | — | Calendar scheduling, LLM integration |
| **Jawad Saeed** | [@Jawamegamind](https://github.com/Jawamegamind) | Reviews & ratings, restaurant dashboard, order management |
| **Omkar Joshi** | [@OJ98](https://github.com/OJ98) | Analytics dashboard, GPU acceleration, CI optimization |
| **Mason Cormany** | [@kaotickoopa](https://github.com/kaotickoopa) | AI menu generation, model selection, prompt engineering |

---

## 🗂️ Data Sources & Citations

The nutrition figures behind the planner's calorie, protein, carb, fat and sodium targets are
not invented. Every demo dish is matched to one or more USDA foods and scaled to its listed
calories; the foods used are snapshotted into `proj2/fndds_foods.py` by
`scripts/build_fndds_snapshot.py`, so seeding and the tests need neither the network nor an
API key.

1. U.S. Department of Agriculture, Agricultural Research Service, Beltsville Human Nutrition
   Research Center. *FoodData Central.* [Internet]. [cited 2026-11-24]. Available from
   <https://fdc.nal.usda.gov/>.

[USDA FoodData Central](https://fdc.nal.usda.gov/) produces thorough resources for navigating
and understanding nutritional info to support dietary choices and nutritional analysis. The
snapshot in this repository comes from the Survey (FNDDS) 2024-10-31 release, which is in the
public domain (CC0 1.0). Dependency licences and the full third-party inventory are listed in
[THIRD_PARTY_LIBRARIES.md](./THIRD_PARTY_LIBRARIES.md).

---

## 🤝 Contributing
We welcome contributions from everyone.  
Please review our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE-OF-CONDUCT.md) before submitting pull requests.

💬 **Talk to us:** the team coordinates day to day on Discord — [join the Weeklies server](https://discord.gg/raSqAj6R8).
Design arguments, review questions and "is this a bug?" all start there. Anything that ends in
a code change should also get a GitHub issue, so the reasoning is on the record next to the
commit that acts on it.

---

## 📜 License
Distributed under the MIT License.  
See [LICENSE.md](./LICENSE.md) for more information.

---

> "Build software that's clean, testable, and transparent — not just functional."
