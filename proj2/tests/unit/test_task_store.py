"""proj2/tasks/store.py and the 002_tasks.sql constraints behind it."""

import sqlite3
from datetime import date, timedelta

import pytest

from proj2 import db
from proj2.db_cli import init_database
from proj2.tasks import store
from proj2.tasks.store import TaskError, TaskNotFound

ALICE, BOB = 1, 2


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "tasks.db")
    init_database(path)
    c = db.connect(path)
    c.execute("INSERT INTO \"User\"(usr_id, email) VALUES (1, 'alice@x.com'), (2, 'bob@x.com')")
    c.commit()
    yield c
    c.close()


def _count(conn, table):
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


# ---------------------------------------------------------------- create / read


def test_create_and_get_task_with_project_and_tags(conn):
    project = store.create_project(conn, ALICE, "  CSC   510 ")
    task_id = store.create_task(
        conn,
        ALICE,
        "  Write   report ",
        notes=" draft ",
        due_date="2026-11-20",
        est_minutes="90",
        priority="1",
        project_id=str(project),
        tags=["Writing", "writing", "Urgent"],
    )
    task = store.get_task(conn, ALICE, task_id)
    assert task["title"] == "Write report"
    assert task["notes"] == "draft"
    assert task["due_date"] == "2026-11-20"
    assert task["est_minutes"] == 90
    assert (task["priority"], task["priority_name"]) == (1, "high")
    assert (task["project_id"], task["project_name"]) == (project, "CSC 510")
    assert task["tags"] == ["Urgent", "Writing"]  # deduplicated ignoring case, sorted
    assert task["status"] == "todo" and task["completed_at"] is None


def test_tags_are_shared_between_a_users_tasks(conn):
    store.create_task(conn, ALICE, "a", tags=["home"])
    store.create_task(conn, ALICE, "b", tags=["HOME"])
    store.create_task(conn, BOB, "c", tags=["home"])
    assert [(t["name"], t["task_count"]) for t in store.list_tags(conn, ALICE)] == [("home", 2)]
    assert _count(conn, "Tag") == 2  # one per user


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"title": "   "}, "Title is required"),
        ({"title": "x" * 201}, "at most 200"),
        ({"due_date": "2026-02-30"}, "real date"),
        ({"due_date": "next week"}, "real date"),
        ({"est_minutes": 0}, "between 1 and 1440"),
        ({"est_minutes": "lots"}, "whole number"),
        ({"priority": 4}, "Priority must be"),
        ({"project_id": 999}, "Unknown project"),
        ({"tags": ["ok", " "]}, "Tag name is required"),
    ],
)
def test_create_task_rejects_bad_input_and_writes_nothing(conn, kwargs, message):
    args = {"title": "t", **kwargs}
    with pytest.raises(TaskError, match=message):
        store.create_task(conn, ALICE, args.pop("title"), **args)
    assert _count(conn, "Task") == 0 and _count(conn, "Tag") == 0


def test_task_and_tags_are_written_in_one_transaction(conn, monkeypatch):
    def fail_after_task_insert(*_args):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(store, "_set_tags", fail_after_task_insert)
    with pytest.raises(sqlite3.OperationalError):
        store.create_task(conn, ALICE, "t", tags=["x"])
    assert _count(conn, "Task") == 0  # the task insert was rolled back too


