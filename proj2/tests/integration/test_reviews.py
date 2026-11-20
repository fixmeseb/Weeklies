"""
Integration tests for the review and rating system.
Tests review submission, viewing, and restaurant reviews page.
"""

import json
import pytest
from datetime import datetime
from proj2.sqlQueries import create_connection, close_connection, execute_query, fetch_one


@pytest.fixture()
def db_connection(temp_db_path):
    """Provide a database connection for tests."""
    conn = create_connection(temp_db_path)
    yield conn
    close_connection(conn)


@pytest.mark.integration
def test_review_button_column_in_my_orders(client, seed_minimal_data, login_session, db_connection):
    """Test that Review column appears in profile page when user has orders."""
    # Create a delivered order so the table shows up
    order_details = {
        "placed_at": datetime.now().isoformat(),
        "items": [],
        "charges": {"total": 10.00}
    }
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    response = client.get("/orders")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Review" in html  # Column header should be present


@pytest.mark.integration
def test_review_form_loads_for_delivered_order(client, seed_minimal_data, login_session, db_connection):
    """Test that review form loads with order details for delivered orders."""
    # Create a delivered order
    order_details = {
        "placed_at": datetime.now().isoformat(),
        "items": [{"name": "Pizza", "qty": 2, "line_total": 20.00}],
        "charges": {"total": 25.00}
    }
    
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    # Access review form
    response = client.get(f"/order/{ord_id}/review")
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify form elements present
    assert "Write a Review" in html or "review" in html.lower()
    assert "star" in html.lower()  # Star rating present
    assert f"#{ord_id}" in html  # Order ID shown


@pytest.mark.integration
def test_review_form_redirects_for_non_delivered_order(client, seed_minimal_data, login_session, db_connection):
    """Test that review form redirects for non-delivered orders."""
    # Create an ordered (not delivered) order
    order_details = {"placed_at": datetime.now().isoformat(), "items": [], "charges": {"total": 10.00}}
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "ordered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    # Try to access review form - should redirect to profile
    response = client.get(f"/order/{ord_id}/review", follow_redirects=False)
    assert response.status_code == 302
    assert "/orders" in response.location


@pytest.mark.integration
def test_submit_review_success(client, seed_minimal_data, login_session, db_connection):
    """Test successful review submission."""
    # Create delivered order
    order_details = {
        "placed_at": datetime.now().isoformat(),
        "items": [{"name": "Burger", "qty": 1, "line_total": 12.00}],
        "charges": {"total": 15.00}
    }
    
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    # Submit review
    response = client.post(f"/order/{ord_id}/review", data={
        "rating": "5",
        "title": "Excellent food!",
        "description": "The burger was amazing and delivery was fast."
    }, follow_redirects=False)
    
    assert response.status_code == 302
    assert response.location.endswith(f"/order/{ord_id}/review")  # back to the page, now showing the review
    
    # Verify review exists in database
    review = fetch_one(
        db_connection,
        'SELECT rating, title, description, ord_id FROM "Review" WHERE ord_id = ?',
        (ord_id,)
    )
    assert review is not None
    assert review[0] == 5  # rating
    assert review[1] == "Excellent food!"  # title
    assert review[3] == ord_id  # ord_id


@pytest.mark.integration
def test_submit_review_without_rating_shows_error(client, seed_minimal_data, login_session, db_connection):
    """Test that review submission without rating shows error."""
    # Create delivered order
    order_details = {"placed_at": datetime.now().isoformat(), "items": [], "charges": {"total": 10.00}}
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    # Submit review without rating
    response = client.post(f"/order/{ord_id}/review", data={
        "title": "Good",
        "description": "Nice"
    })
    
    assert response.status_code == 200
    html = response.data.decode()
    assert "rating" in html.lower()  # Error message about rating


@pytest.mark.integration
def test_reviewed_order_shows_the_review(client, seed_minimal_data, login_session, db_connection):
    """Test that trying to review same order twice redirects to existing review."""
    # Create delivered order
    order_details = {"placed_at": datetime.now().isoformat(), "items": [], "charges": {"total": 10.00}}
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    # Submit first review
    execute_query(
        db_connection,
        'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Great", 5, "Loved it", ord_id, datetime.now().isoformat())
    )
    
    # Try to access review form again - should redirect
    response = client.get(f"/order/{ord_id}/review", follow_redirects=False)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Your Review" in html
    assert 'id="reviewForm"' not in html  # no second form once reviewed


