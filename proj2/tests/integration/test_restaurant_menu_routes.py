"""
The restaurant menu pages and their JSON API.

The checks live in ``proj2.menu_items`` and are tested there; these tests are about the
routes carrying them faithfully: that the signed-in restaurant is the only one that can
be acted on, that the HTML form and the JSON API agree, and that the published schema
describes the server that serves it.
"""

import json

import pytest

from proj2 import menu_items
from proj2.db import get_db


@pytest.fixture()
def owner(client, seed_minimal_data):
    """A signed-in restaurant owner."""
    with client.session_transaction() as sess:
        sess["restaurant_mode"] = True
        sess["rtr_id"] = seed_minimal_data["rtr_id"]
        sess["RestaurantName"] = "Cafe One"
        sess["RestaurantEmail"] = "owner@test.com"
    return seed_minimal_data


@pytest.fixture()
def rival(client, app_context, seed_minimal_data):
    """A second restaurant and one dish of its own, which the owner must not touch.

    The test database is shared across the session, so this is idempotent: it reuses the
    rival and its dish when an earlier test already created them, and always restores the
    dish's price so a test that tried to change it still sees the original.
    """
    conn = get_db()
    row = conn.execute(
        'SELECT rtr_id FROM "Restaurant" WHERE email = ?', ("rival@test.com",)
    ).fetchone()
    if row is None:
        conn.execute(
            'INSERT INTO "Restaurant" (name, email, status) VALUES (?, ?, ?)',
            ("Rival", "rival@test.com", "open"),
        )
        row = conn.execute(
            'SELECT rtr_id FROM "Restaurant" WHERE email = ?', ("rival@test.com",)
        ).fetchone()
    rtr_id = row[0]

    existing = conn.execute(
        'SELECT itm_id FROM "MenuItem" WHERE rtr_id = ? AND name = ?', (rtr_id, "Rival Special")
    ).fetchone()
    if existing is None:
        itm_id, errors = menu_items.create(
            conn,
            rtr_id,
            {
                "name": "Rival Special",
                "price": "11.00",
                "protein": "chicken",
                "cuisine": "american",
                "carb_base": "rice",
            },
        )
        assert errors == {}
    else:
        itm_id = existing[0]
        conn.execute('UPDATE "MenuItem" SET price = 1100 WHERE itm_id = ?', (itm_id,))
    conn.commit()
    return {"rtr_id": rtr_id, "itm_id": itm_id}


def dish(**overrides):
    body = {
        "name": "Seitan Larb Bowl",
        "price": "13.50",
        "protein": "tofu",
        "cuisine": "thai",
        "carb_base": "rice",
    }
    body.update(overrides)
    return body


## --- access ---------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/restaurant/menu"),
        ("post", "/restaurant/menu/new"),
        ("post", "/restaurant/menu/1/edit"),
        ("post", "/restaurant/menu/1/stock"),
        ("post", "/restaurant/menu/1/delete"),
        ("get", "/api/restaurant/menu"),
        ("get", "/api/restaurant/menu/schema"),
        ("post", "/api/restaurant/menu"),
        ("patch", "/api/restaurant/menu/1"),
        ("delete", "/api/restaurant/menu/1"),
    ],
)
def test_every_menu_route_needs_an_owner_session(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code in (302, 303)
    assert "/restaurant/login" in response.headers["Location"]


## --- the page -------------------------------------------------------------


def test_the_page_lists_the_restaurant_s_own_dishes(client, owner):
    response = client.get("/restaurant/menu")
    assert response.status_code == 200
    assert b"Pasta" in response.data


def test_the_page_does_not_show_another_restaurant_s_dish(client, owner, rival):
    response = client.get("/restaurant/menu")
    assert b"Rival Special" not in response.data


def test_the_page_offers_only_tag_values_the_server_accepts(client, owner):
    """The form is built from schema(), so it cannot suggest a value validate() rejects."""
    body = client.get("/restaurant/menu").data.decode()
    assert "tofu" in body and "unicorn" not in body


def test_the_menu_tab_appears_in_the_owner_banner(client, owner):
    assert b"Menu" in client.get("/restaurant/menu").data


## --- adding through the form ---------------------------------------------


def test_the_form_adds_a_dish(client, owner, app_context):
    response = client.post("/restaurant/menu/new", data=dish(), follow_redirects=False)
    assert response.status_code in (302, 303)
    rows = menu_items.list_items(get_db(), owner["rtr_id"])
    assert any(row["name"] == "Seitan Larb Bowl" for row in rows)


def test_the_form_reports_a_missing_required_tag_without_losing_what_was_typed(client, owner):
    submitted = dish(protein="")
    response = client.post("/restaurant/menu/new", data=submitted)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Protein is required" in body
    assert "Seitan Larb Bowl" in body


def test_the_form_reports_a_bad_price(client, owner):
    response = client.post("/restaurant/menu/new", data=dish(price="12.999"))
    assert b"two decimals" in response.data


def test_the_form_reports_a_dish_that_contradicts_itself(client, owner):
    response = client.post("/restaurant/menu/new", data=dish(protein="beef", diet_tags="vegan"))
    assert b"contradicts itself" in response.data


## --- editing and withdrawing through the form ----------------------------


def test_the_form_edits_only_the_signed_in_restaurant_s_dish(client, owner, rival, app_context):
    response = client.post(f"/restaurant/menu/{rival['itm_id']}/edit", data={"price": "0.01"})
    assert response.status_code == 404
    row = menu_items.get_item(get_db(), rival["rtr_id"], rival["itm_id"])
    assert row["price"] == 1100


def test_the_form_takes_a_dish_off_the_menu(client, owner, app_context):
    client.post("/restaurant/menu/new", data=dish())
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Seitan Larb Bowl"
    )
    client.post(f"/restaurant/menu/{itm_id}/stock", data={"instock": "0"})
    assert menu_items.get_item(get_db(), owner["rtr_id"], itm_id)["instock"] == 0


