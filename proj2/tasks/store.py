"""
Tasks, projects, tags and plan entries: all task-planner reads and writes.

Every function takes the connection and the acting user's ``usr_id`` and only ever
touches that user's rows; a row belonging to someone else is reported as not found.
Bad input raises ``TaskError`` (a ``ValueError``; routes turn it into a 400) and a
missing row raises ``TaskNotFound``. Writes that touch several tables run inside one
``transaction()``, so they happen completely or not at all.

The schema (proj2/migrations/002_tasks.sql) enforces the same rules again, so a bug
here fails loudly instead of storing bad data.
"""

import sqlite3
from datetime import date, datetime

from proj2.db import transaction
from proj2.sqlQueries import execute_query, fetch_all, fetch_one

PRIORITIES = {1: "high", 2: "normal", 3: "low"}
STATUSES = ("todo", "in_progress", "done", "cancelled")
SLOTS = ("morning", "afternoon", "evening")

# Allowed status changes. Finished tasks (done/cancelled) can only be reopened to todo.
TRANSITIONS = {
    "todo": {"in_progress", "done", "cancelled"},
    "in_progress": {"todo", "done", "cancelled"},
    "done": {"todo"},
    "cancelled": {"todo"},
}

MAX_TITLE, MAX_PROJECT, MAX_TAG = 200, 100, 40

_TASK_COLUMNS = (
    "t.task_id, t.project_id, p.name AS project_name, t.title, t.notes, t.due_date, "
    "t.est_minutes, t.priority, t.status, t.created_at, t.completed_at"
)
_UNSET = object()


class TaskError(ValueError):
    """Input the task planner cannot accept; the message is safe to show the user."""


class TaskNotFound(LookupError):
    """No such task/project/tag/entry for this user."""


# ---------------------------------------------------------------- validation


def _clean_text(value, what, max_len):
    text = " ".join(str(value or "").split())
    if not text:
        raise TaskError(f"{what} is required.")
    if len(text) > max_len:
        raise TaskError(f"{what} must be at most {max_len} characters.")
    return text


def _clean_date(value, what="Due date"):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise TaskError(f"{what} must be a real date in YYYY-MM-DD form.") from None


def _clean_minutes(value):
    if value in (None, ""):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise TaskError("Estimated time must be a whole number of minutes.") from None
    if not 1 <= minutes <= 1440:
        raise TaskError("Estimated time must be between 1 and 1440 minutes.")
    return minutes


def _clean_priority(value):
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = None
    if priority not in PRIORITIES:
        raise TaskError("Priority must be 1 (high), 2 (normal) or 3 (low).")
    return priority


def _clean_tags(names):
    """Strip, collapse spaces and drop case-insensitive duplicates, keeping order."""
    seen, out = set(), []
    for name in names or ():
        tag = _clean_text(name, "Tag name", MAX_TAG)
        if tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- projects


def create_project(conn, usr_id, name):
    """Create a project. Names are unique per user, ignoring case."""
    name = _clean_text(name, "Project name", MAX_PROJECT)
    try:
        return execute_query(
            conn, 'INSERT INTO "Project"(usr_id, name) VALUES (?, ?)', (usr_id, name)
        ).lastrowid
    except sqlite3.IntegrityError:
        raise TaskError(f"You already have a project called {name!r}.") from None


def list_projects(conn, usr_id):
    rows = fetch_all(
        conn,
        """
        SELECT p.project_id, p.name,
               COUNT(t.task_id) AS task_count,
               SUM(t.status IN ('todo', 'in_progress')) AS open_count
        FROM "Project" p LEFT JOIN "Task" t ON t.project_id = p.project_id
        WHERE p.usr_id = ?
        GROUP BY p.project_id ORDER BY p.name COLLATE NOCASE
        """,
        (usr_id,),
    )
    return [dict(r, open_count=r["open_count"] or 0) for r in rows]


