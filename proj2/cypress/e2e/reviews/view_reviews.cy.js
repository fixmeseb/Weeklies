describe("View Reviews", () => {
  beforeEach(() => {
    cy.seedDatabase();
  });

  it("views individual submitted review for an order", () => {
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/order/1/review/view"); // old address: forwards to the review page
    cy.location("pathname").should("eq", "/order/1/review");

    cy.contains("Order #1").should("be.visible");
    cy.contains("Outstanding Pizza and Pasta!").should("be.visible");
    cy.contains("Taste of Italy").should("be.visible");
  });

  it("views public restaurant reviews page", () => {
    cy.visit("/restaurant/1/reviews");

    cy.contains("Taste of Italy").should("be.visible");
    cy.contains("Outstanding Pizza and Pasta!").should("be.visible");
  });

  it("shows back link to My Orders from the review", () => {
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/order/1/review");

    cy.get("a.back-link").contains(/My Orders/i).click();
    cy.location("pathname").should("eq", "/orders");
  });
});
