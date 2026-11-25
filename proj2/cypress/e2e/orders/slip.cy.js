// The order slip on the Restaurants page: kept in the browser, for each customer

const lines = () => cy.get("#cartGroups .slip-lines tbody tr");
const addDishes = (from, count) => {
  for (let i = from; i < from + count; i++) {
    cy.get(".menu-item").first().within(() => {
      cy.get(".note-input").type(`note ${i}`, { delay: 0 });
      cy.get(".add-btn").click();
    });
  }
};

describe("The order slip", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/restaurants");
    cy.contains(".rest-entry", "Saffron Tandoor").click();
    cy.get("#fSafe").uncheck({ force: true });
  });

  it("keeps 25 lines, also after a reload", () => {
    addDishes(0, 25); // a line per note; the cookie it used to be held about 17
    lines().should("have.length", 25);
    cy.reload();
    lines().should("have.length", 25);
    cy.get("#cartGroups").should("contain.text", "Note: note 24");
  });

  it("says so when the browser cannot keep a dish, and leaves the slip alone", () => {
    addDishes(0, 1);
    cy.window().then((w) => {
      cy.stub(w.Storage.prototype, "setItem").throws(new w.DOMException("full", "QuotaExceededError"));
    });
    addDishes(1, 1);
    cy.get("#toast").should("contain.text", "could not save the slip");
    lines().should("have.length", 1);
  });

  it("carries over a slip kept in the old cookie", () => {
    const old = [{ restaurant_id: 1, restaurant_name: "Taste of Italy",
      item: { itm_id: 1, name: "Margherita Pizza", unit_price: "14.99" }, qty: 2, notes: "half; half" }];
    cy.setCookie("cart", encodeURIComponent(JSON.stringify(old)));
    cy.reload();
    lines().should("have.length", 1).and("contain.text", "Margherita Pizza").and("contain.text", "half; half");
    cy.getCookie("cart").should("be.null");
  });

  it("forgets a slip that has not changed for a week", () => {
    addDishes(0, 1);
    cy.window().then((w) => {
      const key = Object.keys(w.localStorage).find((k) => k.startsWith("weeklies-cart-"));
      const kept = JSON.parse(w.localStorage.getItem(key));
      kept.saved -= 8 * 24 * 60 * 60 * 1000;
      w.localStorage.setItem(key, JSON.stringify(kept));
    });
    cy.reload();
    cy.get("#cartEmptyMsg").should("be.visible");
  });

  it("is not shown to another customer in the same browser", () => {
    addDishes(0, 1);
    cy.logoutUser();
    cy.visit("/register");
    cy.get('input[name="fname"]').type("Other");
    cy.get('input[name="lname"]').type("Person");
    cy.get('input[name="email"]').type("other@example.com");
    cy.get('input[name="phone"]').type("5551234567");
    cy.get('input[name="password"]').type("password123");
    cy.get('input[name="confirm_password"]').type("password123");
    cy.get('form input[type="submit"], form button[type="submit"]').first().click();
    cy.loginAsUser("other@example.com", "password123");
    cy.visit("/restaurants");
    cy.get("#cartEmptyMsg").should("be.visible");
    cy.logoutUser();
    cy.loginAsUser("testuser@example.com", "password123");
    cy.visit("/restaurants");
    lines().should("have.length", 1);
  });
});
