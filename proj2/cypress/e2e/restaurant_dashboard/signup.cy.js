// Restaurant sign-up: the parts only a browser exercises -- the per-day hours controls,
// the checkbox that decides whether a day is open at all, and the hand-off from the
// finished form into the new restaurant's empty menu page.
//
// The spec scopes with descendant selectors rather than cy.get(form).within(...). A
// <form> exposes its named controls as properties on itself, so a field named `contains`
// shadows Node.prototype.contains with a RadioNodeList, and jQuery's #id lookup inside a
// scoped context calls context.contains(el) and throws. This form has no such field
// today, but the menu spec next door does, and the two are read together -- keeping the
// same style here stops the pattern being reintroduced by copying.

const FORM = "#signup-form";

// A fresh address per run: Restaurant.email is UNIQUE and the e2e database persists
// across specs within a run.
const email = () => `cypress-${Date.now()}-${Cypress._.random(1e6)}@signup.test`;

function fillAccount(address) {
  cy.get(`${FORM} #name`).clear().type("Cypress Wings");
  cy.get(`${FORM} #phone`).clear().type("9195550199");
  cy.get(`${FORM} #address`).clear().type("12 Hillsborough St");
  cy.get(`${FORM} #city`).clear().type("Raleigh");
  cy.get(`${FORM} #state`).clear().type("NC");
  cy.get(`${FORM} #zip`).clear().type("27601");
  cy.get(`${FORM} #email`).clear().type(address);
  cy.get(`${FORM} #password`).clear().type("hunter2hunter");
  cy.get(`${FORM} #confirm_password`).clear().type("hunter2hunter");
}

describe("Restaurant sign-up", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.visit("/restaurant/register");
  });

  it("is reachable from the restaurant login page", () => {
    cy.visit("/restaurant/login");
    cy.contains("a", "List your restaurant").click();
    cy.location("pathname").should("eq", "/restaurant/register");
  });

  it("offers a time pair for every day of the week", () => {
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].forEach((day) => {
      cy.get(`${FORM} #${day}_open`).should("have.attr", "type", "time");
      cy.get(`${FORM} #${day}_close`).should("have.attr", "type", "time");
    });
  });

  it("starts open on weekdays and closed at the weekend", () => {
    cy.get(`${FORM} #open_Mon`).should("be.checked");
    cy.get(`${FORM} #open_Sat`).should("not.be.checked");
    cy.get(`${FORM} #open_Sun`).should("not.be.checked");
  });

  it("greys a day out when it is unticked, and back when it is ticked", () => {
    cy.get(`${FORM} #open_Mon`).uncheck();
    cy.get(`${FORM} #open_Mon`).closest(".day").should("have.attr", "data-open", "no");
    cy.get(`${FORM} #open_Sat`).check();
    cy.get(`${FORM} #open_Sat`).closest(".day").should("have.attr", "data-open", "yes");
  });

  it("signs a restaurant up and lands it on its own empty menu", () => {
    fillAccount(email());
    cy.get(`${FORM} #open_Sat`).check();
    cy.get(`${FORM}`).submit();

    cy.location("pathname").should("eq", "/restaurant/menu");
    cy.contains("You are listed").should("be.visible");
    cy.contains("Cypress Wings").should("be.visible");
    cy.contains("Nothing on the menu yet").should("be.visible");
  });

  it("lets the new restaurant add its first dish straight away", () => {
    fillAccount(email());
    cy.get(`${FORM}`).submit();
    cy.location("pathname").should("eq", "/restaurant/menu");

    cy.contains("Add a dish").click();
    cy.get("#add-dish-form #new-name").type("Lemon Pepper Wings");
    cy.get("#add-dish-form #new-price").type("11.50");
    cy.get("#add-dish-form #new-protein input[value='chicken']").check();
    cy.get("#add-dish-form #new-cuisine input[value='american']").check();
    cy.get("#add-dish-form #new-carb_base input[value='none']").check();
    cy.get("#add-dish-form").submit();

    cy.contains("Lemon Pepper Wings").should("be.visible");
  });

  it("refuses a closing time that is not after the opening time, and says why", () => {
    fillAccount(email());
    cy.get(`${FORM} #Mon_close`).clear().type("02:00");
    cy.get(`${FORM}`).submit();

    cy.location("pathname").should("eq", "/restaurant/register");
    cy.contains("later than the opening time").should("be.visible");
    // and nothing had to be retyped
    cy.get(`${FORM} #name`).should("have.value", "Cypress Wings");
  });

  it("refuses a restaurant that is never open", () => {
    fillAccount(email());
    ["Mon", "Tue", "Wed", "Thu", "Fri"].forEach((day) => {
      cy.get(`${FORM} #open_${day}`).uncheck();
    });
    cy.get(`${FORM}`).submit();

    cy.location("pathname").should("eq", "/restaurant/register");
    cy.contains("at least one day").should("be.visible");
  });

  it("refuses an email that already has a restaurant account", () => {
    const taken = email();
    fillAccount(taken);
    cy.get(`${FORM}`).submit();
    cy.location("pathname").should("eq", "/restaurant/menu");

    cy.visit("/restaurant/logout");
    cy.visit("/restaurant/register");
    fillAccount(taken);
    cy.get(`${FORM}`).submit();
    cy.contains("already has a restaurant account").should("be.visible");
  });

  it("lets the new restaurant sign in again with what it signed up with", () => {
    const address = email();
    fillAccount(address);
    cy.get(`${FORM}`).submit();
    cy.location("pathname").should("eq", "/restaurant/menu");

    cy.visit("/restaurant/logout");
    cy.visit("/restaurant/login");
    cy.get('input[name="email"]').type(address);
    cy.get('input[name="password"]').type("hunter2hunter");
    cy.get('input[type="submit"], button[type="submit"]').click();

    cy.location("pathname").should("eq", "/restaurant/orders");
  });

  it("never puts the password back in the page when the form is rejected", () => {
    fillAccount(email());
    cy.get(`${FORM} #zip`).clear().type("nope");
    cy.get(`${FORM}`).submit();

    cy.contains("ZIP code must be five digits").should("be.visible");
    cy.get(`${FORM} #password`).should("have.value", "");
    cy.document().its("documentElement.innerHTML").should("not.contain", "hunter2hunter");
  });
});
