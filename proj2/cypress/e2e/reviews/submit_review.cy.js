describe("Review Submission", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("submits a new review for a delivered order", () => {
    // Order 4 is delivered and unreviewed in the seeded database
    cy.visit("/order/4/review");

    cy.get("h1").should("contain.text", "Write a Review");
    cy.contains("Order #4").should("be.visible");

    // Click 5th star
    cy.get('.star[data-rating="5"]').click();
    cy.get("#ratingInput").should("have.value", "5");

    // Fill in title and description
    cy.get("#title").type("Absolutely phenomenal meal!");
    cy.get("#description").type("Everything was fresh, delicious, and arrived ahead of time!");

    // Submit
    cy.get('button[type="submit"]').click();

    // After submission, the same page shows the review
    cy.location("pathname").should("eq", "/order/4/review");
    cy.get("h1").should("contain.text", "Your Review");
    cy.contains("Absolutely phenomenal meal!").should("be.visible");
  });

  it("keeps submit button disabled until a rating is selected", () => {
    cy.visit("/order/4/review");

    cy.get("#title").type("Missing rating test");
    cy.get("#submitBtn").should("be.disabled");

    // Once a star is clicked, the button enables
    cy.get('.star[data-rating="4"]').click();
    cy.get("#submitBtn").should("not.be.disabled");
  });

  it("shows the written review if the order was already reviewed", () => {
    // Order 1 was already reviewed in seeded data
    cy.visit("/order/1/review");
    cy.get("h1").should("contain.text", "Your Review");
    cy.get("#reviewForm").should("not.exist");
  });
});
