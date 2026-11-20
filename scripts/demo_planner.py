#!/usr/bin/env python3
"""Run the meeting examples and serve a fresh local Weeklies demo."""

import argparse
from contextlib import closing
from datetime import date, timedelta
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from tempfile import TemporaryDirectory

from flask import redirect, request, session, url_for
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proj2 import variety  # noqa: E402
from proj2.allergens import allergen_conflicts, normalize_allergen  # noqa: E402
from proj2.dietary import missing_diets  # noqa: E402
from proj2.meal_budget import parse_weekly_cap, plan_entries  # noqa: E402
from proj2.plan_optimization import OBJECTIVES  # noqa: E402
from proj2.seed import seed_database  # noqa: E402
from scripts.compare_planners import main as compare  # noqa: E402

DEMO_EMAIL = "testuser@example.com"
DEMO_DIET = "vegetarian"
DEMO_ALLERGY = "Peanuts"
DEMO_FOOD_MATCH = "Italian"
DEMO_CAP = "60.00"
DEMO_DAYS = 5
DEMO_WEIGHTS = {
    "variety": 60,
    "cost": 25,
    "preference": 35,
    "calories": 10,
    "mildness": 30,
    "restaurants": 20,
}


def show_profile_examples(app, password, start):
    """Save each set of priorities through Profile and generate the same five dinners."""
    database = app.config["DATABASE"]
    client = app.test_client()
    login = client.post("/login", data={"email": DEMO_EMAIL, "password": password})
    if login.status_code != 302:
        raise RuntimeError("The demo account could not log in.")

    def save_profile(weights, cap=DEMO_CAP):
        fields = {
            "diet_constraints": "1",
            "allergies[]": DEMO_ALLERGY,
            "diets[]": DEMO_DIET,
            "weekly_cap": cap,
            "food_matches": DEMO_FOOD_MATCH,
        }
        fields.update({f"{key}_weight": weights.get(key, 0) for key in OBJECTIVES})
        response = client.post("/profile/edit", data=fields, follow_redirects=True)
        if b"Diet settings saved." not in response.data:
            raise RuntimeError("The demo could not save its Diet settings.")

    def generate():
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute('UPDATE "User" SET generated_menu = ? WHERE email = ?', ("", DEMO_EMAIL))
        return client.post(
            "/menu/generate",
            json={
                "start_date": start.isoformat(),
                "meal_numbers": [3],
                "number_of_days": DEMO_DAYS,
            },
        )

    with closing(sqlite3.connect(database)) as conn:
        catalog = variety.catalog_rows(conn)

    cap_cents = parse_weekly_cap(DEMO_CAP)
    expected_constraints = {
        "diets": [DEMO_DIET],
        "allergies": [normalize_allergen(DEMO_ALLERGY)],
        "weekly_cap_cents": cap_cents,
    }
    print("\nExample 3 — Profile settings in action")
    print(
        f"{DEMO_DAYS} dinners starting {start}, {DEMO_DIET}, avoid {DEMO_ALLERGY.lower()}, "
        f"weekly cap ${DEMO_CAP}, food to match {DEMO_FOOD_MATCH}."
    )
    print(
        "Each row starts with an empty plan. The first six rows set just the named slider to 100."
    )
    print(
        f"{'Saved priority':<26} {'Variety':>8} {'Cost':>8} {DEMO_FOOD_MATCH:>8} "
        f"{'Avg kcal':>8} {'Spice /3':>9} {'Places':>7}"
    )
    runs = [(label, {key: 100}) for key, label in OBJECTIVES.items()]
    runs.append(("All six sliders", DEMO_WEIGHTS))
    for label, weights in runs:
        save_profile(weights)
        response = generate()
        result = response.json
        if response.status_code != 200:
            raise RuntimeError(f"{label}: {result['error']}")
        metrics = result["optimization"]
        total_weight = sum(weights.values())
        if metrics is None or metrics["weights"] != {
            key: weights.get(key, 0) / total_weight for key in OBJECTIVES
        }:
            raise RuntimeError(f"{label}: the optimizer did not receive the saved priorities.")
        entries = list(plan_entries(result["generated_menu"]))
        dishes = [catalog[item] for _, item, _ in entries]
        if (
            metrics["constraints"] != expected_constraints
            or len(entries) != DEMO_DAYS
            or any(missing_diets(dish["diet_tags"], {DEMO_DIET}) for dish in dishes)
            or any(allergen_conflicts(dish["allergens"], DEMO_ALLERGY) for dish in dishes)
            or result["weekly_cap_cents"] != cap_cents
            or sum(dish["price"] for dish in dishes) != result["item_total_cents"]
            or result["item_total_cents"] > cap_cents
        ):
            raise RuntimeError(f"{label}: the plan did not satisfy the saved hard constraints.")
        print(
            f"{label:<26} {metrics['variety']:>8.1%} ${metrics['item_cost_cents'] / 100:>7.2f} "
            f"{metrics['preference_match']:>8.0%} {metrics['average_calories']:>8.0f} "
            f"{metrics['average_spice']:>9.2f} {metrics['distinct_restaurants']:>7}"
        )

    print("Every selected dish satisfies the saved diet and allergen rules.")
    print("Saved slider values for the combined plan")
    print("  " + ", ".join(f"{OBJECTIVES[key]} {value}" for key, value in DEMO_WEIGHTS.items()))
    print("Combined plan meals")
    for (day, _, _), dish in zip(entries, dishes):
        print(f"  {day}  {dish['name']}  ${dish['price'] / 100:.2f}")

    save_profile(DEMO_WEIGHTS, cap="1.00")
    refused = generate()
    if refused.status_code != 422:
        raise RuntimeError("The optimizer accepted the infeasible $1.00 weekly cap.")
    print(f"With a $1.00 cap, the planner refuses the same request. {refused.json['error']}")
    save_profile(DEMO_WEIGHTS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console-only", action="store_true", help="Run the examples and exit")
    parser.add_argument("--port", type=int, default=0, help="Use a specific local port")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    print("\nExample 1 — Three dinners and the cost–variety trade-off")
    compare(["--tradeoffs"])
    print("\nExample 2 — Search strategies on a full week with all six objectives")
    comparison = [
        "--days",
        "7",
        "--meals",
        "1",
        "2",
        "3",
        "--cap",
        "245",
        "--diets",
        DEMO_DIET,
        "--allergens",
        DEMO_ALLERGY,
        "--food-matches",
        DEMO_FOOD_MATCH,
    ]
    for name, value in DEMO_WEIGHTS.items():
        comparison.extend(("--weight", f"{name}={value}"))
    compare(comparison)

    with TemporaryDirectory(prefix="weeklies-demo-") as directory:
        database = str(Path(directory) / "demo.db")
        password = secrets.token_urlsafe(18)
        seed_database(database, password)
        os.environ["WEEKLIES_DB_PATH"] = database
        os.environ["WEEKLIES_SECRET_KEY"] = secrets.token_hex(32)
        from proj2.Flask_app import app, find_customer_for_login, start_customer_session

        app.config.update(DATABASE=database, SECRET_KEY=os.environ["WEEKLIES_SECRET_KEY"])

        @app.before_request
        def open_demo_account():
            if request.method != "GET" or request.endpoint in (None, "static"):
                return None
            if not session.get("Username") and not session.get("restaurant_mode"):
                start_customer_session(find_customer_for_login(DEMO_EMAIL), DEMO_EMAIL)
            if request.endpoint == "login":
                return redirect(url_for("index"))
            return None

        today = date.today()
        # Start on a Monday beyond the seeded order history so the comparisons are repeatable.
        start = today + timedelta(days=14 - today.weekday())
        show_profile_examples(app, password, start)
        if args.console_only:
            return 0

        with make_server("127.0.0.1", args.port, app, threaded=True) as server:
            url = f"http://127.0.0.1:{server.server_port}"
            print(f"\nLive demo at {url}/ (opens the demo account automatically)")
            print(f"\nOpen {url}/profile#diet")
            print("Review the combined settings from the console demo or adjust the sliders.")
            print(f"Then open {url}/{start.year}/{start.month}#new-plan")
            print(f"Pick {start}, {DEMO_DAYS} days, and Dinner only.")
            print("Generate Plan to show the results and applied priorities.")
            print("On Home, choose Seed Catalog & Almanac in the Style picker to show the almanac.")
            print("Press Ctrl-C to stop the demo.\n", flush=True)
            server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
