describe("Restaurant Dashboard & Order Lifecycle", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsRestaurant("owner@tasteofitaly.com", "password123");
  });

  it("sends the old dashboard address to Orders, with tabs for every owner page", () => {
    cy.visit("/restaurant/dashboard");
    cy.location("pathname").should("eq", "/restaurant/orders");

    cy.get(".restaurant-info").should("contain.text", "Taste of Italy");
    cy.get(".owner-tabs .nav-btn.active").should("contain.text", "Orders").and("contain.text", "active");
    cy.get(".owner-tabs").should("contain.text", "Analytics");
    cy.get(".owner-tabs").should("contain.text", "Reviews");
  });

  it("navigates to order management and displays orders grouped by status", () => {
    cy.visit("/restaurant/orders");

    cy.get("h1, .restaurant-info").should("contain.text", "Taste of Italy");
    cy.get(".stats-grid").should("be.visible");

    // Seeded data has Ordered, Accepted, Delivered orders
    cy.contains("Order #2").should("be.visible");
    cy.contains("Order #3").should("be.visible");
  });

  it("advances an order through the fulfillment pipeline", () => {
    cy.visit("/restaurant/orders");

    // Order #2 is in Ordered status; click Accept Order
    cy.contains(".order-card", "Order #2").within(() => {
      cy.get("button.btn-accept").click();
    });

    // After reload, Order #2 should now be Accepted
    cy.contains("h2", "Accepted Orders").closest(".orders-section").within(() => {
      cy.contains(".order-card", "Order #2").within(() => {
        // Now start preparing
        cy.get("button.btn-preparing").click();
      });
    });

    // Now Order #2 should be in Preparing section
    cy.contains("h2", "Preparing").closest(".orders-section").within(() => {
      cy.contains("Order #2").should("be.visible");
      // Mark Ready
      cy.get("button.btn-ready").click();
    });

    // Now Order #2 should be in Ready section
    cy.contains("h2", "Ready").closest(".orders-section").within(() => {
      cy.contains("Order #2").should("be.visible");
      // Mark Delivered
      cy.get("button.btn-deliver").click();
    });

    // Finally Order #2 is Delivered
    cy.contains("h2", /Delivered/i).closest(".orders-section").within(() => {
      cy.contains("Order #2").should("be.visible");
    });
  });

  it("cancels an order when rejected", () => {
    cy.visit("/restaurant/orders");

    // Order #3 is in Accepted status; reject/cancel it
    cy.contains(".order-card", "Order #3").within(() => {
      cy.get("button.btn-reject").click();
    });

    // Verify it is removed from active orders
    cy.contains(".order-card", "Order #3").should("not.exist");
  });
});
