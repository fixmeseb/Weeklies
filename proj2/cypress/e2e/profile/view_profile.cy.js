describe("User Profile View", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/profile");
  });

  it("displays user information correctly", () => {
    cy.get(".card-body").first().within(() => {
      cy.contains("John Doe").should("be.visible");
      cy.contains("testuser@example.com").should("be.visible");
      cy.contains("9195550101").should("be.visible");
    });
  });

  it("displays user allergies and preferences", () => {
    cy.get('[aria-label="Allergies"]').should("contain.text", "Peanuts");
    cy.get("#prefBubbles").should("be.visible");
  });

  it("sends the customer to their order history, which now lives on its own page", () => {
    // #6 moved order history off /profile; the profile page links to it instead.
    cy.get("table, .order-list, .meta-grid").should("exist");
    cy.contains("Taste of Italy").should("not.exist");

    cy.contains("a", "My Orders").click();
    cy.location("pathname").should("eq", "/orders");
    cy.get("h1").should("contain.text", "My Orders");

    // The seeded delivered order is there, with its restaurant and its status.
    cy.contains("Taste of Italy").should("be.visible");
    cy.contains("Delivered").should("be.visible");
  });

  it("redirects unauthenticated users to login", () => {
    cy.logoutUser();
    cy.visit("/profile");
    cy.location("pathname").should("eq", "/login");
  });
});
