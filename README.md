
# 🍽️ WEEKLIES — Intelligent Meal Planning and Delivery System

[![CI](https://github.com/rdpatel2/Weeklies/actions/workflows/ci.yml/badge.svg)](https://github.com/rdpatel2/Weeklies/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-466%20passing-brightgreen.svg)](https://github.com/rdpatel2/Weeklies/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)](https://github.com/rdpatel2/Weeklies/actions/workflows/ci.yml)
[![Docs](https://github.com/rdpatel2/Weeklies/actions/workflows/docs.yml/badge.svg)](https://rdpatel2.github.io/Weeklies/)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)](INSTALL.md)
[![Flask](https://img.shields.io/badge/Flask-2.x-lightgrey?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Cypress](https://img.shields.io/badge/cypress-tested-brightgreen?logo=cypress&logoColor=white)](https://www.cypress.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](pyproject.toml)
[![Lint: ruff](https://img.shields.io/badge/lint-ruff-46a2f1?logo=ruff&logoColor=white)](pyproject.toml)
[![Syntax: ruff](https://img.shields.io/badge/syntax-ruff-46a2f1?logo=ruff&logoColor=white)](pyproject.toml)
[![GitHub last commit](https://img.shields.io/github/last-commit/rdpatel2/Weeklies.svg)](https://github.com/rdpatel2/Weeklies/commits)
[![GitHub issues](https://img.shields.io/github/issues/rdpatel2/Weeklies.svg)](https://github.com/rdpatel2/Weeklies/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/rdpatel2/Weeklies.svg)](https://github.com/rdpatel2/Weeklies/pulls)
[![Contributors](https://img.shields.io/github/contributors/rdpatel2/Weeklies.svg)](https://github.com/rdpatel2/Weeklies/graphs/contributors)
[![DOI](https://zenodo.org/badge/1351756287.svg)](https://doi.org/10.5281/zenodo.23535676)

> 🎬 **Teaser Video (30s)**: [Quick Feature Teaser Video](https://youtu.be/mHaZZrCgCAQ) · **Full Demo (3m)**: [Feature Walk-Through Video](https://youtu.be/7xUXqdqDwcs)

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
- 🔁 **Single-meal swaps** — replace one date/meal slot from the calendar; the server checks stock, restaurant hours, and the account's allergies, and leaves the rest of the plan untouched (`POST /menu/swap`, `GET /menu/swap/options`)

---

## 🎯 Milestones & Project 3 Roadmap

Weeklies delivers **5 completed milestones** for Project 2 and an architectural roadmap for Project 3:
- **[M0: Risk-Killer Eval](./docs/m0.md)** — Runnable hypothesis evaluation instrument with synthetic simulation and CI reporting.
- **[M1: Dynamic Single-Meal Swaps](./docs/milestones.md#milestone-1-m1-dynamic-single-meal-swaps-uc29)** — Calendar slot replacement with allergen and operating-hours checks.
- **[M2: Budget-Aware Plan Generation](./docs/milestones.md#milestone-2-m2-budget-constrained-meal-plan-generation)** — Exact-cents budget caps, candidate ranking, and weekly totals.
- **[M3: Order Progress Stepper](./docs/milestones.md#milestone-3-m3-order-lifecycle--visual-progress-stepper-uc13)** — 5-stage visual lifecycle tracker on `/profile`.
- **[M4: Cypress E2E UI Test Harness](./docs/milestones.md#milestone-4-m4-comprehensive-cypress-e2e-ui-test-harness)** — Automated browser E2E test suite running 17 specs in CI.
- ➡️ **[See Full Milestones & Project 3 Roadmap →](./docs/milestones.md)**

---

## 🧱 Architecture

```
Weeklies/
│
├── 📁 proj2/                          # Main Flask Application
│   ├── 🐍 Flask_app.py                # Core Flask app with all routes
│   ├── 🥗 menu_generation.py          # Meal planner (rules + variety)
│   ├── 🎲 variety.py                  # Variety score between meals and plans
│   ├── 📄 pdf_receipt.py              # PDF generation service
│   ├── 💾 sqlQueries.py               # Database helper functions
│   │
│   ├── 📁 templates/                  # HTML Templates
│   │   ├── index.html                 # Home / calendar view
│   │   ├── login.html                 # User login
│   │   ├── register.html              # User registration
│   │   ├── profile.html               # User profile
│   │   ├── orders.html                # Order history
│   │   ├── restaurants.html           # Restaurant browsing
│   │   ├── restaurant_dashboard.html  # Restaurant owner dashboard
│   │   ├── restaurant_analytics.html  # Analytics dashboard
│   │   └── ...                        # Reviews, order management, etc.
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
    └── LICENSE.md                     # MIT License
```

---

## 🧪 Continuous Integration

Every push or pull request to the `main` branch triggers:
1. **CI tests** via `pytest` and `coverage`  
2. **Cypress E2E tests** against a live Flask server
3. **Documentation build & deployment** to GitHub Pages (`gh-pages` branch)  
4. **Static analysis** via `ruff` and `black` 

You can view live status from the badges above.

---

## 📚 Documentation

Auto-generated API documentation is available through **pdoc** and deployed automatically.  
You can view it online (via GitHub Pages) or build it locally:

🔗 **Live Docs:** [Weeklies Documentation](https://rdpatel2.github.io/Weeklies/)  
🧰 **Local Build:** See [INSTALL.md](./INSTALL.md#documentation)

---

## 🚀 Installation & Usage

Setup, environment creation, and execution instructions have been moved to a dedicated guide:  
➡️ **[See Installation Guide →](./INSTALL.md)**

---

## 📹 Project Demonstration Videos

- ⚡ **Teaser Video (30s)**: High-level visual tour of intelligent meal planning, allergen filters, and calendar interactions.  
  ➡️ **[Watch Teaser Video](https://youtu.be/mHaZZrCgCAQ)**
- 🔍 **Feature Walk-Through Video (3m)**: Detailed demonstration covering single-meal swaps (UC29), budget caps, order lifecycle tracking (UC13), and Cypress E2E test execution.  
  ➡️ **[Watch Feature Walk-Through](https://youtu.be/7xUXqdqDwcs)**

---

## 👥 Team & Contributors

### Project 2 — Fall 2026 (Current Team)

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

## 🤝 Contributing
We welcome contributions from everyone.  
Please review our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE-OF-CONDUCT.md) before submitting pull requests.

---

## 📜 License
Distributed under the MIT License.  
See [LICENSE.md](./LICENSE.md) for more information.

---

> "Build software that's clean, testable, and transparent — not just functional."