@pytest.mark.integration
def test_view_review_shows_individual_review_page(client, seed_minimal_data, login_session, db_connection):
    """Test that viewing a review shows the individual review page."""
    # Create delivered order and review
    order_details = {"placed_at": datetime.now().isoformat(), "items": [], "charges": {"total": 10.00}}
    execute_query(
        db_connection,
        'INSERT INTO "Order" (rtr_id, usr_id, details, status) VALUES (?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], json.dumps(order_details), "delivered")
    )
    
    order = fetch_one(db_connection, 'SELECT ord_id FROM "Order" WHERE usr_id = ? ORDER BY ord_id DESC LIMIT 1', (seed_minimal_data["usr_id"],))
    ord_id = order[0]
    
    execute_query(
        db_connection,
        'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Good", 4, "Nice", ord_id, datetime.now().isoformat())
    )
    
    # View review - should render template with review details
    response = client.get(f"/order/{ord_id}/review")
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify review details are displayed
    assert "Good" in html  # title
    assert "Nice" in html  # description
    assert "Your Review" in html or "review" in html.lower()
    assert f"#{ord_id}" in html or str(ord_id) in html  # Order ID shown


@pytest.mark.integration
def test_restaurant_reviews_page_displays_reviews(client, seed_minimal_data, db_connection):
    """Test that restaurant reviews page displays reviews correctly."""
    # Create multiple reviews
    reviews_data = [
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Great!", 5, "Loved it", 999, datetime.now().isoformat()),
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Good", 4, "Pretty good", 998, datetime.now().isoformat()),
    ]
    
    for review in reviews_data:
        execute_query(
            db_connection,
            'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            review
        )
    
    # Access restaurant reviews page (no login required)
    response = client.get(f"/restaurant/{seed_minimal_data['rtr_id']}/reviews")
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify reviews appear
    assert "Great!" in html
    assert "Good" in html
    assert "Loved it" in html


@pytest.mark.integration
def test_restaurant_reviews_empty_state(client, db_connection):
    """Test that empty state displays when restaurant has no reviews."""
    # Create a restaurant with no reviews
    execute_query(
        db_connection,
        'INSERT INTO "Restaurant" (name, email, password_HS) VALUES (?, ?, ?)',
        ("No Reviews Rest", "noreview@test.com", "hash")
    )
    
    rest = fetch_one(db_connection, 'SELECT rtr_id FROM "Restaurant" WHERE email = ?', ("noreview@test.com",))
    rtr_id = rest[0]
    
    response = client.get(f"/restaurant/{rtr_id}/reviews")
    assert response.status_code == 200
    html = response.data.decode()
    
    assert "No Reviews Yet" in html or "No reviews yet" in html.lower()


@pytest.mark.integration
def test_review_requires_authentication(client):
    """Test that review routes require authentication."""
    # Try to access review form without login
    response = client.get("/order/1/review", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.location
    
    # Try to view review without login
    # the old address forwards to the review page, which asks for a login
    response = client.get("/order/1/review/view", follow_redirects=False)
    assert response.status_code == 302
    assert response.location.endswith("/order/1/review")


@pytest.mark.integration
def test_restaurant_reviews_sorting(client, seed_minimal_data, db_connection):
    """Test sorting functionality on restaurant reviews page."""
    # Create reviews with different ratings
    reviews = [
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Low", 2, "Not great", 996, datetime.now().isoformat()),
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "High", 5, "Amazing", 995, datetime.now().isoformat()),
    ]
    
    for review in reviews:
        execute_query(
            db_connection,
            'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            review
        )
    
    # Test highest rating sort
    response = client.get(f"/restaurant/{seed_minimal_data['rtr_id']}/reviews?sort=highest")
    assert response.status_code == 200
    html = response.data.decode()
    assert "High" in html or "Amazing" in html
    
    # Test lowest rating sort
    response = client.get(f"/restaurant/{seed_minimal_data['rtr_id']}/reviews?sort=lowest")
    assert response.status_code == 200


