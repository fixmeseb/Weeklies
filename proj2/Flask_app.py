import os
import re
import logging
import secrets
import argparse
import math
import json
import calendar
from io import BytesIO
from flask import jsonify
from sqlite3 import IntegrityError
from datetime import timedelta, date, datetime
from functools import wraps
from proj2 import config
from proj2.pdf_receipt import generate_order_receipt_pdf
from proj2 import variety
from proj2.hours import format_hours
from proj2.menu_generation import MenuGenerator
from proj2.plan_rules import SLOT_NAMES
from proj2.meal_budget import (
    BudgetExceededError, parse_weekly_cap, plan_entries, week_start, weekly_item_totals
)
from proj2.order_progress import order_progress
from proj2.dietary import with_account_allergies, with_account_diets
from proj2.meal_swap import (
    SlotNotFoundError,
    find_slot_item,
    list_swap_options,
    load_swap_item,
    rank_swap_options,
    replace_menu_slot,
    slot_weekday_and_time,
    swap_rejection,
)
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, render_template, url_for, redirect, request, session, send_file, abort

# Use ONLY these helpers for DB access: get_db() for the connection, then the
# sqlQueries helpers (which raise on SQL errors) to run statements.
from proj2.db import DatabaseNotInitialisedError, connect, get_db, init_app as init_db_support
from proj2.sqlQueries import fetch_one, fetch_all, execute_query

SECRET_KEY_ENV = "WEEKLIES_SECRET_KEY"


def _read_key_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _write_key_file(path, key) -> bool:
    """Create the key file readable only by the owner. Returns False if it can't be written."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key + "\n")
        return True
    except OSError:
        return False


def load_secret_key(environ=None, key_file=None) -> str:
    """
    Return the session signing key.
    Args:
        environ: Mapping to read from (defaults to os.environ; injectable for tests).
        key_file: Optional git-ignored file used when the env var is unset. The first
            run generates a key and saves it there; later runs and auto-reloads reuse
            it, so local logins survive restarts with no setup.
    Returns:
        str: WEEKLIES_SECRET_KEY if set; else the saved key; else a new random key.
    """
    environ = os.environ if environ is None else environ
    key = (environ.get(SECRET_KEY_ENV) or "").strip()
    if key:
        return key
    # A key committed to the repo lets anyone forge session cookies, so never
    # fall back to a fixed string.
    log = logging.getLogger(__name__)
    if key_file:
        saved = _read_key_file(key_file)
        if saved:
            return saved
        key = secrets.token_hex(32)
        if _write_key_file(key_file, key):
            log.warning("%s is not set; generated a local key in %s.", SECRET_KEY_ENV, key_file)
            return key
    log.warning(
        "%s is not set; using a random key, so logins reset when the server restarts.",
        SECRET_KEY_ENV,
    )
    return key or secrets.token_hex(32)


# Anchored to this file: Flask's instance_path depends on how the module was imported
# (it differed between running from the repo root and from proj2/).
SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "secret_key")

app = Flask(__name__)
# Restaurant hours for display: {{ r.hours | hours_display }} (see proj2/hours.py)
app.add_template_filter(format_hours, "hours_display")
app.config["SECRET_KEY"] = load_secret_key(key_file=SECRET_KEY_FILE)

init_db_support(app)  # app.config["DATABASE"], connection teardown, `flask init-db` etc.


def db_path() -> str:
    """Path of the configured database, for code that opens its own connection."""
    return app.config["DATABASE"]


@app.errorhandler(DatabaseNotInitialisedError)
def _database_not_initialised(exc):
    app.logger.error("%s", exc)
    return (
        "<h1>Database not initialised</h1><p>The server's database is missing or empty. "
        "Run <code>flask --app proj2.Flask_app init-db</code> and "
        "<code>flask --app proj2.Flask_app seed</code>.</p>",
        500,
    )


@app.errorhandler(500)
def _internal_error(exc):
    original = getattr(exc, "original_exception", None) or exc
    app.logger.error("Unhandled error on %s %s", request.method, request.path, exc_info=original)
    return "<h1>Internal Server Error</h1><p>Something went wrong. It has been logged.</p>", 500

# ---------------------- Helpers ----------------------


def _money(x: float) -> float:
    """
    Safely round a numeric value to two decimal places.
    Args:
        x (float): The numeric amount to round.
    Returns:
        float: The amount rounded to two decimals, or 0.0 on failure.
    """
    try:
        return round(float(x) + 1e-9, 2)
    except Exception:
        return 0.0


def _order_charges(subtotal: float, delivery_type: str, tip: float) -> dict:
    """
    Tax, fees and total for an order, from the fee schedule in proj2/config.py.
    Args:
        subtotal (float): Sum of line totals in dollars.
        delivery_type (str): "delivery" or "pickup"; only delivery pays the delivery fee.
        tip (float): Tip in dollars.
    Returns:
        dict: tax, delivery_fee, service_fee and total, each rounded to cents.
    """
    tax = _money(subtotal * config.TAX_RATE)
    delivery_fee = config.DELIVERY_FEE if delivery_type == "delivery" else 0.00
    service_fee = config.SERVICE_FEE
    total = _money(subtotal + tax + delivery_fee + service_fee + tip)
    return {"tax": tax, "delivery_fee": delivery_fee, "service_fee": service_fee, "total": total}


def _cents_to_dollars(cents) -> float:
    """
    Convert an amount in cents to dollars with two-decimal precision.
    Args:
        cents (int | float | None): The value in cents to convert.
    Returns:
        float: The dollar value rounded to two decimals (0.0 on failure).
    """
    try:
        return _money((cents or 0) / 100.0)
    except Exception:
        return 0.0


def parse_generated_menu(gen_str):
    """
    Parse a serialized generated-menu string into a date-indexed structure.
    Args:
        gen_str (str): A string like "[YYYY-MM-DD,ID,(meal)]..." where meal is 1|2|3 (optional).
    Returns:
        dict: Mapping 'YYYY-MM-DD' -> [{'itm_id': int, 'meal': int}, ...].
    """
    if not gen_str:
        return {}

    # date, id, optional meal (1,2,3)
    pairs = re.findall(r"\[\s*(\d{4}-\d{2}-\d{2})\s*,\s*([0-9]+)\s*(?:,\s*([123])\s*)?\]", gen_str)
    out = {}
    for d, mid, meal in pairs:
        try:
            itm_id = int(mid)
            meal_i = int(meal) if meal else 3  # default to Dinner for legacy entries
            out.setdefault(d, []).append({"itm_id": itm_id, "meal": meal_i})
        except ValueError:
            continue
    return out


def record_analytics_snapshot(rtr_id):
    """
    Record an analytics snapshot for a restaurant by calculating current order metrics.

    This function:
    1. Queries all orders for the restaurant
    2. Calculates total orders, revenue, average order value, and completion rate
    3. Identifies the most popular menu item
    4. Inserts a new snapshot record in the Analytics table

    Args:
        rtr_id (int): The restaurant ID to record analytics for.

    Returns:
        bool: True if snapshot was recorded successfully, False otherwise.
    """
    conn = get_db()

    try:
        # Get all orders for this restaurant
        orders = fetch_all(
            conn,
            """
            SELECT ord_id, status, details
            FROM "Order"
            WHERE rtr_id = ?
            """,
            (rtr_id,),
        )

        if not orders:
            # No orders yet, create a blank snapshot
            total_orders = 0
            total_revenue_cents = 0
            avg_order_value_cents = 0
            total_customers = 0
            order_completion_rate = 0.0
            most_popular_item_id = None
        else:
            total_orders = len(orders)
            total_revenue_cents = 0
            unique_customers = set()
            completed_orders = 0
            item_counts = {}

            # Process each order
            for ord_id, status, details_json in orders:
                # Track completion rate
                if status and status.lower() in ["completed", "delivered"]:
                    completed_orders += 1

                # Parse details JSON
                try:
                    if details_json:
                        details = (
                            json.loads(details_json)
                            if isinstance(details_json, str)
                            else details_json
                        )

                        # Extract revenue
                        if "charges" in details and "total" in details["charges"]:
                            total_cents = int(details["charges"]["total"] * 100)
                            total_revenue_cents += total_cents

                        # Track items for popularity
                        if "items" in details:
                            for item in details["items"]:
                                itm_id = item.get("itm_id")
                                if itm_id:
                                    item_counts[itm_id] = item_counts.get(itm_id, 0) + 1
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

                # Note: We don't have usr_id in the Order table currently
                # So we can't track unique_customers reliably
                # This would need to be added to the Order schema if needed

            # Calculate metrics
            avg_order_value_cents = total_revenue_cents // total_orders if total_orders > 0 else 0
            total_customers = total_orders  # Use total orders as proxy since usr_id not available
            order_completion_rate = (completed_orders / total_orders) if total_orders > 0 else 0.0

            # Find most popular item
            most_popular_item_id = None
            if item_counts:
                most_popular_item_id = max(item_counts.items(), key=lambda x: x[1])[0]

        # Record the snapshot
        snapshot_date = date.today().isoformat()
        created_at = datetime.now().isoformat()

        execute_query(
            conn,
            """
            INSERT INTO Analytics
            (rtr_id, snapshot_date, total_orders, total_revenue_cents, avg_order_value_cents,
             total_customers, most_popular_item_id, order_completion_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rtr_id,
                snapshot_date,
                total_orders,
                total_revenue_cents,
                avg_order_value_cents,
                total_customers,
                most_popular_item_id,
                order_completion_rate,
                created_at,
            ),
        )

        return True
    except Exception as e:
        print(f"Error recording analytics snapshot: {e}")
        import traceback

        traceback.print_exc()
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


