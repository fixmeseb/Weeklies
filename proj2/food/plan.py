"""Changing the meal plan: generate, remove, clear, order and swap."""

from datetime import date, timedelta

from flask import current_app, jsonify, redirect, request, session, url_for

from proj2 import meal_times, plan_edit, variety, wallet
from proj2.customer import account, configured_weights
from proj2.db import db_path, get_db
from proj2.dietary import required_diets, with_account_allergies, with_account_diets
from proj2.food.analytics import update_analytics_safe
from proj2.food.blueprint import bp
from proj2.food.orders import _order_charges, _place_order
from proj2.meal_budget import (
    BudgetExceededError,
    parse_weekly_cap,
    plan_entries,
    week_start,
    weekly_item_totals,
)
from proj2.meal_swap import (
    SlotNotFoundError,
    find_slot_item,
    list_swap_options,
    load_swap_item,
    rank_swap_options,
    replace_menu_slot,
    slot_weekday_and_time,
    swap_fits_budget,
    swap_price_limit,
    swap_rejection,
)
from proj2.menu_generation import MenuGenerator
from proj2.nutrition import (
    TargetsUnreachableError,
    nutrition_notice,
    parse_targets,
    saved_targets_json,
)
from proj2.order_history import order_meals
from proj2.ordering import OrderError, build_order
from proj2.plan_optimization import OBJECTIVES, parse_weights
from proj2.plan_rules import SLOT_NAMES
from proj2.planner.meal_plan import SWAP_ERROR_MESSAGES, fetch_menu_items_by_ids
from proj2.sqlQueries import execute_query, fetch_all, fetch_one


def save_generated_plan(conn, user, updated_menu):
    """Persist a plan only if its starting plan and account constraints are still current."""
    return (
        execute_query(
            conn,
            """UPDATE "User" SET generated_menu = ? WHERE usr_id = ?
           AND generated_menu IS ? AND allergies IS ? AND preferences IS ?
           AND weekly_cap_cents IS ? AND optimization_weights IS ?""",
            (
                updated_menu,
                user["usr_id"],
                user["generated_menu"],
                user["allergies"],
                user["preferences"],
                user["weekly_cap_cents"],
                user["optimization_weights"],
            ),
        ).rowcount
        == 1
    )