@pytest.mark.integration
def test_restaurant_reviews_filtering(client, seed_minimal_data, db_connection):
    """Test filtering functionality on restaurant reviews page."""
    # Create reviews with different ratings
    reviews = [
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Five stars", 5, "Perfect", 994, datetime.now().isoformat()),
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Three stars", 3, "OK", 993, datetime.now().isoformat()),
    ]
    
    for review in reviews:
        execute_query(
            db_connection,
            'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            review
        )
    
    # Filter by 5 stars
    response = client.get(f"/restaurant/{seed_minimal_data['rtr_id']}/reviews?filter=5")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Five stars" in html or "Perfect" in html


@pytest.mark.integration
def test_owner_tabs_show_review_stats(client, seed_minimal_data, db_connection):
    """Test that restaurant dashboard displays review statistics."""
    # Create restaurant session
    with client.session_transaction() as sess:
        sess["rtr_id"] = seed_minimal_data["rtr_id"]
        sess["RestaurantName"] = "Test Restaurant"
        sess["RestaurantEmail"] = "restaurant@test.com"
        sess["restaurant_mode"] = True
    
    # Create some reviews
    reviews = [
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Great", 5, "Excellent", 991, datetime.now().isoformat()),
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Good", 4, "Nice", 990, datetime.now().isoformat()),
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "OK", 3, "Decent", 989, datetime.now().isoformat()),
    ]
    
    for review in reviews:
        execute_query(
            db_connection,
            'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            review
        )
    
    # Access restaurant dashboard
    response = client.get("/restaurant/orders")  # rating sits on the Reviews tab
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify review card is present
    assert "Reviews" in html
    assert "3 Reviews" in html or "3" in html  # Review count
    # Average rating should be 4.0 (5+4+3)/3
    assert "4.0" in html or "4" in html


@pytest.mark.integration
def test_owner_tabs_no_reviews_state(client, db_connection):
    """Test that restaurant dashboard shows 'No Reviews Yet' when no reviews exist."""
    # Create a new restaurant with no reviews
    execute_query(
        db_connection,
        'INSERT INTO "Restaurant" (name, email, password_HS, phone, address, city, state, zip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        ("New Restaurant", "new@test.com", "hash", "555-0000", "123 St", "City", "ST", 12345)
    )
    
    rest = fetch_one(db_connection, 'SELECT rtr_id FROM "Restaurant" WHERE email = ?', ("new@test.com",))
    rtr_id = rest[0]
    
    # Create restaurant session
    with client.session_transaction() as sess:
        sess["rtr_id"] = rtr_id
        sess["RestaurantName"] = "New Restaurant"
        sess["RestaurantEmail"] = "new@test.com"
        sess["restaurant_mode"] = True
    
    # Access dashboard
    response = client.get("/restaurant/orders")  # rating sits on the Reviews tab
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify no reviews state
    assert "No Reviews Yet" in html or "0 Reviews" in html


@pytest.mark.integration
def test_restaurant_can_view_their_reviews_page(client, seed_minimal_data, db_connection):
    """Test that restaurant can access their reviews page from dashboard."""
    # Create restaurant session
    with client.session_transaction() as sess:
        sess["rtr_id"] = seed_minimal_data["rtr_id"]
        sess["RestaurantName"] = "Test Restaurant"
        sess["RestaurantEmail"] = "restaurant@test.com"
        sess["restaurant_mode"] = True
    
    # Create a review
    execute_query(
        db_connection,
        'INSERT INTO "Review" (rtr_id, usr_id, title, rating, description, ord_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (seed_minimal_data["rtr_id"], seed_minimal_data["usr_id"], "Great Service", 5, "Amazing food", 988, datetime.now().isoformat())
    )
    
    # Access the secure restaurant owner reviews page
    response = client.get("/restaurant/reviews")
    assert response.status_code == 200
    html = response.data.decode()
    
    # Verify review is displayed
    assert "Great Service" in html
    assert "Amazing food" in html
    
    # Verify restaurant navigation is present (not customer navigation)
    assert 'href="/restaurant/orders"' in html  # the banner's Orders tab
    assert "restaurant@test.com" in html
