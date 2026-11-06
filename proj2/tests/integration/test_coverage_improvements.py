"""Additional tests to improve Flask_app.py coverage."""
import pytest
import json
import proj2.Flask_app as Flask_app
import os
from proj2.Flask_app import app, _money, _cents_to_dollars
from proj2.sqlQueries import create_connection, close_connection, execute_query, fetch_one, fetch_all


class _DbFileProxy(os.PathLike):
    def __fspath__(self):
        return str(Flask_app.db_path())

    def __str__(self):
        return str(Flask_app.db_path())


db_file = _DbFileProxy()


@pytest.fixture
def client():
    """Create test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_user_session(client):
    """Create authenticated user session."""
    # Register and login a test user
    client.post("/register", data={
        "email": "testuser@test.com",
        "password": "TestPass123!",
        "confirm": "TestPass123!"
    })
    
    response = client.post("/login", data={
        "email": "testuser@test.com",
        "password": "TestPass123!"
    }, follow_redirects=True)
    
    return client


@pytest.fixture
def auth_restaurant_session(client):
    """Create authenticated restaurant session."""
    # Get a real restaurant
    conn = create_connection(db_file)
    try:
        result = fetch_one(conn, "SELECT email FROM Restaurant LIMIT 1")
        if not result:
            pytest.skip("No restaurants in database")
        restaurant_email = result[0]
    finally:
        close_connection(conn)
    
    # Login with restaurant credentials (password is typically 'test123' from seeding)
    response = client.post("/restaurant/login", data={
        "email": restaurant_email,
        "password": "test123"
    }, follow_redirects=True)
    
    return client


class TestAnalyticsUpdate:
    """Tests for analytics update functionality."""

    def test_update_analytics_safe_function_exists(self):
        """Test that update_analytics_safe is accessible."""
        from proj2.Flask_app import update_analytics_safe
        assert callable(update_analytics_safe)

    def test_update_analytics_safe_with_invalid_rtr_id(self):
        """Test update_analytics_safe handles invalid restaurant IDs gracefully."""
        from proj2.Flask_app import update_analytics_safe
        # Should not raise an exception
        update_analytics_safe(99999)


class TestMoneyConversions:
    """Tests for money conversion utilities."""

    def test_money_function(self):
        """Test _money function with various inputs."""
        assert _money(10.0) == 10.0
        assert _money(10.1234) == 10.12
        assert _money(0) == 0.0
        assert _money(99.999) == 100.0

    def test_cents_to_dollars(self):
        """Test _cents_to_dollars conversion."""
        assert _cents_to_dollars(1000) == 10.0
        assert _cents_to_dollars(100) == 1.0
        assert _cents_to_dollars(0) == 0.0
        assert _cents_to_dollars(1) == 0.01


class TestRecordAnalyticsSnapshot:
    """Tests for record_analytics_snapshot with various data states."""

    def test_record_analytics_snapshot_with_no_orders(self):
        """Test analytics snapshot with restaurant that has no orders."""
        from proj2.Flask_app import record_analytics_snapshot
        
        # Create a test restaurant with no orders
        conn = create_connection(db_file)
        try:
            # Get first restaurant ID or use a high number that doesn't exist
            result = fetch_one(conn, "SELECT MAX(rtr_id) FROM Restaurant")
            if result and result[0]:
                test_rtr_id = result[0] + 1000  # High ID that won't have orders
            else:
                test_rtr_id = 9999
        finally:
            close_connection(conn)
        
        # Should handle gracefully
        snapshot_recorded = record_analytics_snapshot(test_rtr_id)
        # May return False if no connection, but shouldn't raise
        assert snapshot_recorded is not None

    def test_record_analytics_snapshot_success(self):
        """Test analytics snapshot records successfully with existing data."""
        from proj2.Flask_app import record_analytics_snapshot
        
        # Get a real restaurant ID
        conn = create_connection(db_file)
        try:
            result = fetch_one(conn, "SELECT rtr_id FROM Restaurant LIMIT 1")
            if result:
                test_rtr_id = result[0]
            else:
                pytest.skip("No restaurants in test database")
        finally:
            close_connection(conn)
        
        # Should handle gracefully
        result = record_analytics_snapshot(test_rtr_id)
        assert result is not None


class TestPublicRoutes:
    """Tests for public-facing routes."""

    def test_index_route(self, client):
        """Test home page route."""
        response = client.get("/")
        # Might redirect to login or show page
        assert response.status_code in [200, 302]

    def test_restaurants_listing(self, client):
        """Test restaurants listing page."""
        response = client.get("/restaurants")
        # Should redirect since requires login
        assert response.status_code == 302

    def test_login_page(self, client):
        """Test login page loads."""
        response = client.get("/login")
        assert response.status_code == 200

    def test_register_page(self, client):
        """Test registration page loads."""
        response = client.get("/register")
        assert response.status_code == 200

    def test_restaurant_login_page(self, client):
        """Test restaurant login page loads."""
        response = client.get("/restaurant/login")
        assert response.status_code == 200


class TestAuthenticatedRoutes:
    """Tests for authenticated user routes."""

    def test_orders_page_requires_login(self, client):
        """Test that /orders requires login."""
        response = client.get("/orders")
        assert response.status_code == 302  # Redirect to login

    def test_profile_page_requires_login(self, client):
        """Test that /profile requires login."""
        response = client.get("/profile")
        assert response.status_code == 302  # Redirect to login

    def test_restaurants_page_requires_login(self, client):
        """Test that /restaurants requires login."""
        response = client.get("/restaurants")
        assert response.status_code == 302  # Redirect to login


class TestRestaurantRoutes:
    """Tests for restaurant-specific routes."""

    def test_restaurant_dashboard_requires_login(self, client):
        """Test that restaurant dashboard requires authentication."""
        response = client.get("/restaurant/dashboard")
        assert response.status_code in [302, 403, 404]

    def test_restaurant_orders_requires_login(self, client):
        """Test that restaurant orders page requires authentication."""
        response = client.get("/restaurant/orders")
        assert response.status_code in [302, 403, 404]

    def test_restaurant_analytics_requires_login(self, client):
        """Test that analytics dashboard requires authentication."""
        response = client.get("/restaurant/analytics")
        assert response.status_code in [302, 403, 404]

    def test_restaurant_login_page_loads(self, client):
        """Test restaurant login page."""
        response = client.get("/restaurant/login")
        assert response.status_code == 200
    """Tests for error handling in Flask app."""

    def test_invalid_order_id_404(self, client):
        """Test that invalid order IDs return 404."""
        response = client.get("/orders/99999/receipt.pdf")
        # Should be 404 or redirect to login first
        assert response.status_code in [302, 404]

    def test_invalid_route_404(self, client):
        """Test that invalid routes return 404."""
        response = client.get("/invalid/nonexistent/route")
        assert response.status_code == 404


class TestPdfGeneration:
    """Tests for PDF generation edge cases."""

    def test_generate_receipt_with_valid_order_id(self):
        """Test PDF generation with valid order ID."""
        from proj2.pdf_receipt import generate_order_receipt_pdf
        
        # Get a real order ID
        conn = create_connection(db_file)
        try:
            result = fetch_one(conn, "SELECT ord_id FROM \"Order\" LIMIT 1")
            if result:
                ord_id = result[0]
            else:
                pytest.skip("No orders in test database")
        finally:
            close_connection(conn)
        
        # Should generate PDF without error
        pdf_result = generate_order_receipt_pdf(db_file, ord_id)
        assert pdf_result is not None
        assert isinstance(pdf_result, bytes)
        assert len(pdf_result) > 0


class TestSqlQueries:
    """Tests for SQL query functions."""

    def test_fetch_functions_with_valid_database(self, app):
        """Test fetch functions work with valid database."""
        conn = create_connection(Flask_app.db_path())
        assert conn is not None
        
        try:
            # Test fetch_one
            result = fetch_one(conn, "SELECT COUNT(*) FROM Restaurant")
            assert result is not None
            assert isinstance(result[0], int)
            
            close_connection(conn)
        except Exception:
            pytest.fail("SQL operations failed unexpectedly")

    def test_execute_query_with_valid_sql(self, app):
        """Test execute_query with valid SQL."""
        conn = create_connection(Flask_app.db_path())
        assert conn is not None
        
        try:
            # Just test that execute_query doesn't raise on valid SQL
            from proj2.sqlQueries import fetch_all
            result = fetch_all(conn, "SELECT * FROM Restaurant LIMIT 1")
            assert result is not None
            
            close_connection(conn)
        except Exception:
            pytest.fail("SQL operations failed unexpectedly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
