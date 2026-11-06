"""Customer login, logout and registration."""

import re
from sqlite3 import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Blueprint, render_template, url_for, redirect, request, session

from proj2.sqlQueries import fetch_one, execute_query
from proj2.db import get_db

bp = Blueprint("auth", __name__)


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

        conn = get_db()
        user = fetch_one(
            conn,
            "SELECT usr_id, first_name, last_name, phone, password_HS, wallet, preferences, "
            'allergies, generated_menu FROM "User" WHERE email = ?',
            (email,),
        )

        if user and check_password_hash(user["password_HS"], password):
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
    if request.method == "POST":
        fname = (request.form.get("fname") or "").strip()
        lname = (request.form.get("lname") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        allergies = (request.form.get("allergies") or "").strip()
        preferences = (request.form.get("preferences") or "").strip()

        # Basic validations
        if not fname or not lname:
            return render_template("register.html", error="First and last name are required")
        if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return render_template("register.html", error="Please enter a valid email address")
        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match")
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters")

        digits_only = re.sub(r"\D+", "", phone)
        if len(digits_only) < 7:
            return render_template("register.html", error="Please enter a valid phone number")

        conn = get_db()
        try:
            exists = fetch_one(conn, 'SELECT 1 FROM "User" WHERE email = ?', (email,))
            if exists:
                return render_template("register.html", error="Email already registered")

            password_hashed = generate_password_hash(password)

            # Insert WITHOUT generated_menu (your LLM will populate it later)
            execute_query(
                conn,
                """
                INSERT INTO "User"
                    (first_name, last_name, email, phone, password_HS, wallet, preferences, allergies)
                VALUES
                    (?,          ?,         ?,     ?,     ?,           ?,      ?,            ?)
                """,
                (fname, lname, email, digits_only, password_hashed, 0, preferences, allergies),
            )
        except IntegrityError:
            return render_template("register.html", error="Email already registered")

        return redirect(url_for("auth.login"))

    return render_template("register.html")
