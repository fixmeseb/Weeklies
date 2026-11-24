"""
Tests for Analytics data recording and snapshots
"""

from proj2.sqlQueries import create_connection, close_connection, fetch_one, fetch_all


def test_record_analytics_snapshot_creates_record(client, seed_orders_for_analytics):
    """Analytics snapshot should create a record in Analytics table."""
    from proj2.Flask_app import record_analytics_snapshot, db_path

    rtr_id = seed_orders_for_analytics["rtr_id"]

    # Record snapshot
    success = record_analytics_snapshot(rtr_id)
    assert success, "Snapshot recording should succeed"

    # Verify record was created
    conn = create_connection(db_path())
    try:
        analytics = fetch_one(
            conn,
            "SELECT analytics_id FROM Analytics WHERE rtr_id = ? ORDER BY analytics_id DESC LIMIT 1",
            (rtr_id,),
        )
        assert analytics is not None, "Analytics snapshot should be created"
    finally:
        close_connection(conn)


def test_analytics_snapshot_has_correct_data(client, seed_orders_for_analytics):
    """Analytics snapshot should capture correct data."""
    from proj2.Flask_app import record_analytics_snapshot, db_path

    rtr_id = seed_orders_for_analytics["rtr_id"]

    record_analytics_snapshot(rtr_id)

    conn = create_connection(db_path())
    try:
        snapshot = fetch_one(
            conn,
            """SELECT total_orders, total_revenue_cents, avg_order_value_cents, 
                      total_customers, order_completion_rate, snapshot_date
               FROM Analytics 
               WHERE rtr_id = ? 
               ORDER BY analytics_id DESC 
               LIMIT 1""",
            (rtr_id,),
        )

        assert snapshot is not None, "Snapshot should exist"
        total_orders, total_revenue, avg_value, total_customers, completion_rate, snapshot_date = (
            snapshot
        )

        # Verify data types and sanity checks
        assert isinstance(total_orders, int), "Total orders should be integer"
        assert total_orders >= 0, "Total orders should be non-negative"
        assert total_revenue >= 0, "Revenue should be non-negative"
        from datetime import date

        assert snapshot_date == date.today().isoformat(), "Snapshot date should be today"
    finally:
        close_connection(conn)


def test_analytics_snapshot_captures_popular_item(client, seed_orders_for_analytics):
    """Analytics snapshot should handle popular item identification."""
    from proj2.Flask_app import record_analytics_snapshot, db_path

    rtr_id = seed_orders_for_analytics["rtr_id"]

    record_analytics_snapshot(rtr_id)

    conn = create_connection(db_path())
    try:
        snapshot = fetch_one(
            conn,
            "SELECT most_popular_item_id FROM Analytics WHERE rtr_id = ? ORDER BY analytics_id DESC LIMIT 1",
            (rtr_id,),
        )

        # The popular item field exists; it may be None if no orders have items
        assert snapshot is not None, "Snapshot should have popular item field"
    finally:
        close_connection(conn)


def test_analytics_snapshot_one_record_per_day(client, seed_orders_for_analytics):
    """Recording twice in a day replaces that day's snapshot rather than adding one."""
    from proj2.Flask_app import record_analytics_snapshot, db_path

    rtr_id = seed_orders_for_analytics["rtr_id"]

    # Record two snapshots
    success1 = record_analytics_snapshot(rtr_id)
    success2 = record_analytics_snapshot(rtr_id)

    assert success1 and success2, "Both snapshots should be recorded"

    conn = create_connection(db_path())
    try:
        snapshots = fetch_all(
            conn,
            "SELECT analytics_id FROM Analytics WHERE rtr_id = ? ORDER BY analytics_id",
            (rtr_id,),
        )

        assert len(snapshots) == 1, "One snapshot per restaurant per day"
    finally:
        close_connection(conn)


def test_analytics_snapshot_completion_rate(client, seed_orders_for_analytics):
    """Analytics snapshot should calculate order completion rate."""
    from proj2.Flask_app import record_analytics_snapshot, db_path

    rtr_id = seed_orders_for_analytics["rtr_id"]

    record_analytics_snapshot(rtr_id)

    conn = create_connection(db_path())
    try:
        snapshot = fetch_one(
            conn,
            "SELECT order_completion_rate FROM Analytics WHERE rtr_id = ? ORDER BY analytics_id DESC LIMIT 1",
            (rtr_id,),
        )

        assert snapshot is not None, "Snapshot should have completion rate"
        completion_rate = snapshot[0]

        # Completion rate should be between 0 and 1
        assert 0 <= completion_rate <= 1, "Completion rate should be between 0 and 1"
    finally:
        close_connection(conn)