def test_list_tasks_order_and_filters(conn):
    home = store.create_project(conn, ALICE, "Home")
    today = date.today()
    later = store.create_task(conn, ALICE, "later", due_date=today + timedelta(days=9))
    soon_low = store.create_task(conn, ALICE, "soon low", due_date=today, priority=3)
    soon_high = store.create_task(conn, ALICE, "soon high", due_date=today, priority=1, tags=["x"])
    undated = store.create_task(conn, ALICE, "undated", project_id=home)
    store.create_task(conn, BOB, "bob's")
    store.set_status(conn, ALICE, later, "done")

    ids = lambda tasks: [t["task_id"] for t in tasks]
    assert ids(store.list_tasks(conn, ALICE)) == [soon_high, soon_low, later, undated]
    assert ids(store.list_tasks(conn, ALICE, status=("todo", "in_progress"))) == [
        soon_high,
        soon_low,
        undated,
    ]
    assert ids(store.list_tasks(conn, ALICE, project_id=home)) == [undated]
    assert ids(store.list_tasks(conn, ALICE, project_id=None)) == [soon_high, soon_low, later]
    assert ids(store.list_tasks(conn, ALICE, tag="X")) == [soon_high]
    assert ids(store.list_tasks(conn, ALICE, due_by=today)) == [soon_high, soon_low]
    with pytest.raises(TaskError, match="Unknown status"):
        store.list_tasks(conn, ALICE, status="finished")


# ---------------------------------------------------------------- update / status / delete


def test_update_task_changes_only_given_fields(conn):
    task_id = store.create_task(conn, ALICE, "t", notes="keep", tags=["a", "b"])
    store.update_task(conn, ALICE, task_id, title="new", due_date=None, tags=["c"])
    task = store.get_task(conn, ALICE, task_id)
    assert (task["title"], task["notes"], task["tags"]) == ("new", "keep", ["c"])
    with pytest.raises(TypeError, match="status"):
        store.update_task(conn, ALICE, task_id, status="done")


def test_status_transitions(conn):
    task_id = store.create_task(conn, ALICE, "t")
    store.set_status(conn, ALICE, task_id, "done", now="2026-11-06T10:00:00")
    assert store.get_task(conn, ALICE, task_id)["completed_at"] == "2026-11-06T10:00:00"
    with pytest.raises(TaskError, match="cannot be marked in_progress"):
        store.set_status(conn, ALICE, task_id, "in_progress")
    store.set_status(conn, ALICE, task_id, "todo")  # reopen
    task = store.get_task(conn, ALICE, task_id)
    assert (task["status"], task["completed_at"]) == ("todo", None)
    with pytest.raises(TaskError, match="Unknown status"):
        store.set_status(conn, ALICE, task_id, "archived")


def test_every_transition_in_the_table_is_accepted_by_the_schema(conn):
    for start, targets in store.TRANSITIONS.items():
        for target in targets:
            task_id = store.create_task(conn, ALICE, f"{start}->{target}")
            if start != "todo":
                store.set_status(conn, ALICE, task_id, start)
            assert store.set_status(conn, ALICE, task_id, target) == target


def test_delete_task_removes_its_tag_links_and_plan_entries(conn):
    task_id = store.create_task(conn, ALICE, "t", tags=["x"])
    store.schedule_task(conn, ALICE, task_id, "2026-11-10", "morning")
    store.delete_task(conn, ALICE, task_id)
    assert (_count(conn, "Task"), _count(conn, "TaskTag"), _count(conn, "PlanEntry")) == (0, 0, 0)
    assert _count(conn, "Tag") == 1  # the tag itself stays


def test_delete_project_keeps_its_tasks(conn):
    project = store.create_project(conn, ALICE, "Home")
    task_id = store.create_task(conn, ALICE, "t", project_id=project)
    store.delete_project(conn, ALICE, project)
    assert store.get_task(conn, ALICE, task_id)["project_id"] is None
    assert store.list_projects(conn, ALICE) == []


def test_project_names_are_unique_per_user_ignoring_case(conn):
    store.create_project(conn, ALICE, "Home")
    with pytest.raises(TaskError, match="already have a project"):
        store.create_project(conn, ALICE, "HOME")
    store.create_project(conn, BOB, "Home")  # another user may reuse it


def test_list_projects_counts_open_tasks(conn):
    project = store.create_project(conn, ALICE, "Home")
    done = store.create_task(conn, ALICE, "a", project_id=project)
    store.create_task(conn, ALICE, "b", project_id=project)
    store.set_status(conn, ALICE, done, "done")
    [row] = store.list_projects(conn, ALICE)
    assert (row["name"], row["task_count"], row["open_count"]) == ("Home", 2, 1)