# ----------- Meal Plan Generation Route -----------
@bp.route("/menu/generate", methods=["POST"])
def generate_menu():
    """
    Generate or extend the logged-in user's meal plan and persist it.

    Supports application/json and HTML form submissions.
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    # Load user row (need preferences, allergies, existing generated_menu)
    conn = get_db()
    user = fetch_one(
        conn,
        'SELECT usr_id, email, preferences, allergies, generated_menu, optimization_weights, weekly_cap_cents FROM "User" WHERE email = ?',
        (session.get("Email"),),
    )

    if not user:
        return redirect(url_for("auth.logout"))
    times = meal_times.times_for(account(conn, usr_id=user[0]))

    usr_id = user[0]
    prefs_db = user[2] or ""
    allergies_db = user[3] or ""
    existing_menu = user[4] or ""

    # Parse inputs
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        start_date = (payload.get("start_date") or date.today().isoformat()).strip()
        try:
            meal_numbers = [int(x) for x in (payload.get("meal_numbers") or [1, 2, 3])]
        except Exception:
            meal_numbers = [1, 2, 3]
        try:
            number_of_days = int(payload.get("number_of_days") or 1)
        except Exception:
            number_of_days = 1
        preferences = (payload.get("preferences") or prefs_db).strip()
        allergies = (payload.get("allergens") or allergies_db).strip()
    else:
        start_date = (request.form.get("start_date") or date.today().isoformat()).strip()
        try:
            number_of_days = int(request.form.get("days") or 1)
        except Exception:
            number_of_days = 1
        sel = []
        if request.form.get("meal1"):
            sel.append(1)
        if request.form.get("meal2"):
            sel.append(2)
        if request.form.get("meal3"):
            sel.append(3)
        meal_numbers = sel or [1, 2, 3]
        preferences = (request.form.get("preferences") or prefs_db).strip()
        allergies = (request.form.get("allergens") or allergies_db).strip()
    replace = bool(payload.get("replace")) if request.is_json else bool(request.form.get("replace"))

    # Diets and allergies on the account are hard rules; a request can add to them but not drop them.
    preferences = with_account_diets(preferences, prefs_db)
    allergies = with_account_allergies(allergies, allergies_db)

    want_json = request.is_json or request.accept_mimetypes.best == "application/json"

    def generation_error(message, status):
        if want_json:
            return jsonify({"ok": False, "error": message}), status
        session["menu_generation_error"] = message
        return redirect(url_for("planner.index", _anchor="new-plan"))

    try:
        cap_value = payload.get("weekly_cap") if request.is_json else request.form.get("weekly_cap")
        caps = (parse_weekly_cap(cap_value), user["weekly_cap_cents"])
        weekly_cap_cents = min((cap for cap in caps if cap is not None), default=None)
        fields = payload if request.is_json else request.form
        explicit_weights = any(f"{name}_weight" in fields for name in OBJECTIVES)
        if explicit_weights:
            objective_weights = parse_weights(
                tuple(fields.get(f"{name}_weight") for name in OBJECTIVES)
            )
        else:
            objective_weights = configured_weights(user["optimization_weights"], preferences)
        if objective_weights is None and not explicit_weights:
            preferences = ", ".join(sorted(required_diets(preferences)))
        targets = parse_targets(fields)
        strict_targets = str(fields.get("strict_targets", "")).strip().lower() in (
            "1",
            "true",
            "on",
            "yes",
        )
    except ValueError as exc:
        return generation_error(str(exc), 400)

    # The plan form (sent as form data, also by its fetch) remembers its targets on the
    # account so it opens with them next time, even if this plan is refused. A JSON
    # client changes them only by asking ("save_targets": true).
    from_form = not request.is_json
    if from_form or payload.get("save_targets") in (True, "true", "1", 1):
        execute_query(
            get_db(),
            'UPDATE "User" SET nutrition_targets = ?, strict_targets = ? WHERE usr_id = ?',
            (saved_targets_json(targets), int(strict_targets), usr_id),
        )

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

    # "Replace" re-plans the chosen meals on these days instead of only filling gaps.
    if replace:
        first, last = plan_edit.days_range(start_date, number_of_days)
        existing_menu, _ = plan_edit.clear_days(existing_menu, first, last, meal_numbers)

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
            ordered_meals=order_meals(conn, usr_id),
            objective_weights=objective_weights,
            targets=targets,
            strict_targets=strict_targets,
            meal_times=times,
        )
        start = date.fromisoformat(start_date)
        weeks = list(
            dict.fromkeys(
                week_start((start + timedelta(days=i)).isoformat()) for i in range(number_of_days)
            )
        )
        try:
            totals = weekly_item_totals(updated_menu, gen.item_prices, weeks)
        except ValueError:
            if weekly_cap_cents is not None:
                raise
            # Uncapped plans can retain old meals whose catalog prices are unavailable.
            totals = None
    except (BudgetExceededError, TargetsUnreachableError) as exc:
        return generation_error(str(exc), 422)
    except ValueError as exc:
        return generation_error(str(exc), 400)
    except Exception:
        current_app.logger.exception("Menu generation failed")
        return generation_error("Menu generation failed. Please try again.", 500)

    if not save_generated_plan(conn, user, updated_menu):
        return generation_error(SWAP_ERROR_MESSAGES["plan_changed"], 409)

    session["GeneratedMenu"] = updated_menu
    if gen.optimization is not None and from_form:
        session["menu_optimization"] = gen.optimization

    # The calendar shows the miss once after a form submission, including the form's own
    # fetch, which asks for JSON and then opens the calendar
    notice = nutrition_notice(gen.nutrition_report())
    if notice and from_form:
        session["plan_notice"] = notice

    if want_json:
        return jsonify(
            {
                "ok": True,
                "generated_menu": updated_menu,
                "start_date": start_date,
                "meal_numbers": meal_numbers,
                "number_of_days": number_of_days,
                "weekly_cap_cents": weekly_cap_cents,
                "item_total_cents": sum(totals.values()) if totals is not None else None,
                "weekly_item_totals_cents": totals,
                "variety": gen.variety.as_json() if gen.variety else None,
                "optimization": gen.optimization,
                "nutrition": gen.nutrition_report(),
            }
        )
    return redirect(url_for("planner.index"))


def _plan_owner(conn):
    """The logged-in user's (usr_id, saved plan), or None."""
    row = fetch_one(
        conn, 'SELECT usr_id, generated_menu FROM "User" WHERE email = ?', (session.get("Email"),)
    )
    return (row[0], row[1] or "") if row else None


