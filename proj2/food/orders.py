"""Placing orders, My Orders and receipts."""

from io import BytesIO

from flask import abort, jsonify, redirect, render_template, request, send_file, session, url_for

from proj2 import config, wallet
from proj2.customer import account
from proj2.db import db_path, get_db, transaction
from proj2.food.analytics import update_analytics_safe
from proj2.food.blueprint import bp
from proj2.order_history import user_orders
from proj2.ordering import OrderError, build_order, insert_order
from proj2.pdf_receipt import generate_order_receipt_pdf
from proj2.sqlQueries import fetch_one


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


def _place_order(conn, rtr_id, usr_id, details) -> int:
    """
    Charge the customer's wallet for an order and store it, both or neither.
    Args:
        conn (sqlite3.Connection): Open database connection.
        rtr_id (int): The restaurant.
        usr_id (int): The customer.
        details (dict): The order's details; its charges' total is what is taken.
    Returns:
        int: The new order's id.
    Raises:
        wallet.InsufficientFundsError: The wallet holds less than the total.
    """
    cents = wallet.to_cents(details["charges"]["total"])
    with transaction(conn):
        wallet.charge(conn, usr_id, cents)
        return insert_order(conn, usr_id, rtr_id, {**details, "wallet_cents": cents})


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


# Order route (Calendar "Order" button target)
@bp.route("/order", methods=["GET", "POST"])
def order():
    """
    Place an order via JSON (POST) or handle legacy single-item GET flow.
    Args:
        None
    Returns:
        Response: JSON with {'ok', 'ord_id'} on success, or {'ok': False, 'error',
        'message'} with 400/404/409 (see proj2.ordering.build_order), or 402 when the
        wallet cannot cover it. A GET places nothing and redirects to the Restaurants page.
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    # Resolve usr_id strictly
    usr_id = session.get("usr_id")
    if not usr_id:
        conn = get_db()
        row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email = ?', (session.get("Email"),))
        if not row:
            return redirect(url_for("auth.logout"))
        usr_id = row[0]
        session["usr_id"] = usr_id

    # GET /order used to place an order from query arguments; a link or prefetch could
    # buy food. Orders are placed only by POST now.
    if request.method != "POST" or not request.is_json:
        return redirect(url_for("food.restaurants"))

    conn = get_db()
    user = account(conn, usr_id=usr_id)
    if not user:
        return redirect(url_for("auth.logout"))
    try:
        rtr_id, details = build_order(
            conn, user, request.get_json(silent=True) or {}, _order_charges
        )
    except OrderError as err:
        return jsonify({"ok": False, "error": err.code, "message": err.message}), err.status
    try:
        new_ord_id = _place_order(conn, rtr_id, usr_id, details)
    except wallet.InsufficientFundsError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "insufficient_funds",
                    "message": exc.message,
                    "balance_cents": exc.balance_cents,
                    "total_cents": exc.total_cents,
                }
            ),
            402,
        )
    update_analytics_safe(rtr_id)
    return jsonify({"ok": True, "ord_id": new_ord_id})


@bp.route("/orders")
def orders():
    """
    My Orders: the user's orders with their progress, receipts, totals and reviews.
    Browsing menus and the cart live on the Restaurants page.
    Args:
        None
    Returns:
        Response: HTML page listing the user's orders (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    email = session.get("Email")
    if not email:
        return redirect(url_for("auth.logout"))

    conn = get_db()
    row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email = ?', (email,))
    if not row:
        return redirect(url_for("auth.logout"))
    session["usr_id"] = row[0]

    placed = request.args.get("ordered", type=int)
    return render_template("orders.html", orders=user_orders(conn, row[0]), placed=placed)


# Order receipt PDF route
@bp.route("/orders/<int:ord_id>/receipt.pdf")
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
        return redirect(url_for("auth.login"))

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
        urow = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email = ?', (session.get("Email"),))
        if not urow or urow[0] != row[0]:
            abort(403)

    pdf_bytes = generate_order_receipt_pdf(db_path(), ord_id)  # returns bytes

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"order_{ord_id}_receipt.pdf",
    )


@bp.app_context_processor
def inject_order_fees():
    """Expose the fee schedule so cart previews compute the same totals the server bills."""
    return {"order_fees": config.order_fees()}