def palette_for_item_ids(item_ids):
    """
    Generate a deterministic, pleasant color palette for item IDs.
    Args:
        item_ids (Iterable[int]): The menu item IDs to colorize.
    Returns:
        dict: Mapping itm_id -> hex color string (e.g., '#a1b2c3').
    """
    import colorsys

    def hsl_to_hex(h, s, l):
        r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    palette = {}
    for iid in item_ids:
        seed = (iid * 9301 + 49297) % 233280
        hue = seed % 360
        palette[iid] = hsl_to_hex(hue, 65, 52)
    return palette


def fetch_menu_items_by_ids(ids):
    """
    Load menu items (and their restaurant metadata) for given item IDs.
    Args:
        ids (Iterable[int]): The item IDs to fetch.
    Returns:
        dict: Mapping itm_id -> dict with fields like name, price, calories, allergens,
            and restaurant info (name, address, hours, phone).
    """
    if not ids:
        return {}
    conn = get_db()
    qmarks = ",".join(["?"] * len(ids))
    sql = f"""
      SELECT m.itm_id, m.rtr_id, m.name, m.description, m.price, m.calories,
             m.allergens, r.name AS restaurant_name, r.address, r.city, r.state, r.zip,
             r.hours, r.phone
      FROM MenuItem m
      JOIN Restaurant r ON r.rtr_id = m.rtr_id
      WHERE m.itm_id IN ({qmarks})
    """
    rows = fetch_all(conn, sql, tuple(ids))

    def _addr(a, c, s, z) -> str:
        parts_raw = [a, c, s, z]
        parts = []
        for p in parts_raw:
            if p is None:
                continue
            sp = str(p).strip()
            if sp:
                parts.append(sp)
        return ", ".join(parts)

    out = {}
    for r in rows:
        out[r[0]] = {
            "itm_id": r[0],
            "rtr_id": r[1],
            "name": r[2],
            "description": r[3],
            "price": r[4],
            "calories": r[5],
            "allergens": r[6],
            "restaurant_name": r[7],
            "restaurant_address": _addr(r[8], r[9], r[10], r[11]),
            "restaurant_hours": r[12] or "",
            "restaurant_phone": r[13] or "",
        }
    return out


def build_calendar_cells(gen_map, year, month, items_by_id):
    """
    Build month-view calendar cells enriched with menu items per day.
    Args:
        gen_map (dict): Mapping 'YYYY-MM-DD' -> [{'itm_id': int, 'meal': 1|2|3}, ...].
        year (int): The calendar year.
        month (int): The calendar month (1–12).
        items_by_id (dict): Mapping itm_id -> item detail dict from DB.
    Returns:
        list: A flat list of calendar cell dicts with day number and a 'meals' list.
    """

    def meal_sort_key(e):
        # Breakfast(1) first, then Lunch(2), then Dinner(3)
        return e.get("meal", 3)

    palette = palette_for_item_ids(items_by_id.keys())
    cal = calendar.Calendar(firstweekday=6)  # Sunday start
    cells = []

    for week in cal.monthdayscalendar(year, month):
        for d in week:
            if d == 0:
                cells.append({"day": 0})
                continue

            iso = f"{year:04d}-{month:02d}-{d:02d}"
            entries = sorted(gen_map.get(iso, []), key=meal_sort_key)

            meals = []
            for e in entries:
                itm = items_by_id.get(e["itm_id"])
                if not itm:
                    continue
                meals.append(
                    {
                        "meal": e.get("meal", 3),
                        "item": itm,
                        "color": palette.get(itm["itm_id"], "#7aa2f7"),
                    }
                )

            cells.append({"day": d, "meals": meals})

    return cells


## Banner text for /?swap_error=<code> after a form-based swap
SWAP_ERROR_MESSAGES = {
    "invalid_slot": "That meal slot is not valid.",
    "invalid_item": "Choose an item to swap in.",
    "slot_not_found": "There is no planned meal in that slot.",
    "same_item": "That item is already planned for this slot.",
    "item_not_found": "That menu item does not exist.",
    "out_of_stock": "That item is out of stock.",
    "restaurant_unavailable": "That restaurant is not currently taking orders.",
    "restaurant_closed": "That restaurant is closed at that meal time.",
    "allergen": "That item contains one of your allergens.",
}


# ---------------------- Routes ----------------------


# Home route (supports /<year>/<month> for nav)
def describe_similar_pair(pair, items_by_id) -> str:
    """One similar pair from proj2.variety as a sentence for the calendar."""

    def label(entry):
        day = date.fromisoformat(entry["date"])
        name = items_by_id.get(entry["itm_id"], {}).get("name", f"item {entry['itm_id']}")
        return f"{name} ({day.strftime('%a')} {SLOT_NAMES.get(entry['meal'], 'meal')})"

    shared = "; ".join(pair["shared"]) or "similar tags"
    return f"{label(pair['a'])} and {label(pair['b'])}: {shared}"


def calendar_week_variety(conn, gen_str, year, month, items_by_id):
    """
    Variety of each Monday–Sunday week shown in a calendar month (see proj2.variety)

    Returns:
        dict: week start -> {"score": percent or None, "similar": [sentence, ...]}
    """
    prefix = f"{year:04d}-{month:02d}-"
    entries = list(plan_entries(gen_str))
    weeks = sorted({week_start(day) for day, _, _ in entries if day.startswith(prefix)})
    if not weeks:
        return {}
    catalog = variety.catalog_rows(conn)
    out = {}
    for week in weeks:
        report = variety.plan_variety(
            [e for e in entries if week_start(e[0]) == week], catalog
        )
        out[week] = {
            "score": None if report.score is None else round(report.score * 100),
            "similar": [describe_similar_pair(p, items_by_id) for p in report.similar_pairs(2)],
        }
    return out


@app.route("/", defaults={"year": None, "month": None})
@app.route("/<int:year>/<int:month>")
def index(year, month):
    """
    Render the calendar home view for the current or specified month.
    Args:
        year (int | None): Optional year path parameter.
        month (int | None): Optional month path parameter (1–12).
    Returns:
        Response: HTML page showing the monthly plan and today's meals (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("login"))

    today = date.today()
    if not year or not month:
        year, month = today.year, today.month

    # Load current user's generated_menu
    conn = get_db()
    user = fetch_one(
        conn, 'SELECT generated_menu FROM "User" WHERE email = ?', (session.get("Email"),)
    )

    if not user:
        return redirect(url_for("logout"))

    gen_str = user["generated_menu"] or ""
    gen_map = parse_generated_menu(gen_str)

    # All item ids referenced (for the whole plan)
    all_item_ids = sorted({e["itm_id"] for entries in gen_map.values() for e in entries})
    items_by_id = fetch_menu_items_by_ids(all_item_ids)

    # Show item totals for weeks represented in this calendar month.
    item_totals = {}
    item_total_error = None
    try:
        visible_weeks = sorted({
            week_start(day) for day in gen_map
            if day.startswith(f"{year:04d}-{month:02d}-")
        })
        visible_week_item_ids = {
            item_id
            for day, item_id, _ in plan_entries(gen_str)
            if week_start(day) in visible_weeks
        }
        totals_by_item = fetch_menu_items_by_ids(sorted(visible_week_item_ids))
        item_totals = weekly_item_totals(
            gen_str,
            {item: data["price"] for item, data in totals_by_item.items()},
            visible_weeks,
        )
    except ValueError:
        item_total_error = "Item totals are unavailable because a planned meal or its price is missing."

    weekly_variety = calendar_week_variety(conn, gen_str, year, month, items_by_id)

    # Build cells for the month
    cells = build_calendar_cells(gen_map, year, month, items_by_id)

    # Build "today_menu" (Breakfast, Lunch, Dinner if present)
    today_iso = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"
    today_entries = sorted(gen_map.get(today_iso, []), key=lambda e: e.get("meal", 3))
    today_menu = []
    for e in today_entries:
        item = items_by_id.get(e["itm_id"])
        if item:
            # expose 'meal' and the full item dict to the template
            today_menu.append(type("TodayEntry", (), {"meal": e["meal"], "item": item}))

    # prev/next month nav (unchanged)
    cur = date(year, month, 15)
    prev_m = (cur.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_m = (cur.replace(day=28) + timedelta(days=10)).replace(day=1)

    swap_notice = None
    if request.args.get("swapped"):
        swap_notice = ("success", "Meal swapped. The rest of your plan is unchanged.")
    elif request.args.get("swap_error"):
        swap_notice = ("danger", SWAP_ERROR_MESSAGES.get(
            request.args.get("swap_error"), "That meal could not be swapped."
        ))

    return render_template(
        "index.html",
        swap_notice=swap_notice,
        username=session["Username"],
        month_name=calendar.month_name[month],
        month=month,
        year=year,
        prev_month=prev_m.month,
        prev_year=prev_m.year,
        next_month=next_m.month,
        next_year=next_m.year,
        calendar_cells=cells,
        today_year=today.year,
        today_month=today.month,
        today_day=today.day,
        today_menu=today_menu,
        weekly_item_totals=item_totals,
        item_total_error=item_total_error,
        weekly_variety=weekly_variety,
    )


# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Display the login form (GET) and authenticate user credentials (POST).
    Args:
        None
    Returns:
        Response: Renders login page, or redirects to home on successful login.
    """
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        user = fetch_one(
            conn,
            'SELECT usr_id, first_name, last_name, phone, password_HS, wallet, preferences, '
            'allergies, generated_menu FROM "User" WHERE email = ?',
            (email,),
        )

        if user and check_password_hash(user["password_HS"], password):
            session["usr_id"] = user["usr_id"]
            session["Fname"] = user["first_name"]
            session["Lname"] = user["last_name"]
            session["Username"] = user["first_name"] + " " + user["last_name"]
            session["Email"] = email
            session["Phone"] = user["phone"]
            session["Wallet"] = user["wallet"]
            session["Preferences"] = user["preferences"] or ""
            session["Allergies"] = user["allergies"] or ""
            session["GeneratedMenu"] = user["generated_menu"] or ""
            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=30)
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


