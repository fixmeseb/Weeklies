"""The app factory and the boundaries between the blueprints."""

import ast
import pathlib
import re

import pytest

from proj2 import create_app

PROJ2 = pathlib.Path(__file__).resolve().parents[2]

# These must not depend on proj2.food: code they share with it lives outside it.
CORE_PACKAGES = ["auth", "account", "planner", "tasks"]
CORE_MODULES = ["settings.py", "customer.py", "order_history.py", "db.py", "db_cli.py"]
CORE_FILES = [p for pkg in CORE_PACKAGES for p in sorted((PROJ2 / pkg).rglob("*.py"))] + [
    PROJ2 / name for name in CORE_MODULES
]


def _imported_modules(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.relative_to(PROJ2).as_posix())
def test_core_code_does_not_import_food(path):
    food = [m for m in _imported_modules(path) if m == "proj2.food" or m.startswith("proj2.food.")]
    assert food == [], f"{path.name} imports {food}; move the shared code out of proj2/food"


def test_create_app_applies_test_config(tmp_path):
    db = str(tmp_path / "x.db")
    app = create_app({"TESTING": True, "DATABASE": db, "SECRET_KEY": "k"})
    assert app.config["DATABASE"] == db and app.config["SECRET_KEY"] == "k" and app.testing
    assert set(app.blueprints) == {"auth", "account", "planner", "food"}


def test_create_app_builds_independent_apps():
    a, b = create_app({"TESTING": True}), create_app({"TESTING": True})
    assert a is not b and a.config is not b.config
    assert _endpoints(a) == _endpoints(b)


def _endpoints(app):
    return {rule.endpoint for rule in app.url_map.iter_rules()}


def test_endpoints_are_namespaced_by_blueprint():
    names = _endpoints(create_app({"TESTING": True}))
    assert {"auth.login", "account.profile", "planner.index", "food.order"} <= names
    assert {name for name in names if "." not in name} == {"static"}


def test_every_url_for_names_a_real_endpoint():
    """A stale name only fails when its line runs, which a rarely shown branch may hide."""
    names = _endpoints(create_app({"TESTING": True}))
    sources = list((PROJ2 / "templates").rglob("*.html"))
    for pkg in ("auth", "account", "planner", "food"):
        sources += (PROJ2 / pkg).rglob("*.py")
    used = {
        (path.name, name)
        for path in sources
        for name in re.findall(r"url_for\(\s*['\"]([^'\"]+)", path.read_text(encoding="utf-8"))
    }
    assert used and sorted(u for u in used if u[1] not in names) == []
