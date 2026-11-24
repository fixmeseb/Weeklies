"""
Entry point: builds the app for the Flask CLI (`.flaskenv` points at this module) and for
`python -m proj2.Flask_app`.

The routes live in blueprints (see proj2/__init__.py). The names re-exported below keep
`from proj2.Flask_app import ...` working for tests and scripts. To monkeypatch one, patch
the module that uses it (for example proj2.food.analytics), not this one.
"""

import argparse

from proj2 import create_app
from proj2.auth.views import find_customer_for_login, start_customer_session  # noqa: F401
from proj2.customer import diet_summary  # noqa: F401
from proj2.db import DatabaseNotInitialisedError, connect
from proj2.food.analytics import record_analytics_snapshot, update_analytics_safe  # noqa: F401
from proj2.food.db_view import (  # noqa: F401
    DB_VIEW_HIDDEN_COLUMNS,
    _quote_ident,
    db_view_enabled,
    inject_db_view_enabled,
)
from proj2.food.orders import _cents_to_dollars, _money, _order_charges  # noqa: F401
from proj2.food.restaurants import open_now  # noqa: F401
from proj2.order_history import _meal_at, order_meals  # noqa: F401
from proj2.planner.meal_plan import (  # noqa: F401
    build_calendar_cells,
    fetch_menu_items_by_ids,
    palette_for_item_ids,
    parse_generated_menu,
)
from proj2.settings import (  # noqa: F401
    DB_VIEW_ENV,
    SECRET_KEY_ENV,
    SECRET_KEY_FILE,
    env_flag,
    load_secret_key,
)

app = create_app()


def db_path() -> str:
    """Path of this app's database (usable outside a request)."""
    return app.config["DATABASE"]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flask App for Meal Planner")
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to run the Flask app on"
    )
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask app on")
    # Off by default: the Werkzeug debugger lets anyone who can reach the page run code.
    parser.add_argument(
        "--debug", action="store_true", help="Enable auto-reload and the interactive debugger"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    """
    DB column names:

    MenuItem: itm_id,rtr_id,name,description,price,calories,instock,restock,allergens
    Order: ord_id,rtr_id,usr_id,details,status
    Restaurant: rtr_id,name,description,phone,email,password_HS,address,city,state,zip,hours,status
    Review: rev_id,rtr_id,usr_id,title,rating,description,ord_id,created_at
    User: usr_id,first_name,last_name,email,phone,password_HS,wallet,preferences,allergies,generated_menu
    """
    args = parse_args()
    try:  # fail at startup, not on the first request, if the database isn't set up
        connect(app.config["DATABASE"]).close()
    except DatabaseNotInitialisedError as exc:
        raise SystemExit(str(exc))
    app.run(host=args.host, port=args.port, debug=args.debug)