# Logout route (single, no duplicates)
@app.route("/logout")
def logout():
    """
    Clear the user session and redirect to the login page.
    Args:
        None
    Returns:
        Response: Redirect to the login route.
    """
    for k in [
        "Username",
        "Fname",
        "Lname",
        "Email",
        "Phone",
        "Wallet",
        "Preferences",
        "Allergies",
        "GeneratedMenu",
    ]:
        session.pop(k, None)
    return redirect(url_for("login"))


# ---------------------- Restaurant Authentication ----------------------


def restaurant_required(f):
    """
    Decorator to protect restaurant-only routes.
    Redirects to restaurant login if not authenticated as a restaurant.
    Also adds cache-control headers to prevent browser caching.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("restaurant_mode") or not session.get("rtr_id"):
            return redirect(url_for("restaurant_login"))

        # Normalize Flask return values, including (body, status, headers) tuples.
        from flask import make_response

        response = make_response(f(*args, **kwargs))

        # Add cache-control headers to prevent browser caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    return decorated_function


@app.route("/restaurant/login", methods=["GET", "POST"])
def restaurant_login():
    """
    Restaurant owner login page and authentication handler.
    Args:
        None
    Returns:
        Response: Renders restaurant login page or redirects to dashboard on success.
    """
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        restaurant = fetch_one(
            conn,
            "SELECT rtr_id, name, email, password_HS FROM Restaurant WHERE email = ?",
            (email,),
        )

        if restaurant and check_password_hash(restaurant[3], password):
            # Set restaurant session
            session["restaurant_mode"] = True
            session["rtr_id"] = restaurant[0]
            session["RestaurantName"] = restaurant[1]
            session["RestaurantEmail"] = email
            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=30)

            return redirect(url_for("restaurant_dashboard"))

        return render_template("restaurant_login.html", error="Invalid credentials")

    return render_template("restaurant_login.html")


@app.route("/restaurant/logout")
def restaurant_logout():
    """
    Clear restaurant session and redirect to restaurant login.
    Args:
        None
    Returns:
        Response: Redirect to restaurant login page.
    """
    session.pop("restaurant_mode", None)
    session.pop("rtr_id", None)
    session.pop("RestaurantName", None)
    session.pop("RestaurantEmail", None)
    return redirect(url_for("restaurant_login"))


@app.route("/restaurant/dashboard")
@restaurant_required
def restaurant_dashboard():
    """
    Main dashboard landing page with module cards.
    Args:
        None
    Returns:
        Response: Renders restaurant dashboard home with quick stats.
    """
    rtr_id = session.get("rtr_id")
    restaurant_name = session.get("RestaurantName", "Restaurant")
    restaurant_email = session.get("RestaurantEmail", "")

    # Get quick stats for dashboard cards
    conn = get_db()
    orders = fetch_all(
        conn,
        """
        SELECT status FROM "Order"
        WHERE rtr_id = ?
    """,
        (rtr_id,),
    )
        
    # Get review stats
    review_stats = fetch_one(
        conn,
        """
        SELECT COUNT(*), AVG(rating)
        FROM "Review"
        WHERE rtr_id = ?
        """,
        (rtr_id,),
    )

    # Calculate status counts for badge
    status_counts = {
        "Ordered": 0,
        "Accepted": 0,
        "Preparing": 0,
        "Ready": 0,
        "Delivered": 0,
        "Cancelled": 0,
    }

    for (status,) in orders:
        if status in status_counts:
            status_counts[status] += 1
    
    # Review stats
    total_reviews = review_stats[0] if review_stats else 0
    average_rating = float(review_stats[1]) if review_stats and review_stats[1] else 0.0

    return render_template(
        "restaurant_dashboard_home.html",
        restaurant_name=restaurant_name,
        restaurant_email=restaurant_email,
        status_counts=status_counts,
        total_reviews=total_reviews,
        average_rating=average_rating,
        rtr_id=rtr_id,
    )


@app.route("/restaurant/orders")
@restaurant_required
def restaurant_orders():
    """
    Order management page showing all orders for the restaurant, grouped by status.
    Args:
        None
    Returns:
        Response: Renders restaurant orders page with all orders.
    """
    rtr_id = session.get("rtr_id")
    restaurant_name = session.get("RestaurantName", "Restaurant")
    restaurant_email = session.get("RestaurantEmail", "")

    conn = get_db()
    # Get all orders for this restaurant
    orders = fetch_all(
        conn,
        """
        SELECT o.ord_id, o.usr_id, o.details, o.status, 
               u.first_name, u.last_name, u.email, u.phone
        FROM "Order" o
        JOIN "User" u ON o.usr_id = u.usr_id
        WHERE o.rtr_id = ?
        ORDER BY o.ord_id DESC
    """,
        (rtr_id,),
    )

    # Group orders by status
    orders_by_status = {
        "Ordered": [],
        "Accepted": [],
        "Preparing": [],
        "Ready": [],
        "Delivered": [],
        "Cancelled": [],
    }

    for order in orders:
        ord_id, usr_id, details_json, status, fname, lname, email, phone = order

        # Parse JSON details
        try:
            details = json.loads(details_json)
        except:
            details = {}

        # Ensure charges has all required keys
        charges = details.get("charges", {})
        if not charges or "total" not in charges:
            # Fallback: calculate from items or use 0
            charges = {
                "subtotal": charges.get("subtotal", 0.0),
                "tax": charges.get("tax", 0.0),
                "delivery_fee": charges.get("delivery_fee", 0.0),
                "service_fee": charges.get("service_fee", 0.0),
                "tip": charges.get("tip", 0.0),
                "total": charges.get("total", 0.0),
            }

        order_obj = {
            "ord_id": ord_id,
            "usr_id": usr_id,
            "status": status,
            "customer_name": f"{fname} {lname}",
            "customer_email": email,
            "customer_phone": phone,
            "placed_at": details.get("placed_at", ""),
            "items": details.get("items", []),
            "charges": charges,
            "delivery_type": details.get("delivery_type", "delivery"),
            "eta_minutes": details.get("eta_minutes", 40),
            "date": details.get("date", ""),
            "meal": details.get("meal", 3),
            "notes": details.get("notes", ""),
        }

        if status in orders_by_status:
            orders_by_status[status].append(order_obj)
        else:
            orders_by_status.setdefault("Other", []).append(order_obj)

    return render_template(
        "restaurant_orders.html",
        restaurant_name=restaurant_name,
        restaurant_email=restaurant_email,
        orders_by_status=orders_by_status,
        status_counts={k: len(v) for k, v in orders_by_status.items()},
    )


@app.route("/restaurant/reviews")
@restaurant_required
def restaurant_owner_reviews():
    """
    Restaurant owner's view of their reviews.
    Args:
        None
    Returns:
        Response: Renders restaurant reviews page for the owner.
    """
    rtr_id = session.get("rtr_id")
    restaurant_name = session.get("RestaurantName", "Restaurant")
    restaurant_email = session.get("RestaurantEmail", "")

    conn = get_db()
    # Get query parameters
    page = max(1, int(request.args.get("page", 1)))
    sort = request.args.get("sort", "recent")
    filter_rating = request.args.get("filter", "all")

    per_page = 10
    offset = (page - 1) * per_page

    # Build WHERE clause for filter
    where_clause = "rtr_id = ?"
    params = [rtr_id]
    if filter_rating != "all":
        try:
            filter_int = int(filter_rating)
            if 1 <= filter_int <= 5:
                where_clause += " AND rating = ?"
                params.append(filter_int)
        except ValueError:
            pass

    # Build ORDER BY clause for sort
    if sort == "highest":
        order_by = "rating DESC, created_at DESC"
    elif sort == "lowest":
        order_by = "rating ASC, created_at DESC"
    else:  # recent
        order_by = "created_at DESC"

    # Get total count
    total_reviews = fetch_one(
        conn, f'SELECT COUNT(*) FROM "Review" WHERE {where_clause}', tuple(params)
    )[0]

    # Calculate average rating
    avg_row = fetch_one(
        conn, 'SELECT AVG(rating) FROM "Review" WHERE rtr_id = ?', (rtr_id,)
    )
    average_rating = float(avg_row[0]) if avg_row and avg_row[0] else 0.0

    # Get reviews
    review_rows = fetch_all(
        conn,
        f"""
        SELECT r.rev_id, r.title, r.rating, r.description, r.created_at, r.ord_id,
               u.first_name, u.last_name
        FROM "Review" r
        JOIN "User" u ON r.usr_id = u.usr_id
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        tuple(params + [per_page, offset]),
    )

    reviews = []
    for rev_id, title, rating, description, created_at, ord_id, first_name, last_name in review_rows:
        # Format date
        date_str = ""
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                date_str = dt.strftime("%B %d, %Y")
            except Exception:
                date_str = created_at

        # Get user initial for avatar
        user_initial = first_name[0].upper() if first_name else "?"
        user_name = f"{first_name} {last_name}" if first_name and last_name else "Anonymous"

        reviews.append(
            {
                "rev_id": rev_id,
                "title": title,
                "rating": rating,
                "description": description,
                "date": date_str,
                "ord_id": ord_id,
                "user_name": user_name,
                "user_initial": user_initial,
            }
        )

    total_pages = math.ceil(total_reviews / per_page) if total_reviews > 0 else 1

    return render_template(
        "restaurant_owner_reviews.html",
        restaurant_name=restaurant_name,
        restaurant_email=restaurant_email,
        reviews=reviews,
        total_reviews=total_reviews,
        average_rating=average_rating,
        page=page,
        total_pages=total_pages,
        sort=sort,
        filter=filter_rating,
    )



