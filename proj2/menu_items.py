"""
One rule for what a restaurant may put on its own menu.

Until now nothing in the application wrote to ``MenuItem``: every dish came from
``proj2.seed``, ``proj2.demo_menu`` or the CSV importer in ``proj2.menu_tags_io``. A
restaurant owner could work their order queue but could not add a dish, correct a price
or pull something they had stopped serving. This module is the write path, and the
checks it applies are the same ones the CSV importer applies, so a dish means the same
thing however it arrived.

Two decisions here are not obvious, and both are about the planner rather than the form.

**Why the planner's three strongest tags are required.** ``proj2.variety`` scores a week
by how unlike each other its meals are, comparing them over tagged attributes and
skipping any tag missing on either side. ``WEIGHTS`` also carries ``item: 3.0``, so for a
dish with no tags at all the only comparable attribute left is its identity -- which
never matches -- and the dish scores the *maximum* distance against everything:

    two fully tagged dishes, as different as the seeded catalog gets : 0.944
    an untagged dish against anything at another restaurant          : 1.000

The planner maximises distance, so it prefers dishes nobody has described. Five untagged
dishes added to the 76-dish seeded catalog took 2 of 5 planned slots and pushed the
reported variety score from 0.937 to 0.965: the product would claim that week was *more*
varied for containing food it knew nothing about. Requiring ``protein``, ``cuisine`` and
``carb_base`` -- the three highest-weighted tags, at 3.0, 3.0 and 2.0 -- keeps a dish from
entering the catalog uncharacterised. It is a guard at the gate, not a fix to the score;
``variety.distance`` giving absent data a perfect mark is its own defect.

**Why there is no plain delete.** A saved plan is a text blob of ``[date,itm_id,meal]``
entries in ``User.generated_menu``, and ``meal_budget.weekly_item_totals`` raises
``ValueError: Cannot total planned item N: it is no longer in the catalog.`` when an id in
it has gone. Deleting a dish a diner had planned therefore breaks that diner's calendar,
for every diner who had planned it. Taking a dish off the menu is ``instock = 0``, which
the planner already honours (it draws candidates from ``WHERE instock == 1``) and which
leaves totals computable. A row is removed only when nothing refers to it.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from proj2 import meal_tags
from proj2.dietary import DIET_TAGS_COLUMN, KNOWN_DIETS
from proj2.menu_tags_io import canonical_cell, contradictions
from proj2.sqlQueries import execute_query, fetch_all, fetch_one

## The three highest-weighted tags in variety.WEIGHTS. See the module docstring.
REQUIRED_TAGS = ("protein", "cuisine", "carb_base")

## Tag columns an owner may set, diet tags first so the form reads in that order.
TAG_COLUMNS = (DIET_TAGS_COLUMN, *meal_tags.TAG_COLUMNS)

## Everything an owner may set. rtr_id is never taken from a request.
PLAIN_COLUMNS = ("name", "description", "price", "calories", "instock", "restock", "allergens")
EDITABLE_COLUMNS = (*PLAIN_COLUMNS, *TAG_COLUMNS)

NAME_MAX = 120
DESCRIPTION_MAX = 1000
RESTOCK_MAX = 120
ALLERGENS_MAX = 500
## A dish over this is almost certainly a typo (a price typed in cents, say).
PRICE_CENTS_MAX = 100_000
CALORIES_MAX = 20_000


@dataclass
class Validated:
    """A submitted dish, checked. ``values`` is only safe to store when ``ok``."""

    values: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)  # field name -> one message

    @property
    def ok(self) -> bool:
        return not self.errors


def price_cents(value):
    """
    Convert a dollar amount as typed into integer cents, exactly

    The catalog stores prices as whole cents, so this refuses anything that is not a
    nonnegative amount with at most two decimals rather than rounding it quietly.

    Args:
        value (str | int | float | None): The amount as typed, e.g. "12.99"

    Returns:
        int: The amount in cents

    Raises:
        ValueError: The amount is missing, negative, or has more than two decimals
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Price is required, as a dollar amount such as 12.99.")
    try:
        cents = Decimal(str(value).strip().lstrip("$")) * 100
        if not cents.is_finite() or cents < 0 or cents != cents.to_integral_value():
            raise ValueError
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError("Price must be a dollar amount with at most two decimals, e.g. 12.99.")
    cents = int(cents)
    if cents > PRICE_CENTS_MAX:
        raise ValueError(f"Price must be at most ${PRICE_CENTS_MAX // 100:,}.")
    return cents


