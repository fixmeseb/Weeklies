-- 001: baseline schema. This file and the ones after it are the only schema
-- definition: `flask init-db`, `flask migrate`, the seed and the test suite all build
-- databases by applying them in order. Never edit an applied migration; add a new one.
--
-- Changes from the schema the old scripts created:
--   * Review: ord_id + created_at always present, and UNIQUE(ord_id) (one review per order)
--   * rating CHECKed to 1-5
--   * foreign keys everywhere (enforced: proj2/db.py turns PRAGMA foreign_keys on)
--   * dropped "Orders" and "OrderItems": nothing in the app read them
--
-- Deliberately NOT constrained: Order.status, MenuItem.price and MenuItem.instock. The
-- app tolerates odd values there on purpose (statuses are compared case-insensitively,
-- unknown ones fall back; unpriceable items are skipped) and tests rely on storing
-- them. These tables go away in the task-planner pivot, so the strict constraints
-- belong on the new task tables instead.

CREATE TABLE "User" (
  usr_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name     TEXT NOT NULL DEFAULT '',
  last_name      TEXT NOT NULL DEFAULT '',
  email          TEXT NOT NULL UNIQUE,
  phone          TEXT,
  password_HS    TEXT,
  wallet         INTEGER NOT NULL DEFAULT 0,
  preferences    TEXT DEFAULT '',
  allergies      TEXT DEFAULT '',
  generated_menu TEXT DEFAULT ''
);

CREATE TABLE "Restaurant" (
  rtr_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  description TEXT,
  phone       TEXT,
  email       TEXT UNIQUE,
  password_HS TEXT,
  address     TEXT,
  city        TEXT,
  state       TEXT,
  zip         TEXT,
  hours       TEXT,
  status      TEXT DEFAULT 'open'
);

CREATE TABLE "MenuItem" (
  itm_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id      INTEGER NOT NULL REFERENCES "Restaurant"(rtr_id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  description TEXT,
  price       INTEGER,  -- cents
  calories    INTEGER,
  instock     INTEGER DEFAULT 1,
  restock     TEXT,
  allergens   TEXT
);

CREATE TABLE "Order" (
  ord_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id  INTEGER NOT NULL REFERENCES "Restaurant"(rtr_id),
  usr_id  INTEGER NOT NULL REFERENCES "User"(usr_id),
  details TEXT,  -- JSON: items, charges (float dollars), delivery info
  status  TEXT DEFAULT 'Ordered'  -- Ordered, Accepted, Preparing, Ready, Delivered, Cancelled
);

CREATE TABLE "Review" (
  rev_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id      INTEGER NOT NULL REFERENCES "Restaurant"(rtr_id),
  usr_id      INTEGER NOT NULL REFERENCES "User"(usr_id),
  title       TEXT,
  rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  description TEXT,
  ord_id      INTEGER UNIQUE REFERENCES "Order"(ord_id),
  created_at  TEXT
);

CREATE TABLE "Analytics" (
  analytics_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  rtr_id                INTEGER NOT NULL REFERENCES "Restaurant"(rtr_id),
  snapshot_date         TEXT NOT NULL,
  total_orders          INTEGER DEFAULT 0,
  total_revenue_cents   INTEGER DEFAULT 0,
  avg_order_value_cents INTEGER DEFAULT 0,
  total_customers       INTEGER DEFAULT 0,
  most_popular_item_id  INTEGER REFERENCES "MenuItem"(itm_id),
  order_completion_rate REAL DEFAULT 0.0,
  created_at            TEXT NOT NULL
);

CREATE INDEX idx_menuitem_rtr ON "MenuItem"(rtr_id);
CREATE INDEX idx_order_rtr    ON "Order"(rtr_id);
CREATE INDEX idx_order_usr    ON "Order"(usr_id);
CREATE INDEX idx_review_rtr   ON "Review"(rtr_id);
CREATE INDEX idx_analytics_rtr_date ON "Analytics"(rtr_id, snapshot_date);
