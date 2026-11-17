describe("Restaurant Analytics Dashboard", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsRestaurant("owner@tasteofitaly.com", "password123");
    cy.visit("/restaurant/analytics");
  });

  it("renders the analytics dashboard with key metric cards", () => {
    cy.get(".owner-tabs .nav-btn.active").should("contain.text", "Analytics");
    cy.contains("Taste of Italy").should("be.visible");

    // Metrics grid
    cy.get(".analytics-grid").should("be.visible");
    cy.contains(".metric-label", "Total Orders").should("be.visible");
    cy.contains(".metric-label", "Total Revenue").should("be.visible");
    cy.contains(".metric-label", "Avg Order Value").should("be.visible");
  });

  it("switches to the other owner pages from the banner tabs", () => {
    cy.get(".owner-tabs a").contains("Orders").click();
    cy.location("pathname").should("eq", "/restaurant/orders");
    cy.get(".owner-tabs a").contains("Reviews").click();
    cy.location("pathname").should("eq", "/restaurant/reviews");
  });
});
