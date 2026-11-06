"""
Weeklies: a Flask app. Build it with ``create_app()``.

The app is split into blueprints:

    auth     /login, /logout, /register
    account  /profile, /profile/edit, /profile/change-password
    planner  /, /<year>/<month>  (the calendar)
    food     everything food-delivery specific; nothing else may import it, because
             the task-planner pivot deletes it

``proj2/Flask_app.py`` builds the app the Flask CLI and ``python -m proj2.Flask_app`` use.
"""

from datetime import timedelta


def create_app(test_config=None):
    """
    Create and configure the Flask app.

    Args:
        test_config (dict | None): Settings applied last, overriding the environment.
    """
    # Imports live here so that importing a submodule (proj2.db, proj2.sqlQueries, ...)
    # does not build an app or import every blueprint.
    from flask import Flask, request

    from proj2 import db
    from proj2.account.views import bp as account_bp
    from proj2.auth.views import bp as auth_bp
    from proj2.food.views import bp as food_bp
    from proj2.planner.views import bp as planner_bp
    from proj2.settings import DB_VIEW_ENV, SECRET_KEY_FILE, env_flag, load_secret_key

    app = Flask(__name__)
    app.config["SECRET_KEY"] = load_secret_key(key_file=SECRET_KEY_FILE)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
    app.config["DB_VIEW_ENABLED"] = env_flag(DB_VIEW_ENV)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)  # app.config["DATABASE"], connection teardown, `flask init-db` etc.

    @app.errorhandler(db.DatabaseNotInitialisedError)
    def _database_not_initialised(exc):
        app.logger.error("%s", exc)
        page = (
            "<h1>Database not initialised</h1><p>The server's database is missing, empty "
            "or out of date. The server log says which, and the command that fixes it "
            "(<code>flask init-db</code>, <code>flask migrate</code> or "
            "<code>flask seed</code>).</p>"
        )
        return page, 500

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