def delete_project(conn, usr_id, project_id):
    """Delete a project; its tasks are kept and become project-less."""
    with transaction(conn):
        _require(conn, "Project", "project_id", project_id, usr_id)
        execute_query(
            conn,
            'UPDATE "Task" SET project_id = NULL WHERE project_id = ? AND usr_id = ?',
            (project_id, usr_id),
        )
        execute_query(
            conn, 'DELETE FROM "Project" WHERE project_id = ? AND usr_id = ?', (project_id, usr_id)
        )


def _check_project(conn, usr_id, project_id):
    if project_id in (None, ""):
        return None
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        raise TaskError("Unknown project.") from None
    row = fetch_one(
        conn,
        'SELECT 1 FROM "Project" WHERE project_id = ? AND usr_id = ?',
        (project_id, usr_id),
    )
    if row is None:
        raise TaskError("Unknown project.")
    return project_id


# ---------------------------------------------------------------- tags


def list_tags(conn, usr_id):
    rows = fetch_all(
        conn,
        """
        SELECT g.tag_id, g.name, COUNT(tt.task_id) AS task_count
        FROM "Tag" g LEFT JOIN "TaskTag" tt ON tt.tag_id = g.tag_id
        WHERE g.usr_id = ? GROUP BY g.tag_id ORDER BY g.name COLLATE NOCASE
        """,
        (usr_id,),
    )
    return [dict(r) for r in rows]


def delete_tag(conn, usr_id, tag_id):
    """Delete a tag; it is removed from every task that had it."""
    _require(conn, "Tag", "tag_id", tag_id, usr_id)
    execute_query(conn, 'DELETE FROM "Tag" WHERE tag_id = ? AND usr_id = ?', (tag_id, usr_id))


def _set_tags(conn, usr_id, task_id, names):
    """Replace a task's tags, creating tags that don't exist yet. Call inside a transaction."""
    execute_query(conn, 'DELETE FROM "TaskTag" WHERE task_id = ? AND usr_id = ?', (task_id, usr_id))
    for name in names:
        row = fetch_one(
            conn,
            'SELECT tag_id FROM "Tag" WHERE usr_id = ? AND name = ? COLLATE NOCASE',
            (usr_id, name),
        )
        if row is None:
            tag_id = execute_query(
                conn, 'INSERT INTO "Tag"(usr_id, name) VALUES (?, ?)', (usr_id, name)
            ).lastrowid
        else:
            tag_id = row["tag_id"]
        execute_query(
            conn,
            'INSERT INTO "TaskTag"(task_id, tag_id, usr_id) VALUES (?, ?, ?)',
            (task_id, tag_id, usr_id),
        )


def _tags_by_task(conn, usr_id, task_ids):
    if not task_ids:
        return {}
    marks = ",".join("?" * len(task_ids))
    rows = fetch_all(
        conn,
        f"""
        SELECT tt.task_id, g.name FROM "TaskTag" tt JOIN "Tag" g ON g.tag_id = tt.tag_id
        WHERE tt.usr_id = ? AND tt.task_id IN ({marks}) ORDER BY g.name COLLATE NOCASE
        """,
        (usr_id, *task_ids),
    )
    out = {}
    for r in rows:
        out.setdefault(r["task_id"], []).append(r["name"])
    return out


# ---------------------------------------------------------------- tasks


def create_task(
    conn,
    usr_id,
    title,
    *,
    notes="",
    due_date=None,
    est_minutes=None,
    priority=2,
    project_id=None,
    tags=(),
):
    """Create a task (and any new tags) in one transaction. Returns the task_id."""
    title = _clean_text(title, "Title", MAX_TITLE)
    values = (
        usr_id,
        _check_project(conn, usr_id, project_id),
        title,
        (notes or "").strip(),
        _clean_date(due_date),
        _clean_minutes(est_minutes),
        _clean_priority(priority),
    )
    tags = _clean_tags(tags)
    with transaction(conn):
        task_id = execute_query(
            conn,
            'INSERT INTO "Task"(usr_id, project_id, title, notes, due_date, est_minutes, priority) '
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            values,
        ).lastrowid
        _set_tags(conn, usr_id, task_id, tags)
    return task_id


