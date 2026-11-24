"""Browsing restaurants and their menus."""

import json
from datetime import datetime

from flask import redirect, render_template, session, url_for

from proj2.customer import _csv_list
from proj2.db import get_db
from proj2.food.blueprint import bp
from proj2.hours import format_hours
from proj2.menu_generation import DAYS_OF_WEEK
from proj2.plan_rules import is_restaurant_open, parse_allergens
from proj2.sqlQueries import fetch_all, fetch_one


# Restaurants browse route
@bp.route("/restaurants")
def restaurants():
    """
    Browse restaurants with details and currently in-stock items.
    Args:
        None
    Returns:
        Response: HTML page listing restaurants and their items (requires login).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

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

    user_row = fetch_one(
        conn, 'SELECT allergies, wallet FROM "User" WHERE email = ?', (session.get("Email"),)
    )
    user_allergies = (user_row[0] if user_row else "") or ""
    wallet_cents = (user_row[1] if user_row else 0) or 0
    banned = parse_allergens(user_allergies)
    for it in item_list:
        it["conflicts"] = sorted(banned & parse_allergens(it["allergens"]))

    stats = {
        rtr_id: (count, avg)
        for rtr_id, count, avg in fetch_all(
            conn, 'SELECT rtr_id, COUNT(*), AVG(rating) FROM "Review" GROUP BY rtr_id'
        )
    }
    now = datetime.now()
    for r in rest_list:
        count, avg = stats.get(r["rtr_id"], (0, None))
        r["review_count"] = count
        r["rating"] = round(avg, 1) if avg is not None else None
        r["open_now"] = open_now(r["hours"], r["status"], now)

    return render_template(
        "restaurants.html",
        restaurants=rest_list,
        items=item_list,
        user_allergies=_csv_list(user_allergies),
        wallet_cents=wallet_cents,
    )


def open_now(hours, status, now):
    """
    Whether a restaurant is open at a moment, for the Restaurants page's "Open now" filter.
    Args:
        hours (str): The stored hours JSON, e.g. '{"Mon": [1100, 2200], ...}'.
        status (str): The restaurant's status; "closed" means closed whatever the hours.
        now (datetime): The moment to check.
    Returns:
        bool | None: True or False from the hours, or None when the hours are not JSON
        (then the page cannot tell and does not hide the restaurant).
    """
    if (status or "").strip().lower() == "closed":
        return False
    try:
        parsed = json.loads(hours)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return is_restaurant_open(hours, DAYS_OF_WEEK[now.weekday()], now.hour * 100 + now.minute)