def test_the_form_refuses_to_delete_a_planned_dish_and_explains_why(client, owner, app_context):
    conn = get_db()
    itm_id, errors = menu_items.create(conn, owner["rtr_id"], dish(name="Planned Plate"))
    assert errors == {}
    conn.execute('UPDATE "User" SET generated_menu = ?', (f"[2026-11-23,{itm_id},3]",))
    conn.commit()
    response = client.post(f"/restaurant/menu/{itm_id}/delete")
    assert response.status_code == 200
    assert b"out of stock instead" in response.data
    assert menu_items.get_item(get_db(), owner["rtr_id"], itm_id) is not None


## --- the JSON API --------------------------------------------------------


def test_the_api_lists_dishes_with_the_price_in_cents_and_dollars(client, owner):
    payload = client.get("/api/restaurant/menu").get_json()
    item = next(row for row in payload["items"] if row["name"] == "Pasta")
    assert item["price_cents"] == 1299
    assert item["price_dollars"] == "12.99"


def test_the_api_creates_a_dish_and_returns_it(client, owner):
    response = client.post("/api/restaurant/menu", json=dish())
    assert response.status_code == 201
    item = response.get_json()["item"]
    assert item["name"] == "Seitan Larb Bowl"
    assert item["price_cents"] == 1350


def test_the_api_rejects_a_bad_field_with_422_and_names_it(client, owner):
    response = client.post("/api/restaurant/menu", json=dish(protein="unicorn"))
    assert response.status_code == 422
    assert "protein" in response.get_json()["errors"]


def test_the_api_rejects_a_body_that_is_not_an_object(client, owner):
    response = client.post("/api/restaurant/menu", data="[]", content_type="application/json")
    assert response.status_code == 400


def test_the_api_patches_only_the_fields_the_body_carries(client, owner):
    created = client.post("/api/restaurant/menu", json=dish()).get_json()["item"]
    response = client.patch(f"/api/restaurant/menu/{created['itm_id']}", json={"calories": 700})
    assert response.status_code == 200
    item = response.get_json()["item"]
    assert item["calories"] == 700
    assert item["price_cents"] == 1350
    assert item["protein"] == "tofu"


def test_the_api_will_not_touch_another_restaurant_s_dish(client, owner, rival):
    assert (
        client.patch(f"/api/restaurant/menu/{rival['itm_id']}", json={"price": "0.01"}).status_code
        == 404
    )
    assert client.delete(f"/api/restaurant/menu/{rival['itm_id']}").status_code == 404


def test_the_api_takes_a_dish_off_the_menu(client, owner):
    created = client.post("/api/restaurant/menu", json=dish()).get_json()["item"]
    response = client.post(
        f"/api/restaurant/menu/{created['itm_id']}/stock", json={"instock": False}
    )
    assert response.get_json()["item"]["instock"] == 0


def test_the_api_deletes_an_unreferenced_dish(client, owner):
    created = client.post("/api/restaurant/menu", json=dish()).get_json()["item"]
    response = client.delete(f"/api/restaurant/menu/{created['itm_id']}")
    assert response.status_code == 200
    assert (
        client.patch(
            f"/api/restaurant/menu/{created['itm_id']}", json={"price": "1.00"}
        ).status_code
        == 404
    )


def test_the_api_refuses_to_delete_a_planned_dish_with_409(client, owner, app_context):
    created = client.post("/api/restaurant/menu", json=dish(name="Held Plate")).get_json()["item"]
    conn = get_db()
    conn.execute('UPDATE "User" SET generated_menu = ?', (f"[2026-11-23,{created['itm_id']},3]",))
    conn.commit()
    response = client.delete(f"/api/restaurant/menu/{created['itm_id']}")
    assert response.status_code == 409
    assert "_blocked" in response.get_json()["errors"]


def test_the_api_accepts_form_encoded_bodies_too(client, owner):
    """The HTML form and the API are the same validator; neither encoding is privileged."""
    response = client.post("/api/restaurant/menu", data=dish(name="Form Encoded"))
    assert response.status_code == 201


## --- the published contract ----------------------------------------------


def test_the_schema_route_describes_the_server_that_serves_it(client, owner):
    published = client.get("/api/restaurant/menu/schema").get_json()
    assert published == menu_items.schema()


def test_every_required_field_in_the_schema_is_actually_enforced(client, owner):
    published = client.get("/api/restaurant/menu/schema").get_json()
    for field in published["required"]:
        body = dish()
        body[field] = ""
        response = client.post("/api/restaurant/menu", json=body)
        assert response.status_code == 422, f"{field} is published as required but was accepted"
        assert field in response.get_json()["errors"]


def test_the_schema_is_json_serialisable_without_surprises(client, owner):
    raw = client.get("/api/restaurant/menu/schema").data
    assert json.loads(raw)["fields"]["protein"]["required"] is True
