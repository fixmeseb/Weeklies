"""The app factory and the blueprint boundaries the task-planner pivot relies on."""

import ast
import pathlib

import pytest

from proj2 import create_app

PROJ2 = pathlib.Path(__file__).resolve().parents[2]

# Blueprints that survive the pivot. They must not depend on proj2.food, so that the
# food package can be deleted in one commit (pivot Phase 5).
CORE = ["auth", "account", "planner", "tasks"]
CORE_MODULES = ["settings.py", "db.py", "db_cli.py", "sqlQueries.py"]


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def _core_files():
    for pkg in CORE:
        yield from sorted((PROJ2 / pkg).rglob("*.py"))
    for name in CORE_MODULES:
        yield PROJ2 / name


@pytest.mark.parametrize("path", list(_core_files()), ids=lambda p: p.relative_to(PROJ2).as_posix())
def test_core_code_does_not_import_food(path):
    food = [m for m in _imported_modules(path) if m == "proj2.food" or m.startswith("proj2.food.")]
    assert food == [], f"{path.name} imports {food}; move the shared code out of proj2/food"


def test_create_app_applies_test_config(tmp_path):
    db = str(tmp_path / "x.db")
    app = create_app({"TESTING": True, "DATABASE": db, "SECRET_KEY": "k"})
    assert app.config["DATABASE"] == db and app.testing
    assert set(app.blueprints) == {"auth", "account", "planner", "food"}


def test_create_app_builds_independent_apps():
    a, b = create_app({"TESTING": True}), create_app({"TESTING": True})
    assert a is not b and a.config is not b.config
    rules = lambda app: sorted((r.rule, r.endpoint) for r in app.url_map.iter_rules())
    assert rules(a) == rules(b)


def test_endpoints_are_namespaced_by_blueprint():
    app = create_app({"TESTING": True})
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert {"auth.login", "auth.register", "account.profile", "planner.index"} <= endpoints
    assert "food.order" in endpoints and "login" not in endpoints
