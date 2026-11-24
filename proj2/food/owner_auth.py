"""Restaurant owners' sign-up, login and logout."""

from functools import wraps
from sqlite3 import IntegrityError

from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from proj2 import restaurant_signup
from proj2.db import get_db
from proj2.food.blueprint import bp
from proj2.sqlQueries import fetch_one


# ---------------------- Restaurant Authentication ----------------------
def restaurant_required(f):
    """
    Decorator to protect restaurant-only routes.
    Redirects to restaurant login if not authenticated as a restaurant.
    Also adds cache-control headers to prevent browser caching.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("restaurant_mode") or not session.get("rtr_id"):
            return redirect(url_for("food.restaurant_login"))

        # Normalize Flask return values, including (body, status, headers) tuples.
        from flask import make_response

        response = make_response(f(*args, **kwargs))

        # Add cache-control headers to prevent browser caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    return decorated_function


@bp.route("/restaurant/login", methods=["GET", "POST"])
def restaurant_login():
    """
    Restaurant owner login page and authentication handler.
    Args:
        None
    Returns:
        Response: Renders restaurant login page or redirects to the Orders page on success.
    """
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        restaurant = fetch_one(
            conn,
            "SELECT rtr_id, name, email, password_HS FROM Restaurant WHERE email = ?",
            (email,),
        )

        if restaurant and check_password_hash(restaurant[3], password):
            # Set restaurant session
            session["restaurant_mode"] = True
            session["rtr_id"] = restaurant[0]
            session["RestaurantName"] = restaurant[1]
            session["RestaurantEmail"] = email
            session.permanent = True

            return redirect(url_for("food.restaurant_orders"))

        return render_template("restaurant_login.html", error="Invalid credentials")

    return render_template("restaurant_login.html")


@bp.route("/restaurant/logout")
def restaurant_logout():
    """
    Clear restaurant session and redirect to restaurant login.
    Args:
        None
    Returns:
        Response: Redirect to restaurant login page.
    """
    session.pop("restaurant_mode", None)
    session.pop("rtr_id", None)
    session.pop("RestaurantName", None)
    session.pop("RestaurantEmail", None)
    return redirect(url_for("food.restaurant_login"))


## The days a new restaurant is offered as open before they change anything, and the
## times those days start with. Mon-Fri 11:00-21:00 is the commonest shape in the seeded
## catalog; a weekend-only restaurant unticks two boxes.
SIGNUP_DEFAULT_OPEN = ("Mon", "Tue", "Wed", "Thu", "Fri")


SIGNUP_DEFAULT_HOURS = ("11:00", "21:00")


def _signup_page(errors=None, submitted=None):
    """
    Render the sign-up form, blank or with what was typed and why it was rejected.
    Args:
        errors (dict | None): Field name -> message, from restaurant_signup.validate.
        submitted (Mapping | None): The rejected form, so nothing has to be retyped.
    Returns:
        Response: The rendered sign-up page.
    """
    return render_template(
        "restaurant_register.html",
        schema=restaurant_signup.schema(),
        errors=errors or {},
        submitted=submitted,
        default_open=SIGNUP_DEFAULT_OPEN,
        default_hours=SIGNUP_DEFAULT_HOURS,
    )


def _sign_in_restaurant(rtr_id, name, email):
    """
    Put a restaurant into the session exactly as restaurant_login does.
    Args:
        rtr_id (int): The restaurant's id.
        name (str): The restaurant's name, shown in the owner banner.
        email (str): The address they signed up with, already lowercased.
    Returns:
        None
    """
    session["restaurant_mode"] = True
    session["rtr_id"] = rtr_id
    session["RestaurantName"] = name
    session["RestaurantEmail"] = email
    session.permanent = True


@bp.route("/restaurant/register", methods=["GET", "POST"])
def restaurant_register():
    """
    Sign a restaurant up, then sign it in and send it to its empty menu.

    There was a /restaurant/login with no door behind it: every restaurant came from
    proj2.seed, so nobody could join. A new restaurant lands on the menu page because a
    restaurant with no dishes is invisible to the planner, so adding the first dish is
    the only useful next step.
    Args:
        None
    Returns:
        Response: The sign-up form, the form again with errors, or a redirect to the
        new restaurant's menu page.
    """
    if request.method == "GET":
        return _signup_page()

    conn = get_db()
    checked = restaurant_signup.validate(request.form, conn=conn)
    if not checked.ok:
        return _signup_page(errors=checked.errors, submitted=request.form)

    try:
        rtr_id = restaurant_signup.create(conn, checked.values)
    except IntegrityError:
        # Restaurant.email is UNIQUE; another sign-up won the race since validate looked.
        return _signup_page(
            errors={"email": "That email already has a restaurant account. Log in instead."},
            submitted=request.form,
        )

    _sign_in_restaurant(rtr_id, checked.values["name"], checked.values["email"])
    return redirect(url_for("food.restaurant_menu", welcome=1))


@bp.route("/api/restaurant/register/schema")
def api_restaurant_register_schema():
    """
    The sign-up contract: every field, whether it is required, and how hours are stored.

    Public, like the form it describes: a client cannot have an account yet.
    Args:
        None
    Returns:
        Response: JSON generated from the validator, so it cannot drift from the server.
    """
    return jsonify(restaurant_signup.schema())


@bp.route("/api/restaurant/register", methods=["POST"])
def api_restaurant_register():
    """
    Sign a restaurant up from a JSON body, through the same validator as the form.

    This does not sign the caller in: a programmatic client posts credentials to
    /restaurant/login for that.
    Args:
        None
    Returns:
        Response: 201 with the new restaurant, or 422 with one message per bad field.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"errors": {"_body": "Send a JSON object."}}), 400

    conn = get_db()
    checked = restaurant_signup.validate(body, conn=conn)
    if not checked.ok:
        return jsonify({"errors": checked.errors}), 422

    try:
        rtr_id = restaurant_signup.create(conn, checked.values)
    except IntegrityError:
        return jsonify({"errors": {"email": "That email already has a restaurant account."}}), 422

    stored = {key: value for key, value in checked.values.items() if key != "password"}
    return jsonify({"rtr_id": rtr_id, **stored}), 201
