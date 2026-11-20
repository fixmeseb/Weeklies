"""
Integration tests for restaurant authentication system.

Tests cover:
- Restaurant login page rendering
- Restaurant authentication with valid/invalid credentials
- Restaurant session management
- Restaurant logout functionality
- Protected route access with @restaurant_required decorator
"""

import pytest
from werkzeug.security import generate_password_hash
from proj2.sqlQueries import create_connection, close_connection, execute_query, fetch_one


@pytest.fixture()
def seed_restaurant(temp_db_path):
    """
    Seed a test restaurant with known credentials.
    Email: restaurant@test.com
    Password: rest123
    """
    conn = create_connection(temp_db_path)
    try:
        # Check if restaurant already exists
        rtr_row = fetch_one(
            conn, "SELECT rtr_id FROM Restaurant WHERE email=?", ("restaurant@test.com",)
        )

        if rtr_row is None:
            # Insert test restaurant
            password_hash = generate_password_hash("rest123")
            execute_query(
                conn,
                """
                INSERT INTO Restaurant(name, email, password_HS, phone, address, city, state, zip, status, hours)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "Test Restaurant",
                    "restaurant@test.com",
                    password_hash,
                    "5551234567",
                    "123 Test St",
                    "Raleigh",
                    "NC",
                    "27606",
                    "open",
                    '{"Monday": "9-5", "Tuesday": "9-5"}',
                ),
            )

            rtr_row = fetch_one(
                conn, "SELECT rtr_id FROM Restaurant WHERE email=?", ("restaurant@test.com",)
            )
        else:
            # Update password to ensure consistency
            password_hash = generate_password_hash("rest123")
            execute_query(
                conn,
                "UPDATE Restaurant SET password_HS=? WHERE email=?",
                (password_hash, "restaurant@test.com"),
            )

        rtr_id = rtr_row[0] if rtr_row else None
        assert rtr_id is not None, "Failed to seed test restaurant"

    finally:
        close_connection(conn)

    return {"rtr_id": rtr_id, "email": "restaurant@test.com", "password": "rest123"}


@pytest.mark.integration
class TestRestaurantLogin:
    """Test suite for restaurant login functionality."""

    def test_restaurant_login_page_renders(self, client):
        """GET /restaurant/login should render the login page."""
        response = client.get("/restaurant/login")
        assert response.status_code == 200
        assert b"Restaurant Portal" in response.data
        assert b"Restaurant Email" in response.data
        assert b"Login to Dashboard" in response.data

    def test_restaurant_login_with_valid_credentials(self, client, seed_restaurant):
        """POST /restaurant/login with valid credentials should redirect to dashboard."""
        response = client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert "/restaurant/orders" in response.location

    def test_restaurant_login_with_invalid_email(self, client, seed_restaurant):
        """POST /restaurant/login with non-existent email should show error."""
        response = client.post(
            "/restaurant/login", data={"email": "nonexistent@test.com", "password": "anypassword"}
        )

        assert response.status_code == 200
        assert b"Invalid credentials" in response.data

    def test_restaurant_login_with_wrong_password(self, client, seed_restaurant):
        """POST /restaurant/login with wrong password should show error."""
        response = client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": "wrongpassword"},
        )

        assert response.status_code == 200
        assert b"Invalid credentials" in response.data

    def test_restaurant_login_with_empty_credentials(self, client):
        """POST /restaurant/login with empty fields should handle gracefully."""
        response = client.post("/restaurant/login", data={"email": "", "password": ""})

        assert response.status_code == 200
        assert b"Invalid credentials" in response.data

    def test_restaurant_login_case_insensitive_email(self, client, seed_restaurant):
        """Restaurant email should be case-insensitive."""
        response = client.post(
            "/restaurant/login",
            data={
                "email": "RESTAURANT@TEST.COM",  # uppercase
                "password": seed_restaurant["password"],
            },
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert "/restaurant/orders" in response.location

    def test_restaurant_login_trims_whitespace(self, client, seed_restaurant):
        """Restaurant login should trim whitespace from email."""
        response = client.post(
            "/restaurant/login",
            data={
                "email": "  restaurant@test.com  ",  # with spaces
                "password": seed_restaurant["password"],
            },
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert "/restaurant/orders" in response.location


@pytest.mark.integration
class TestRestaurantSession:
    """Test suite for restaurant session management."""

    def test_restaurant_session_created_on_login(self, client, seed_restaurant):
        """Login should create restaurant session with correct data."""
        # Login and follow redirect to dashboard
        response = client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
            follow_redirects=True,
        )

        # Verify we got to the dashboard (session was created successfully)
        assert response.status_code == 200
        assert b"Test Restaurant" in response.data
        assert b"restaurant@test.com" in response.data

    def test_restaurant_session_persists_across_requests(self, client, seed_restaurant):
        """Restaurant session should persist across multiple requests."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Make another request
        response = client.get("/restaurant/orders")
        assert response.status_code == 200
        assert b"Test Restaurant" in response.data

    def test_customer_session_does_not_grant_restaurant_access(self, client, seed_minimal_data):
        """Customer login should not grant access to restaurant routes."""
        # Login as customer
        client.post("/login", data={"email": "test@x.com", "password": "secret123"})

        # Try to access restaurant dashboard
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location


@pytest.mark.integration
class TestRestaurantLogout:
    """Test suite for restaurant logout functionality."""

    def test_restaurant_logout_clears_session(self, client, seed_restaurant):
        """Logout should clear all restaurant session data."""
        # Login first
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Verify dashboard is accessible (session exists)
        response = client.get("/restaurant/orders")
        assert response.status_code == 200

        # Logout
        client.get("/restaurant/logout")

        # Verify session cleared - dashboard should redirect to login
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location

    def test_restaurant_logout_redirects_to_login(self, client, seed_restaurant):
        """Logout should redirect to restaurant login page."""
        # Login first
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Logout
        response = client.get("/restaurant/logout", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location

    def test_logout_prevents_dashboard_access(self, client, seed_restaurant):
        """After logout, dashboard should be inaccessible."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Verify dashboard accessible
        response = client.get("/restaurant/orders")
        assert response.status_code == 200

        # Logout
        client.get("/restaurant/logout")

        # Try to access dashboard again
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location


@pytest.mark.integration
class TestRestaurantDashboard:
    """Test suite for restaurant dashboard access and rendering."""

    def test_dashboard_requires_authentication(self, client):
        """Dashboard should redirect to login when not authenticated."""
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location

    def test_dashboard_accessible_after_login(self, client, seed_restaurant):
        """Dashboard should be accessible after successful login."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Access dashboard
        response = client.get("/restaurant/orders")
        assert response.status_code == 200
        assert b"Test Restaurant" in response.data
        assert b"restaurant@test.com" in response.data

    def test_dashboard_displays_restaurant_name(self, client, seed_restaurant):
        """Dashboard should display the logged-in restaurant's name."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Check dashboard content
        response = client.get("/restaurant/orders")
        assert b"Test Restaurant" in response.data

    def test_dashboard_has_logout_button(self, client, seed_restaurant):
        """Dashboard should have a logout button/link."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Check dashboard has logout
        response = client.get("/restaurant/orders")
        assert b"Logout" in response.data or b"logout" in response.data

    def test_dashboard_has_cache_control_headers(self, client, seed_restaurant):
        """Dashboard should have cache-control headers to prevent caching."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Check headers
        response = client.get("/restaurant/orders")
        assert "Cache-Control" in response.headers
        assert "no-cache" in response.headers["Cache-Control"].lower()
        assert "no-store" in response.headers["Cache-Control"].lower()


@pytest.mark.integration
class TestRestaurantProtectedRoutes:
    """Test suite for @restaurant_required decorator on protected routes."""

    def test_direct_dashboard_access_without_login(self, client):
        """Accessing dashboard URL directly should redirect to login."""
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location

    def test_multiple_requests_maintain_session(self, client, seed_restaurant):
        """Multiple requests should maintain restaurant session."""
        # Login
        client.post(
            "/restaurant/login",
            data={"email": seed_restaurant["email"], "password": seed_restaurant["password"]},
        )

        # Make multiple requests
        for _ in range(3):
            response = client.get("/restaurant/orders")
            assert response.status_code == 200

    def test_session_isolation_between_customer_and_restaurant(
        self, client, seed_minimal_data, seed_restaurant
    ):
        """Customer and restaurant sessions should be isolated."""
        # Login as customer
        client.post("/login", data={"email": "test@x.com", "password": "secret123"})

        # Customer should access their routes
        response = client.get("/profile")
        assert response.status_code == 200

        # But not restaurant routes
        response = client.get("/restaurant/orders", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/restaurant/login" in response.location


@pytest.mark.integration
class TestRestaurantLoginNavigation:
    """Test suite for navigation links between customer and restaurant login."""

    def test_customer_login_has_restaurant_link(self, client):
        """Customer login page should have link to restaurant login."""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Restaurant Owner" in response.data or b"restaurant/login" in response.data

    def test_restaurant_login_has_customer_link(self, client):
        """Restaurant login page should have link back to customer login."""
        response = client.get("/restaurant/login")
        assert response.status_code == 200
        assert b"Customer Login" in response.data or b"/login" in response.data
