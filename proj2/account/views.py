"""The customer's profile page, profile edits and password change."""

from proj2.order_progress import order_progress
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Blueprint, render_template, url_for, redirect, request, session

from proj2.sqlQueries import fetch_one, fetch_all, execute_query
from proj2.db import get_db

bp = Blueprint("account", __name__)


# Profile route
@bp.route("/profile")
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
        return redirect(url_for("auth.login"))

    # Load the full user row by session email
    email = session.get("Email")
    if not email:
        return redirect(url_for("auth.logout"))

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
        return redirect(url_for("auth.logout"))

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
        has_review = (
            fetch_one(
                conn,
                'SELECT 1 FROM "Review" WHERE ord_id = ?',
                (ord_id,),
            )
            is not None
        )

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
        "profile.html",
        user=user,
        orders=orders,
        pw_updated=pw_updated,
        pw_error=pw_error,
        generation_error=session.pop("menu_generation_error", None),
    )


# Edit Profile route
@bp.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    """
    Display and process the profile edit form (phone, preferences, allergies).
    Args:
        None
    Returns:
        Response: Renders form (GET) or updates and redirects to profile (POST).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("auth.logout"))

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
        return redirect(url_for("auth.logout"))

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

        return redirect(url_for("account.profile"))

    return render_template("edit_profile.html", user=user)


@bp.route("/profile/change-password", methods=["POST"])
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
        return redirect(url_for("auth.login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        # Fallback: resolve via email
        email = session.get("Email")
        if not email:
            return redirect(url_for("auth.logout"))
        conn = get_db()
        row = fetch_one(conn, 'SELECT usr_id FROM "User" WHERE email = ?', (email,))
        if not row:
            return redirect(url_for("auth.logout"))
        usr_id = row[0]
        session["usr_id"] = usr_id

    # Read form fields
    current_password = (request.form.get("current_password") or "").strip()
    new_password = (request.form.get("new_password") or "").strip()
    confirm_password = (request.form.get("confirm_password") or "").strip()

    # Basic validations (mirror your frontend behavior)
    if not current_password:
        return redirect(url_for("account.profile", pw_error="missing_current"))
    if len(new_password) < 6:
        return redirect(url_for("account.profile", pw_error="too_short"))
    if new_password != confirm_password:
        return redirect(url_for("account.profile", pw_error="mismatch"))
    if new_password == current_password:
        return redirect(url_for("account.profile", pw_error="same_as_current"))

    # Verify current hash & update to new hash
    conn = get_db()
    row = fetch_one(conn, 'SELECT password_HS FROM "User" WHERE usr_id = ?', (usr_id,))
    if not row:
        return redirect(url_for("auth.logout"))

    stored_hash = row[0]
    if not check_password_hash(stored_hash, current_password):
        # wrong current password
        return redirect(url_for("account.profile", pw_error="incorrect_current"))

    # All good → update
    new_hash = generate_password_hash(new_password)
    execute_query(conn, 'UPDATE "User" SET password_HS = ? WHERE usr_id = ?', (new_hash, usr_id))

    # Success
    return redirect(url_for("account.profile", pw_updated=1))