def get_task(conn, usr_id, task_id):
    row = fetch_one(
        conn,
        f"""
        SELECT {_TASK_COLUMNS} FROM "Task" t
        LEFT JOIN "Project" p ON p.project_id = t.project_id
        WHERE t.task_id = ? AND t.usr_id = ?
        """,
        (task_id, usr_id),
    )
    if row is None:
        raise TaskNotFound(f"No task {task_id}.")
    return _task_dict(row, _tags_by_task(conn, usr_id, [row["task_id"]]))


def list_tasks(conn, usr_id, *, status=None, project_id=_UNSET, tag=None, due_by=None):
    """
    The user's tasks: earliest due date first (undated last), then priority, then age.

    Args:
        status: one status, or an iterable of them (e.g. ("todo", "in_progress")).
        project_id: only this project's tasks; None for tasks without a project.
        tag: only tasks with this tag (case-insensitive).
        due_by: only tasks due on or before this date.
    """
    where, params = ["t.usr_id = ?"], [usr_id]
    if status is not None:
        statuses = [status] if isinstance(status, str) else list(status)
        bad = set(statuses) - set(STATUSES)
        if bad:
            raise TaskError(f"Unknown status {min(bad)!r}.")
        where.append(f"t.status IN ({','.join('?' * len(statuses))})")
        params += statuses
    if project_id is not _UNSET:
        if project_id is None:
            where.append("t.project_id IS NULL")
        else:
            where.append("t.project_id = ?")
            params.append(project_id)
    if tag:
        where.append(
            'EXISTS (SELECT 1 FROM "TaskTag" tt JOIN "Tag" g ON g.tag_id = tt.tag_id '
            "WHERE tt.task_id = t.task_id AND g.name = ? COLLATE NOCASE)"
        )
        params.append(tag)
    if due_by is not None:
        where.append("t.due_date IS NOT NULL AND t.due_date <= ?")
        params.append(_clean_date(due_by, "Due-by date"))
    rows = fetch_all(
        conn,
        f"""
        SELECT {_TASK_COLUMNS} FROM "Task" t
        LEFT JOIN "Project" p ON p.project_id = t.project_id
        WHERE {' AND '.join(where)}
        ORDER BY t.due_date IS NULL, t.due_date, t.priority, t.task_id
        """,
        params,
    )
    tags = _tags_by_task(conn, usr_id, [r["task_id"] for r in rows])
    return [_task_dict(r, tags) for r in rows]


def update_task(conn, usr_id, task_id, **changes):
    """
    Change some of a task's fields: title, notes, due_date, est_minutes, priority,
    project_id, tags (replaces the whole set). Status has its own function, set_status.
    """
    allowed = {"title", "notes", "due_date", "est_minutes", "priority", "project_id", "tags"}
    unknown = set(changes) - allowed
    if unknown:
        raise TypeError(f"update_task() got unexpected fields {sorted(unknown)}")
    cleaners = {
        "title": lambda v: _clean_text(v, "Title", MAX_TITLE),
        "notes": lambda v: (v or "").strip(),
        "due_date": _clean_date,
        "est_minutes": _clean_minutes,
        "priority": _clean_priority,
        "project_id": lambda v: _check_project(conn, usr_id, v),
    }
    columns = {k: cleaners[k](v) for k, v in changes.items() if k != "tags"}
    tags = _clean_tags(changes["tags"]) if "tags" in changes else None
    with transaction(conn):
        _require(conn, "Task", "task_id", task_id, usr_id)
        if columns:
            assignments = ", ".join(f"{col} = ?" for col in columns)
            execute_query(
                conn,
                f'UPDATE "Task" SET {assignments} WHERE task_id = ? AND usr_id = ?',
                (*columns.values(), task_id, usr_id),
            )
        if tags is not None:
            _set_tags(conn, usr_id, task_id, tags)


