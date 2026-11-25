"""The owner's order queue and reviews, and the banner over the owner pages."""

import json
from datetime import datetime

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from proj2 import wallet
from proj2.db import get_db, transaction
from proj2.food.analytics import update_analytics_safe
from proj2.food.blueprint import bp
from proj2.food.owner_auth import restaurant_required
from proj2.order_history import _order_for
from proj2.ordering import set_status
from proj2.request_data import page_number
from proj2.sqlQueries import fetch_all, fetch_one


@bp.route("/restaurant/dashboard")
@restaurant_required
def restaurant_dashboard():
    """
    Old landing page for owners, kept so saved links still work.
    Owners now land on the Orders page; the banner's tabs reach Analytics and Reviews.
    Returns:
        Response: Redirect to the Orders page.
    """
    return redirect(url_for("food.restaurant_orders"))


# Order statuses still in progress, counted on the banner's Orders tab
ACTIVE_ORDER_STATUSES = ("Ordered", "Accepted", "Preparing", "Ready")


@bp.app_context_processor
def inject_owner_nav():
    """
    Give the owner banner (templates/_owner_header.html) its tab notes: how many
    orders are in progress, how many dishes are on the menu, and the review rating.
    Returns:
        dict: {"owner_nav": {...}} on restaurant-owner pages, else {"owner_nav": None}.
    """
    if not session.get("restaurant_mode") or not session.get("rtr_id"):
        return {"owner_nav": None}
    if request.endpoint not in (
        "food.restaurant_orders",
        "food.restaurant_analytics",
        "food.restaurant_owner_reviews",
        "food.restaurant_menu",
        "food.restaurant_menu_new",
        "food.restaurant_menu_edit",
        "food.restaurant_menu_delete",
    ):
        return {"owner_nav": None}
    rtr_id = session.get("rtr_id")
    conn = get_db()
    marks = ",".join("?" for _ in ACTIVE_ORDER_STATUSES)
    active = fetch_one(
        conn,
        f'SELECT COUNT(*) FROM "Order" WHERE rtr_id = ? AND status IN ({marks})',
        (rtr_id, *ACTIVE_ORDER_STATUSES),
    )
    stats = fetch_one(
        conn, 'SELECT COUNT(*), AVG(rating) FROM "Review" WHERE rtr_id = ?', (rtr_id,)
    )
    dishes = fetch_one(conn, 'SELECT COUNT(*) FROM "MenuItem" WHERE rtr_id = ?', (rtr_id,))
    return {
        "owner_nav": {
            "active_orders": active[0] if active else 0,
            "total_reviews": stats[0] if stats else 0,
            "average_rating": float(stats[1]) if stats and stats[1] else 0.0,
            "menu_items": dishes[0] if dishes else 0,
        }
    }


@bp.route("/restaurant/orders")
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
        except (TypeError, ValueError):
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
            "for": _order_for(details_json),
            "due_at": details.get("due_at", ""),
            "deliver_to": details.get("deliver_to", ""),
        }

        if status in orders_by_status:
            orders_by_status[status].append(order_obj)
        else:
            orders_by_status.setdefault("Other", []).append(order_obj)

    # Orders still to make come soonest-due first; orders without a due time keep
    # their newest-first place after them.
    for status in ("Ordered", "Accepted", "Preparing", "Ready"):
        if status in orders_by_status:
            orders_by_status[status].sort(key=lambda o: (not o["due_at"], o["due_at"]))

    return render_template(
        "restaurant_orders.html",
        restaurant_name=restaurant_name,
        restaurant_email=restaurant_email,
        orders_by_status=orders_by_status,
        status_counts={k: len(v) for k, v in orders_by_status.items()},
    )


@bp.route("/restaurant/reviews")
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
    sort = request.args.get("sort", "recent")
    filter_rating = request.args.get("filter", "all")

    per_page = 10

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
    page, total_pages = page_number(total_reviews, per_page)
    offset = (page - 1) * per_page

    # Calculate average rating
    avg_row = fetch_one(conn, 'SELECT AVG(rating) FROM "Review" WHERE rtr_id = ?', (rtr_id,))
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
    for (
        rev_id,
        title,
        rating,
        description,
        created_at,
        ord_id,
        first_name,
        last_name,
    ) in review_rows:
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


