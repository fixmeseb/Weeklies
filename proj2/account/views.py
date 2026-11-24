"""The customer's profile page, profile edits and password change."""

import json

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from proj2 import meal_times, variety
from proj2.customer import (
    DIET_OPTIONS,
    _csv_list,
    account,
    diet_summary,
    profile_weights,
    submitted_diet_constraints,
    submitted_weights,
)
from proj2.db import get_db
from proj2.dietary import required_diets
from proj2.meal_budget import parse_weekly_cap
from proj2.order_history import user_orders
from proj2.ordering import delivery_address
from proj2.plan_optimization import OBJECTIVES
from proj2.sqlQueries import execute_query, fetch_one

bp = Blueprint("account", __name__)


# Profile route
@bp.route("/profile")
def profile():
    """
    Show the logged-in user's account: details, allergies, preferences and password.
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

    conn = get_db()
    row = account(conn, email=email)
    if not row:
        return redirect(url_for("auth.logout"))

    user = {
        "usr_id": row["usr_id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
        "phone": row["phone"],
        "wallet": (row["wallet"] or 0) / 100.0,
        "preferences": row["preferences"] or "",
        "allergies": row["allergies"] or "",
        "address": row["address"] or "",
        "city": row["city"] or "",
        "state": row["state"] or "",
        "zip": row["zip"] or "",
    }
    times = meal_times.times_for(row)

    session["usr_id"] = user["usr_id"]

    pw_updated = request.args.get("pw_updated")
    pw_error = request.args.get("pw_error")

    recent = user_orders(conn, user["usr_id"])
    food_matches = [tag for tag in _csv_list(user["preferences"]) if variety.soft_preferences(tag)]
    cap = row["weekly_cap_cents"]
    selected_diets = required_diets(user["preferences"])
    return render_template(
        "profile.html",
        user=user,
        diet=diet_summary(conn, user["allergies"], user["preferences"]),
        last_order=recent[0] if recent else None,
        optimization_objectives=OBJECTIVES,
        optimization_weights=profile_weights(row["optimization_weights"], user["preferences"]),
        food_matches=", ".join(food_matches),
        diet_options=DIET_OPTIONS,
        selected_diets=selected_diets,
        selected_diet_labels=[DIET_OPTIONS[code] for code in sorted(selected_diets)],
        weekly_cap=f"{cap // 100}.{cap % 100:02d}" if cap is not None else "",
        diet_notice=session.pop("diet_notice", None),
        pw_updated=pw_updated,
        pw_error=pw_error,
        address_line=delivery_address(row),
        times_text={meal: meal_times.as_text(t) for meal, t in times.items()},
        times_display={meal: meal_times.as_display(t) for meal, t in times.items()},
        times_error=session.pop("meal_times_error", None),
        times_saved=bool(request.args.get("times_saved")),
    )


@bp.post("/profile/optimization")
def save_optimization():
    """Save the account's selected objectives and relative weights."""
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    try:
        weights = submitted_weights()
    except ValueError as exc:
        session["diet_notice"] = ("danger", str(exc))
    else:
        execute_query(
            get_db(),
            'UPDATE "User" SET optimization_weights = ? WHERE email = ?',
            (json.dumps(weights), session.get("Email")),
        )
        session["diet_notice"] = ("success", "Optimization preferences saved.")
    return redirect(url_for("account.profile", _anchor="optimization-preferences"))


# Edit Profile route
@bp.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    """
    Save the profile's phone, preferences, or allergies.
    Args:
        None
    Returns:
        Response: Redirect to the profile after saving (POST), or to the profile with
        the pop-up open (GET, for old links to the separate edit page).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("auth.logout"))

    conn = get_db()
    row = fetch_one(
        conn,
        'SELECT usr_id FROM "User" WHERE usr_id = ?',
        (usr_id,),
    )

    if not row:
        return redirect(url_for("auth.logout"))

    if request.method == "POST":
        if "diet_constraints" in request.form:
            return save_diet_settings(conn, usr_id)

        # Older clients can still submit the original CSV fields. The form updates only
        # the columns it sends, so it cannot overwrite a concurrent diet edit; a field
        # sent empty clears it (that is how allergies or a delivery address are removed).
        fields = {"phone": request.form.get("phone") or None}
        fields.update(
            {
                name: request.form.get(name)
                for name in ("preferences", "allergies", "address", "city", "state", "zip")
            }
        )
        updates = {name: value.strip() for name, value in fields.items() if value is not None}
        if updates:
            assignments = ", ".join(f"{name} = ?" for name in updates)
            execute_query(
                conn,
                f'UPDATE "User" SET {assignments} WHERE usr_id = ?',
                (*updates.values(), usr_id),
            )
            session.update(
                {
                    name.title(): value
                    for name, value in updates.items()
                    if name in ("phone", "preferences", "allergies")
                }
            )
        anchor = "diet" if request.form.get("section") == "diet" else None
        return redirect(url_for("account.profile", _anchor=anchor))

    return redirect(url_for("account.profile", _anchor="edit"))


def save_diet_settings(conn, usr_id):
    """Validate both groups before committing any Diet settings."""
    allergies, diets = submitted_diet_constraints()
    food_matches = [
        tag for tag in _csv_list(request.form.get("food_matches")) if variety.soft_preferences(tag)
    ]
    preferences = ", ".join(filter(None, (diets, ", ".join(food_matches))))
    try:
        cap = parse_weekly_cap(request.form.get("weekly_cap"))
        weights = submitted_weights()
        if weights.get("preference") and not food_matches:
            raise ValueError("Enter foods to match or set the food-match slider to zero.")
    except ValueError as exc:
        session["diet_notice"] = ("danger", str(exc))
    else:
        # Record an explicit zero so clearing the sliders doesn't restore legacy food matching.
        weights.setdefault("preference", 0)
        execute_query(
            conn,
            """UPDATE "User" SET allergies = ?, preferences = ?, weekly_cap_cents = ?,
               optimization_weights = ? WHERE usr_id = ?""",
            (allergies, preferences, cap, json.dumps(weights), usr_id),
        )
        session.update({"Allergies": allergies, "Preferences": preferences})
        session["diet_notice"] = ("success", "Diet settings saved.")
    return redirect(url_for("account.profile", _anchor="diet"))


@bp.route("/profile/meal-times", methods=["POST"])
def save_meal_times():
    """
    Save when the user eats breakfast, lunch and dinner (proj2/meal_times.py).

    Form fields breakfast_time, lunch_time and dinner_time as HH:MM. Plans, swaps and
    orders check that restaurants are open at these times.
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    usr_id = session.get("usr_id")
    if not usr_id:
        return redirect(url_for("auth.logout"))
    try:
        times = {
            meal: meal_times.parse_time(request.form.get(column))
            for meal, (_name, column, _default) in meal_times.MEALS.items()
        }
        meal_times.check_order(times)
    except meal_times.MealTimeError as err:
        session["meal_times_error"] = str(err)
        return redirect(url_for("account.profile", _anchor="meal-times"))
    execute_query(
        get_db(),
        'UPDATE "User" SET breakfast_time = ?, lunch_time = ?, dinner_time = ? WHERE usr_id = ?',
        (times[1], times[2], times[3], usr_id),
    )
    return redirect(url_for("account.profile", times_saved=1, _anchor="meal-times"))


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