def set_status(conn, usr_id, task_id, status, *, now=None):
    """Move a task to ``status`` if TRANSITIONS allows it. Returns the new status."""
    if status not in STATUSES:
        raise TaskError(f"Unknown status {status!r}.")
    row = fetch_one(
        conn, 'SELECT status FROM "Task" WHERE task_id = ? AND usr_id = ?', (task_id, usr_id)
    )
    if row is None:
        raise TaskNotFound(f"No task {task_id}.")
    current = row["status"]
    if status == current:
        return status
    if status not in TRANSITIONS[current]:
        raise TaskError(f"A {current.replace('_', ' ')} task cannot be marked {status}.")
    completed_at = (now or _now()) if status == "done" else None
    execute_query(
        conn,
        'UPDATE "Task" SET status = ?, completed_at = ? WHERE task_id = ? AND usr_id = ?',
        (status, completed_at, task_id, usr_id),
    )
    return status


def delete_task(conn, usr_id, task_id):
    """Delete a task; its tags links and plan entries go with it (ON DELETE CASCADE)."""
    _require(conn, "Task", "task_id", task_id, usr_id)
    execute_query(conn, 'DELETE FROM "Task" WHERE task_id = ? AND usr_id = ?', (task_id, usr_id))


def _task_dict(row, tags_by_task):
    task = dict(row)
    task["priority_name"] = PRIORITIES[task["priority"]]
    task["tags"] = tags_by_task.get(task["task_id"], [])
    return task


# ---------------------------------------------------------------- plan entries


def schedule_task(conn, usr_id, task_id, day, slot):
    """Put a task into a day's slot. A task can be in several slots, but each only once."""
    if slot not in SLOTS:
        raise TaskError(f"Slot must be one of {', '.join(SLOTS)}.")
    day = _clean_date(day, "Date")
    if day is None:
        raise TaskError("Date is required.")
    _require(conn, "Task", "task_id", task_id, usr_id)
    try:
        return execute_query(
            conn,
            'INSERT INTO "PlanEntry"(usr_id, task_id, date, slot) VALUES (?, ?, ?, ?)',
            (usr_id, task_id, day, slot),
        ).lastrowid
    except sqlite3.IntegrityError:
        raise TaskError("That task is already planned for that slot.") from None


def unschedule(conn, usr_id, entry_id):
    _require(conn, "PlanEntry", "entry_id", entry_id, usr_id)
    execute_query(
        conn, 'DELETE FROM "PlanEntry" WHERE entry_id = ? AND usr_id = ?', (entry_id, usr_id)
    )


def plan_between(conn, usr_id, start, end):
    """Plan entries from ``start`` to ``end`` inclusive, in day and slot order."""
    start, end = _clean_date(start, "Start date"), _clean_date(end, "End date")
    rows = fetch_all(
        conn,
        """
        SELECT e.entry_id, e.date, e.slot, t.task_id, t.title, t.status, t.priority,
               t.est_minutes
        FROM "PlanEntry" e JOIN "Task" t ON t.task_id = e.task_id
        WHERE e.usr_id = ? AND e.date BETWEEN ? AND ?
        ORDER BY e.date,
                 CASE e.slot WHEN 'morning' THEN 1 WHEN 'afternoon' THEN 2 ELSE 3 END,
                 t.priority, t.task_id
        """,
        (usr_id, start, end),
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- shared


def _require(conn, table, key, value, usr_id):
    row = fetch_one(
        conn, f'SELECT 1 FROM "{table}" WHERE {key} = ? AND usr_id = ?', (value, usr_id)
    )
    if row is None:
        raise TaskNotFound(f"No {table.lower()} {value}.")
