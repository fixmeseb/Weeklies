"""The calendar home page and the insights page."""

import calendar
from datetime import date, timedelta

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from proj2 import almanac, meal_times, variety
from proj2.customer import account
from proj2.db import get_db
from proj2.meal_budget import plan_entries
from proj2.nutrition import form_values, load_saved_targets
from proj2.order_history import order_meals
from proj2.ordering import delivery_address
from proj2.plan_optimization import OBJECTIVES
from proj2.planner.meal_plan import (
    SWAP_ERROR_MESSAGES,
    build_calendar_cells,
    calendar_week_variety,
    fetch_menu_items_by_ids,
    month_item_totals,
    month_nav,
    parse_generated_menu,
    shown_week,
    week_variety,
)
from proj2.sqlQueries import fetch_one

bp = Blueprint("planner", __name__)


def _requested_day():
    """?week=YYYY-MM-DD as a date, or None if it is missing or not a usable date."""
    try:
        day = date.fromisoformat(request.args.get("week", ""))
    except ValueError:
        return None
    return day if 1 < day.year < 9999 else None  # room for the weeks either side


def _check_month(year, month):
    """Not found (404) for a month that does not exist or has no month either side of it."""
    if not (1 <= month <= 12 and 1 < year < 9999):
        abort(404)


@bp.route("/", defaults={"year": None, "month": None})
@bp.route("/<int:year>/<int:month>")
def index(year, month):
    """
    Render the calendar home view for the current or specified month. The Almanac style
    draws one week instead: the one holding ?week=YYYY-MM-DD (see shown_week).
    Args:
        year (int | None): Optional year path parameter.
        month (int | None): Optional month path parameter (1–12). Without them, the month
            of ?week, else the current month.
    Returns:
        Response: HTML page showing the plan and today's meals (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    today = date.today()
    requested_day = _requested_day()
    if not year or not month:
        shown_day = requested_day or today
        year, month = shown_day.year, shown_day.month
    _check_month(year, month)

    # Load current user's generated_menu, and the targets the plan form opens with
    conn = get_db()
    user = account(conn, email=session.get("Email"))

    if not user:
        return redirect(url_for("auth.logout"))
    # Planned meals whose dish is on an order for that day and meal (not cancelled), as
    # "YYYY-MM-DD|meal". Another dish ordered at that time does not count.
    planned = set(plan_entries(user["generated_menu"] or ""))
    ordered_slots = sorted(
        {
            f"{day}|{meal}"
            for day, itm_id, meal in order_meals(conn, user["usr_id"])
            if (day, itm_id, meal) in planned
        }
    )
    times = meal_times.times_for(user)

    gen_str = user["generated_menu"] or ""
    gen_map = parse_generated_menu(gen_str)

    # All item ids referenced (for the whole plan)
    all_item_ids = sorted({e["itm_id"] for entries in gen_map.values() for e in entries})
    items_by_id = fetch_menu_items_by_ids(all_item_ids)

    # One week drawn as an almanac page, for the "Seed Catalog & Almanac" style
    week = shown_week(requested_day, gen_str, year, month, today)
    weekly_variety = week_variety(conn, gen_str, [week.isoformat()], items_by_id)
    almanac_weeks = (
        almanac.build_weeks(
            plan_entries(gen_str), items_by_id, variety.catalog_rows(conn), weekly_variety
        )
        if weekly_variety
        else []
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

    prev_year, prev_month, next_year, next_month = month_nav(year, month)

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
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        calendar_cells=cells,
        today_year=today.year,
        today_month=today.month,
        today_day=today.day,
        today_menu=today_menu,
        generation_error=session.pop("menu_generation_error", None),
        almanac_weeks=almanac_weeks,
        week_title=almanac.week_title(week),
        prev_week=(week - timedelta(days=7)).isoformat(),
        next_week=(week + timedelta(days=7)).isoformat(),
        optimization=session.pop("menu_optimization", None),
        optimization_objectives=OBJECTIVES,
        # The plan form opens with the targets last planned with (see generate_menu)
        target_values=form_values(load_saved_targets(user["nutrition_targets"])),
        strict_saved=bool(user["strict_targets"]),
        saved_weekly_cap=user["weekly_cap_cents"],
        ordered_slots=ordered_slots,
        plan_notice=session.pop("plan_notice", None),
        delivery_to=delivery_address(user),
        meal_time_labels={meal: meal_times.as_display(t) for meal, t in times.items()},
    )


@bp.route("/insights", defaults={"year": None, "month": None})
@bp.route("/insights/<int:year>/<int:month>")
def insights(year, month):
    """
    The Insights tab: item totals and variety of the weeks planned in a month.
    Args:
        year (int | None): Optional year path parameter.
        month (int | None): Optional month path parameter (1–12).
    Returns:
        Response: HTML page (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    today = date.today()
    if not year or not month:
        year, month = today.year, today.month
    _check_month(year, month)

    conn = get_db()
    user = fetch_one(
        conn, 'SELECT generated_menu FROM "User" WHERE email = ?', (session.get("Email"),)
    )
    if not user:
        return redirect(url_for("auth.logout"))
    gen_str = user["generated_menu"] or ""
    gen_map = parse_generated_menu(gen_str)
    item_ids = sorted({e["itm_id"] for entries in gen_map.values() for e in entries})
    items_by_id = fetch_menu_items_by_ids(item_ids)
    item_totals, item_total_error = month_item_totals(gen_str, gen_map, year, month)
    prev_year, prev_month, next_year, next_month = month_nav(year, month)
    return render_template(
        "insights.html",
        month_name=calendar.month_name[month],
        year=year,
        month=month,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        weekly_item_totals=item_totals,
        item_total_error=item_total_error,
        weekly_variety=calendar_week_variety(conn, gen_str, year, month, items_by_id),
    )