# ---------------------- Restaurant Order Management Routes ----------------------
@bp.route("/restaurant/orders/<int:ord_id>/accept", methods=["POST"])
@restaurant_required
def restaurant_accept_order(ord_id):
    """
    Accept a pending order (Ordered → Accepted).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    # Verify order belongs to this restaurant
    order = fetch_one(conn, 'SELECT ord_id, rtr_id FROM "Order" WHERE ord_id = ?', (ord_id,))

    if not order:
        abort(404)

    if order[1] != rtr_id:
        abort(403)  # Not this restaurant's order

    # The status is checked by the same statement that changes it, so an order cancelled
    # (and refunded) meanwhile is not moved on. The steps below do the same.
    if not set_status(conn, ord_id, "Accepted", only_from=("Ordered",)):
        return (
            jsonify({"ok": False, "error": "Order not in pending state"}),
            400,
        )

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    # Return JSON for AJAX or redirect for full page
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Accepted"})
    else:
        return redirect(url_for("food.restaurant_orders"))


@bp.route("/restaurant/orders/<int:ord_id>/reject", methods=["POST"])
@restaurant_required
def restaurant_reject_order(ord_id):
    """
    Reject a pending order (Ordered → Cancelled) and refund the customer's wallet.
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(
        conn,
        'SELECT ord_id, rtr_id, status, usr_id, details FROM "Order" WHERE ord_id = ?',
        (ord_id,),
    )

    if not order or order[1] != rtr_id:
        abort(403)

    # The status is checked by the same statement that changes it, so cancelling twice at
    # once refunds only once.
    with transaction(conn):
        cancelled = set_status(
            conn, ord_id, "Cancelled", only_from=("Ordered", "Accepted", "Preparing")
        )
        if cancelled:
            wallet.refund_order(conn, order[3], order[4])
    if not cancelled:
        return (
            jsonify({"ok": False, "error": "Cannot cancel at this stage"}),
            400,
        )

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Cancelled"})
    else:
        return redirect(url_for("food.restaurant_orders"))


@bp.route("/restaurant/orders/<int:ord_id>/prepare", methods=["POST"])
@restaurant_required
def restaurant_prepare_order(ord_id):
    """
    Mark order as being prepared (Accepted → Preparing).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(conn, 'SELECT ord_id, rtr_id FROM "Order" WHERE ord_id = ?', (ord_id,))

    if not order or order[1] != rtr_id:
        abort(403)

    if not set_status(conn, ord_id, "Preparing", only_from=("Accepted",)):
        return (
            jsonify({"ok": False, "error": "Order must be accepted first"}),
            400,
        )

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Preparing"})
    else:
        return redirect(url_for("food.restaurant_orders"))


@bp.route("/restaurant/orders/<int:ord_id>/ready", methods=["POST"])
@restaurant_required
def restaurant_ready_order(ord_id):
    """
    Mark order as ready for pickup/delivery (Preparing → Ready).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(conn, 'SELECT ord_id, rtr_id FROM "Order" WHERE ord_id = ?', (ord_id,))

    if not order or order[1] != rtr_id:
        abort(403)

    if not set_status(conn, ord_id, "Ready", only_from=("Preparing",)):
        return (
            jsonify({"ok": False, "error": "Order must be preparing first"}),
            400,
        )

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Ready"})
    else:
        return redirect(url_for("food.restaurant_orders"))


@bp.route("/restaurant/orders/<int:ord_id>/deliver", methods=["POST"])
@restaurant_required
def restaurant_deliver_order(ord_id):
    """
    Mark order as delivered/completed (Ready → Delivered).
    """
    rtr_id = session.get("rtr_id")

    conn = get_db()
    order = fetch_one(conn, 'SELECT ord_id, rtr_id FROM "Order" WHERE ord_id = ?', (ord_id,))

    if not order or order[1] != rtr_id:
        abort(403)

    if not set_status(conn, ord_id, "Delivered", only_from=("Ready",)):
        return (
            jsonify({"ok": False, "error": "Order must be ready first"}),
            400,
        )

    # Update analytics for this restaurant
    update_analytics_safe(rtr_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "new_status": "Delivered"})
    else:
        return redirect(url_for("food.restaurant_orders"))
