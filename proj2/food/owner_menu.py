"""The owner's menu pages and the menu JSON API."""

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from proj2 import menu_items
from proj2.db import get_db
from proj2.food.blueprint import bp
from proj2.food.owner_auth import restaurant_required


## ---------------------------------------------------------------------------
## Restaurant menu management
##
## The owner pages could work an order queue but not the menu those orders were for:
## nothing in the application had ever written to MenuItem. These routes are that write
## path. Every rule lives in proj2.menu_items, which the CSV importer's checks back, so
## a dish typed into the form and a dish imported from a spreadsheet are held to the
## same standard. The JSON API below is the same validator behind a different encoding,
## and /api/restaurant/menu/schema publishes the contract generated from it, so a client
## cannot be written against rules the server does not actually apply.
## ---------------------------------------------------------------------------
def _owner_page(errors=None, submitted=None, editing=None, open_add=False):
    """
    Render the menu page.

    Three endpoints render it -- the page itself, and the add and edit forms when they
    come back with errors -- so the state that differs between them is passed in rather
    than read from request.endpoint.

    Args:
        errors (dict | None): One message per rejected field, plus "_consistency" or
            "_blocked" for problems that belong to the dish rather than to one field.
        submitted (Mapping | None): What was typed, so a rejected form is not emptied.
        editing (int | None): The dish whose edit form is open.
        open_add (bool): Whether the "Add a dish" panel starts open.

    Returns:
        str: The rendered page.
    """
    conn = get_db()
    rtr_id = session.get("rtr_id")
    query = (request.args.get("q") or "").strip()
    show = request.args.get("show") or "all"
    if show not in menu_items.FILTERS:
        show = "all"
    return render_template(
        "restaurant_menu.html",
        owner_tab="restaurant_menu",
        restaurant_name=session.get("RestaurantName", "Restaurant"),
        restaurant_email=session.get("RestaurantEmail", ""),
        items=menu_items.list_items(conn, rtr_id, query, show),
        schema=menu_items.schema(),
        tag_columns=menu_items.TAG_COLUMNS,
        required_tags=menu_items.REQUIRED_TAGS,
        errors=errors or {},
        # A tag picker posts one value per ticked box behind an always-sent empty one, so
        # the raw form's .get() would read every picker back as empty.
        submitted=menu_items.flatten(submitted or {}),
        editing=editing,
        open_add=open_add,
        query=query,
        show=show,
    )


@bp.route("/restaurant/menu")
@restaurant_required
def restaurant_menu():
    """
    The owner's menu page: every dish they serve, with forms to add and edit.

    Editing is ``?edit=<itm_id>`` rather than a script, so exactly one edit form is on
    the page and the page works without JavaScript. ``?q=`` searches and ``?show=``
    narrows (see menu_items.FILTERS).
    Args:
        None
    Returns:
        Response: Renders the restaurant menu page, or 404 for an ?edit id that is not
        this restaurant's.
    """
    editing = request.args.get("edit", type=int)
    if (
        editing is not None
        and menu_items.get_item(get_db(), session.get("rtr_id"), editing) is None
    ):
        abort(404)
    return _owner_page(editing=editing, open_add=request.args.get("add") == "1")


@bp.route("/restaurant/menu/new", methods=["POST"])
@restaurant_required
def restaurant_menu_new():
    """
    Add a dish to the signed-in restaurant's menu.
    Args:
        None
    Returns:
        Response: Redirect to the menu on success, or the page with per-field errors.
    """
    conn = get_db()
    itm_id, errors = menu_items.create(conn, session.get("rtr_id"), request.form)
    if errors:
        return _owner_page(errors=errors, submitted=request.form, open_add=True)
    return redirect(url_for("food.restaurant_menu", added=itm_id))


@bp.route("/restaurant/menu/<int:itm_id>/edit", methods=["POST"])
@restaurant_required
def restaurant_menu_edit(itm_id):
    """
    Save changes to one dish.
    Args:
        itm_id (int): The dish being edited.
    Returns:
        Response: Redirect to the menu on success, or the page with per-field errors.
    """
    conn = get_db()
    saved, errors = menu_items.update(conn, session.get("rtr_id"), itm_id, request.form)
    if not saved:
        if "_missing" in errors:
            abort(404)
        return _owner_page(errors=errors, submitted=request.form, editing=itm_id)
    return redirect(url_for("food.restaurant_menu", saved=itm_id))


@bp.route("/restaurant/menu/<int:itm_id>/stock", methods=["POST"])
@restaurant_required
def restaurant_menu_stock(itm_id):
    """
    Put a dish back on the menu or take it off, which is how a dish is withdrawn.
    Args:
        itm_id (int): The dish to change.
    Returns:
        Response: Redirect to the menu.
    """
    conn = get_db()
    wanted = request.form.get("instock", "0").strip() not in {"0", "", "no", "false", "off"}
    if not menu_items.set_stock(conn, session.get("rtr_id"), itm_id, wanted):
        abort(404)
    return redirect(url_for("food.restaurant_menu", stock=itm_id))


