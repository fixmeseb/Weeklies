# ⚙️ Installation Guide

> Tested on **Python 3.11+** (recommended: 3.12).  
> Follow the steps below to set up, run, and test the project on any OS.

---

## 🧩 Setup

### 🪟 Windows (PowerShell)
```powershell
# 1️⃣ Clone the repository
git clone https://github.com/rdpatel2/Weeklies.git
cd Weeklies

# 2️⃣ Create and activate a virtual environment
py -3 -m venv .venv
. .\.venv\Scripts\Activate.ps1
# If activation is blocked:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 3️⃣ Install dependencies
python -m pip install --upgrade pip
pip install -r proj2/requirements.txt
```

### 🐧 MacOS / Linux (Bash/Zsh)
```bash
# 1️⃣ Clone the repository
git clone https://github.com/rdpatel2/Weeklies.git
cd Weeklies

# 2️⃣ Create & activate a venv
python3 -m venv .venv
source .venv/bin/activate

# 3️⃣ Install packages
python -m pip install --upgrade pip
pip install -r proj2/requirements.txt
```

---

## 🚀 Usage

### Configuration
No configuration is needed for local development. The app reads optional settings from environment variables, which `flask run` loads from a git-ignored `.env` file in the repo root:

```bash
cp .env.example .env
# on a shared server, set WEEKLIES_SECRET_KEY in .env to the output of:
python -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Purpose | If unset |
|---|---|---|
| `WEEKLIES_SECRET_KEY` | Signs session cookies. Never commit a real value. | On first run the app generates a key and saves it to `proj2/instance/secret_key` (git-ignored), then reuses it, so logins survive restarts and auto-reloads. Delete that file to log everyone out. |
| `WEEKLIES_DATABASE` | Path of the SQLite database. Relative paths are taken from the repo root. | `proj2/CSC510_DB.db` |
| `FLASK_DEBUG` | `1` enables auto-reload and the interactive debugger for local development. | Debug is off. |

When starting the app directly with `python -m proj2.Flask_app`, debug mode is off unless you pass `--debug`. Never enable it on a server others can reach: the debugger lets anyone who sees an error page run code on the machine.

### Setting up the database
Run these from the repo root (`.flaskenv` tells `flask` where the app is):

```bash
flask seed       # create the database with demo data (deletes any existing one)
# or
flask init-db    # create an empty database
```

`flask seed` creates these accounts, all with the password `password123`:

| Account | Email |
|---|---|
| Customer | `testuser@example.com`, `seconduser@example.com` |
| Restaurant owner | `owner@tasteofitaly.com`, `owner@greengarden.com` |

The schema lives in numbered files in `proj2/migrations/`. After pulling changes that add one, run `flask migrate` to bring your database up to date without losing data. Databases made by the old setup scripts have no schema version and are refused: recreate them with `flask seed`.

If the database is missing or empty, the app shows a "Database not initialised" error instead of starting normally.

### Running the Application
Once dependencies are installed and the database is set up, you can run the Flask server from the repo root:

```bash
# Start the development server
flask run
```

The application will be available at `http://127.0.0.1:5000`.

---

## 🧪 Running Tests

### Python Tests (pytest)
Execute the test suite using pytest:
```bash
# Run all tests with verbose output
pytest -v

# Run with quiet output (dots for passes, F for failures)
pytest -q

# Run a specific test category
pytest proj2/tests/unit/ -v
pytest proj2/tests/integration/ -v
pytest proj2/tests/e2e/ -v
```

### Cypress E2E Tests
Cypress tests require Node.js (v18+) and a running Flask server:

```bash
# Install Cypress (one-time setup)
cd proj2
npm install

# Run Cypress tests headlessly
npx cypress run

# Open Cypress interactive runner
npx cypress open
```

> [!NOTE]
> Cypress uses its own database, `proj2/instance/cypress.db`, and reseeds it before
> each test, so E2E runs never touch your development data. Start the Flask server
> on `http://127.0.0.1:5000` against that database, in a separate terminal, before
> running Cypress:
>
> ```bash
> WEEKLIES_DATABASE=proj2/instance/cypress.db flask run          # Bash/Zsh
> $env:WEEKLIES_DATABASE="proj2/instance/cypress.db"; flask run  # PowerShell
> ```

---

## 📚 Documentation

### _Documentation is generated using pdoc._
Documentation is automatically generated using pdoc and deployed to GitHub Pages whenever new changes are merged into the `main` branch.

### 🧩 Automated Docs
* CI/CD workflow (`docs.yml`) builds and publishes docs from `proj2/` to the `gh-pages` branch.
* Live documentation becomes available at the GitHub Pages link after each successful merge.
* Source code is hidden; only public functions, classes, and docstrings are shown.

### 🖥️ Build Docs Locally

#### 🪟 Windows (PowerShell)
```powershell
# Temporarily add current directory to Python path
$env:PYTHONPATH="." ;
pdoc proj2 --no-show-source --template-dir proj2\pdoc_templates -o proj2\site
python .\scripts\build_docs.py
# View the documentation in your default browser
start proj2\site\index.html
```

#### 🐧 MacOS / Linux (Bash/Zsh)
```bash
# Temporarily add current directory to Python path
export PYTHONPATH="."
pdoc proj2 --no-show-source --template-dir proj2/pdoc_templates -o proj2/site
python ./scripts/build_docs.py
# View the documentation in your default browser
open proj2/site/index.html
```

The generated HTML files will be available in the `proj2/site` directory.
