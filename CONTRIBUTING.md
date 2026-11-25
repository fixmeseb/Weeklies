# Contributing to Weeklies

Thank you for your interest in contributing to **Weeklies**! We welcome contributions, bug reports, and feature suggestions from everyone.

Please take a moment to review this document to ensure a smooth and effective contribution workflow.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE-OF-CONDUCT.md). Please report any violations or unacceptable behavior to **actanton@ncsu.edu**.

---

## Getting Started

### 1. Fork & Clone
1. Fork the repository on GitHub: [`https://github.com/fixmeseb/Weeklies`](https://github.com/fixmeseb/Weeklies)
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/Weeklies.git
   cd Weeklies
   ```
3. Set the upstream remote:
   ```bash
   git remote add upstream https://github.com/fixmeseb/Weeklies.git
   ```

### 2. Environment Setup
1. Create and activate a Python 3.11+ virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Upgrade `pip` and install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r proj2/requirements.txt
   ```
3. (Optional for Cypress testing) Install Node.js dependencies:
   ```bash
   cd proj2
   npm install
   cd ..
   ```

---

## Branching Strategy & Workflow

1. Always branch off the latest `main`:
   ```bash
   git checkout main
   git pull upstream main
   git checkout -b feature/your-feature-name
   # or: fix/issue-description
   # or: docs/update-topic
   ```
2. Keep branches focused on a single topic, bug fix, or feature.
3. Commit messages should be clear and follow conventional commit conventions:
   - `feat: add order cancellation route`
   - `fix: resolve allergen filtering issue`
   - `test: add Cypress tests for login flow`
   - `docs: update installation instructions`
   - `chore: update dependencies`

---

## Testing Guidelines

All contributions must pass existing tests and include new tests where applicable.

### Running Python Tests
```bash
# Run entire test suite
pytest -v

# Run with quiet reporting
pytest -q

# Run specific test suites
pytest proj2/tests/unit/ -v
pytest proj2/tests/integration/ -v
pytest proj2/tests/e2e/ -v
```

### Running Cypress E2E Tests
```bash
cd proj2
# Make sure Flask app is running on port 5000 in another terminal:
# python -m flask run --port 5000
npx cypress run
```

---

## Code Style & Formatting

We enforce strict formatting and linting rules:

1. **Formatting**: Code must follow [Black](https://github.com/psf/black) standards:
   ```bash
   black --check proj2/
   # Format code with:
   black proj2/
   ```
2. **Linting**: Code must pass [Ruff](https://github.com/astral-sh/ruff) checks:
   ```bash
   ruff check proj2/
   ```

---

## Submitting Pull Requests

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
2. Open a Pull Request targeting the `main` branch of `fixmeseb/Weeklies`.
3. Fill out the PR template or description:
   - Describe the purpose and changes introduced by the PR.
   - Reference any related issue numbers (e.g., `Fixes #12`).
   - Confirm that all unit tests, linters, and Cypress tests pass.
4. Respond to feedback and make any requested revisions.
5. Once approved and CI checks pass, a maintainer will merge the PR.

---

## Questions and Support

Feel free to open an issue or reach out via our project discussions on GitHub. Thank you for helping make Weeklies better!
