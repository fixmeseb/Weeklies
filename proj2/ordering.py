"""
Placing orders, recording their status changes, and summing them up for analytics.

An order is checked against the same facts the planner and meal swap rely on: every item
must exist, be in stock, come from one restaurant that is taking orders and is open when
the meal is due, and be free of the allergens on the customer's account (whatever the
request says). A delivery needs an address on the account. Nothing is written unless the
whole order passes.

An order is either for a planned meal (a date and meal number: it is due at the user's
time for that meal on that day) or "as soon as possible" (due now, and counted as the
meal that time of day belongs to).
"""

import datetime
import json

from proj2 import meal_times
from proj2.allergens import allergen_conflicts
from proj2.plan_rules import is_restaurant_open
from proj2.sqlQueries import execute_query, fetch_all

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

## The statuses an order moves through, and the side exit
LIFECYCLE = ["Ordered", "Accepted", "Preparing", "Ready", "Delivered"]
CANCELLED = "Cancelled"

MAX_QTY = 50


class OrderError(ValueError):
    """An order that cannot be placed; code and status are what the JSON response carries."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ---------------------------------------------------------------- addresses


def delivery_address(user) -> str:
    """
    The account's delivery address on one line, or "" if it has no street address

    Args:
        user (Mapping): A "User" row with address, city, state and zip (any may be missing)
    """

    def get(key):
        try:
            return (user[key] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""

    street = get("address")
    if not street:
        return ""
    place = " ".join(part for part in (get("state"), get("zip")) if part)
    return ", ".join(part for part in (street, get("city"), place) if part)


# ---------------------------------------------------------------- checks


def _hours_readable(hours) -> bool:
    try:
        return isinstance(json.loads(hours), dict)
    except (TypeError, ValueError):
        return False


def item_order_rejection(item, user_allergies, weekday: str, hhmm: int):
    """
    Checks whether one menu item may be ordered for a meal due at weekday/hhmm

    Unlike the planner, a restaurant whose hours are not recorded in the readable form is
    not treated as closed: the customer can see when it says it is open, and the order
    still has to be accepted by the restaurant. Diets are not checked either; they decide
    what the planner suggests, not what a customer may buy.

    Returns:
        Tuple[str, str] | None: (error_code, message), or None if the item may be ordered
    """
    if item is None:
        return "item_not_found", "That menu item does not exist."
    if item["instock"] is not None and not item["instock"]:
        return "out_of_stock", f"{item['name']} is currently out of stock."
    if (item["restaurant_status"] or "").strip().lower() != "open":
        return "restaurant_unavailable", f"{item['restaurant_name']} is not taking orders."
    if _hours_readable(item["hours"]) and not is_restaurant_open(item["hours"], weekday, hhmm):
        when = meal_times.as_display(hhmm)
        return (
            "restaurant_closed",
            f"{item['restaurant_name']} is closed at {when} on {weekday}.",
        )
    conflicts = allergen_conflicts(item["allergens"], user_allergies)
    if conflicts:
        return (
            "allergen",
            f"{item['name']} contains your allergens: {', '.join(sorted(conflicts))}.",
        )
    return None


def _load_items(conn, itm_ids):
    if not itm_ids:
        return {}
    marks = ",".join("?" * len(itm_ids))
    rows = fetch_all(
        conn,
        f"""
        SELECT m.itm_id, m.rtr_id, m.name, m.price, m.instock, m.allergens,
               r.name, r.status, r.hours
        FROM "MenuItem" m JOIN "Restaurant" r ON r.rtr_id = m.rtr_id
        WHERE m.itm_id IN ({marks})
        """,
        tuple(itm_ids),
    )
    return {
        int(r[0]): {
            "itm_id": int(r[0]),
            "rtr_id": int(r[1]),
            "name": r[2],
            "price_cents": int(r[3] or 0),
            "instock": r[4],
            "allergens": r[5],
            "restaurant_name": r[6],
            "restaurant_status": r[7],
            "hours": r[8],
        }
        for r in rows
    }


def _money(value) -> float:
    return round(float(value) + 1e-9, 2)


def parse_tip(value) -> float:
    """A tip in dollars: missing means 0; negative or non-numbers are refused."""
    if value in (None, ""):
        return 0.0
    try:
        tip = float(value)
    except (TypeError, ValueError):
        raise OrderError("bad_tip", "The tip must be a number of dollars.")
    if tip != tip or tip < 0:  # NaN or negative
        raise OrderError("bad_tip", "The tip cannot be negative.")
    if tip > 1000:
        raise OrderError("bad_tip", "That tip is larger than we can take.")
    return _money(tip)


def when_due(times: dict, day=None, meal=None, now=None):
    """
    When an order is due, as (date, meal, weekday, hhmm, asap)

    Args:
        times (dict): The customer's meal times (proj2.meal_times.times_for)
        day (str | None): The planned date, YYYY-MM-DD; None for "as soon as possible"
        meal (int | None): The planned meal; required with a date
        now (datetime | None): The current time (for tests)

    Raises:
        OrderError: for a malformed date or meal, or a date in the past
    """
    now = now or datetime.datetime.now()
    if day in (None, ""):
        hhmm = now.hour * 100 + now.minute
        return (
            now.date().isoformat(),
            meal_times.meal_at(times, hhmm),
            DAYS_OF_WEEK[now.weekday()],
            hhmm,
            True,
        )
    try:
        planned = datetime.date.fromisoformat(str(day))
    except ValueError:
        raise OrderError("bad_date", "The meal date must be in YYYY-MM-DD format.")
    try:
        meal = int(meal)
    except (TypeError, ValueError):
        meal = 0
    if meal not in (1, 2, 3):
        raise OrderError("bad_meal", "The meal must be 1 (breakfast), 2 (lunch) or 3 (dinner).")
    if planned < now.date():
        raise OrderError("past_date", "That meal's day has already passed.")
    return planned.isoformat(), meal, DAYS_OF_WEEK[planned.weekday()], times[meal], False


def build_order(conn, user, request, charges_for, now=None):
    """
    Checks one order request and builds what to store, without writing anything

    Args:
        conn: Open database connection
        user (Mapping): The customer's "User" row (usr_id, allergies, address fields,
            meal-time columns)
        request (dict): restaurant_id, items [{itm_id, qty, notes}], delivery_type, tip,
            eta_minutes, and optionally date and meal (a planned meal)
        charges_for (Callable): (subtotal, delivery_type, tip) -> charges dict
        now (datetime | None): The current time (for tests)

    Returns:
        Tuple[int, dict]: (rtr_id, the order's details JSON object)

    Raises:
        OrderError: the first reason the order cannot be placed
    """
    try:
        rtr_id = int(request.get("restaurant_id") or 0)
    except (TypeError, ValueError):
        rtr_id = 0
    lines = request.get("items") or []
    if rtr_id <= 0 or not isinstance(lines, list) or not lines:
        raise OrderError("invalid_input", "Choose a restaurant and at least one dish.")

    delivery_type = str(request.get("delivery_type") or "delivery").lower()
    if delivery_type not in ("delivery", "pickup"):
        delivery_type = "delivery"
    tip = parse_tip(request.get("tip"))
    try:
        eta_minutes = max(0, int(request.get("eta_minutes") or 40))
    except (TypeError, ValueError):
        eta_minutes = 40

    parsed = []
    for line in lines:
        try:
            itm_id = int((line or {}).get("itm_id") or 0)
            qty = int((line or {}).get("qty") or 1)
        except (TypeError, ValueError, AttributeError):
            raise OrderError("invalid_input", "Every dish needs an item and a quantity.")
        if itm_id <= 0:
            raise OrderError("no_items", "Every dish needs an item.")
        qty = max(qty, 1)  # use-cases.md UC10 2a: a quantity that is not positive counts as one
        if qty > MAX_QTY:
            raise OrderError("bad_qty", f"At most {MAX_QTY} of one dish per order.")
        parsed.append((itm_id, qty, str((line or {}).get("notes") or "").strip()))

    items = _load_items(conn, sorted({itm_id for itm_id, _, _ in parsed}))
    if not items:
        raise OrderError("items_not_found", "None of those menu items exist.", 404)
    for itm_id, _, _ in parsed:
        if itm_id not in items:
            raise OrderError(f"item_{itm_id}_not_found", "That menu item does not exist.", 404)
        if items[itm_id]["rtr_id"] != rtr_id:
            raise OrderError("mixed_restaurants", "An order can only be from one restaurant.")

    times = meal_times.times_for(user)
    day, meal, weekday, hhmm, asap = when_due(times, request.get("date"), request.get("meal"), now)
    for itm_id, _, _ in parsed:
        rejection = item_order_rejection(items[itm_id], user["allergies"], weekday, hhmm)
        if rejection:
            raise OrderError(rejection[0], rejection[1], 409)

    deliver_to = delivery_address(user)
    if delivery_type == "delivery" and not deliver_to:
        raise OrderError(
            "no_address",
            "Add a delivery address on your profile, or choose pickup.",
        )

    detail_items, subtotal = [], 0.0
    for itm_id, qty, notes in parsed:
        unit = _money(items[itm_id]["price_cents"] / 100)
        line_total = _money(unit * qty)
        subtotal = _money(subtotal + line_total)
        detail_items.append(
            {
                "itm_id": itm_id,
                "name": items[itm_id]["name"],
                "qty": qty,
                "unit_price": unit,
                "line_total": line_total,
                **({"notes": notes} if notes else {}),
            }
        )
    placed = (now or datetime.datetime.now()).astimezone()
    details = {
        "placed_at": placed.isoformat(),
        "restaurant_id": rtr_id,
        "items": detail_items,
        "charges": {"subtotal": subtotal, **charges_for(subtotal, delivery_type, tip), "tip": tip},
        "delivery_type": delivery_type,
        "eta_minutes": eta_minutes,
        "date": day,
        "meal": meal,
        "due_at": f"{day}T{meal_times.as_text(hhmm)}",
        "asap": asap,
    }
    if delivery_type == "delivery":
        details["deliver_to"] = deliver_to
    return rtr_id, details


def insert_order(conn, usr_id, rtr_id, details) -> int:
    """Writes a built order with status Ordered and starts its status history."""
    ord_id = execute_query(
        conn,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (rtr_id, usr_id, json.dumps(details), "Ordered"),
    ).lastrowid
    _record_history(conn, ord_id, "Ordered", details.get("placed_at"))
    return ord_id


# ---------------------------------------------------------------- status history


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _record_history(conn, ord_id, status, at=None):
    execute_query(
        conn,
        'INSERT INTO "OrderStatus" (ord_id, status, at) VALUES (?, ?, ?)',
        (ord_id, status, at or _now_iso()),
    )


def set_status(conn, ord_id, status, at=None, only_from=None) -> bool:
    """
    Moves an order to a new status and records when.

    Args:
        only_from (Sequence[str] | None): Move it only if its status is one of these,
            checked by the same statement that changes it

    Returns:
        bool: True if the order was moved
    """
    sql, params = 'UPDATE "Order" SET status = ? WHERE ord_id = ?', (status, ord_id)
    if only_from is not None:
        sql += f" AND status IN ({','.join('?' * len(only_from))})"
        params += tuple(only_from)
    if execute_query(conn, sql, params).rowcount != 1:
        return False
    _record_history(conn, ord_id, status, at)
    return True


def status_history(conn, ord_ids) -> dict:
    """
    Every recorded status change for some orders

    Returns:
        dict: ord_id -> [(status, at ISO string)] oldest first
    """
    ord_ids = [int(i) for i in ord_ids]
    if not ord_ids:
        return {}
    marks = ",".join("?" * len(ord_ids))
    rows = fetch_all(
        conn,
        f'SELECT ord_id, status, at FROM "OrderStatus" WHERE ord_id IN ({marks}) '
        "ORDER BY ord_id, ost_id",
        tuple(ord_ids),
    )
    history = {}
    for ord_id, status, at in rows:
        history.setdefault(int(ord_id), []).append((status, at))
    return history


# ---------------------------------------------------------------- analytics


def _details(raw):
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _cents(value) -> int:
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def restaurant_metrics(orders) -> dict:
    """
    Sums up a restaurant's orders

    Cancelled orders are counted on their own and left out of everything else: they
    earned nothing, so they belong in neither revenue nor the average order.

    Args:
        orders (Iterable[Tuple]): (status, usr_id, details) per order

    Returns:
        dict: total_orders (not cancelled), cancelled, total_revenue_cents,
            avg_order_value_cents, total_customers (distinct), completed (delivered),
            order_completion_rate (delivered / all orders), most_popular_item_id
    """
    total = cancelled = completed = revenue = 0
    customers, counts = set(), {}
    for status, usr_id, raw in orders:
        key = (status or "").strip().lower()
        if key in ("cancelled", "canceled"):
            cancelled += 1
            continue
        total += 1
        if key in ("delivered", "completed"):
            completed += 1
        if usr_id is not None:
            customers.add(usr_id)
        details = _details(raw)
        revenue += _cents((details.get("charges") or {}).get("total"))
        for item in details.get("items") or []:
            itm_id = item.get("itm_id") if isinstance(item, dict) else None
            if itm_id:
                counts[itm_id] = counts.get(itm_id, 0) + int(item.get("qty") or 1)
    everything = total + cancelled
    popular = max(sorted(counts), key=lambda i: counts[i]) if counts else None
    return {
        "total_orders": total,
        "cancelled": cancelled,
        "total_revenue_cents": revenue,
        "avg_order_value_cents": revenue // total if total else 0,
        "total_customers": len(customers),
        "completed": completed,
        "order_completion_rate": completed / everything if everything else 0.0,
        "most_popular_item_id": popular,
    }


def daily_order_counts(orders, today, days=30):
    """
    Orders placed on each of the last `days` days (cancelled ones left out)

    Args:
        orders (Iterable[Tuple]): (status, usr_id, details) per order
        today (date): The last day to show

    Returns:
        Tuple[list, list]: (dates as YYYY-MM-DD, counts), oldest first, every day present
    """
    first = today - datetime.timedelta(days=days - 1)
    counts = {(first + datetime.timedelta(days=i)).isoformat(): 0 for i in range(days)}
    for status, _usr_id, raw in orders:
        if (status or "").strip().lower() in ("cancelled", "canceled"):
            continue
        placed = _details(raw).get("placed_at") or ""
        day = str(placed)[:10]
        if day in counts:
            counts[day] += 1
    return list(counts), list(counts.values())