def _plan_reply(ok, message, status=200, back_to=None, **extra):
    """JSON for fetch() callers; otherwise a notice on the calendar and a redirect to it."""
    if request.is_json or request.accept_mimetypes.best == "application/json":
        body = {"ok": ok, "message": message, **extra}
        return jsonify(body), status
    session["plan_notice"] = ("success" if ok else "danger", message)
    if back_to:
        year, month, _ = back_to.split("-")
        return redirect(url_for("planner.index", year=int(year), month=int(month), week=back_to))
    return redirect(url_for("planner.index"))


def _plan_form():
    return (request.get_json(silent=True) or {}) if request.is_json else request.form


def _save_plan(conn, usr_id, menu):
    execute_query(conn, 'UPDATE "User" SET generated_menu = ? WHERE usr_id = ?', (menu, usr_id))
    session["GeneratedMenu"] = menu


@bp.route("/menu/remove", methods=["POST"])
def remove_planned_meal():
    """
    Remove one planned meal: date (YYYY-MM-DD) and meal (1|2|3), as JSON or form fields.
    Every other meal in the plan is left as it was.
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    form = _plan_form()
    conn = get_db()
    owner = _plan_owner(conn)
    if not owner:
        return redirect(url_for("auth.logout"))
    try:
        menu, removed = plan_edit.remove_meal(owner[1], form.get("date"), form.get("meal"))
    except plan_edit.PlanEditError as err:
        return _plan_reply(False, str(err), 400)
    if not removed:
        return _plan_reply(False, "There is no planned meal in that slot.", 404, form.get("date"))
    _save_plan(conn, owner[0], menu)
    meal = SLOT_NAMES[int(form.get("meal"))].capitalize()
    return _plan_reply(
        True, f"{meal} on {form.get('date')} removed from your plan.", back_to=form.get("date")
    )


def _range_from(form):
    """(first day, last day, meals) from the plan form's start_date, days and meal1..3."""
    try:
        days = int(form.get("days") or form.get("number_of_days") or 1)
    except (TypeError, ValueError):
        days = 1
    days = min(max(days, 1), 31)
    if request.is_json:
        meals = [int(m) for m in (form.get("meal_numbers") or [1, 2, 3])]
    else:
        meals = [m for m in (1, 2, 3) if form.get(f"meal{m}")] or [1, 2, 3]
    first, last = plan_edit.days_range(form.get("start_date") or date.today().isoformat(), days)
    return first, last, meals