@bp.route("/restaurant/menu/<int:itm_id>/delete", methods=["POST"])
@restaurant_required
def restaurant_menu_delete(itm_id):
    """
    Remove a dish for good, refusing when a saved plan or order still names it.
    Args:
        itm_id (int): The dish to remove.
    Returns:
        Response: Redirect to the menu, or the page explaining why it was refused.
    """
    conn = get_db()
    removed, errors = menu_items.delete(conn, session.get("rtr_id"), itm_id)
    if not removed:
        if "_missing" in errors:
            abort(404)
        return _owner_page(errors=errors)
    return redirect(url_for("food.restaurant_menu", removed=1))


## --- JSON API -------------------------------------------------------------
## Same validator, same ownership scoping; only the encoding differs. 422 is used for a
## body that was understood but broke a rule, 409 for a delete that a saved plan blocks.
def _json_body():
    """The request body as a mapping, whether it arrived as JSON or as form fields."""
    if request.is_json:
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else None
    return request.form if request.form else None


def _api_error(errors, status=422):
    """One shape for every rejection, so a client can rely on it."""
    return jsonify({"ok": False, "errors": errors}), status


def _as_dict(row):
    """One dish as JSON, with the price in cents as stored and in dollars for display."""
    item = {key: row[key] for key in row.keys()}
    if item.get("price") is not None:
        item["price_cents"] = item["price"]
        item["price_dollars"] = f"{item['price'] / 100:.2f}"
    return item


@bp.route("/api/restaurant/menu/schema")
@restaurant_required
def api_menu_schema():
    """
    The field contract: every field, whether it is required, and its vocabulary.
    Args:
        None
    Returns:
        Response: JSON generated from the validator, so it cannot drift from the server.
    """
    return jsonify(menu_items.schema())


@bp.route("/api/restaurant/menu")
@restaurant_required
def api_menu_list():
    """
    Every dish on the signed-in restaurant's menu.
    Args:
        None
    Returns:
        Response: JSON ``{"items": [...]}``.
    """
    conn = get_db()
    rows = menu_items.list_items(conn, session.get("rtr_id"))
    return jsonify({"items": [_as_dict(row) for row in rows]})


@bp.route("/api/restaurant/menu", methods=["POST"])
@restaurant_required
def api_menu_create():
    """
    Add a dish.
    Args:
        None
    Returns:
        Response: 201 and the new dish, or 422 and one message per bad field.
    """
    body = _json_body()
    if body is None:
        return _api_error({"_body": "Send a JSON object of fields."}, 400)
    conn = get_db()
    rtr_id = session.get("rtr_id")
    itm_id, errors = menu_items.create(conn, rtr_id, body)
    if errors:
        return _api_error(errors)
    return jsonify({"ok": True, "item": _as_dict(menu_items.get_item(conn, rtr_id, itm_id))}), 201


@bp.route("/api/restaurant/menu/<int:itm_id>", methods=["PATCH", "POST"])
@restaurant_required
def api_menu_update(itm_id):
    """
    Change the fields the body carries, leaving the rest alone.
    Args:
        itm_id (int): The dish to change.
    Returns:
        Response: The saved dish, 404 when it is not theirs, or 422 for a bad field.
    """
    body = _json_body()
    if body is None:
        return _api_error({"_body": "Send a JSON object of fields."}, 400)
    conn = get_db()
    rtr_id = session.get("rtr_id")
    saved, errors = menu_items.update(conn, rtr_id, itm_id, body)
    if not saved:
        return _api_error(errors, 404 if "_missing" in errors else 422)
    return jsonify({"ok": True, "item": _as_dict(menu_items.get_item(conn, rtr_id, itm_id))})


@bp.route("/api/restaurant/menu/<int:itm_id>/stock", methods=["POST", "PUT"])
@restaurant_required
def api_menu_stock(itm_id):
    """
    Put a dish back on the menu or take it off.
    Args:
        itm_id (int): The dish to change.
    Returns:
        Response: The saved dish, or 404 when it is not theirs.
    """
    body = _json_body() or {}
    conn = get_db()
    rtr_id = session.get("rtr_id")
    wanted = body.get("instock", True)
    if isinstance(wanted, str):
        wanted = wanted.strip().casefold() not in {"0", "", "no", "false", "off", "n", "f"}
    if not menu_items.set_stock(conn, rtr_id, itm_id, bool(wanted)):
        return _api_error({"_missing": "That dish is not on your menu."}, 404)
    return jsonify({"ok": True, "item": _as_dict(menu_items.get_item(conn, rtr_id, itm_id))})


@bp.route("/api/restaurant/menu/<int:itm_id>", methods=["DELETE"])
@restaurant_required
def api_menu_delete(itm_id):
    """
    Remove a dish for good, refusing when a saved plan or order still names it.
    Args:
        itm_id (int): The dish to remove.
    Returns:
        Response: 200 on removal, 404 when it is not theirs, 409 when something holds it.
    """
    conn = get_db()
    removed, errors = menu_items.delete(conn, session.get("rtr_id"), itm_id)
    if not removed:
        return _api_error(errors, 404 if "_missing" in errors else 409)
    return jsonify({"ok": True, "deleted": itm_id})
