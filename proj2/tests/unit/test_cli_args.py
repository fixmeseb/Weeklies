"""Command-line options for running the app directly (python -m proj2.Flask_app).

Debug mode must be opt-in: the Werkzeug debugger allows remote code execution.
"""
import runpy

import pytest
from flask import Flask

from proj2.Flask_app import parse_args


# ---- expected cases ----

def test_defaults():
    args = parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 5000
    assert args.debug is False


def test_debug_flag_enables_debug():
    assert parse_args(["--debug"]).debug is True


def test_host_and_port():
    args = parse_args(["--host", "0.0.0.0", "--port", "5001"])
    assert (args.host, args.port) == ("0.0.0.0", 5001)


# ---- failure cases ----

@pytest.mark.parametrize("argv", [["--port", "abc"], ["--port"], ["--debug=yes"], ["--nope"]])
def test_bad_arguments_exit(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


# ---- the __main__ block passes the flag through to app.run ----
# runpy executes a second copy of the module as __main__ and warns that the
# package copy is already imported; that is intended here, since only the
# app.run call is captured.
pytestmark_runpy = pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")


def _run_main(monkeypatch, argv, database):
    calls = []
    monkeypatch.setattr(Flask, "run", lambda self, **kw: calls.append(kw))
    monkeypatch.setattr("sys.argv", ["Flask_app.py", *argv])
    # The __main__ block checks the database before starting: point it at the
    # migrated test database, never at the developer's proj2/CSC510_DB.db.
    monkeypatch.setenv("WEEKLIES_DATABASE", str(database))
    runpy.run_module("proj2.Flask_app", run_name="__main__")
    assert len(calls) == 1
    return calls[0]


@pytestmark_runpy
def test_main_runs_without_debug_by_default(monkeypatch, temp_db_path):
    assert _run_main(monkeypatch, [], temp_db_path)["debug"] is False


@pytestmark_runpy
def test_main_refuses_to_start_without_a_database(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        _run_main(monkeypatch, [], tmp_path / "missing.db")
    assert not (tmp_path / "missing.db").exists()


@pytestmark_runpy
def test_main_runs_with_debug_when_requested(monkeypatch, temp_db_path):
    kw = _run_main(monkeypatch, ["--debug", "--port", "5001"], temp_db_path)
    assert kw["debug"] is True
    assert kw["port"] == 5001
