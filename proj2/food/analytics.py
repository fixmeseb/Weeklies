"""Restaurant analytics: daily snapshots and the owner's analytics page."""

import json
from datetime import date, datetime

from flask import current_app, render_template, session

from proj2.db import get_db, transaction
from proj2.food.blueprint import bp
from proj2.food.owner_auth import restaurant_required
from proj2.ordering import daily_order_counts, restaurant_metrics
from proj2.sqlQueries import execute_query, fetch_all


def _restaurant_orders_for_metrics(conn, rtr_id):
    """(status, usr_id, details) of every order a restaurant has received."""
    return fetch_all(
        conn, 'SELECT status, usr_id, details FROM "Order" WHERE rtr_id = ?', (rtr_id,)
    )


def record_analytics_snapshot(rtr_id):
    """
    Save today's figures for a restaurant (proj2.ordering.restaurant_metrics).

    There is one snapshot per restaurant per day: a later call the same day replaces
    that day's row instead of adding another, so the history has one point per day
    however often orders change. Cancelled orders are left out of revenue.

    Args:
        rtr_id (int): The restaurant ID to record analytics for.

    Returns:
        bool: True if snapshot was recorded successfully, False otherwise.
    """
    conn = get_db()
    today = date.today().isoformat()
    try:
        m = restaurant_metrics(_restaurant_orders_for_metrics(conn, rtr_id))
        with transaction(conn):
            # Replace today's row (migration 010 also makes a second one impossible).
            execute_query(
                conn,
                "DELETE FROM Analytics WHERE rtr_id = ? AND snapshot_date = ?",
                (rtr_id, today),
            )
            execute_query(
                conn,
                """
                INSERT INTO Analytics
                (rtr_id, snapshot_date, total_orders, total_revenue_cents,
                 avg_order_value_cents, total_customers, most_popular_item_id,
                 order_completion_rate, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rtr_id,
                    today,
                    m["total_orders"],
                    m["total_revenue_cents"],
                    m["avg_order_value_cents"],
                    m["total_customers"],
                    m["most_popular_item_id"],
                    m["order_completion_rate"],
                    datetime.now().isoformat(),
                ),
            )
        return True
    except Exception:
        current_app.logger.exception("Could not record the analytics snapshot for %s", rtr_id)
        return False


def update_analytics_safe(rtr_id):
    """
    Safe wrapper to update analytics snapshot without blocking request.
    Silently fails if unable to update (doesn't disrupt order/status flow).

    Args:
        rtr_id (int): The restaurant ID to update analytics for.
    """
    try:
        record_analytics_snapshot(rtr_id)
    except Exception:
        pass  # Silently fail - don't interrupt main request


@bp.route("/restaurant/analytics")
@restaurant_required
def restaurant_analytics():
    """
    Analytics dashboard showing restaurant order statistics and trends.
    Calculates analytics snapshot on the fly from current order data.

    Args:
        None
    Returns:
        Response: Renders analytics dashboard with charts and metrics.
    """
    restaurant_name = session.get("RestaurantName", "Restaurant")
    rtr_id = session.get("rtr_id")

    # Figures straight from the orders; viewing the page writes nothing.
    conn = get_db()
    all_orders = _restaurant_orders_for_metrics(conn, rtr_id)
    metrics = restaurant_metrics(all_orders)
    total_orders = metrics["total_orders"]
    total_revenue = metrics["total_revenue_cents"] / 100.0
    avg_order_value = metrics["avg_order_value_cents"] / 100.0

    # Get order status distribution from actual orders
    status_data = fetch_all(
        conn,
        """
        SELECT status, COUNT(*) as count
        FROM "Order"
        WHERE rtr_id = ?
        GROUP BY status
        ORDER BY count DESC
        """,
        (rtr_id,),
    )

    status_labels = [s[0] for s in status_data] if status_data else []
    status_counts = [s[1] for s in status_data] if status_data else []

    # Get top menu items from order details JSON
    # Since items are in JSON, we'll parse them and count
    orders = fetch_all(
        conn,
        """
        SELECT details FROM "Order"
        WHERE rtr_id = ? AND LOWER(COALESCE(status, '')) NOT IN ('cancelled', 'canceled')
        """,
        (rtr_id,),
    )

    item_frequency = {}
    for order_row in orders:
        if order_row[0]:
            try:
                details = (
                    json.loads(order_row[0]) if isinstance(order_row[0], str) else order_row[0]
                )
                if "items" in details:
                    for item in details["items"]:
                        item_name = item.get("name", "Unknown")
                        item_frequency[item_name] = item_frequency.get(item_name, 0) + item.get(
                            "qty", 1
                        )
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    # Sort by frequency and get top 10
    top_items = sorted(item_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
    item_names = [item[0] for item in top_items]
    item_counts = [item[1] for item in top_items]

    # Orders placed on each of the last 30 days (every day shown, cancelled left out)
    date_labels, date_counts = daily_order_counts(all_orders, date.today(), days=30)

    return render_template(
        "restaurant_analytics.html",
        restaurant_name=restaurant_name,
        restaurant_email=session.get("RestaurantEmail", ""),
        total_orders=total_orders,
        total_revenue=total_revenue,
        avg_order_value=avg_order_value,
        date_labels=date_labels,
        date_counts=date_counts,
        status_labels=status_labels,
        status_counts=status_counts,
        item_names=item_names,
        item_counts=item_counts,
    )