def _text(submitted, key, limit, *, required=False, label=None):
    """One trimmed text field, or (None, message)."""
    raw = submitted.get(key)
    value = ("" if raw is None else str(raw)).strip()
    name = label or key.replace("_", " ").capitalize()
    if not value:
        return (None, f"{name} is required.") if required else ("", None)
    if len(value) > limit:
        return None, f"{name} must be at most {limit} characters."
    return value, None


def _whole_number(submitted, key, limit, label):
    """One optional nonnegative integer field, or (None, message)."""
    raw = submitted.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, f"{label} must be a whole number."
    if value < 0:
        return None, f"{label} cannot be negative."
    if value > limit:
        return None, f"{label} must be at most {limit:,}."
    return value, None


def _flag(submitted, key, default=1):
    """A checkbox or JSON boolean as 1/0, defaulting when the field is absent."""
    if key not in submitted:
        return default
    raw = submitted.get(key)
    if isinstance(raw, bool):
        return int(raw)
    text = str(raw).strip().casefold()
    if not text:
        return 0
    return 0 if text in {"0", "no", "n", "false", "f", "off"} else 1


def flatten(submitted):
    """
    One plain dict from any submission, with repeated fields joined

    A tag picker is a group of checkboxes sharing one name, so a form sends several
    values under that name and ``Mapping.get`` would see only the first; a JSON client
    may send a list for the same field. Both become the comma-separated text the tag
    parsers already read, so neither encoding is a special case further down.

    Args:
        submitted (Mapping): A Werkzeug MultiDict, a plain dict, or anything mapping-like

    Returns:
        dict: One value per key, lists joined with ", "
    """
    getlist = getattr(submitted, "getlist", None)
    out = {}
    for key in submitted.keys():
        value = submitted.getlist(key) if getlist else submitted[key]
        if isinstance(value, (list, tuple, set)):
            parts = [str(part).strip() for part in value if str(part).strip()]
            ## A single value stays itself, so "12.99" never becomes a one-item join.
            value = parts[0] if len(parts) == 1 else ", ".join(parts)
        out[key] = value
    return out


def validate(submitted, *, partial=False) -> Validated:
    """
    Check a submitted dish against every rule before it reaches the catalog

    Args:
        submitted (Mapping): Field values as typed, from a form or a JSON body. Keys not
            in EDITABLE_COLUMNS are ignored, so a request cannot set rtr_id or itm_id.
        partial (bool): True for an edit, where an absent field means "leave it alone".
            Required fields are only enforced for the fields actually present.

    Returns:
        Validated: The storable values keyed by column, and one message per bad field
    """
    out = Validated()
    submitted = flatten(submitted)
    present = set(submitted) & set(EDITABLE_COLUMNS)

    def wanted(column):
        return column in present or not partial

    if wanted("name"):
        value, problem = _text(submitted, "name", NAME_MAX, required=True, label="Name")
        if problem:
            out.errors["name"] = problem
        else:
            out.values["name"] = value
    if wanted("description"):
        value, problem = _text(submitted, "description", DESCRIPTION_MAX, label="Description")
        if problem:
            out.errors["description"] = problem
        else:
            out.values["description"] = value or None
    if wanted("restock"):
        value, problem = _text(submitted, "restock", RESTOCK_MAX, label="Restock note")
        if problem:
            out.errors["restock"] = problem
        else:
            out.values["restock"] = value or None
    if wanted("allergens"):
        value, problem = _text(submitted, "allergens", ALLERGENS_MAX, label="Allergens")
        if problem:
            out.errors["allergens"] = problem
        else:
            out.values["allergens"] = value or None

    if wanted("price"):
        try:
            out.values["price"] = price_cents(submitted.get("price"))
        except ValueError as problem:
            out.errors["price"] = str(problem)
    if wanted("calories"):
        value, problem = _whole_number(submitted, "calories", CALORIES_MAX, "Calories")
        if problem:
            out.errors["calories"] = problem
        else:
            out.values["calories"] = value
    if wanted("instock"):
        out.values["instock"] = _flag(submitted, "instock")

    for column in TAG_COLUMNS:
        if not wanted(column):
            continue
        stored, problems = canonical_cell(column, submitted.get(column))
        if problems:
            out.errors[column] = "; ".join(problems)
            continue
        ## canonical() returns "" for an empty cell; levels and flags are INTEGER columns.
        out.values[column] = None if stored == "" else stored

    for column in REQUIRED_TAGS:
        if wanted(column) and not out.errors.get(column) and not out.values.get(column):
            spec = meal_tags.COLUMNS[column]
            out.errors[column] = (
                f"{column.replace('_', ' ').capitalize()} is required, so the planner can tell "
                f"this dish apart from others. Choose from: {', '.join(sorted(spec.values))}."
            )

    return out


