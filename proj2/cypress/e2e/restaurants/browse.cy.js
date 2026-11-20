describe("Restaurant & Menu Browsing", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/restaurants");
  });

  it("renders the restaurant directory with seeded restaurants", () => {
    cy.get("h1").should("contain.text", "Restaurants");
    cy.get("#restList").should("be.visible");
    cy.contains("Taste of Italy").should("be.visible");
    cy.contains("Green Garden Bistro").should("be.visible");
  });

  it("opens a restaurant's menu as a catalog page from the index", () => {
    cy.contains(".rest-entry", "Taste of Italy").click();
    cy.contains(".rest-entry", "Taste of Italy").should("have.attr", "aria-pressed", "true");
    cy.get("#catalogPage").should("contain.text", "Margherita Pizza");
    cy.get("#catalogPage").should("contain.text", "Penne Arrabbiata");
    cy.get("#catalogPage").should("contain.text", "$14.99");
  });

  it("filters restaurants and menu items using the search input", () => {
    cy.get("#searchInput").type("Avocado");
    // Green Garden Bistro should match
    cy.get("#restList").should("contain.text", "Green Garden Bistro");
    cy.get("#restList").should("not.contain.text", "Taste of Italy");
  });

  it("adds a menu item to the cart and displays it in the cart panel", () => {
    cy.contains(".rest-entry", "Taste of Italy").click();
    // Add Margherita Pizza to the order slip
    cy.contains(".menu-item", "Margherita Pizza").find("button, .btn").contains(/Add/i).click();

    // Verify cart section updates
    cy.get("#cartSection").should("be.visible");
    cy.get("#cartGroups").should("contain.text", "Margherita Pizza");

    // Clear cart button resets the cart
    cy.get("#clearCartBtn").click();
    cy.get("#cartEmptyMsg").should("be.visible");
  });
});
