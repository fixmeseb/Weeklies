"""A customer's orders, as My Orders shows them and as the planner counts them."""

import json
from datetime import date, datetime

from proj2.order_progress import order_progress
from proj2.ordering import status_history
from proj2.plan_rules import SLOT_NAMES
from proj2.sqlQueries import fetch_all


# Orders route
def _order_date(iso_str: str) -> str:
    """Show an order's ISO timestamp as "YYYY-MM-DD HH:MM" (or as stored, if not ISO)."""
    if not iso_str:
        return ""
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str


def _order_for(details_json) -> str:
    """What a planned order is for, e.g. "Sat Nov 21, dinner" ("" for as-soon-as-possible)."""
    try:
        j = json.loads(details_json) if details_json else {}
        if j.get("asap") or not j.get("date"):
            return ""
        day = date.fromisoformat(j["date"])
        meal = SLOT_NAMES.get(int(j.get("meal") or 3), "dinner").lower()
    except (TypeError, ValueError, KeyError, AttributeError):
        return ""
    return f"{day.strftime('%a %b')} {day.day}, {meal}"


def _meal_at(hour: int) -> int:
    """The meal slot an order placed at this hour stands for (1 breakfast, 2 lunch, 3 dinner)."""
    return 1 if hour < 11 else 2 if hour < 16 else 3


def order_meals(conn, usr_id) -> list:
    """
    What the user ate from their orders, as plan entries for the planner's lookback.
    Args:
        conn: Open database connection.
        usr_id (int): The customer.
    Returns:
        list[tuple]: (date, itm_id, meal) per ordered item, skipping cancelled orders. An
            order placed from the plan carries its date and meal; any other order uses the
            day and hour it was placed.
    """
    rows = fetch_all(
        conn,
        'SELECT details, status FROM "Order" WHERE usr_id = ?',
        (usr_id,),
    )
    meals = []
    for details, status in rows:
        if (status or "").strip().lower() == "cancelled" or not details:
            continue
        try:
            j = json.loads(details)
            day, meal = j.get("date"), j.get("meal")
            if not (day and meal):
                placed = datetime.fromisoformat(j.get("placed_at") or j.get("time"))
                day, meal = placed.date().isoformat(), _meal_at(placed.hour)
            day, meal = date.fromisoformat(str(day)).isoformat(), int(meal)
            items = [int(item["itm_id"]) for item in j.get("items") or []]
        except (TypeError, ValueError, KeyError, AttributeError):
            continue  # an order we cannot place in time tells the planner nothing
        meals.extend((day, itm_id, meal) for itm_id in items)
    return meals


def user_orders(conn, usr_id):
    """
    The user's orders, newest first, as the My Orders page shows them.
    Args:
        conn: Open database connection.
        usr_id (int): The customer.
    Returns:
        list[dict]: id, date, status, progress, restaurant, total and has_review per order.
    """
    rows = fetch_all(
        conn,
        """
        SELECT o.ord_id, o.details, o.status, r.name,
               EXISTS (SELECT 1 FROM "Review" v WHERE v.ord_id = o.ord_id)
        FROM "Order" o
        JOIN "Restaurant" r ON o.rtr_id = r.rtr_id
        WHERE o.usr_id = ?
        ORDER BY o.ord_id DESC
        """,
        (usr_id,),
    )
    orders = []
    for ord_id, details, status, r_name, has_review in rows:
        placed = ""
        total = ""
        if details:
            try:
                j = json.loads(details)
                placed = _order_date(j.get("placed_at") or j.get("time"))
                charges = j.get("charges") or {}
                total_val = (
                    charges.get("total") or charges.get("grand_total") or charges.get("amount")
                )
                if total_val is not None:
                    total = f"${float(total_val):.2f}"
            except Exception:
                pass
        orders.append(
            {
                "id": ord_id,
                "date": placed,
                "status": status or "",
                "status_raw": status,
                "restaurant": r_name,
                "total": total,
                "has_review": bool(has_review),
                "for": _order_for(details),
            }
        )
    history = status_history(conn, [o["id"] for o in orders])
    for o in orders:
        o["progress"] = order_progress(o.pop("status_raw"), history.get(o["id"]))
    return orders
