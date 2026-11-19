describe("Order Workflow", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("adds a menu item with a note to the cart on the Restaurants page", () => {
    cy.visit("/restaurants");

    // Open the restaurant's catalog page
    cy.contains(".rest-entry", "Taste of Italy").click();

    cy.contains(".menu-item", "Margherita Pizza").within(() => {
      cy.get(".note-input").type("Please deliver with extra crushed red pepper");
      cy.get('input[type="number"]').clear().type("2");
      cy.contains("button", "Add").click();
    });

    // The cart shows the item and its note
    cy.get("#cartSection").should("contain.text", "Margherita Pizza");
    cy.get("#cartSection").should("contain.text", "Note: Please deliver with extra crushed red pepper");
  });

  it("successfully places an order via POST /order API and verifies it in My Orders", () => {
    const today = new Date().toISOString().split("T")[0];

    cy.request({
      method: "POST",
      url: "/order",
      body: {
        restaurant_id: 1,
        delivery_type: "delivery",
        date: today,
        meal: 3,
        tip: 4.5,
        eta_minutes: 30,
        items: [
          { itm_id: 1, qty: 1, notes: "Well done" },
          { itm_id: 2, qty: 2, notes: "Extra spicy" }
        ]
      }
    }).then((response) => {
      expect(response.status).to.eq(200);
      expect(response.body).to.have.property("ok", true);
      expect(response.body).to.have.property("ord_id");

      const newOrderId = response.body.ord_id;

      // My Orders lists the newly placed order
      cy.visit(`/orders?ordered=${newOrderId}`);
      cy.contains(`Order #${newOrderId} placed.`).should("be.visible");
      cy.contains("Taste of Italy").should("be.visible");
      cy.contains("Ordered").should("be.visible");
    });
  });

  it("rejects order placement with invalid restaurant or items", () => {
    cy.request({
      method: "POST",
      url: "/order",
      failOnStatusCode: false,
      body: {
        restaurant_id: 9999, // nonexistent
        items: [{ itm_id: 1, qty: 1 }]
      }
    }).then((response) => {
      expect(response.status).to.be.oneOf([400, 404]);
      expect(response.body.ok).to.be.false;
    });
  });
});
