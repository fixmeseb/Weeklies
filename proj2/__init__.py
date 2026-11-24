"""
Weeklies: a Flask app. Build it with ``create_app()``.

The routes are split into blueprints:

    auth     /login, /logout, /register
    account  /profile and everything under it
    planner  / (the calendar) and /insights
    food     restaurants, ordering, reviews, changing the plan, the owner pages and /db

``auth``, ``account`` and ``planner`` do not import ``food``; code they share with it lives
outside the blueprints (``customer``, ``order_history``) or in ``planner/meal_plan``.
``proj2/Flask_app.py`` builds the app the Flask CLI and ``python -m proj2.Flask_app`` use.
"""


def create_app(test_config=None):
    """
    Create and configure the Flask app.

    Args:
        test_config (dict | None): Settings applied last, overriding the environment.
    Returns:
        Flask: The app, with its own config.
    """
    # Imported here so that importing a submodule (proj2.db, proj2.config, ...) does not
    # load every blueprint.
    from datetime import timedelta

    from flask import Flask, request

    from proj2 import db
    from proj2.account.views import bp as account_bp
    from proj2.auth.views import bp as auth_bp
    from proj2.food.views import bp as food_bp
    from proj2.hours import format_hours
    from proj2.planner.views import bp as planner_bp
    from proj2.settings import DB_VIEW_ENV, SECRET_KEY_FILE, env_flag, load_secret_key

    app = Flask(__name__)
    # Restaurant hours for display: {{ r.hours | hours_display }} (see proj2/hours.py)
    app.add_template_filter(format_hours, "hours_display")
    app.config["SECRET_KEY"] = load_secret_key(key_file=SECRET_KEY_FILE)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
    app.config["DB_VIEW_ENABLED"] = env_flag(DB_VIEW_ENV)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)  # app.config["DATABASE"], connection teardown, `flask init-db` etc.

    @app.errorhandler(db.DatabaseNotInitialisedError)
    def _database_not_initialised(exc):
        app.logger.error("%s", exc)
        return (
            "<h1>Database not initialised</h1><p>The server's database is missing or empty. "
            "Run <code>flask --app proj2.Flask_app init-db</code> and "
            "<code>flask --app proj2.Flask_app seed</code>.</p>",
            500,
        )

    @app.errorhandler(500)
    def _internal_error(exc):
        original = getattr(exc, "original_exception", None) or exc
        app.logger.error(
            "Unhandled error on %s %s", request.method, request.path, exc_info=original
        )
        return "<h1>Internal Server Error</h1><p>Something went wrong. It has been logged.</p>", 500

    for bp in (auth_bp, account_bp, planner_bp, food_bp):
        app.register_blueprint(bp)
    return app
