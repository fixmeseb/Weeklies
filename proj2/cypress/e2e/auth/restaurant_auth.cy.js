describe("Restaurant Owner Authentication", () => {
  beforeEach(() => {
    cy.seedDatabase();
  });

  it("successfully logs in with valid restaurant credentials and lands on Orders", () => {
    cy.visit("/restaurant/login");
    cy.get('input[name="email"]').type("owner@tasteofitaly.com");
    cy.get('input[name="password"]').type("password123");
    cy.get('input[type="submit"], button[type="submit"]').click();

    cy.location("pathname").should("eq", "/restaurant/orders");
    cy.get(".restaurant-info").should("contain.text", "Taste of Italy");
  });

  it("shows an error when restaurant credentials are invalid", () => {
    cy.visit("/restaurant/login");
    cy.get('input[name="email"]').type("owner@tasteofitaly.com");
    cy.get('input[name="password"]').type("incorrectpassword");
    cy.get('input[type="submit"], button[type="submit"]').click();

    cy.location("pathname").should("eq", "/restaurant/login");
    cy.get(".flash, .error").should("contain.text", "Invalid credentials");
  });

  it("successfully logs out the restaurant and redirects to restaurant login", () => {
    cy.loginAsRestaurant("owner@tasteofitaly.com", "password123");
    cy.visit("/restaurant/orders");

    cy.get(".owner-tabs a").contains("Logout").click();
    cy.location("pathname").should("eq", "/restaurant/login");

    // Attempting to visit an owner page should redirect back to restaurant login
    cy.visit("/restaurant/orders");
    cy.location("pathname").should("eq", "/restaurant/login");
  });

  it("redirects unauthorized access to restaurant pages", () => {
    cy.visit("/restaurant/dashboard");
    cy.location("pathname").should("eq", "/restaurant/login");

    cy.visit("/restaurant/orders");
    cy.location("pathname").should("eq", "/restaurant/login");

    cy.visit("/restaurant/analytics");
    cy.location("pathname").should("eq", "/restaurant/login");

    cy.visit("/restaurant/reviews");
    cy.location("pathname").should("eq", "/restaurant/login");
  });
});
