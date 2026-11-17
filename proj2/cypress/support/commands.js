// Custom reusable Cypress commands

/**
 * Seed the test database using the backend seeding script
 */
Cypress.Commands.add("seedDatabase", () => {
  cy.task("seedDatabase");
});

/**
 * Log in as a customer user via the web interface
 */
Cypress.Commands.add("loginAsUser", (email = "testuser@example.com", password = "password123") => {
  cy.visit("/login");
  cy.get('input[name="email"]').clear().type(email);
  cy.get('input[name="password"]').clear().type(password);
  cy.get('input[type="submit"]').click();
  // Ensure we are redirected away from login
  cy.location("pathname").should("not.eq", "/login");
});

/**
 * Log in as a restaurant owner via the restaurant login page
 */
Cypress.Commands.add("loginAsRestaurant", (email = "owner@tasteofitaly.com", password = "password123") => {
  cy.visit("/restaurant/login");
  cy.get('input[name="email"]').clear().type(email);
  cy.get('input[name="password"]').clear().type(password);
  cy.get('input[type="submit"], button[type="submit"]').click();
  // Owners land on the Orders page
  cy.location("pathname").should("eq", "/restaurant/orders");
});

/**
 * Log out from customer account
 */
Cypress.Commands.add("logoutUser", () => {
  cy.visit("/logout");
});

/**
 * Log out from restaurant account
 */
Cypress.Commands.add("logoutRestaurant", () => {
  cy.visit("/restaurant/logout");
});