@bp.route("/menu/clear", methods=["POST"])
def clear_plan_days():
    """
    Remove the planned meals from start_date for `days` days (the plan form's fields,
    or JSON start_date / number_of_days / meal_numbers). Other days are left alone.
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    form = _plan_form()
    conn = get_db()
    owner = _plan_owner(conn)
    if not owner:
        return redirect(url_for("auth.logout"))
    try:
        first, last, meals = _range_from(form)
        menu, removed = plan_edit.clear_days(owner[1], first, last, meals)
    except (plan_edit.PlanEditError, ValueError) as err:
        return _plan_reply(False, str(err), 400)
    _save_plan(conn, owner[0], menu)
    span = first if first == last else f"{first} to {last}"
    count = len(removed)
    return _plan_reply(
        True,
        (
            f"Cleared {count} meal{'' if count == 1 else 's'} from {span}."
            if count
            else f"Nothing was planned from {span}."
        ),
        back_to=first,
        removed=count,
    )


@bp.route("/menu/order-plan", methods=["POST"])
def order_plan_days():
    """
    Order every planned meal from start_date for `days` days that is not ordered yet.

    Each meal becomes its own order, due at the user's time for that meal on its day, so
    the restaurant sees when it is for. Meals that cannot be ordered (sold out, closed
    then, an allergen, a day already past, more than the wallet holds) are skipped and reported; the rest are placed.
    Fields: start_date, days, meal1..3 (or JSON number_of_days / meal_numbers),
    delivery_type and tip (per order).
    """
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))
    form = _plan_form()
    conn = get_db()
    owner = _plan_owner(conn)
    if not owner:
        return redirect(url_for("auth.logout"))
    usr_id, menu = owner
    try:
        first, last, meals = _range_from(form)
    except (plan_edit.PlanEditError, ValueError) as err:
        return _plan_reply(False, str(err), 400)
    user = account(conn, usr_id=usr_id)
    already = set(order_meals(conn, usr_id))  # (day, itm_id, meal) already on an order
    wanted = [
        (day, itm_id, meal)
        for day, itm_id, meal in plan_entries(menu)
        if first <= day <= last and meal in meals and (day, itm_id, meal) not in already
    ]
    if not wanted:
        return _plan_reply(
            False,
            "Every planned meal on those days is already ordered, or none is planned.",
            back_to=first,
        )
    restaurants = dict(
        fetch_all(
            conn,
            f'SELECT itm_id, rtr_id FROM "MenuItem" WHERE itm_id IN ({",".join("?" * len(wanted))})',
            tuple(itm for _, itm, _ in wanted),
        )
    )
    placed, skipped = [], []
    for day, itm_id, meal in wanted:
        request_body = {
            "restaurant_id": restaurants.get(itm_id, 0),
            "items": [{"itm_id": itm_id, "qty": 1}],
            "delivery_type": form.get("delivery_type") or "delivery",
            "tip": form.get("tip") or 0,
            "date": day,
            "meal": meal,
        }
        try:
            rtr_id, details = build_order(conn, user, request_body, _order_charges)
        except OrderError as err:
            skipped.append({"date": day, "meal": meal, "error": err.code, "message": err.message})
            if err.code == "no_address":
                break  # the same for every meal
            continue
        try:
            placed.append(_place_order(conn, rtr_id, usr_id, details))
        except wallet.InsufficientFundsError as exc:  # a later, cheaper meal may still fit
            skipped.append(
                {
                    "date": day,
                    "meal": meal,
                    "error": "insufficient_funds",
                    "message": exc.message,
                }
            )
            continue
        update_analytics_safe(rtr_id)
    message = f"Ordered {len(placed)} meal{'' if len(placed) == 1 else 's'}."
    if skipped:
        reasons = "; ".join(
            f"{SLOT_NAMES[s['meal']].capitalize()} {s['date']}: {s['message']}" for s in skipped[:3]
        )
        more = f" (and {len(skipped) - 3} more)" if len(skipped) > 3 else ""
        message += f" Not ordered: {reasons}{more}"
    return _plan_reply(
        bool(placed),
        message,
        200 if placed else 409,
        back_to=first,
        ord_ids=placed,
        skipped=skipped,
    )


@bp.route("/menu/swap", methods=["POST"])
def swap_meal():
    """
    Replace the item in one date/meal slot of the logged-in user's plan.

    Accepts JSON {"date", "meal", "itm_id"} or the same form fields. The replacement
    must be available for the meal time and satisfy the user's allergies, required
    diets, and saved weekly cap.
    """
    want_json = request.is_json
    payload = (request.get_json(silent=True) or {}) if want_json else request.form

    def _fail(code, message, status):
        if want_json:
            return jsonify({"ok": False, "error": code, "message": message}), status
        return redirect(url_for("planner.index", swap_error=code))

    if session.get("Username") is None:
        if want_json:
            return jsonify({"ok": False, "error": "login_required"}), 401
        return redirect(url_for("auth.login"))

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
        "SELECT usr_id, allergies, generated_menu, preferences, weekly_cap_cents, optimization_weights "
        'FROM "User" WHERE email = ?',
        (session.get("Email"),),
    )
    if not user:
        return redirect(url_for("auth.logout"))
    allergies = user["allergies"] or ""
    menu = user["generated_menu"] or ""
    preferences = user["preferences"] or ""

    current_itm_id = find_slot_item(menu, slot_date, meal)
    if current_itm_id is None:
        return _fail("slot_not_found", "There is no planned meal in that slot.", 404)
    if current_itm_id == itm_id:
        return _fail("same_item", "That item is already planned for this slot.", 400)

    rejection = swap_rejection(
        load_swap_item(conn, itm_id),
        allergies,
        slot_date,
        meal,
        preferences,
        meal_times.times_for(account(conn, usr_id=user["usr_id"])),
    )
    if rejection:
        code, message = rejection
        return _fail(code, message, 404 if code == "item_not_found" else 409)

    cap = user["weekly_cap_cents"]
    if cap is not None:
        catalog = variety.catalog_rows(conn)
        try:
            limit = swap_price_limit(menu, slot_date, meal, cap, catalog)
        except ValueError as exc:
            return _fail("weekly_cap", str(exc), 409)
        if not swap_fits_budget(itm_id, catalog, limit):
            return _fail("weekly_cap", SWAP_ERROR_MESSAGES["weekly_cap"], 409)

    try:
        updated_menu = replace_menu_slot(menu, slot_date, meal, itm_id)
    except SlotNotFoundError:
        return _fail("slot_not_found", "There is no planned meal in that slot.", 404)
    if not save_generated_plan(conn, user, updated_menu):
        return _fail("plan_changed", SWAP_ERROR_MESSAGES["plan_changed"], 409)

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
    return redirect(
        url_for("planner.index", year=int(year), month=int(month), swapped=1, week=slot_date)
    )


@bp.route("/menu/swap/options")
def swap_meal_options():
    """
    List the items that could replace one planned slot for the logged-in user.

    Query args: date (YYYY-MM-DD) and meal (1|2|3). Eligible options are ranked
    using the account's saved optimization preferences.
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
        'SELECT allergies, generated_menu, preferences, weekly_cap_cents, optimization_weights FROM "User" WHERE email = ?',
        (session.get("Email"),),
    )
    if not user:
        return jsonify({"ok": False, "error": "login_required"}), 401
    current_itm_id = find_slot_item(user[1] or "", slot_date, meal)
    if current_itm_id is None:
        return jsonify({"ok": False, "error": "slot_not_found"}), 404
    eligible = list_swap_options(
        conn,
        user[0] or "",
        slot_date,
        meal,
        current_itm_id,
        user[2] or "",
        meal_times.times_for(account(conn, email=session.get("Email"))),
    )
    catalog = variety.catalog_rows(conn)
    cap = user["weekly_cap_cents"]
    if cap is not None:
        try:
            limit = swap_price_limit(user["generated_menu"], slot_date, meal, cap, catalog)
        except ValueError as exc:
            return jsonify({"ok": False, "error": "weekly_cap", "message": str(exc)}), 409
        eligible = [item for item in eligible if swap_fits_budget(item["itm_id"], catalog, limit)]

    preferences = user["preferences"] or ""
    weights = configured_weights(user["optimization_weights"], preferences)
    eligible = rank_swap_options(
        eligible,
        catalog,
        user["generated_menu"],
        slot_date,
        meal,
        preferences if weights is not None and weights[2] else "",
        weights=weights,
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
