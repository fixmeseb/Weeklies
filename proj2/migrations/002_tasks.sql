-- 002: the task planner's tables.
--
-- Every row belongs to one user. Composite foreign keys such as
-- (project_id, usr_id) -> Project(project_id, usr_id) make it impossible for a task
-- to point at another user's project or tag, whatever the route code does.
-- Dates are checked with date(x, '+0 days') IS x: plain date(x) accepts 2026-02-30.

CREATE TABLE "Project" (
  project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  usr_id     INTEGER NOT NULL REFERENCES "User"(usr_id) ON DELETE CASCADE,
  name       TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
  UNIQUE (usr_id, name COLLATE NOCASE),
  UNIQUE (project_id, usr_id)  -- target of the composite FK below
);

CREATE TABLE "Task" (
  task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  usr_id       INTEGER NOT NULL REFERENCES "User"(usr_id) ON DELETE CASCADE,
  project_id   INTEGER,
  title        TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
  notes        TEXT NOT NULL DEFAULT '',
  due_date     TEXT CHECK (due_date IS NULL OR date(due_date, '+0 days') IS due_date),  -- real YYYY-MM-DD
  est_minutes  INTEGER CHECK (est_minutes IS NULL OR est_minutes BETWEEN 1 AND 1440),
  priority     INTEGER NOT NULL DEFAULT 2 CHECK (priority IN (1, 2, 3)),  -- 1 high, 2 normal, 3 low
  status       TEXT NOT NULL DEFAULT 'todo'
               CHECK (status IN ('todo', 'in_progress', 'done', 'cancelled')),
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
  completed_at TEXT,
  CHECK ((status = 'done') = (completed_at IS NOT NULL)),
  UNIQUE (task_id, usr_id),
  -- Deleting a project with tasks is refused; the app clears project_id first
  -- (proj2/tasks/store.py: delete_project), in one transaction.
  FOREIGN KEY (project_id, usr_id) REFERENCES "Project"(project_id, usr_id)
);

CREATE TABLE "Tag" (
  tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
  usr_id INTEGER NOT NULL REFERENCES "User"(usr_id) ON DELETE CASCADE,
  name   TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 40),
  UNIQUE (usr_id, name COLLATE NOCASE),
  UNIQUE (tag_id, usr_id)
);

CREATE TABLE "TaskTag" (
  task_id INTEGER NOT NULL,
  tag_id  INTEGER NOT NULL,
  usr_id  INTEGER NOT NULL,
  PRIMARY KEY (task_id, tag_id),
  FOREIGN KEY (task_id, usr_id) REFERENCES "Task"(task_id, usr_id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id, usr_id)  REFERENCES "Tag"(tag_id, usr_id)   ON DELETE CASCADE
);

-- A task scheduled into a day's slot. Replaces the User.generated_menu string once the
-- planner is ported (pivot Phase 4).
CREATE TABLE "PlanEntry" (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  usr_id   INTEGER NOT NULL,
  task_id  INTEGER NOT NULL,
  date     TEXT NOT NULL CHECK (date(date, '+0 days') IS date),  -- '+0 days' rejects 02-30 etc.
  slot     TEXT NOT NULL CHECK (slot IN ('morning', 'afternoon', 'evening')),
  UNIQUE (task_id, date, slot),
  FOREIGN KEY (task_id, usr_id) REFERENCES "Task"(task_id, usr_id) ON DELETE CASCADE
);

CREATE INDEX idx_task_usr_status ON "Task"(usr_id, status);
CREATE INDEX idx_task_usr_due    ON "Task"(usr_id, due_date);
CREATE INDEX idx_task_project    ON "Task"(project_id, usr_id);
CREATE INDEX idx_tasktag_tag     ON "TaskTag"(tag_id, usr_id);
CREATE INDEX idx_planentry_day   ON "PlanEntry"(usr_id, date);
