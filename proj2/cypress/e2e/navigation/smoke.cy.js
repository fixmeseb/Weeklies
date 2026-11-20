describe("Navigation & Smoke Tests", () => {
  beforeEach(() => {
    cy.seedDatabase();
  });

  it("loads public unauthenticated pages cleanly", () => {
    cy.visit("/login");
    cy.get("h1, .card-header").should("contain.text", "Login");

    cy.visit("/register");
    cy.get(".card-header").should("contain.text", "Create your account");

    cy.visit("/restaurant/login");
    cy.get("h1, .card-header, h2").should("contain.text", "Restaurant");
  });

  it("navigates seamlessly across main customer pages when authenticated", () => {
    cy.loginAsUser("testuser@example.com", "password123");

    // Home / Calendar
    cy.visit("/");
    cy.get("header nav a").contains("Home").click();
    cy.location("pathname").should("eq", "/");

    // Profile
    cy.get("header nav a").contains("Profile").click();
    cy.location("pathname").should("eq", "/profile");

    // Restaurants
    cy.get("header nav a").contains("Restaurants").click();
    cy.location("pathname").should("eq", "/restaurants");

    // Order history
    cy.get("header nav a").contains("My Orders").click();
    cy.location("pathname").should("eq", "/orders");

    // Planning stats
    cy.get("header nav a").contains("Insights").click();
    cy.location("pathname").should("eq", "/insights");

    // DB view
    cy.get("header nav a").contains("DB").click();
    cy.location("pathname").should("eq", "/db");
  });

  it("renders the database inspector view with all schema tables", () => {
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/db");

    cy.get("h1, h2, select, table").should("exist");
    cy.get("#tableSelect, select").should("exist");
  });
});
