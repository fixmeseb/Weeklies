# 📋 Project 3 Self-Assessed Repo Rubric

This document contains the self-assessed repository rubric for **Weeklies** (CSC 510, Fall 2026),
evaluated against the project requirements.

**Scoring Scale**: `0` = None, `1` = A little, `2` = Somewhat, `3` = A lot.

Every score is backed by a clickable link into **this** repository, `fixmeseb/Weeklies`.
Counts were measured on `main` at commit [`3c67fe0`](https://github.com/fixmeseb/Weeklies/commit/3c67fe0)
on 2026-11-25, and cover the Project 3 window — 2026-11-02 onward, when this fork's team began
work — except where a figure is explicitly for the whole repository history.

> **This is a working self-assessment, not a finished scorecard.** Several items below score
> low because the evidence does not exist yet, not because the work is weak. The
> [Gaps to close](#-gaps-to-close-before-submission) section at the end lists exactly what each
> one needs. Please do not raise a score here until the evidence it links to is real.

---

### 👥 Teamwork, Visible in GitHub

| Item | Evidence Link | Score (0–3) | Justification |
|---|---|:---:|---|
| **Many commits**: hundreds by the end is normal for teams that commit small | [Commits on `main`](https://github.com/fixmeseb/Weeklies/commits/main) | **3** | **472 commits** on `main` in total, **95 of them from this team** since 2026-11-02 — an average of 4 a day, in small, single-purpose steps. |
| **Commits come from different people** | [Contributors](https://github.com/fixmeseb/Weeklies/graphs/contributors) | **3** | All **4 team members** have commits in the Project 3 window: [@fixmeseb](https://github.com/fixmeseb) (33), [@KarthikPanicker2000](https://github.com/KarthikPanicker2000) (33), [@ccast44](https://github.com/ccast44) (24), [@Tacho2](https://github.com/Tacho2) (5). |
| **Workload is spread over the whole team** | [Contributors](https://github.com/fixmeseb/Weeklies/graphs/contributors) | **2** | Three members are within a third of each other (33 / 33 / 24 commits). The fourth is at 5, about 5% of the window, so the spread is real but not even. |
| **Team members work across many parts of the code, not one silo each** | [Merged pull requests](https://github.com/fixmeseb/Weeklies/pulls?q=is%3Apr+is%3Amerged) | **3** | No member owns one directory. All four have commits touching `proj2/tests/`, `proj2/templates/` and `scripts/`; `menu_generation.py` has been edited by all four, and `Flask_app.py` by three. |
| **Short release cycles**: frequent small commits, merged promptly | [Merged pull requests](https://github.com/fixmeseb/Weeklies/pulls?q=is%3Apr+is%3Amerged) | **3** | **24 pull requests merged in 23 days** — roughly one a day. 23 of the 28 changesets that landed on `main` arrived through a pull request; the other 5 were pushed straight to `main`. |
| **Whole team uses the same tools**: config files in repo, updated by many different people | [`pyproject.toml`](./pyproject.toml), [`pytest.ini`](./pytest.ini), [`cypress.config.js`](./proj2/cypress.config.js), [`.coderabbit.yaml`](./.coderabbit.yaml), [`ci.yml`](./.github/workflows/ci.yml) | **3** | Black, Ruff, pytest and Cypress are configured once in the repository and enforced for everyone by the CI lint gate, so the settings cannot drift between machines. |
| **Whole team can run the system**: anyone can share screen and demo on machine | [`INSTALL.md`](./INSTALL.md) | **3** | Separate Windows (PowerShell) and macOS/Linux (Bash) paths, both ending in a working `flask run`. macOS-specific breakage was found and fixed on its own branch rather than worked around locally. |

**Teamwork: 20 / 21**

---

### 💬 Issues and Discussion

| Item | Evidence Link | Score (0–3) | Justification |
|---|---|:---:|---|
| **Issue reports: there are many** | [Issues](https://github.com/fixmeseb/Weeklies/issues?q=is%3Aissue) | **0** | **This repository has no issues — zero, open or closed.** Defects have been found and fixed, but each went straight to a branch and a pull request, so none of that work is visible as an issue. |
| **Issues are being closed** | [Closed issues](https://github.com/fixmeseb/Weeklies/issues?q=is%3Aissue+is%3Aclosed) | **0** | Nothing to close. |
| **Issues are discussed before they are closed** | [Issues](https://github.com/fixmeseb/Weeklies/issues?q=is%3Aissue) | **0** | No issue threads exist. Of 25 pull requests, **1 carries any comment and 0 have a review**, so the discussion is not recorded on pull requests either. |
| **A large share of issues relate to handling failing cases** | [Merged pull requests](https://github.com/fixmeseb/Weeklies/pulls?q=is%3Apr+is%3Amerged) | **0** | The underlying work exists and is substantial — the variety score treating absent tags as evidence of difference, restaurant hours stored in a format the planner silently cannot read, refunds lost on wallet changes, a Cypress spec that depended on the time of day — but it is recorded only in commit messages, not in issues. |
| **Chat channel / discussion forum exists and is active** | [Team Discord](https://discord.gg/raSqAj6R8), [`README.md`](./README.md#-contributing), [`CONTRIBUTING.md`](./CONTRIBUTING.md#questions-and-support) | **3** | The team's Discord server is where design arguments, review questions and day-to-day coordination happen throughout Project 3. The invite is now linked from the README and from CONTRIBUTING's support section, so it is reachable from the repository rather than only from the poster. GitHub Discussions is not enabled, so a grader cannot read the history without joining — worth turning on for an on-platform record. |

**Issues & Discussion: 3 / 15** — see [Gaps to close](#-gaps-to-close-before-submission). This is the
single largest recoverable loss on the rubric.

---

### 🧪 Tests

| Item | Evidence Link | Score (0–3) | Justification |
|---|---|:---:|---|
| **Tests exist: 50 is good, 100 is better; expected and failure cases** | [`proj2/tests/`](./proj2/tests/), [`proj2/sef26tests/`](./proj2/sef26tests/), [`scripts/tests/`](./scripts/tests/), [`proj2/cypress/e2e/`](./proj2/cypress/e2e/) | **3** | **1,282 test functions across 111 files**, expanding to **2,311 test cases** through parametrization, plus **88 Cypress assertions across 19 browser specs**. Failure cases are first-class: refused dishes, unreachable nutrition targets, closing times before opening times, duplicate restaurant emails, and plans that cannot satisfy a budget. |
| **Tests are a serious share of the code base** | [`proj2/tests/`](./proj2/tests/), [`proj2/cypress/`](./proj2/cypress/) | **3** | **19,138 lines of test code against 14,095 lines of application code — 58% of the Python and JavaScript in the repository is tests.** |
| **Tests run automatically on every commit (CI)** | [`ci.yml`](./.github/workflows/ci.yml), [Actions](https://github.com/fixmeseb/Weeklies/actions/workflows/ci.yml) | **3** | CI runs on a push to **any** branch and on pull requests into `main` or `dev-branch`: a scoped Black/Ruff gate, the M0 evaluation instrument, the full pytest suite with coverage, and Cypress against a live Flask server on a seeded database. |
| **Coverage is measured; the badge shows the number** | [`ci.yml`](./.github/workflows/ci.yml), [`README.md`](./README.md) | **3** | `pytest-cov` reports **98% line coverage** (13,930 statements, 220 missed) and the figure is on the README badge. The Codecov upload step runs with `fail_ci_if_error: false`, so treat the badge — not Codecov — as the source of truth. |

**Tests: 12 / 12**

---

### 📖 Documentation

| Item | Evidence Link | Score (0–3) | Justification |
|---|---|:---:|---|
| **Docs are generated, and the format is not ugly** | [`docs.yml`](./.github/workflows/docs.yml), [`proj2/pdoc_templates/`](./proj2/pdoc_templates/) | **2** | `pdoc` builds a custom-templated API site on every qualifying change and publishes it to the `gh-pages` branch, which is up to date. **GitHub Pages is not enabled for this repository, so the published site 404s** and the generated docs cannot actually be read in a browser. |
| **Docs, the WHAT: point descriptions of each class/function** | [`proj2/nutrition.py`](./proj2/nutrition.py), [`proj2/variety.py`](./proj2/variety.py), [`proj2/restaurant_signup.py`](./proj2/restaurant_signup.py), [`proj2/hours.py`](./proj2/hours.py) | **3** | Modules, routes and helpers carry PEP 257 docstrings. The planner modules go further and document *why* a rule exists — `variety.py` explains why absent tags are shrunk toward neutral, `nutrition.py` why targets are soft by default. |
| **Docs, the HOW: mini-tutorials with worked examples** | [`use-cases.md`](./use-cases.md), [`INSTALL.md`](./INSTALL.md), [`README.md`](./README.md#planner-experiments) | **3** | **31 worked use cases (UC01–UC31)**, a cross-platform install guide, and a runnable planner-experiments section with copy-pasteable `compare_planners.py` invocations. |
| **Docs, the WHY: docs tell a story — motivate the whole thing** | [`README.md`](./README.md), [`docs/m0.md`](./docs/m0.md), [`docs/milestones.md`](./docs/milestones.md) | **3** | The M0 document states a falsifiable hypothesis and reports the verdict from a reproducible instrument rather than asserting value. Milestones carry the same reasoning forward. |
| **Teaser video (12–30 s), prominent at TOP of README** | [`README.md`](./README.md) | **1** | A 30-second teaser is linked directly under the badges, so the placement is right — but it is **the Project 2 team's recording**. None of this team's work (restaurant sign-up, nutrition targets, the blueprint split, the Almanac themes) appears in it. |
| **Feature walk-through video (2–5 min), linked in README** | [`README.md`](./README.md) | **1** | Same recording and the same problem: it walks through UC29 and UC13 as they stood before this fork began. |

**Documentation: 13 / 18**

---

### 🛡️ Standard Files and Bling

| Item | Evidence Link | Score (0–3) | Justification |
|---|---|:---:|---|
| **README.md: all badges working when clicked** | [`README.md`](./README.md) | **2** | 17 badges, all pointing at `fixmeseb/Weeklies` and all returning 200 — CI and Docs both report *passing*. One target is still broken: the Docs badge links to the GitHub Pages site, which 404s because Pages is off. A DOI badge will make 18 once the first release is archived. |
| **.gitignore: lists what must not enter the repo** | [`.gitignore`](./.gitignore) | **3** | Excludes virtual environments, SQLite databases, caches, `node_modules`, and Cypress screenshots and videos. |
| **INSTALL.md: how to install** | [`INSTALL.md`](./INSTALL.md) | **3** | Windows and macOS/Linux paths, each ending in a verified run, plus the documentation build. |
| **LICENSE.md: rules of use** | [`LICENSE.md`](./LICENSE.md) | **3** | MIT, in the standard location. |
| **CODE-OF-CONDUCT.md: rules of behavior** | [`CODE-OF-CONDUCT.md`](./CODE-OF-CONDUCT.md) | **3** | Contributor Covenant with a named contact. |
| **CONTRIBUTING.md: coding standards & tips to extend** | [`CONTRIBUTING.md`](./CONTRIBUTING.md), [`PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md), [issue templates](./.github/ISSUE_TEMPLATE) | **3** | Branch conventions, how to run both suites, formatting rules, and the pull request workflow — and the templates it refers to now exist, so a contributor is prompted for the issue link, the verification steps and the lint gate rather than being told about them once. |
| **Style checker, formatter, syntax checker config + badges** | [`pyproject.toml`](./pyproject.toml), [`scripts/check-changed.sh`](./scripts/check-changed.sh) | **3** | Black and Ruff are configured in `pyproject.toml`, badged in the README, and — unusually — actually **enforced**: `check-changed.sh` fails CI on any Python file the branch touched that is unformatted or unclean. |
| **DOI badge from Zenodo** | [`CITATION.cff`](./CITATION.cff), [`.zenodo.json`](./.zenodo.json) | **0** | The old badge resolved to **`rdpatel2/Weeklies: v1.1.0 – Project 2 Release`**, the upstream archive, whose nine listed authors are the Project 1 and Project 2 teams; **no member of this team is on it**. It has been removed rather than left to mislead. Archive metadata is staged in `.zenodo.json` and `CITATION.cff`, so this becomes a 3 the moment the `v3.0.0` release is archived — see step 6 below. |
| **THIRD_PARTY_LIBRARIES.md: every dependency with license** | [`THIRD_PARTY_LIBRARIES.md`](./THIRD_PARTY_LIBRARIES.md) | **3** | Every Python, development and Node dependency with its version and licence, plus the USDA FoodData Central dataset and its CC0 1.0 terms. |
| **AI use is visible and disclosed** | [`AI_DISCLOSURE.md`](./AI_DISCLOSURE.md), [`.coderabbit.yaml`](./.coderabbit.yaml) | **3** | Tools, applications and the human verification process are documented. One correction is needed: the disclosure presents CodeRabbit as an active review bot, but the configuration file is present without the GitHub App installed, and **no pull request in this repository has a bot review**. |

**Standard Files & Bling: 26 / 30**

---

### 📊 Summary Score

| Category | Maximum | Self-Assessed | Recoverable |
|---|:---:|:---:|:---:|
| **Teamwork** (7 items) | 21 | **20** | +1 |
| **Issues & Discussion** (5 items) | 15 | **3** | +12 |
| **Tests** (4 items) | 12 | **12** | — |
| **Documentation** (6 items) | 18 | **13** | +5 |
| **Standard Files & Bling** (10 items) | 30 | **26** | +4 |
| **Total** | **96** | **74 / 96 (77%)** | **+22** |

Every point currently missing is recoverable, and most of it in an afternoon. The work is
done; what is missing is the record of it.

---

### 🔧 Gaps to close before submission

Ordered by points per hour of effort.

1. **File issues for work already done — up to +12.** Every defect this team fixed deserves an
   issue, opened, discussed and closed by its pull request: the variety score treating absent
   tags as difference, restaurant hours the planner could not read, lost wallet refunds, ticked
   tags dropped on a refused dish, the diet-editor Cypress breakage, the time-of-day-dependent
   scroll spec. Writing them retrospectively is honest as long as they are not backdated —
   reference the pull request that closed each one.
2. **Review each other's pull requests — part of the same +12.** Zero of 25 have a review and
   one has a comment. From here on, no merge without one approving review.
3. **Enable GitHub Discussions — optional, 0 points now.** The chat-channel item is satisfied by
   the Discord server, which is linked from the README and CONTRIBUTING. Turning Discussions on
   (Settings → General → Features) and moving one real design argument into a thread would put
   that record on-platform, where a grader can read it without joining the server.
4. **Enable GitHub Pages — +2 (one item here, one under Documentation).** Settings → Pages →
   source `gh-pages`. The branch is already built and current; only the switch is off. This also
   un-breaks the Docs badge link.
5. **Record a Project 3 teaser and walk-through — +4.** The linked videos are the previous team's.
   Thirty seconds and three minutes covering restaurant sign-up, nutrition targets and the
   Almanac themes would close both items.
6. **Mint this repository's own Zenodo DOI — +3.** The metadata is written; what remains is
   three steps in a browser, and **the order matters** — Zenodo only archives releases
   published *after* the repository is switched on there:
   1. Sign in at [zenodo.org](https://zenodo.org/) with GitHub and authorize it.
   2. Under *GitHub*, flip `fixmeseb/Weeklies` **on**. Only an account with admin on the
      repository sees it in that list.
   3. Publish a GitHub release tagged `v3.0.0`. Zenodo archives it and mints two DOIs; take the
      **concept DOI** (the one that always resolves to the latest version), put it in
      `CITATION.cff`, and add its badge to `README.md`.
7. **Even out the fourth member's contribution — +1.** One member is at 5 commits against 33, 33
   and 24.
8. ~~**Add a pull request template.**~~ Done: [`PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md)
   and bug/feature [issue templates](./.github/ISSUE_TEMPLATE), whose chooser also links the
   Discord server and the API docs. No points on its own; `CONTRIBUTING.md` had promised a
   template that did not exist.

---

### 📑 How these numbers were obtained

So that any of them can be re-checked rather than taken on trust:

```bash
# Commits, overall and in the Project 3 window
git rev-list --count main
git log --since=2026-11-02 --format='%an' main | sort | uniq -c | sort -rn

# Pull requests merged, versus changes pushed straight to main
git log --since=2026-11-02 --merges --format='%s' main | grep -c 'Merge pull request'
git log --since=2026-11-02 --first-parent --no-merges --oneline main | wc -l

# Test functions, files, and cases after parametrization
grep -rh '^\s*def test_' proj2/tests proj2/sef26tests scripts/tests | wc -l
find proj2/tests proj2/sef26tests scripts/tests -name 'test_*.py' | wc -l
cd proj2 && python -m pytest -q --cov=. --cov-report=term

# Share of the codebase that is tests
find proj2/tests proj2/sef26tests scripts/tests -name '*.py' | xargs wc -l | tail -1
find proj2 -name '*.py' -not -path '*/tests/*' -not -path '*/sef26tests/*' | xargs wc -l | tail -1
```

Issue, discussion, review and comment counts come from the repository's own GitHub search
(`is:issue`, `is:pr reviewed-by:*`, `is:pr comments:>0`) on 2026-11-25.