def check_consistency(values) -> list:
    """
    Cross-field problems in an otherwise valid dish, e.g. a vegan dish whose protein is beef

    Args:
        values (dict): Canonical column values, as returned by validate()

    Returns:
        List[str]: Messages; empty when the dish is self-consistent
    """
    return contradictions(
        values.get(DIET_TAGS_COLUMN) or "",
        values.get("allergens") or "",
        values.get("protein"),
        values.get("contains"),
    ) + meal_tags.tag_clashes(values)


def schema() -> dict:
    """
    The field contract, generated from the validator's own rules

    Serving this rather than a hand-written document means the published contract cannot
    drift from what the server accepts: both come from meal_tags.COLUMNS.

    Returns:
        dict: ``fields``, each with its kind, whether it is required, and its vocabulary
    """
    fields = {
        "name": {"kind": "text", "required": True, "max_length": NAME_MAX},
        "description": {"kind": "text", "required": False, "max_length": DESCRIPTION_MAX},
        "price": {
            "kind": "money",
            "required": True,
            "unit": "dollars, at most two decimals",
            "stored_as": "integer cents",
            "max": PRICE_CENTS_MAX / 100,
        },
        "calories": {"kind": "integer", "required": False, "max": CALORIES_MAX},
        "instock": {"kind": "flag", "required": False, "default": 1},
        "restock": {"kind": "text", "required": False, "max_length": RESTOCK_MAX},
        "allergens": {
            "kind": "text",
            "required": False,
            "max_length": ALLERGENS_MAX,
            "note": "comma-separated, free text; checked against the dish's diet tags",
        },
        DIET_TAGS_COLUMN: {
            "kind": "tags",
            "required": False,
            "values": sorted(KNOWN_DIETS),
        },
    }
    for column in meal_tags.TAG_COLUMNS:
        spec = meal_tags.COLUMNS[column]
        entry = {"kind": spec.kind, "required": column in REQUIRED_TAGS, "help": spec.help}
        if spec.kind == "tags":
            entry["values"] = sorted(spec.values)
            entry["single"] = spec.single
            if spec.aliases:
                entry["aliases"] = dict(sorted(spec.aliases.items()))
        elif spec.kind == "level":
            entry["min"], entry["max"] = spec.low, spec.high
        fields[column] = entry
    return {
        "fields": fields,
        "required": ["name", "price", *REQUIRED_TAGS],
        "required_tags_rationale": (
            "variety.distance skips tags missing on either dish and weights item identity, "
            "so an untagged dish scores the maximum distance against everything and the "
            "planner prefers it. These three are the highest-weighted tags."
        ),
    }


def _stored_columns(conn, wanted):
    """Only the columns this database actually has, so older files still work."""
    return [
        column for column in wanted if column in PLAIN_COLUMNS or meal_tags.has_column(conn, column)
    ]