@app.route("/restaurant/analytics")
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

    # Record a fresh analytics snapshot from current order data
    record_analytics_snapshot(rtr_id)

    conn = get_db()
    # Get the latest snapshot for current metrics
    latest_snapshot = fetch_one(
        conn,
        """
        SELECT total_orders, total_revenue_cents, avg_order_value_cents, 
               order_completion_rate
        FROM Analytics
        WHERE rtr_id = ?
        ORDER BY analytics_id DESC
        LIMIT 1
        """,
        (rtr_id,),
    )

    if latest_snapshot:
        total_orders, total_revenue_cents, avg_order_value_cents, completion_rate = (
            latest_snapshot
        )
        total_revenue = total_revenue_cents / 100.0
        avg_order_value = avg_order_value_cents / 100.0
    else:
        total_orders = 0
        total_revenue = 0.0
        avg_order_value = 0.0
        completion_rate = 0.0

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
        WHERE rtr_id = ?
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

    # Get historical data for time series chart (last 30 days)
    snapshots = fetch_all(
        conn,
        """
        SELECT snapshot_date, total_orders
        FROM Analytics
        WHERE rtr_id = ?
        ORDER BY snapshot_date DESC
        LIMIT 30
        """,
        (rtr_id,),
    )

    # Reverse to show oldest to newest
    snapshots = list(reversed(snapshots))
    date_labels = [s[0] for s in snapshots]
    date_counts = [s[1] for s in snapshots]

    return render_template(
        "restaurant_analytics.html",
        restaurant_name=restaurant_name,
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


# ---------------------- Restaurant Order Management Routes ----------------------


@app.route("/restaurant/orders/<int:ord_id>/accept", methods=["POST"])
@restaurant_required
def restaurant_accept_order(ord_id):
    """
    Accept a pending order (Ordered → Accepted).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    # Verify order belongs to this restaurant and is in 'Ordered' status
    order = fetch_one(
        conn, 'SELECT ord_id, rtr_id, status FROM "Order" WHERE ord_id = ?', (ord_id,)
    )

    if not order:
        abort(404)

    if order[1] != rtr_id:
        abort(403)  # Not this restaurant's order

    if order[2] != "Ordered":
        return (
            jsonify({"ok": False, "error": "Order not in pending state"}),
            400,
        )

    # Update status
    execute_query(conn, 'UPDATE "Order" SET status = ? WHERE ord_id = ?', ("Accepted", ord_id))

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    # Return JSON for AJAX or redirect for full page
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Accepted"})
    else:
        return redirect(url_for("restaurant_orders"))


@app.route("/restaurant/orders/<int:ord_id>/reject", methods=["POST"])
@restaurant_required
def restaurant_reject_order(ord_id):
    """
    Reject a pending order (Ordered → Cancelled).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(
        conn, 'SELECT ord_id, rtr_id, status FROM "Order" WHERE ord_id = ?', (ord_id,)
    )

    if not order or order[1] != rtr_id:
        abort(403)

    if order[2] not in ["Ordered", "Accepted", "Preparing"]:
        return (
            jsonify({"ok": False, "error": "Cannot cancel at this stage"}),
            400,
        )

    execute_query(conn, 'UPDATE "Order" SET status = ? WHERE ord_id = ?', ("Cancelled", ord_id))

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Cancelled"})
    else:
        return redirect(url_for("restaurant_orders"))


@app.route("/restaurant/orders/<int:ord_id>/prepare", methods=["POST"])
@restaurant_required
def restaurant_prepare_order(ord_id):
    """
    Mark order as being prepared (Accepted → Preparing).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(
        conn, 'SELECT ord_id, rtr_id, status FROM "Order" WHERE ord_id = ?', (ord_id,)
    )

    if not order or order[1] != rtr_id:
        abort(403)

    if order[2] != "Accepted":
        return (
            jsonify({"ok": False, "error": "Order must be accepted first"}),
            400,
        )

    execute_query(conn, 'UPDATE "Order" SET status = ? WHERE ord_id = ?', ("Preparing", ord_id))

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Preparing"})
    else:
        return redirect(url_for("restaurant_orders"))


@app.route("/restaurant/orders/<int:ord_id>/ready", methods=["POST"])
@restaurant_required
def restaurant_ready_order(ord_id):
    """
    Mark order as ready for pickup/delivery (Preparing → Ready).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(
        conn, 'SELECT ord_id, rtr_id, status FROM "Order" WHERE ord_id = ?', (ord_id,)
    )

    if not order or order[1] != rtr_id:
        abort(403)

    if order[2] != "Preparing":
        return (
            jsonify({"ok": False, "error": "Order must be preparing first"}),
            400,
        )

    execute_query(conn, 'UPDATE "Order" SET status = ? WHERE ord_id = ?', ("Ready", ord_id))

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Ready"})
    else:
        return redirect(url_for("restaurant_orders"))


@app.route("/restaurant/orders/<int:ord_id>/deliver", methods=["POST"])
@restaurant_required
def restaurant_deliver_order(ord_id):
    """
    Mark order as delivered/completed (Ready → Delivered).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(
        conn, 'SELECT ord_id, rtr_id, status FROM "Order" WHERE ord_id = ?', (ord_id,)
    )

    if not order or order[1] != rtr_id:
        abort(403)

    if order[2] != "Ready":
        return (
            jsonify({"ok": False, "error": "Order must be ready first"}),
            400,
        )

    execute_query(conn, 'UPDATE "Order" SET status = ? WHERE ord_id = ?', ("Delivered", ord_id))

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Delivered"})
    else:
        return redirect(url_for("restaurant_orders"))


# Registration route
@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Display the registration form (GET) and create a new user (POST).
    Args:
        None
    Returns:
        Response: Renders registration page or redirects to login on success.
    """
    if request.method == "POST":
        fname = (request.form.get("fname") or "").strip()
        lname = (request.form.get("lname") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        allergies = (request.form.get("allergies") or "").strip()
        preferences = (request.form.get("preferences") or "").strip()

        # Basic validations
        if not fname or not lname:
            return render_template("register.html", error="First and last name are required")
        if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return render_template("register.html", error="Please enter a valid email address")
        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match")
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters")

        digits_only = re.sub(r"\D+", "", phone)
        if len(digits_only) < 7:
            return render_template("register.html", error="Please enter a valid phone number")

        conn = get_db()
        try:
            exists = fetch_one(conn, 'SELECT 1 FROM "User" WHERE email = ?', (email,))
            if exists:
                return render_template("register.html", error="Email already registered")

            password_hashed = generate_password_hash(password)

            # Insert WITHOUT generated_menu (meal planning fills it later)
            execute_query(
                conn,
                """
                INSERT INTO "User"
                    (first_name, last_name, email, phone, password_HS, wallet, preferences, allergies)
                VALUES
                    (?,          ?,         ?,     ?,     ?,           ?,      ?,            ?)
                """,
                (fname, lname, email, digits_only, password_hashed, 0, preferences, allergies),
            )
        except IntegrityError:
            return render_template("register.html", error="Email already registered")

        return redirect(url_for("login"))

    return render_template("register.html")


# Profile route
@app.route("/profile")
def profile():
    """
    Show the logged-in user's profile, including recent orders.
    Args:
        None
    Returns:
        Response: HTML profile page (requires login).
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    # Load the full user row by session email
    email = session.get("Email")
    if not email:
        return redirect(url_for("logout"))

    import json
    from datetime import datetime

    def _fmt_date(iso_str: str) -> str:
        if not iso_str:
            return ""
        try:
            # Handles "2025-10-18T18:22:00-04:00" style strings
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return iso_str  # if it’s not ISO, show raw

    def _fmt_total(val) -> str:
        try:
            return f"${float(val):.2f}"
        except Exception:
            return ""

    conn = get_db()
    row = fetch_one(
        conn,
        'SELECT usr_id,first_name,last_name,email,phone,password_HS,wallet,preferences,allergies FROM "User" WHERE email = ?',
        (email,),
    )
    if not row:
        return redirect(url_for("logout"))

    user = {
        "usr_id": row[0],
        "first_name": row[1],
        "last_name": row[2],
        "email": row[3],
        "phone": row[4],
        "password_HS": row[5],
        "wallet": (row[6] or 0) / 100.0,
        "preferences": row[7] or "",
        "allergies": row[8] or "",
    }

    session["usr_id"] = user["usr_id"]

    # Pull orders for this user; details is JSON we will parse
    order_rows = fetch_all(
        conn,
        """
        SELECT o.ord_id, o.details, o.status, r.name
        FROM "Order" o
        JOIN "Restaurant" r ON o.rtr_id = r.rtr_id
        WHERE o.usr_id = ?
        ORDER BY o.ord_id DESC
        """,
        (user["usr_id"],),
    )

    orders = []
    for ord_id, details, status, r_name in order_rows:
        placed = ""
        total = ""
        if details:
            try:
                j = json.loads(details)
                placed = _fmt_date(j.get("placed_at") or j.get("time"))
                charges = j.get("charges") or {}
                total_val = (
                    charges.get("total") or charges.get("grand_total") or charges.get("amount")
                )
                total = _fmt_total(total_val) if total_val is not None else ""
            except Exception:
                pass

        # Check if this order has a review
        has_review = fetch_one(
            conn,
            'SELECT 1 FROM "Review" WHERE ord_id = ?',
            (ord_id,),
        ) is not None

        orders.append(
            {
                "id": ord_id,
                "date": placed,
                "status": status or "",
                "progress": order_progress(status),
                "restaurant": r_name,
                "total": total,
                "has_review": has_review,
            }
        )

    pw_updated = request.args.get("pw_updated")
    pw_error = request.args.get("pw_error")

    return render_template(
        "profile.html", user=user, orders=orders, pw_updated=pw_updated, pw_error=pw_error,
        generation_error=session.pop("menu_generation_error", None),
    )


# Edit Profile route
@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    """
    Display and process the profile edit form (phone, preferences, allergies).
    Args:
        None
    Returns:
        Response: Renders form (GET) or updates and redirects to profile (POST).
    """
    if session.get("Username") is None:
        return redirect(url_for("login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("logout"))

    conn = get_db()
    row = fetch_one(
        conn,
        """
        SELECT usr_id, first_name, last_name, email, phone, wallet, preferences, allergies
        FROM "User" WHERE usr_id = ?
    """,
        (usr_id,),
    )

    if not row:
        return redirect(url_for("logout"))

    user = {
        "usr_id": row[0],
        "first_name": row[1],
        "last_name": row[2],
        "email": row[3],
        "phone": row[4],
        "wallet": (row[5] or 0) / 100.0,
        "preferences": row[6] or "",
        "allergies": row[7] or "",
    }

    # For now just render an edit form (you can build edit_profile.html)
    if request.method == "POST":
        # You’ll expand this with update logic later
        # Example: update phone, preferences, allergies
        new_phone = request.form.get("phone") or user["phone"]
        new_prefs = request.form.get("preferences") or user["preferences"]
        new_allergies = request.form.get("allergies") or user["allergies"]

        conn = get_db()
        execute_query(
            conn,
            """
            UPDATE "User"
            SET phone = ?, preferences = ?, allergies = ?
            WHERE usr_id = ?
        """,
            (new_phone, new_prefs, new_allergies, usr_id),
        )

        # Refresh session values
        session["Phone"] = new_phone
        session["Preferences"] = new_prefs
        session["Allergies"] = new_allergies

        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=user)


@app.route("/profile/change-password", methods=["POST"])
def change_password():
    """
    Change the current user's password after validating the current password.
    Args:
        None
    Returns:
        Response: Redirect back to profile with success or error flags.
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        # Fallback: resolve via email
        email = session.get("Email")
        if not email:
            return redirect(url_for("logout"))
        conn = get_db()
        row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email = ?', (email,))
        if not row:
            return redirect(url_for("logout"))
        usr_id = row[0]
        session["usr_id"] = usr_id

    # Read form fields
    current_password = (request.form.get("current_password") or "").strip()
    new_password = (request.form.get("new_password") or "").strip()
    confirm_password = (request.form.get("confirm_password") or "").strip()

    # Basic validations (mirror your frontend behavior)
    if not current_password:
        return redirect(url_for("profile", pw_error="missing_current"))
    if len(new_password) < 6:
        return redirect(url_for("profile", pw_error="too_short"))
    if new_password != confirm_password:
        return redirect(url_for("profile", pw_error="mismatch"))
    if new_password == current_password:
        return redirect(url_for("profile", pw_error="same_as_current"))

    # Verify current hash & update to new hash
    conn = get_db()
    row = fetch_one(conn, 'SELECT password_HS FROM "User" WHERE usr_id = ?', (usr_id,))
    if not row:
        return redirect(url_for("logout"))

    stored_hash = row[0]
    if not check_password_hash(stored_hash, current_password):
        # wrong current password
        return redirect(url_for("profile", pw_error="incorrect_current"))

    # All good → update
    new_hash = generate_password_hash(new_password)
    execute_query(
        conn, 'UPDATE "User" SET password_HS = ? WHERE usr_id = ?', (new_hash, usr_id)
    )


    # Success
    return redirect(url_for("profile", pw_updated=1))


# ==================== Review Routes ====================


@app.route("/order/<int:ord_id>/review", methods=["GET", "POST"])
def review_order(ord_id):
    """
    Display review form (GET) or submit a new review (POST) for a delivered order.
    Args:
        ord_id (int): The order ID to review.
    Returns:
        Response: Review form HTML (GET) or redirect to profile (POST).
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("logout"))

    conn = get_db()
    # Verify order exists, belongs to user, and is delivered
    order_row = fetch_one(
        conn,
        """
        SELECT o.ord_id, o.rtr_id, o.details, o.status, r.name
        FROM "Order" o
        JOIN "Restaurant" r ON o.rtr_id = r.rtr_id
        WHERE o.ord_id = ? AND o.usr_id = ?
        """,
        (ord_id, usr_id),
    )

    if not order_row:
        return redirect(url_for("profile"))

    ord_id_db, rtr_id, details, status, r_name = order_row

    # Must be delivered to review
    if status.lower() != "delivered":
        return redirect(url_for("profile"))

    # Check if review already exists
    existing_review = fetch_one(
        conn, 'SELECT 1 FROM "Review" WHERE ord_id = ?', (ord_id,)
    )
    if existing_review:
        return redirect(url_for("view_review", ord_id=ord_id))

    # Parse order details for display
    items = []
    total = 0.0
    order_date = ""
    if details:
        try:
            j = json.loads(details)
            order_date = j.get("placed_at") or j.get("time") or ""
            if order_date:
                try:
                    dt = datetime.fromisoformat(order_date)
                    order_date = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            charges = j.get("charges") or {}
            total = float(charges.get("total") or charges.get("grand_total") or 0)

            for item in j.get("items") or []:
                items.append(
                    {
                        "name": item.get("name") or "Item",
                        "qty": item.get("qty") or 1,
                        "line_total": float(item.get("line_total") or 0),
                    }
                )
        except Exception:
            pass

    order = {
        "ord_id": ord_id,
        "restaurant_name": r_name,
        "order_date": order_date,
        "total": total,
        "items": items,
    }

    # Handle POST - Submit review
    if request.method == "POST":
        rating = request.form.get("rating")
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()

        # Validate rating
        if not rating:
            return render_template("review_form.html", order=order, error="Please select a rating")

        try:
            rating_int = int(rating)
            if rating_int < 1 or rating_int > 5:
                raise ValueError
        except ValueError:
            return render_template("review_form.html", order=order, error="Invalid rating value")

        # Insert review
        created_at = datetime.now().isoformat()
        execute_query(
            conn,
            """
            INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (rtr_id, usr_id, title, rating_int, description, ord_id, created_at),
        )

        return redirect(url_for("profile"))

    # GET - Show form
    return render_template("review_form.html", order=order)



@app.route("/order/<int:ord_id>/review/view")
def view_review(ord_id):
    """
    View an existing review for an order.
    Args:
        ord_id (int): The order ID.
    Returns:
        Response: Renders the user's individual review.
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("logout"))

    conn = get_db()
    # Get review details with restaurant info
    review_row = fetch_one(
        conn,
        """
        SELECT r.rev_id, r.rtr_id, r.ord_id, r.title, r.rating, r.description, r.created_at,
               rest.name as restaurant_name
        FROM "Review" r
        JOIN "Restaurant" rest ON r.rtr_id = rest.rtr_id
        WHERE r.ord_id = ? AND r.usr_id = ?
        """,
        (ord_id, usr_id),
    )

    if not review_row:
        return redirect(url_for("profile"))

    review = {
        "rev_id": review_row[0],
        "rtr_id": review_row[1],
        "ord_id": review_row[2],
        "title": review_row[3],
        "rating": review_row[4],
        "description": review_row[5],
        "created_at": review_row[6],
        "restaurant_name": review_row[7],
    }

    return render_template("view_review.html", review=review)



@app.route("/restaurant/<int:rtr_id>/reviews")
def restaurant_reviews(rtr_id):
    """
    Display all reviews for a restaurant with pagination, sorting, and filtering.
    Args:
        rtr_id (int): The restaurant ID.
    Returns:
        Response: Restaurant reviews page HTML.
    """
    conn = get_db()
    # Get restaurant info
    restaurant_row = fetch_one(
        conn, 'SELECT name FROM "Restaurant" WHERE rtr_id = ?', (rtr_id,)
    )
    if not restaurant_row:
        abort(404)

    restaurant = {"name": restaurant_row[0]}

    # Get query parameters
    page = max(1, int(request.args.get("page", 1)))
    sort = request.args.get("sort", "recent")
    filter_rating = request.args.get("filter", "all")
    highlight = request.args.get("highlight")  # Optional review ID to highlight

    per_page = 10
    offset = (page - 1) * per_page

    # Build WHERE clause for filter
    where_clause = "rtr_id = ?"
    params = [rtr_id]
    if filter_rating != "all":
        try:
            filter_int = int(filter_rating)
            if 1 <= filter_int <= 5:
                where_clause += " AND rating = ?"
                params.append(filter_int)
        except ValueError:
            pass

    # Build ORDER BY clause for sort
    if sort == "highest":
        order_by = "rating DESC, created_at DESC"
    elif sort == "lowest":
        order_by = "rating ASC, created_at DESC"
    else:  # recent
        order_by = "created_at DESC"

    # Get total count
    total_reviews = fetch_one(
        conn, f'SELECT COUNT(*) FROM "Review" WHERE {where_clause}', tuple(params)
    )[0]

    # Calculate average rating
    avg_row = fetch_one(
        conn, 'SELECT AVG(rating) FROM "Review" WHERE rtr_id = ?', (rtr_id,)
    )
    average_rating = float(avg_row[0]) if avg_row and avg_row[0] else 0.0

    # Get reviews
    review_rows = fetch_all(
        conn,
        f"""
        SELECT r.rev_id, r.title, r.rating, r.description, r.created_at, r.ord_id,
               u.first_name, u.last_name
        FROM "Review" r
        JOIN "User" u ON r.usr_id = u.usr_id
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        tuple(params + [per_page, offset]),
    )

    reviews = []
    for rev_id, title, rating, description, created_at, ord_id, first_name, last_name in review_rows:
        # Format date
        date_str = ""
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                date_str = dt.strftime("%B %d, %Y")
            except Exception:
                date_str = created_at

        # Get user initial for avatar
        user_initial = first_name[0].upper() if first_name else "?"
        user_name = f"{first_name} {last_name}" if first_name and last_name else "Anonymous"

        reviews.append(
            {
                "rev_id": rev_id,
                "title": title,
                "rating": rating,
                "description": description,
                "date": date_str,
                "ord_id": ord_id,
                "user_name": user_name,
                "user_initial": user_initial,
                "is_highlighted": str(rev_id) == highlight,
            }
        )

    total_pages = math.ceil(total_reviews / per_page) if total_reviews > 0 else 1

    return render_template(
        "restaurant_reviews.html",
        restaurant=restaurant,
        reviews=reviews,
        total_reviews=total_reviews,
        average_rating=average_rating,
        page=page,
        total_pages=total_pages,
        sort=sort,
        filter=filter_rating,
    )



