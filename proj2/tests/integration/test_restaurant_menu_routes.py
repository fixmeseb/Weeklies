"""
The restaurant menu pages and their JSON API.

The checks live in ``proj2.menu_items`` and are tested there; these tests are about the
routes carrying them faithfully: that the signed-in restaurant is the only one that can
be acted on, that the HTML form and the JSON API agree, and that the published schema
describes the server that serves it.
"""

import json
import re

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


## --- searching, narrowing and editing on the page ------------------------


def test_search_narrows_the_page_to_matching_dishes(client, owner):
    body = client.get("/restaurant/menu?q=pasta").data
    assert b"Pasta" in body and b"Salad" not in body


def test_a_search_that_matches_nothing_offers_a_way_back(client, owner):
    body = client.get("/restaurant/menu?q=zzzznothing").data
    assert b"Nothing here matches" in body


def test_the_filters_narrow_the_page(client, owner, app_context):
    conn = get_db()
    itm_id, errors = menu_items.create(conn, owner["rtr_id"], dish(name="Withdrawn Plate"))
    assert errors == {}
    menu_items.set_stock(conn, owner["rtr_id"], itm_id, False)
    conn.commit()
    assert b"Withdrawn Plate" not in client.get("/restaurant/menu?show=on").data
    assert b"Withdrawn Plate" in client.get("/restaurant/menu?show=off").data


def test_an_unknown_filter_falls_back_to_showing_everything(client, owner):
    assert client.get("/restaurant/menu?show=../etc").status_code == 200
    assert b"Pasta" in client.get("/restaurant/menu?show=../etc").data


def test_the_untagged_filter_surfaces_a_dish_the_planner_cannot_place(client, owner, app_context):
    conn = get_db()
    conn.execute(
        'INSERT INTO "MenuItem" (rtr_id, name, price, instock) VALUES (?, ?, 1200, 1)',
        (owner["rtr_id"], "Imported Mystery"),
    )
    conn.commit()
    body = client.get("/restaurant/menu?show=untagged").data
    assert b"Imported Mystery" in body
    assert b"needs tags" in body


def test_edit_opens_one_form_for_one_dish(client, owner, app_context):
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Pasta"
    )
    body = client.get(f"/restaurant/menu?edit={itm_id}").data.decode()
    assert "Editing Pasta" in body
    ## The form posts to that dish's edit route, with its stored values already in it.
    assert f'action="/restaurant/menu/{itm_id}/edit"' in body
    assert 'value="Pasta"' in body
    assert 'value="12.99"' in body


def test_only_the_edited_dish_gets_a_form(client, owner, app_context):
    """One form on the page, not one per dish: ?edit is what keeps the page small."""
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Pasta"
    )
    body = client.get(f"/restaurant/menu?edit={itm_id}").data.decode()
    assert body.count("Editing ") == 1


def test_edit_of_another_restaurant_s_dish_is_not_found(client, owner, rival):
    assert client.get(f"/restaurant/menu?edit={rival['itm_id']}").status_code == 404


def test_edit_of_a_dish_that_does_not_exist_is_not_found(client, owner):
    assert client.get("/restaurant/menu?edit=999999").status_code == 404


def test_a_nonsense_edit_id_is_ignored_rather_than_crashing(client, owner):
    assert client.get("/restaurant/menu?edit=abc").status_code == 200


## --- the tag pickers -----------------------------------------------------


def test_a_tag_group_always_sends_a_value_so_clearing_works(client, owner):
    """Without the hidden empty value, unticking every box would silently do nothing."""
    body = client.get("/restaurant/menu").data.decode()
    assert '<input type="hidden" name="protein" value="" />' in body


def test_the_form_builds_its_choices_from_the_server_s_vocabulary(client, owner):
    body = client.get("/restaurant/menu").data.decode()
    for value in menu_items.schema()["fields"]["protein"]["values"]:
        assert f'value="{value}"' in body


def test_ticking_several_boxes_stores_one_cell(client, owner, app_context):
    ## A list value is how the test client sends one field twice, which is what a
    ## checkbox group does in a browser.
    client.post(
        "/restaurant/menu/new",
        data={
            "name": "Combo Bowl",
            "price": "10.00",
            "protein": ["tofu", "legumes"],
            "cuisine": "thai",
            "carb_base": "rice",
        },
    )
    row = next(
        item
        for item in menu_items.list_items(get_db(), owner["rtr_id"])
        if item["name"] == "Combo Bowl"
    )
    assert row["protein"] == "legumes, tofu"


def test_unticking_every_box_clears_an_optional_tag(client, owner, app_context):
    conn = get_db()
    itm_id, errors = menu_items.create(
        conn, owner["rtr_id"], dish(name="Smoky Plate", flavor="smoky")
    )
    assert errors == {}
    conn.commit()
    client.post(f"/restaurant/menu/{itm_id}/edit", data={"flavor": ""})
    assert menu_items.get_item(get_db(), owner["rtr_id"], itm_id)["flavor"] is None