## What the menu page can be narrowed to. "untagged" is the one that matters: the
## required tags are enforced on write, so a dish can only be missing one if it predates
## this page or arrived through the CSV importer -- and the planner mishandles exactly
## those. See the module docstring.
FILTERS = ("all", "on", "off", "untagged")


def is_untagged(row) -> bool:
    """
    Whether a dish is missing a tag the planner leans on

    Args:
        row (Mapping): A dish, as list_items returns it

    Returns:
        bool: True when any of REQUIRED_TAGS is absent
    """
    keys = row.keys() if hasattr(row, "keys") else row
    return any(column not in keys or not row[column] for column in REQUIRED_TAGS)


def list_items(conn, rtr_id, query: str = None, show: str = "all"):
    """
    One restaurant's dishes, in stock first then by name, optionally narrowed

    Filtering is done here rather than in the page so that the rule for "untagged"
    is the same rule the validator enforces, and so it can be tested without a request.

    Args:
        conn (sqlite3.Connection): Active connection
        rtr_id (int): The owning restaurant
        query (str | None): Free text matched against the name and description
        show (str): One of FILTERS; anything else is treated as "all"

    Returns:
        List[sqlite3.Row]: The matching dishes
    """
    columns = ", ".join(["itm_id", *_stored_columns(conn, EDITABLE_COLUMNS)])
    sql = f'SELECT {columns} FROM "MenuItem" WHERE rtr_id = ?'
    params = [rtr_id]

    text = (query or "").strip()
    if text:
        ## LIKE is case-insensitive for ASCII in SQLite; escape so a name containing
        ## % or _ is searched for literally rather than as a wildcard.
        pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (name LIKE ? ESCAPE '\\' OR IFNULL(description, '') LIKE ? ESCAPE '\\')"
        params += [pattern, pattern]

    if show == "on":
        sql += " AND instock == 1"
    elif show == "off":
        sql += " AND IFNULL(instock, 0) != 1"

    rows = fetch_all(conn, sql + " ORDER BY instock DESC, name COLLATE NOCASE", tuple(params))
    if show == "untagged":
        rows = [row for row in rows if is_untagged(row)]
    return rows


def get_item(conn, rtr_id, itm_id):
    """
    One dish, but only if this restaurant owns it

    Scoping every read and write by rtr_id is what stops one owner editing another's
    menu by guessing an id; the route layer never passes rtr_id from a request.

    Returns:
        sqlite3.Row | None: The dish, or None when it does not exist or is not theirs
    """
    columns = ", ".join(["itm_id", *_stored_columns(conn, EDITABLE_COLUMNS)])
    return fetch_one(
        conn,
        f'SELECT {columns} FROM "MenuItem" WHERE itm_id = ? AND rtr_id = ?',
        (itm_id, rtr_id),
    )


def create(conn, rtr_id, submitted):
    """
    Add a dish to a restaurant's menu

    Args:
        conn (sqlite3.Connection): Active connection
        rtr_id (int): The owning restaurant, from the session and never from the request
        submitted (Mapping): Field values as typed

    Returns:
        Tuple[int | None, dict]: The new itm_id, or None and one message per bad field
    """
    checked = validate(submitted)
    if not checked.ok:
        return None, checked.errors
    clashes = check_consistency(checked.values)
    if clashes:
        return None, {"_consistency": "; ".join(clashes)}

    columns = _stored_columns(conn, [c for c in EDITABLE_COLUMNS if c in checked.values])
    values = [checked.values[column] for column in columns]
    cursor = execute_query(
        conn,
        f'INSERT INTO "MenuItem" (rtr_id, {", ".join(columns)})'
        f' VALUES ({", ".join("?" * (len(columns) + 1))})',
        (rtr_id, *values),
    )
    return cursor.lastrowid, {}


