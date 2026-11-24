"""Customer login, logout and registration."""

import re
from sqlite3 import IntegrityError

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from proj2 import config
from proj2.customer import DIET_OPTIONS, submitted_diet_constraints
from proj2.db import get_db
from proj2.dietary import required_diets
from proj2.sqlQueries import execute_query, fetch_one

bp = Blueprint("auth", __name__)


def find_customer_for_login(email):
    """Find the customer and account fields needed to start a session."""
    return fetch_one(
        get_db(),
        "SELECT usr_id, first_name, last_name, phone, password_HS, wallet, preferences, "
        'allergies, generated_menu FROM "User" WHERE email = ?',
        (email,),
    )


def start_customer_session(user, email):
    """Copy an authenticated customer account into the current session."""
    session["usr_id"] = user["usr_id"]
    session["Fname"] = user["first_name"]
    session["Lname"] = user["last_name"]
    session["Username"] = user["first_name"] + " " + user["last_name"]
    session["Email"] = email
    session["Phone"] = user["phone"]
    session["Wallet"] = user["wallet"]
    session["Preferences"] = user["preferences"] or ""
    session["Allergies"] = user["allergies"] or ""
    session["GeneratedMenu"] = user["generated_menu"] or ""
    session.permanent = True


# Login route
@bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Display the login form (GET) and authenticate user credentials (POST).
    Args:
        None
    Returns:
        Response: Renders login page, or redirects to home on successful login.
    """
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = find_customer_for_login(email)
        if user and check_password_hash(user["password_HS"], password):
            start_customer_session(user, email)
            return redirect(url_for("planner.index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


# Logout route (single, no duplicates)
@bp.route("/logout")
def logout():
    """
    Clear the user session and redirect to the login page.
    Args:
        None
    Returns:
        Response: Redirect to the login route.
    """
    for k in [
        "Username",
        "Fname",
        "Lname",
        "Email",
        "Phone",
        "Wallet",
        "Preferences",
        "Allergies",
        "GeneratedMenu",
    ]:
        session.pop(k, None)
    return redirect(url_for("auth.login"))


# Registration route
@bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Display the registration form (GET) and create a new user (POST).
    Args:
        None
    Returns:
        Response: Renders registration page or redirects to login on success.
    """
    allergies, preferences = submitted_diet_constraints()

    def registration_page(error=None):
        return render_template(
            "register.html",
            error=error,
            submitted_allergies=allergies,
            diet_options=DIET_OPTIONS,
            selected_diets=required_diets(preferences),
        )

    if request.method == "POST":
        fname = (request.form.get("fname") or "").strip()
        lname = (request.form.get("lname") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        # Basic validations
        if not fname or not lname:
            return registration_page("First and last name are required")
        if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return registration_page("Please enter a valid email address")
        if password != confirm_password:
            return registration_page("Passwords do not match")
        if len(password) < 6:
            return registration_page("Password must be at least 6 characters")

        digits_only = re.sub(r"\D+", "", phone)
        if len(digits_only) < 7:
            return registration_page("Please enter a valid phone number")

        conn = get_db()
        try:
            exists = fetch_one(conn, 'SELECT 1 FROM "User" WHERE email = ?', (email,))
            if exists:
                return registration_page("Email already registered")

            password_hashed = generate_password_hash(password)

            # Insert WITHOUT generated_menu (meal planning fills it later)
            execute_query(
                conn,
                """
                INSERT INTO "User"
                    (first_name, last_name, email, phone, password_HS, wallet, preferences, allergies)
                VALUES
                    (?,          ?,         ?,     ?,     ?,           ?,      ?,            ?)
                """,
                (
                    fname,
                    lname,
                    email,
                    digits_only,
                    password_hashed,
                    config.starting_wallet_cents(),
                    preferences,
                    allergies,
                ),
            )
        except IntegrityError:
            return registration_page("Email already registered")

        return redirect(url_for("auth.login"))

    return registration_page()