# Order route (Calendar "Order" button target)
@app.route("/order", methods=["GET", "POST"])
def order():
    """
    Place an order via JSON (POST) or handle legacy single-item GET flow.
    Args:
        None
    Returns:
        Response: JSON with {'ok', 'ord_id'} on POST; redirects/HTML for legacy GET.
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    # Resolve usr_id strictly
    usr_id = session.get("usr_id")
    if not usr_id:
        conn = get_db()
        row = fetch_one(
            conn, 'SELECT usr_id FROM "User" WHERE email = ?', (session.get("Email"),)
        )
        if not row:
            return redirect(url_for("logout"))
        usr_id = row[0]
        session["usr_id"] = usr_id

    # ---- POST JSON: place a single order containing ALL items in the restaurant group ----
    if request.method == "POST" and request.is_json:
        payload = request.get_json(silent=True) or {}
        rtr_id = int(payload.get("restaurant_id") or 0)
        items_in = payload.get("items") or []  # [{itm_id, qty, notes}]
        delivery_type = (payload.get("delivery_type") or "delivery").lower()
        if delivery_type not in ("delivery", "pickup"):
            delivery_type = "delivery"
        tip_dollars = _money(payload.get("tip") or 0)
        eta_minutes = int(payload.get("eta_minutes") or 40)
        iso_date = payload.get("date") or datetime.now().date().isoformat()
        try:
            meal = int(payload.get("meal") or 3)
        except Exception:
            meal = 3

        if rtr_id <= 0 or not items_in:
            return jsonify({"ok": False, "error": "invalid_input"}), 400

        # Look up all items strictly from DB to get authoritative prices/names
        itm_ids = [int(it.get("itm_id") or 0) for it in items_in if int(it.get("itm_id") or 0) > 0]
        if not itm_ids:
            return jsonify({"ok": False, "error": "no_items"}), 400

        conn = get_db()
        qmarks = ",".join(["?"] * len(itm_ids))
        rows = fetch_all(
            conn,
            f"""
            SELECT m.itm_id, m.rtr_id, m.name, m.price, r.name
            FROM "MenuItem" m
            JOIN "Restaurant" r ON r.rtr_id = m.rtr_id
            WHERE m.itm_id IN ({qmarks})
        """,
            tuple(itm_ids),
        )

        # Validate that all items belong to the same restaurant
        if not rows:
            return jsonify({"ok": False, "error": "items_not_found"}), 404

        # Map itm_id -> {price, name, rtr_id, rtr_name}
        dbmap = {
            row[0]: {
                "rtr_id": row[1],
                "name": row[2],
                "price_cents": row[3] or 0,
                "restaurant_name": row[4],
            }
            for row in rows
        }
        for it in itm_ids:
            if it not in dbmap:
                return jsonify({"ok": False, "error": f"item_{it}_not_found"}), 404
            if int(dbmap[it]["rtr_id"]) != rtr_id:
                return jsonify({"ok": False, "error": "mixed_restaurants"}), 400

        # Build items array for details; compute charges
        detail_items = []
        subtotal = 0.0
        for it in items_in:
            iid = int(it.get("itm_id"))
            qty = int(it.get("qty") or 1)
            if qty <= 0:
                qty = 1
            meta = dbmap[iid]
            unit_price = _cents_to_dollars(meta["price_cents"])
            line_total = _money(unit_price * qty)
            subtotal = _money(subtotal + line_total)
            detail_items.append(
                {
                    "itm_id": iid,
                    "name": meta["name"],
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    **({"notes": (it.get("notes") or "")} if it.get("notes") else {}),
                }
            )

        charges = _order_charges(subtotal, delivery_type, tip_dollars)
        tax, delivery_fee = charges["tax"], charges["delivery_fee"]
        service_fee, total = charges["service_fee"], charges["total"]

        placed_iso = datetime.now().astimezone().isoformat()

        details = {
            "placed_at": placed_iso,
            "restaurant_id": int(rtr_id),
            "items": detail_items,
            "charges": {
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "service_fee": service_fee,
                "tip": tip_dollars,
                "total": total,
            },
            "delivery_type": delivery_type,
            "eta_minutes": int(eta_minutes),
            "date": iso_date,
            "meal": meal,
        }

        # Insert the single order row with status "Ordered"
        conn = get_db()
        new_ord_id = execute_query(
            conn,
            'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
            (rtr_id, usr_id, json.dumps(details), "Ordered"),
        ).lastrowid

        # Update analytics for this restaurant
        update_analytics_safe(rtr_id)

        return jsonify({"ok": True, "ord_id": new_ord_id})

    # ---- (optional) legacy GET single-item path, kept for compatibility ----
    # If you don't need this anymore, you can remove the whole GET section.
    # Expect query: itm_id, qty, notes, delivery, tip, eta, date, meal
    itm_id = int(request.args.get("itm_id") or 0)
    if itm_id <= 0:
        return redirect(url_for("orders"))

    try:
        qty = max(1, int(request.args.get("qty", "1")))
    except ValueError:
        qty = 1
    delivery_type = (request.args.get("delivery") or "delivery").lower()
    if delivery_type not in ("delivery", "pickup"):
        delivery_type = "delivery"
    try:
        tip_dollars = _money(float(request.args.get("tip", "0")))
    except Exception:
        tip_dollars = 0.0
    try:
        eta_minutes = int(request.args.get("eta", "40"))
    except Exception:
        eta_minutes = 40
    iso_date = request.args.get("date") or datetime.now().date().isoformat()
    try:
        meal = int(request.args.get("meal", "3"))
    except Exception:
        meal = 3
    notes = (request.args.get("notes") or "").strip()

    # Look up item & restaurant strictly
    conn = get_db()
    mi = fetch_one(
        conn,
        """
        SELECT m.itm_id, m.rtr_id, m.name, m.price, r.name
        FROM "MenuItem" m
        JOIN "Restaurant" r ON r.rtr_id = m.rtr_id
        WHERE m.itm_id = ?
    """,
        (itm_id,),
    )
    if not mi:
        return redirect(url_for("orders"))

    item_id, rtr_id, item_name, price_cents, restaurant_name = mi
    unit_price = _cents_to_dollars(price_cents)
    line_total = _money(unit_price * qty)

    charges = _order_charges(line_total, delivery_type, tip_dollars)
    tax, delivery_fee = charges["tax"], charges["delivery_fee"]
    service_fee, total = charges["service_fee"], charges["total"]

    details = {
        "placed_at": datetime.now().astimezone().isoformat(),
        "restaurant_id": int(rtr_id),
        "items": [
            {
                "itm_id": int(item_id),
                "name": item_name,
                "qty": int(qty),
                "unit_price": unit_price,
                "line_total": line_total,
                **({"notes": notes} if notes else {}),
            }
        ],
        "charges": {
            "subtotal": line_total,
            "tax": tax,
            "delivery_fee": delivery_fee,
            "service_fee": service_fee,
            "tip": tip_dollars,
            "total": total,
        },
        "delivery_type": delivery_type,
        "eta_minutes": int(eta_minutes),
        "date": iso_date,
        "meal": meal,
    }

    conn = get_db()
    new_ord_id = execute_query(
        conn,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (rtr_id, usr_id, json.dumps(details), "Ordered"),
    ).lastrowid

    return redirect(url_for("profile") + (f"?ordered={new_ord_id}" if new_ord_id else ""))


# Orders route
@app.route("/orders")
def orders():
    """
    List restaurants and in-stock menu items for browsing.
    Args:
        None
    Returns:
        Response: HTML page showing restaurants and items (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("login"))

    conn = get_db()
    # Pull address fields too
    restaurants = fetch_all(
        conn, 'SELECT rtr_id, name, address, city, state, zip FROM "Restaurant"'
    )
    menu_items = fetch_all(
        conn,
        """
        SELECT itm_id, rtr_id, name, price, calories, allergens, description
        FROM "MenuItem"
        WHERE instock IS NULL OR instock = 1
    """,
    )

    def _addr(a, c, s, z) -> str:
        """
        Safely join address parts that might be None/ints.
        Args:
            a (Any): Street address.
            c (Any): City.
            s (Any): State/region.
            z (Any): Zip/postal code.
        Returns:
            str: A single formatted address string.
        """
        parts_raw = [a, c, s, z]
        parts = []
        for p in parts_raw:
            if p is None:
                continue
            # Coerce to string and strip
            sp = str(p).strip()
            if sp:
                parts.append(sp)
        return ", ".join(parts)

    rest_list = [
        {
            "rtr_id": r[0],
            "name": r[1],
            "address": r[2] or "",
            "city": r[3] or "",
            "state": r[4] or "",
            "zip": r[5] if r[5] is not None else "",
            "address_full": _addr(r[2], r[3], r[4], r[5]),
        }
        for r in restaurants
    ]

    item_list = [
        {
            "itm_id": m[0],
            "rtr_id": m[1],
            "name": m[2],
            "price_cents": m[3] or 0,
            "calories": m[4] or 0,
            "allergens": m[5] or "",
            "description": m[6] or "",
        }
        for m in menu_items
    ]

    return render_template("orders.html", restaurants=rest_list, items=item_list)