## --- reporting problems --------------------------------------------------


def test_a_rejected_form_lists_its_problems_and_links_to_them(client, owner):
    body = client.post("/restaurant/menu/new", data=dish(protein="", cuisine="")).data.decode()
    assert 'href="#new-protein"' in body
    assert 'href="#new-cuisine"' in body


def test_a_rejected_field_is_marked_invalid_for_assistive_technology(client, owner):
    body = client.post("/restaurant/menu/new", data=dish(price="nope")).data.decode()
    assert 'aria-invalid="true"' in body
    assert 'aria-describedby="new-price-bad"' in body
    assert 'id="new-price-bad"' in body


def test_a_rejected_add_reopens_the_add_panel(client, owner):
    body = client.post("/restaurant/menu/new", data=dish(price="nope")).data.decode()
    assert '<details class="panel" open>' in body


def _ticked(body, form_id):
    """The (name, value) of every ticked box in one form."""
    form = body.split(f'id="{form_id}"')[1].split("</form>")[0]
    boxes = re.findall(r'<input type="checkbox"[^>]*>', form)
    return {
        (re.search(r'name="([^"]*)"', box)[1], re.search(r'value="([^"]*)"', box)[1])
        for box in boxes
        if re.search(r"\schecked\b", box)
    }


# What a browser posts: the picker's empty hidden value, then one value per ticked box
CONTRADICTION = {
    "protein": ["", "fish", "legumes"],
    "cuisine": ["", "japanese"],
    "carb_base": ["", "rice"],
    "diet_tags": ["", "vegan"],
}
TICKED = {(name, value) for name, values in CONTRADICTION.items() for value in values if value}


def test_a_refused_dish_keeps_its_ticked_boxes(client, owner):
    body = client.post("/restaurant/menu/new", data=dish(**CONTRADICTION)).data.decode()
    assert "contradicts itself" in body
    assert _ticked(body, "add-dish-form") == TICKED


def test_a_refused_edit_keeps_its_ticked_boxes(client, owner, app_context):
    itm_id, errors = menu_items.create(
        get_db(), owner["rtr_id"], dish(name="Edited Plate", diet_tags="vegetarian")
    )
    assert errors == {}
    body = client.post(
        f"/restaurant/menu/{itm_id}/edit", data=dish(name="Edited Plate", **CONTRADICTION)
    ).data.decode()
    assert "contradicts itself" in body
    # what was submitted, with the stored tofu and vegetarian ticks gone
    assert _ticked(body, "edit-dish-form") == TICKED


def test_a_rejected_edit_keeps_that_dish_s_form_open(client, owner, app_context):
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Pasta"
    )
    body = client.post(f"/restaurant/menu/{itm_id}/edit", data={"price": "nope"}).data.decode()
    assert "Editing Pasta" in body
    assert f'href="#e{itm_id}-price"' in body


def test_a_stored_null_renders_as_an_empty_field_not_the_word_none(client, owner, app_context):
    conn = get_db()
    itm_id, errors = menu_items.create(conn, owner["rtr_id"], dish(name="Bare Plate"))
    assert errors == {}
    conn.commit()
    body = client.get(f"/restaurant/menu?edit={itm_id}").data.decode()
    assert 'value="None"' not in body
    assert ">None<" not in body


## --- keeping the two forms apart -----------------------------------------
##
## The add form stays in the page, collapsed, while an edit form is open, so every
## tag checkbox exists twice. Anything driving one form -- the Cypress spec, a future
## script -- has to scope itself, and these tests are what keep the ids there to
## scope to.


def test_the_page_has_one_add_form_and_no_edit_form(client, owner):
    body = client.get("/restaurant/menu").data.decode()
    assert body.count('id="add-dish-form"') == 1
    assert 'id="edit-dish-form"' not in body


def test_opening_an_edit_adds_exactly_one_more_form(client, owner, app_context):
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Pasta"
    )
    body = client.get(f"/restaurant/menu?edit={itm_id}").data.decode()
    assert body.count('id="add-dish-form"') == 1
    assert body.count('id="edit-dish-form"') == 1


def test_a_tag_checkbox_is_ambiguous_while_an_edit_is_open(client, owner, app_context):
    """The reason the ids exist: an unscoped selector would match twice."""
    conn = get_db()
    itm_id = next(
        row["itm_id"]
        for row in menu_items.list_items(conn, owner["rtr_id"])
        if row["name"] == "Pasta"
    )
    flat = re.sub(r"\s+", " ", client.get(f"/restaurant/menu?edit={itm_id}").data.decode())
    assert flat.count('name="protein" value="legumes"') == 2
