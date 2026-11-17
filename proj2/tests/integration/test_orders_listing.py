def test_restaurants_page_lists_restaurants_and_items(client, seed_minimal_data, login_session):
    r = client.get("/restaurants")
    assert r.status_code == 200
    # Should contain restaurant and menu items seeded
    assert b"Cafe One" in r.data
    assert b"Pasta" in r.data or b"Salad" in r.data