# Restaurants browse route
@app.route("/restaurants")
def restaurants():
    """
    Browse restaurants with details and currently in-stock items.
    Args:
        None
    Returns:
        Response: HTML page listing restaurants and their items (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("login"))

    conn = get_db()
    restaurants = fetch_all(
        conn,
        'SELECT rtr_id, name, description, phone, email, address, city, state, zip, hours, status FROM "Restaurant"',
    )
    menu_items = fetch_all(
        conn,
        """
        SELECT itm_id, rtr_id, name, price, calories, allergens, description
        FROM "MenuItem"
        WHERE instock IS NULL OR instock = 1
    """,
    )

    def _addr(a, c, s, z) -> str:
        parts_raw = [a, c, s, z]
        parts = []
        for p in parts_raw:
            if p is None:
                continue
            sp = str(p).strip()
            if sp:
                parts.append(sp)
        return ", ".join(parts)

    rest_list = [
        {
            "rtr_id": r[0],
            "name": r[1],
            "description": r[2] or "",
            "phone": r[3] or "",
            "email": r[4] or "",
            "address": r[5] or "",
            "city": r[6] or "",
            "state": r[7] or "",
            "zip": r[8] if r[8] is not None else "",
            "hours": r[9] or "",
            "hours_display": format_hours(r[9]),
            "status": r[10] or "",
            "address_full": _addr(r[5], r[6], r[7], r[8]),
        }
        for r in restaurants
    ]

    item_list = [
        {
            "itm_id": m[0],
            "rtr_id": m[1],
            "name": m[2],
            "price_cents": m[3] or 0,
            "calories": m[4] or 0,
            "allergens": m[5] or "",
            "description": m[6] or "",
        }
        for m in menu_items
    ]

    return render_template("restaurants.html", restaurants=rest_list, items=item_list)


# Order receipt PDF route
@app.route("/orders/<int:ord_id>/receipt.pdf")
def order_receipt(ord_id: int):
    """
    Stream a PDF receipt for an order owned by the logged-in user.
    Args:
        ord_id (int): The order identifier in the path.
    Returns:
        Response: PDF file download or an error status (404/403) if inaccessible.
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("login"))

    # Ensure the order belongs to the logged-in user
    conn = get_db()
    row = fetch_one(conn, 'SELECT usr_id FROM "Order" WHERE ord_id = ?', (ord_id,))
    if not row:
        abort(404)
    if session.get("usr_id") and row[0] != session["usr_id"]:
        abort(403)
    # If usr_id not in session (older sessions), compare via email
    if not session.get("usr_id"):
        # Resolve current user's usr_id by email
        urow = fetch_one(
            conn, 'SELECT usr_id FROM "User" WHERE email = ?', (session.get("Email"),)
        )
        if not urow or urow[0] != row[0]:
            abort(403)

    pdf_bytes = generate_order_receipt_pdf(db_path(), ord_id)  # returns bytes

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"order_{ord_id}_receipt.pdf",
    )


