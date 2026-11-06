"""Calendar home page: the month view of the user's plan."""

import calendar
from datetime import timedelta, date
from proj2.meal_budget import plan_entries, week_start, weekly_item_totals
from flask import Blueprint, render_template, url_for, redirect, request, session

from proj2.sqlQueries import fetch_one
from proj2.db import get_db
from proj2.planner.meal_plan import (
    build_calendar_cells,
    fetch_menu_items_by_ids,
    parse_generated_menu,
    SWAP_ERROR_MESSAGES,
)

bp = Blueprint("planner", __name__)


# Home route (supports /<year>/<month> for nav)
@bp.route("/", defaults={"year": None, "month": None})
@bp.route("/<int:year>/<int:month>")
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
        return redirect(url_for("auth.login"))

    today = date.today()
    if not year or not month:
        year, month = today.year, today.month

    # Load current user's generated_menu
    conn = get_db()
    user = fetch_one(
        conn, 'SELECT generated_menu FROM "User" WHERE email = ?', (session.get("Email"),)
    )

    if not user:
        return redirect(url_for("auth.logout"))

    gen_str = user["generated_menu"] or ""
    gen_map = parse_generated_menu(gen_str)

    # All item ids referenced (for the whole plan)
    all_item_ids = sorted({e["itm_id"] for entries in gen_map.values() for e in entries})
    items_by_id = fetch_menu_items_by_ids(all_item_ids)

    # Show item totals for weeks represented in this calendar month.
    item_totals = {}
    item_total_error = None
    try:
        visible_weeks = sorted(
            {week_start(day) for day in gen_map if day.startswith(f"{year:04d}-{month:02d}-")}
        )
        visible_week_item_ids = {
            item_id for day, item_id, _ in plan_entries(gen_str) if week_start(day) in visible_weeks
        }
        totals_by_item = fetch_menu_items_by_ids(sorted(visible_week_item_ids))
        item_totals = weekly_item_totals(
            gen_str,
            {item: data["price"] for item, data in totals_by_item.items()},
            visible_weeks,
        )
    except ValueError:
        item_total_error = (
            "Item totals are unavailable because a planned meal or its price is missing."
        )

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
        swap_notice = (
            "danger",
            SWAP_ERROR_MESSAGES.get(
                request.args.get("swap_error"), "That meal could not be swapped."
            ),
        )

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
    )