def update(conn, rtr_id, itm_id, submitted):
    """
    Change the fields a request actually carries, leaving the rest alone

    Returns:
        Tuple[bool, dict]: Whether it was saved, and one message per bad field.
            A missing dish reports itself under "_missing".
    """
    existing = get_item(conn, rtr_id, itm_id)
    if existing is None:
        return False, {"_missing": "That dish is not on your menu."}

    checked = validate(submitted, partial=True)
    if not checked.ok:
        return False, checked.errors
    if not checked.values:
        return True, {}

    ## Consistency is a property of the whole dish, so check the merged result rather
    ## than the submitted fields: clearing a diet tag can resolve a clash, and setting
    ## a protein can create one against a diet tag that was already stored.
    merged = {column: existing[column] for column in existing.keys() if column != "itm_id"}
    merged.update(checked.values)
    clashes = check_consistency(merged)
    if clashes:
        return False, {"_consistency": "; ".join(clashes)}

    columns = list(checked.values)
    assignments = ", ".join(f"{column} = ?" for column in columns)
    execute_query(
        conn,
        f'UPDATE "MenuItem" SET {assignments} WHERE itm_id = ? AND rtr_id = ?',
        (*[checked.values[column] for column in columns], itm_id, rtr_id),
    )
    return True, {}


def set_stock(conn, rtr_id, itm_id, in_stock: bool):
    """
    Put a dish back on the menu or take it off, which is how a dish is withdrawn

    This is the safe counterpart to delete(): the planner only draws candidates from
    ``WHERE instock == 1``, so an out-of-stock dish stops being planned immediately,
    while plans and orders that already name it still price correctly.

    Returns:
        bool: True when the dish exists and belongs to this restaurant
    """
    if get_item(conn, rtr_id, itm_id) is None:
        return False
    execute_query(
        conn,
        'UPDATE "MenuItem" SET instock = ? WHERE itm_id = ? AND rtr_id = ?',
        (1 if in_stock else 0, itm_id, rtr_id),
    )
    return True


def references(conn, itm_id):
    """
    Where a dish is still spoken for, which is what makes deleting it unsafe

    A saved plan is a text blob of ``[date,itm_id,meal]`` entries in
    ``User.generated_menu``, and order contents are JSON in ``Order.details``; neither is
    a foreign key, so neither is checked by the database.

    Returns:
        dict: ``plans`` and ``orders`` counts; all zero when the dish is free to remove
    """
    ## Match the id as a whole field. "[2026-11-23,7,3]" must not match itm_id 73.
    ## Both shapes meal_budget.plan_entries accepts: with a meal number and without.
    plans = fetch_one(
        conn,
        'SELECT COUNT(*) FROM "User" WHERE generated_menu LIKE ? OR generated_menu LIKE ?',
        (f"%,{int(itm_id)},%", f"%,{int(itm_id)}]%"),
    )
    orders = fetch_one(
        conn,
        'SELECT COUNT(*) FROM "Order" WHERE details LIKE ? OR details LIKE ?',
        (f'%"itm_id": {int(itm_id)}%', f'%"itm_id":{int(itm_id)}%'),
    )
    return {"plans": plans[0] if plans else 0, "orders": orders[0] if orders else 0}


def delete(conn, rtr_id, itm_id):
    """
    Remove a dish for good, but only when nothing refers to it

    Deleting a dish that a diner has planned breaks that diner's calendar:
    ``meal_budget.weekly_item_totals`` raises for a planned id that is no longer in the
    catalog. Owners who simply want it off the menu want set_stock() instead.

    Returns:
        Tuple[bool, dict]: Whether it was removed, and why not under "_blocked" or
            "_missing"
    """
    if get_item(conn, rtr_id, itm_id) is None:
        return False, {"_missing": "That dish is not on your menu."}
    held = references(conn, itm_id)
    if held["plans"] or held["orders"]:
        parts = []
        if held["plans"]:
            parts.append(f"{held['plans']} saved meal plan(s)")
        if held["orders"]:
            parts.append(f"{held['orders']} order(s)")
        return False, {
            "_blocked": (
                f"This dish appears in {' and '.join(parts)}, so deleting it would break "
                "those calendars. Mark it out of stock instead to stop it being planned."
            )
        }
    execute_query(conn, 'DELETE FROM "MenuItem" WHERE itm_id = ? AND rtr_id = ?', (itm_id, rtr_id))
    return True, {}
