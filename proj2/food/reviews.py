"""Customers' reviews of orders, and a restaurant's public reviews."""

import json
import math
from datetime import datetime

from flask import abort, redirect, render_template, request, session, url_for

from proj2.db import get_db
from proj2.food.blueprint import bp
from proj2.sqlQueries import execute_query, fetch_all, fetch_one


# ==================== Review Routes ====================
def user_review(conn, ord_id, usr_id):
    """
    The user's review of one order, with the restaurant's name.
    Args:
        conn: Open database connection.
        ord_id (int): The order ID.
        usr_id (int): The reviewing user.
    Returns:
        dict | None: The review's fields, or None if the user has not reviewed it.
    """
    row = fetch_one(
        conn,
        """
        SELECT r.rev_id, r.rtr_id, r.ord_id, r.title, r.rating, r.description, r.created_at,
               rest.name
        FROM "Review" r
        JOIN "Restaurant" rest ON r.rtr_id = rest.rtr_id
        WHERE r.ord_id = ? AND r.usr_id = ?
        """,
        (ord_id, usr_id),
    )
    if not row:
        return None
    keys = (
        "rev_id",
        "rtr_id",
        "ord_id",
        "title",
        "rating",
        "description",
        "created_at",
        "restaurant_name",
    )
    return dict(zip(keys, row))


@bp.route("/order/<int:ord_id>/review", methods=["GET", "POST"])
def review_order(ord_id):
    """
    The review page for one order: the form until the order is reviewed, then the review.
    Args:
        ord_id (int): The order ID.
    Returns:
        Response: The form or the written review (GET), or a redirect back to this
        page once a review is saved (POST).
    """
    # Must be logged in
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("auth.logout"))

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
        return redirect(url_for("food.orders"))

    ord_id_db, rtr_id, details, status, r_name = order_row

    # Already reviewed: show the review (a second POST changes nothing)
    review = user_review(conn, ord_id, usr_id)
    if review:
        if request.method == "POST":
            return redirect(url_for("food.review_order", ord_id=ord_id))
        return render_template("review.html", review=review)
    if fetch_one(conn, 'SELECT 1 FROM "Review" WHERE ord_id = ?', (ord_id,)):
        return redirect(url_for("food.orders"))

    # Must be delivered to review
    if status.lower() != "delivered":
        return redirect(url_for("food.orders"))

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
            return render_template("review.html", order=order, error="Please select a rating")

        try:
            rating_int = int(rating)
            if rating_int < 1 or rating_int > 5:
                raise ValueError
        except ValueError:
            return render_template("review.html", order=order, error="Invalid rating value")

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

        return redirect(url_for("food.review_order", ord_id=ord_id))

    # GET - Show form
    return render_template("review.html", order=order)


@bp.route("/order/<int:ord_id>/review/view")
def view_review(ord_id):
    """
    Old address of a written review, kept so saved links still work.
    Args:
        ord_id (int): The order ID.
    Returns:
        Response: Redirect to the order's review page.
    """
    return redirect(url_for("food.review_order", ord_id=ord_id))


@bp.route("/restaurant/<int:rtr_id>/reviews")
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
    restaurant_row = fetch_one(conn, 'SELECT name FROM "Restaurant" WHERE rtr_id = ?', (rtr_id,))
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
