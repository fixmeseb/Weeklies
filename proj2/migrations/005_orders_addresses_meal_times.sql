-- Delivery addresses and meal times on the account, a status history for orders, and
-- one analytics snapshot per restaurant per day.

-- Where delivery orders go. All optional; a delivery order needs at least the street.
ALTER TABLE "User" ADD COLUMN address TEXT;
ALTER TABLE "User" ADD COLUMN city    TEXT;
ALTER TABLE "User" ADD COLUMN state   TEXT;
ALTER TABLE "User" ADD COLUMN zip     TEXT;

-- When the user eats each meal, in HHMM (24h). NULL means the default
-- (proj2/meal_times.py: breakfast 1000, lunch 1400, dinner 2000).
ALTER TABLE "User" ADD COLUMN breakfast_time INTEGER CHECK (breakfast_time BETWEEN 0 AND 2359);
ALTER TABLE "User" ADD COLUMN lunch_time     INTEGER CHECK (lunch_time BETWEEN 0 AND 2359);
ALTER TABLE "User" ADD COLUMN dinner_time    INTEGER CHECK (dinner_time BETWEEN 0 AND 2359);

-- Every status an order has had, with when it changed (proj2/order_progress.py).
CREATE TABLE "OrderStatus" (
  ost_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  ord_id  INTEGER NOT NULL REFERENCES "Order"(ord_id) ON DELETE CASCADE,
  status  TEXT NOT NULL,
  at      TEXT NOT NULL
);
CREATE INDEX idx_order_status_ord ON "OrderStatus"(ord_id, ost_id);

-- Existing orders start their history with the status they have now, dated when they
-- were placed (or now, for orders that never recorded it).
INSERT INTO "OrderStatus"(ord_id, status, at)
SELECT ord_id, COALESCE(status, 'Ordered'),
       COALESCE(json_extract(details, '$.placed_at'), strftime('%Y-%m-%dT%H:%M:%S', 'now'))
FROM "Order"
WHERE json_valid(details);
INSERT INTO "OrderStatus"(ord_id, status, at)
SELECT ord_id, COALESCE(status, 'Ordered'), strftime('%Y-%m-%dT%H:%M:%S', 'now')
FROM "Order"
WHERE details IS NULL OR NOT json_valid(details);

-- Analytics kept one row per page view; keep only each day's latest row, then allow one.
DELETE FROM "Analytics"
WHERE analytics_id NOT IN (
  SELECT MAX(analytics_id) FROM "Analytics" GROUP BY rtr_id, snapshot_date
);
CREATE UNIQUE INDEX idx_analytics_day ON "Analytics"(rtr_id, snapshot_date);