# ---------------------------------------------------------------- other users' rows


def test_users_cannot_see_or_change_each_others_tasks(conn):
    task_id = store.create_task(conn, ALICE, "private")
    project = store.create_project(conn, ALICE, "Home")
    for action in (
        lambda: store.get_task(conn, BOB, task_id),
        lambda: store.update_task(conn, BOB, task_id, title="mine now"),
        lambda: store.set_status(conn, BOB, task_id, "done"),
        lambda: store.delete_task(conn, BOB, task_id),
        lambda: store.schedule_task(conn, BOB, task_id, "2026-11-10", "morning"),
        lambda: store.delete_project(conn, BOB, project),
    ):
        with pytest.raises(TaskNotFound):
            action()
    with pytest.raises(TaskError, match="Unknown project"):
        store.create_task(conn, BOB, "t", project_id=project)
    assert store.list_tasks(conn, BOB) == []
    assert store.get_task(conn, ALICE, task_id)["title"] == "private"


def test_schema_rejects_cross_user_links_even_without_the_store(conn):
    project = store.create_project(conn, ALICE, "Home")
    task_id = store.create_task(conn, ALICE, "t")
    tag_conn = conn.execute("INSERT INTO \"Tag\"(usr_id, name) VALUES (2, 'bobs')")
    for sql, params in [
        ('INSERT INTO "Task"(usr_id, project_id, title) VALUES (?, ?, ?)', (BOB, project, "x")),
        (
            'INSERT INTO "TaskTag"(task_id, tag_id, usr_id) VALUES (?, ?, ?)',
            (task_id, tag_conn.lastrowid, ALICE),
        ),
        (
            'INSERT INTO "PlanEntry"(usr_id, task_id, date, slot) VALUES (?, ?, ?, ?)',
            (BOB, task_id, "2026-11-10", "morning"),
        ),
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(sql, params)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO \"Task\"(usr_id, title, status) VALUES (1, 't', 'done')",  # no completed_at
        "INSERT INTO \"Task\"(usr_id, title, status) VALUES (1, 't', 'archived')",
        "INSERT INTO \"Task\"(usr_id, title, due_date) VALUES (1, 't', '2026-02-30')",
        "INSERT INTO \"Task\"(usr_id, title, priority) VALUES (1, 't', 0)",
        "INSERT INTO \"Task\"(usr_id, title) VALUES (1, '   ')",
    ],
)
def test_schema_rejects_invalid_tasks(conn, sql):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(sql)


# ---------------------------------------------------------------- plan entries


def test_schedule_and_plan_between(conn):
    a = store.create_task(conn, ALICE, "a", priority=3)
    b = store.create_task(conn, ALICE, "b", priority=1)
    store.schedule_task(conn, ALICE, a, "2026-11-10", "evening")
    store.schedule_task(conn, ALICE, a, "2026-11-10", "morning")
    entry = store.schedule_task(conn, ALICE, b, "2026-11-10", "morning")
    store.schedule_task(conn, ALICE, b, "2026-11-12", "afternoon")
    plan = store.plan_between(conn, ALICE, "2026-11-10", "2026-11-11")
    assert [(e["slot"], e["title"]) for e in plan] == [
        ("morning", "b"),
        ("morning", "a"),
        ("evening", "a"),
    ]
    with pytest.raises(TaskError, match="already planned"):
        store.schedule_task(conn, ALICE, a, "2026-11-10", "morning")
    with pytest.raises(TaskError, match="Slot must be"):
        store.schedule_task(conn, ALICE, a, "2026-11-10", "night")
    store.unschedule(conn, ALICE, entry)
    with pytest.raises(TaskNotFound):
        store.unschedule(conn, BOB, entry - 1)
    assert len(store.plan_between(conn, ALICE, "2026-11-10", "2026-11-10")) == 2
