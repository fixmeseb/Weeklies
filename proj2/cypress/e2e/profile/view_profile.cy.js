describe("User Profile View", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/profile");
  });

  it("displays user information correctly", () => {
    cy.get("#particulars").within(() => {
      cy.contains("John Doe").should("be.visible");
      cy.contains("testuser@example.com").should("be.visible");
      cy.contains("9195550101").should("be.visible");
    });
  });

  it("displays user allergies and preferences", () => {
    cy.get("#dietSummary").should("contain.text", "Peanuts");
    cy.get("#dietSummary").should("contain.text", "Vegetarian");
  });

  it("names the last order in the Wallet chapter and links to My Orders", () => {
    cy.get("#wallet").should("contain.text", "Taste of Italy");
    cy.get('#wallet a[href="/orders"]').should("exist");
  });

  it("redirects unauthenticated users to login", () => {
    cy.logoutUser();
    cy.visit("/profile");
    cy.location("pathname").should("eq", "/login");
  });
});
