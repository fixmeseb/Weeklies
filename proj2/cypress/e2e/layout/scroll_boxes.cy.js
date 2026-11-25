// Long lists scroll inside their own box on wide screens (.scroll-box in static/style.css)

const scrolls = ($el) => $el[0].scrollHeight > $el[0].clientHeight + 1;
const shouldScroll = (selector) =>
  cy.get(selector).should(($el) => expect(scrolls($el), `${selector} scrolls`).to.eq(true));

// For tomorrow's dinner: an order for now is refused when the restaurant is closed, so the
// tests would pass or fail with the time of day.
function placeOrders(count) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const pad = (n) => String(n).padStart(2, "0");
  const date = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}`;
  for (let i = 0; i < count; i++) {
    cy.request("POST", "/order", {
      restaurant_id: 1, delivery_type: "pickup", date, meal: 3, items: [{ itm_id: 1, qty: 1 }],
    });
  }
}

describe("Scroll boxes", () => {
  beforeEach(() => {
    cy.viewport(1280, 520);
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("scrolls My Orders under headings that stay in view", () => {
    placeOrders(4);
    cy.visit("/orders");
    shouldScroll(".scroll-box");
    cy.get(".scroll-box").should("have.attr", "tabindex", "0").and("have.attr", "aria-label", "Your orders");
    cy.get(".scroll-box").then(($box) => { $box[0].scrollTop = 200; });
    cy.get(".scroll-box thead th").first().should(($th) => {
      const box = $th.closest(".scroll-box")[0].getBoundingClientRect();
      expect($th[0].getBoundingClientRect().top).to.be.closeTo(box.top, 2);
    });
  });

  it("starts each restaurant's dishes at the top", () => {
    cy.visit("/restaurants");
    cy.contains(".rest-entry", "Sunrise Griddle").click();
    shouldScroll("#dishBox");
    cy.get("#dishBox").then(($box) => { $box[0].scrollTop = 200; });
    cy.contains(".rest-entry", "Tokyo Bento Bar").click();
    cy.get("#dishBox").should(($box) => expect($box[0].scrollTop).to.eq(0));
  });

  it("brings a restaurant opened by its link into view in the list", () => {
    cy.visit("/restaurants#r-11");
    shouldScroll("#restBox");
    cy.get('.rest-entry[aria-pressed="true"]').should(($entry) => {
      const box = $entry.closest("#restBox")[0].getBoundingClientRect();
      expect($entry[0].getBoundingClientRect().bottom).to.be.at.most(box.bottom + 1);
    });
  });

  it("scrolls the slip's lines, not its total, and shows the dish just added", () => {
    cy.visit("/restaurants");
    cy.contains(".rest-entry", "Saffron Tandoor").click();
    cy.get("#fSafe").uncheck({ force: true });
    for (let i = 0; i < 6; i++) cy.get(".add-btn").eq(i).click();
    shouldScroll(".slip-lines");
    cy.get(".slip-lines").should(($box) => {
      expect($box[0].scrollWidth, "no sideways scrolling").to.be.at.most($box[0].clientWidth);
      const last = $box.find("tbody tr").last()[0].getBoundingClientRect();
      expect(last.bottom).to.be.at.most($box[0].getBoundingClientRect().bottom + 1);
      expect($box.find(".slip-place, .slip-sums").length).to.eq(0);
    });
  });

  it("never scrolls the slip sideways, in any style, and prints whole lists", () => {
    ["standard", "almanac", "ticket", "primer", "menuboard"].forEach((style) => {
      cy.visit("/restaurants", {
        onBeforeLoad: (w) => {
          w.localStorage.clear(); // an empty slip for each style
          w.localStorage.setItem("weeklies-style", style);
        },
      });
      cy.contains(".rest-entry", "Saffron Tandoor").click();
      cy.get("#fSafe").uncheck({ force: true });
      for (let i = 0; i < 6; i++) cy.get(".add-btn").eq(i).click();
      shouldScroll(".slip-lines");
      cy.get(".slip-lines").should(($box) => {
        expect($box[0].scrollWidth, `${style} slip width`).to.be.at.most($box[0].clientWidth);
      });
    });
    const media = (value) => cy.then(() => Cypress.automation("remote:debugger:protocol", {
      command: "Emulation.setEmulatedMedia", params: { media: value },
    }));
    media("print");
    cy.get(".scroll-box").should(($boxes) => {
      $boxes.each((_, box) => expect(getComputedStyle(box).maxHeight).to.eq("none"));
    });
    media("");
  });

  it("shows whole lists on a phone", () => {
    placeOrders(4);
    cy.viewport(390, 800);
    cy.visit("/orders");
    cy.get(".scroll-box").should(($box) => {
      expect(scrolls($box)).to.eq(false);
      expect($box.css("max-height")).to.eq("none");
    });
  });

  it("boxes the owner's orders and menu, but not a dish being edited", () => {
    placeOrders(3);
    cy.loginAsRestaurant();
    shouldScroll('[aria-label="Pending orders"]');
    cy.visit("/restaurant/menu");
    cy.get('[aria-label="Your dishes"]').should("have.class", "scroll-box");
    cy.get("table.menu .action").first().click();
    cy.get("#edit-dish-form").should("be.visible");
    cy.get('[aria-label="Your dishes"]').should("not.exist");
  });
});
