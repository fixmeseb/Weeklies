describe("Calendar & Meal Plan View", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("renders the interactive meal calendar for the current month", () => {
    cy.visit("/");
    cy.get("h1").should("contain.text", "Menu Calendar");
    cy.get(".greet, main").should("contain.text", "John Doe");
    cy.get(".cal-grid, .calendar-wrap, .day-cell").should("exist");
  });

  it("navigates between months using calendar controls", () => {
    cy.visit("/");

    // Click previous month or next month link
    cy.get("a").filter('[href*="/20"]').first().then(($link) => {
      const targetUrl = $link.attr("href");
      cy.wrap($link).click();
      cy.location("pathname").should("eq", targetUrl);
      cy.get("h1").should("contain.text", "Menu Calendar");
    });
  });

  it("allows navigating to explicit year and month via route params", () => {
    cy.visit("/2026/11");
    cy.get("h1").should("contain.text", "Menu Calendar");
    cy.contains("November").should("be.visible");
  });

  it("moves by week in the Almanac style, and by month in the others", () => {
    const almanac = { onBeforeLoad: (w) => w.localStorage.setItem("weeklies-style", "almanac") };
    cy.visit("/?week=2026-11-25", almanac);
    cy.get("#weekNav").should("be.visible").and("contain.text", "Week of the 23rd to the 29th of November, 2026");
    cy.get('.calendar-toolbar a[href="/2026/12"]').should("not.be.visible");
    cy.get("#weekNav").contains("Next").click();
    cy.location("search").should("eq", "?week=2026-11-30");
    cy.get("#weekNav").should("contain.text", "the 30th of November to the 6th of December, 2026");
    cy.get("#weekNav").contains("Next").click();
    cy.get("#weekNav").should("contain.text", "the 7th to the 13th of December, 2026");
    cy.get("#weekNav").contains("Prev").click();
    cy.location("search").should("eq", "?week=2026-11-30");

    cy.visit("/?week=2026-11-25", { onBeforeLoad: (w) => w.localStorage.removeItem("weeklies-style") });
    cy.get("#weekNav").should("not.be.visible");
    cy.get('.calendar-toolbar a[href="/2026/12"]').should("be.visible").click();
    cy.location("pathname").should("eq", "/2026/12");
  });
});
