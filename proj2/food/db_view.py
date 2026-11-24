"""The /db developer viewer."""

import math

from flask import abort, current_app, redirect, render_template, request, session, url_for

from proj2.db import get_db
from proj2.food.blueprint import bp
from proj2.sqlQueries import fetch_all, fetch_one

# Columns the database viewer never selects. Password hashes can be cracked offline,
# so they must not reach the page (User and Restaurant both have password_HS).
DB_VIEW_HIDDEN_COLUMNS = frozenset({"password_HS"})


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def db_view_enabled() -> bool:
    """
    Whether /db is available: when WEEKLIES_ENABLE_DB_VIEW is set, and always under
    pytest (current_app.testing) so the existing viewer tests keep running.
    Returns:
        bool: True if the viewer should be served.
    """
    return bool(current_app.config.get("DB_VIEW_ENABLED")) or current_app.testing


@bp.app_context_processor
def inject_db_view_enabled():
    """Expose db_view_enabled to templates so the nav only links to /db when it is served."""
    return {"db_view_enabled": db_view_enabled()}


# Database viewer route (uses helpers only)
@bp.route("/db")
def db_view():
    """
    Display a simple, paginated database table viewer (developer tool).
    Args:
        None
    Returns:
        Response: HTML page showing rows/columns for a selected table (requires login);
        404 when the viewer is disabled.
    """
    if not db_view_enabled():
        abort(404)
    if session.get("Username") is None:
        return redirect(url_for("auth.login"))

    allowed_tables = {"User", "Restaurant", "MenuItem", "Order", "Review"}
    table = request.args.get("t", "User")
    if table not in allowed_tables:
        table = "User"

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    page = max(page, 1)
    per_page = 10

    conn = get_db()
    total_row = fetch_one(conn, f'SELECT COUNT(*) FROM "{table}"')
    total = (total_row[0] if total_row else 0) or 0

    pages = max(math.ceil(total / per_page), 1)
    page = min(page, pages)
    offset = (page - 1) * per_page

    col_rows = fetch_all(conn, f'PRAGMA table_info("{table}")')
    columns = [r[1] for r in col_rows or [] if r[1] not in DB_VIEW_HIDDEN_COLUMNS]

    # Select only the visible columns, so hidden values never leave the database.
    if columns:
        select_list = ", ".join(_quote_ident(c) for c in columns)
        rows = fetch_all(
            conn, f'SELECT {select_list} FROM "{table}" LIMIT ? OFFSET ?', (per_page, offset)
        )
    else:
        rows = []

    start = 0 if total == 0 else offset + 1
    end = min(offset + per_page, total)

    return render_template(
        "db_view.html",
        table=table,
        allowed=sorted(allowed_tables),
        columns=columns,
        rows=rows,
        page=page,
        pages=pages,
        total=total,
        start=start,
        end=end,
    )