# Columns the database viewer never selects. Password hashes can be cracked offline,
# so they must not reach the page (User and Restaurant both have password_HS).
DB_VIEW_HIDDEN_COLUMNS = frozenset({"password_HS"})


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# The database viewer is a developer tool: it shows every user's email and phone,
# so it is off unless explicitly enabled (team decision, option A on the /db issue).
DB_VIEW_ENV = "WEEKLIES_ENABLE_DB_VIEW"


def env_flag(name, environ=None) -> bool:
    """
    Read a boolean environment variable.
    Args:
        name: Variable name.
        environ: Mapping to read from (defaults to os.environ; injectable for tests).
    Returns:
        bool: True for 1/true/yes/on (any case, surrounding spaces ignored), else False.
    """
    environ = os.environ if environ is None else environ
    return (environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


app.config["DB_VIEW_ENABLED"] = env_flag(DB_VIEW_ENV)


def db_view_enabled() -> bool:
    """
    Whether /db is available: when WEEKLIES_ENABLE_DB_VIEW is set, and always under
    pytest (app.testing) so the existing viewer tests keep running.
    Returns:
        bool: True if the viewer should be served.
    """
    return bool(app.config.get("DB_VIEW_ENABLED")) or app.testing


@app.context_processor
def inject_db_view_enabled():
    """Expose db_view_enabled to templates so the nav only links to /db when it is served."""
    return {"db_view_enabled": db_view_enabled()}


@app.context_processor
def inject_order_fees():
    """Expose the fee schedule so cart previews compute the same totals the server bills."""
    return {"order_fees": config.order_fees()}


# Database viewer route (uses helpers only)
@app.route("/db")
def db_view():
    """
    Display a simple, paginated database table viewer (developer tool).
    Args:
        None
    Returns:
        Response: HTML page showing rows/columns for a selected table (requires login);
        404 when the viewer is disabled.
    """
    if not db_view_enabled():
        abort(404)
    if session.get("Username") is None:
        return redirect(url_for("login"))

    allowed_tables = {"User", "Restaurant", "MenuItem", "Order", "Review"}
    table = request.args.get("t", "User")
    if table not in allowed_tables:
        table = "User"

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    page = max(page, 1)
    per_page = 10

    conn = get_db()
    total_row = fetch_one(conn, f'SELECT COUNT(*) FROM "{table}"')
    total = (total_row[0] if total_row else 0) or 0

    pages = max(math.ceil(total / per_page), 1)
    page = min(page, pages)
    offset = (page - 1) * per_page

    col_rows = fetch_all(conn, f'PRAGMA table_info("{table}")')
    columns = [r[1] for r in col_rows or [] if r[1] not in DB_VIEW_HIDDEN_COLUMNS]

    # Select only the visible columns, so hidden values never leave the database.
    if columns:
        select_list = ", ".join(_quote_ident(c) for c in columns)
        rows = fetch_all(
            conn, f'SELECT {select_list} FROM "{table}" LIMIT ? OFFSET ?', (per_page, offset)
        )
    else:
        rows = []

    start = 0 if total == 0 else offset + 1
    end = min(offset + per_page, total)

    return render_template(
        "db_view.html",
        table=table,
        allowed=sorted(allowed_tables),
        columns=columns,
        rows=rows,
        page=page,
        pages=pages,
        total=total,
        start=start,
        end=end,
    )


# ----------- Meal Plan Generation Route -----------
@app.route('/menu/generate', methods=['POST'])
def generate_menu():
    """
    Generate or extend the logged-in user's meal plan and persist it.

    Supports application/json and HTML form submissions.
    """
    if session.get('Username') is None:
        return redirect(url_for('login'))

    # Load user row (need preferences, allergies, existing generated_menu)
    conn = get_db()
    user = fetch_one(
        conn,
        'SELECT usr_id, email, preferences, allergies, generated_menu FROM "User" WHERE email = ?',
        (session.get('Email'),)
    )

    if not user:
        return redirect(url_for('logout'))

    usr_id = user[0]
    prefs_db = user[2] or ""
    allergies_db = user[3] or ""
    existing_menu = user[4] or ""

    # Parse inputs
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        start_date = (payload.get('start_date') or date.today().isoformat()).strip()
        try:
            meal_numbers = [int(x) for x in (payload.get('meal_numbers') or [1,2,3])]
        except Exception:
            meal_numbers = [1,2,3]
        try:
            number_of_days = int(payload.get('number_of_days') or 1)
        except Exception:
            number_of_days = 1
        preferences = (payload.get('preferences') or prefs_db).strip()
        allergies = (payload.get('allergens') or allergies_db).strip()
    else:
        start_date = (request.form.get('start_date') or date.today().isoformat()).strip()
        try:
            number_of_days = int(request.form.get('days') or 1)
        except Exception:
            number_of_days = 1
        sel = []
        if request.form.get('meal1'): sel.append(1)
        if request.form.get('meal2'): sel.append(2)
        if request.form.get('meal3'): sel.append(3)
        meal_numbers = sel or [1,2,3]
        preferences = (request.form.get('preferences') or prefs_db).strip()
        allergies = (request.form.get('allergens') or allergies_db).strip()

    # Diets and allergies on the account are hard rules; a request can add to them but not drop them.
    preferences = with_account_diets(preferences, prefs_db)
    allergies = with_account_allergies(allergies, allergies_db)

    want_json = request.is_json or request.accept_mimetypes.best == 'application/json'

    def generation_error(message, status):
        if want_json:
            return jsonify({"ok": False, "error": message}), status
        session['menu_generation_error'] = message
        return redirect(url_for('profile'))

    try:
        cap_value = payload.get('weekly_cap') if request.is_json else request.form.get('weekly_cap')
        weekly_cap_cents = parse_weekly_cap(cap_value)
    except ValueError as exc:
        return generation_error(str(exc), 400)

    # Validate start_date
    try:
        _ = date.fromisoformat(start_date)
    except Exception:
        start_date = date.today().isoformat()

    # Clamp days
    if number_of_days < 1:
        number_of_days = 1
    if number_of_days > 14:
        number_of_days = 14

    # Generate
    try:
        gen = MenuGenerator(database_path=db_path())
        updated_menu = gen.update_menu(
            menu=existing_menu,
            preferences=preferences,
            allergens=allergies,
            date=start_date,
            meal_numbers=meal_numbers,
            number_of_days=number_of_days,
            weekly_cap_cents=weekly_cap_cents,
        )
        start = date.fromisoformat(start_date)
        weeks = list(dict.fromkeys(
            week_start((start + timedelta(days=i)).isoformat()) for i in range(number_of_days)
        ))
        try:
            totals = weekly_item_totals(updated_menu, gen.item_prices, weeks)
        except ValueError:
            if weekly_cap_cents is not None:
                raise
            # Uncapped plans can retain old meals whose catalog prices are unavailable.
            totals = None
    except BudgetExceededError as exc:
        return generation_error(str(exc), 422)
    except ValueError as exc:
        return generation_error(str(exc), 400)
    except Exception:
        app.logger.exception("Menu generation failed")
        return generation_error("Menu generation failed. Please try again.", 500)

    # Persist
    conn = get_db()
    execute_query(conn, 'UPDATE "User" SET generated_menu = ? WHERE usr_id = ?', (updated_menu, usr_id))

    session['GeneratedMenu'] = updated_menu

    if want_json:
        return jsonify({
            "ok": True,
            "generated_menu": updated_menu,
            "start_date": start_date,
            "meal_numbers": meal_numbers,
            "number_of_days": number_of_days,
            "weekly_cap_cents": weekly_cap_cents,
            "item_total_cents": sum(totals.values()) if totals is not None else None,
            "weekly_item_totals_cents": totals,
            "variety": gen.variety.as_json() if gen.variety else None,
        })
    return redirect(url_for('index'))


@app.route("/menu/swap", methods=["POST"])
def swap_meal():
    """
    Replace the item in one date/meal slot of the logged-in user's plan.

    Accepts JSON {"date", "meal", "itm_id"} or the same form fields. The replacement must
    be in stock, at an open restaurant that serves that meal time, and free of the
    allergens stored on the user's account. Every other slot is left unchanged.
    """
    want_json = request.is_json
    payload = (request.get_json(silent=True) or {}) if want_json else request.form

    def _fail(code, message, status):
        if want_json:
            return jsonify({"ok": False, "error": code, "message": message}), status
        return redirect(url_for("index", swap_error=code))

    if session.get("Username") is None:
        if want_json:
            return jsonify({"ok": False, "error": "login_required"}), 401
        return redirect(url_for("login"))

    slot_date = str(payload.get("date") or "").strip()
    try:
        meal = int(payload.get("meal"))
        slot_weekday_and_time(slot_date, meal)
    except (TypeError, ValueError):
        return _fail("invalid_slot", "Provide a YYYY-MM-DD date and a meal of 1, 2, or 3.", 400)
    try:
        itm_id = int(payload.get("itm_id"))
    except (TypeError, ValueError):
        return _fail("invalid_item", "Provide the itm_id of the replacement item.", 400)

    conn = get_db()
    user = fetch_one(
        conn,
        'SELECT usr_id, allergies, generated_menu, preferences FROM "User" WHERE email = ?',
        (session.get("Email"),),
    )
    if not user:
        return redirect(url_for("logout"))
    usr_id, allergies, menu = user[0], user[1] or "", user[2] or ""
    preferences = user[3] or ""

    current_itm_id = find_slot_item(menu, slot_date, meal)
    if current_itm_id is None:
        return _fail("slot_not_found", "There is no planned meal in that slot.", 404)
    if current_itm_id == itm_id:
        return _fail("same_item", "That item is already planned for this slot.", 400)

    rejection = swap_rejection(
        load_swap_item(conn, itm_id), allergies, slot_date, meal, preferences
    )
    if rejection:
        code, message = rejection
        return _fail(code, message, 404 if code == "item_not_found" else 409)

    try:
        updated_menu = replace_menu_slot(menu, slot_date, meal, itm_id)
    except SlotNotFoundError:
        return _fail("slot_not_found", "There is no planned meal in that slot.", 404)
    execute_query(
        conn, 'UPDATE "User" SET generated_menu = ? WHERE usr_id = ?', (updated_menu, usr_id)
    )

    session["GeneratedMenu"] = updated_menu

    if want_json:
        return jsonify(
            {
                "ok": True,
                "date": slot_date,
                "meal": meal,
                "previous_itm_id": current_itm_id,
                "itm_id": itm_id,
                "generated_menu": updated_menu,
            }
        )
    year, month, _ = slot_date.split("-")
    return redirect(url_for("index", year=int(year), month=int(month), swapped=1))


@app.route("/menu/swap/options")
def swap_meal_options():
    """
    List the items that could replace one planned slot for the logged-in user.

    Query args: date (YYYY-MM-DD) and meal (1|2|3). Only items that pass the same
    availability, allergen and diet checks as POST /menu/swap are returned.
    """
    if session.get("Username") is None:
        return jsonify({"ok": False, "error": "login_required"}), 401

    slot_date = (request.args.get("date") or "").strip()
    try:
        meal = int(request.args.get("meal"))
        slot_weekday_and_time(slot_date, meal)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_slot"}), 400

    conn = get_db()
    user = fetch_one(
        conn,
        'SELECT allergies, generated_menu, preferences FROM "User" WHERE email = ?',
        (session.get("Email"),),
    )
    if not user:
        return jsonify({"ok": False, "error": "login_required"}), 401
    current_itm_id = find_slot_item(user[1] or "", slot_date, meal)
    if current_itm_id is None:
        return jsonify({"ok": False, "error": "slot_not_found"}), 404
    eligible = list_swap_options(
        conn, user[0] or "", slot_date, meal, current_itm_id, user[2] or ""
    )
    # Most varied next to the rest of the plan first (same score as generation)
    eligible = rank_swap_options(
        eligible, variety.catalog_rows(conn), user[1] or "", slot_date, meal, user[2] or ""
    )

    details = fetch_menu_items_by_ids([o["itm_id"] for o in eligible])
    options = [
        {
            "itm_id": o["itm_id"],
            "name": o["name"],
            "restaurant_name": details.get(o["itm_id"], {}).get("restaurant_name", ""),
            "price": details.get(o["itm_id"], {}).get("price"),
            "calories": details.get(o["itm_id"], {}).get("calories"),
            "allergens": o["allergens"] or "",
            "variety": o["variety"],
        }
        for o in eligible
    ]
    return jsonify(
        {
            "ok": True,
            "date": slot_date,
            "meal": meal,
            "current_itm_id": current_itm_id,
            "options": options,
        }
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flask App for Meal Planner")
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to run the Flask app on"
    )
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask app on")
    # Off by default: the Werkzeug debugger lets anyone who can reach the page run code.
    parser.add_argument(
        "--debug", action="store_true", help="Enable auto-reload and the interactive debugger"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    """
    DB column names:

    MenuItem: itm_id,rtr_id,name,description,price,calories,instock,restock,allergens
    Order: ord_id,rtr_id,usr_id,details,status
    Restaurant: rtr_id,name,description,phone,email,password_HS,address,city,state,zip,hours,status
    Review: rev_id,rtr_id,usr_id,title,rating,description,ord_id,created_at
    User: usr_id,first_name,last_name,email,phone,password_HS,wallet,preferences,allergies,generated_menu
    """
    args = parse_args()
    try:  # fail at startup, not on the first request, if the database isn't set up
        connect(app.config["DATABASE"]).close()
    except DatabaseNotInitialisedError as exc:
        raise SystemExit(str(exc))
    app.run(host=args.host, port=args.port, debug=args.debug)
