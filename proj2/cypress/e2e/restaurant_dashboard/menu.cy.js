/**
 * Managing a restaurant's own menu, in a real browser.
 *
 * The Python route tests cover the rules; this covers the parts only a browser
 * exercises: that a checkbox group really posts one value per ticked box, that
 * unticking every box clears a tag rather than silently leaving it, and that a
 * rejected form comes back with what was typed still in it.
 *
 * Two things shape how this is written.
 *
 * The add form stays in the page, collapsed, while an edit form is open, so a bare
 * `input[name="protein"][value="tofu"]` matches twice and Cypress refuses .check() on
 * two elements. Every selector below is prefixed with #add-dish-form or #edit-dish-form.
 *
 * The prefix also has to be one selector rather than .within(), because a <form>
 * exposes its named controls as properties on itself and this form has a field called
 * `contains` -- the caffeine/alcohol tag column. That shadows Node.prototype.contains
 * with a RadioNodeList, and jQuery's #id lookup inside a scoped context calls
 * context.contains(el), which then throws "a.contains is not a function". Scoping with
 * a descendant selector goes through querySelectorAll on the document and never
 * touches it.
 */
describe("Restaurant Menu Management", () => {
  const ADD = "#add-dish-form";
  const EDIT = "#edit-dish-form";

  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsRestaurant("owner@tasteofitaly.com", "password123");
    cy.visit("/restaurant/menu");
  });

  const openAddForm = () => cy.contains("summary", "Add a dish").click();

  it("lists the restaurant's own dishes under a Menu tab", () => {
    cy.get(".owner-tabs .nav-btn.active").should("contain.text", "Menu");
    cy.get(".restaurant-info").should("contain.text", "Taste of Italy");

    cy.contains("table.menu", "Margherita Pizza").should("be.visible");
    cy.contains("table.menu tr", "Margherita Pizza").should("contain.text", "$14.99");

    // Another restaurant's dishes are not on this page.
    cy.contains("table.menu", "Jerk Chicken").should("not.exist");
  });

  it("adds a dish, ticking several boxes in one tag group", () => {
    openAddForm();
    cy.get(`${ADD} #new-name`).type("Farro Verde Bowl");
    cy.get(`${ADD} #new-price`).type("13.25");
    cy.get(`${ADD} #new-description`).type("Charred broccolini, farro, salsa verde");

    // One group, two values: the browser posts `protein` twice.
    cy.get(`${ADD} input[name="protein"][value="legumes"]`).check();
    cy.get(`${ADD} input[name="protein"][value="tofu"]`).check();
    cy.get(`${ADD} input[name="cuisine"][value="italian"]`).check();
    cy.get(`${ADD} input[name="carb_base"][value="grain"]`).check();
    cy.get(ADD).contains("button", "Add to menu").click();

    cy.location("search").should("contain", "added=");
    cy.contains(".alert.good", "Dish added").should("be.visible");
    cy.contains("table.menu tr", "Farro Verde Bowl")
      .should("contain.text", "$13.25")
      .and("contain.text", "legumes, tofu");
  });

  it("refuses a dish with no tags, and keeps what was typed", () => {
    openAddForm();
    cy.get(`${ADD} #new-name`).type("Mystery Plate");
    cy.get(`${ADD} #new-price`).type("9.00");
    cy.get(ADD).contains("button", "Add to menu").click();

    cy.get(".alert").should("contain.text", "could not be saved");
    cy.get(".alert a").first().should("have.attr", "href", "#new-protein");
    cy.get("#new-protein").should("have.attr", "aria-invalid", "true");

    // Nothing was stored, and the typing survived.
    cy.get(`${ADD} #new-name`).should("have.value", "Mystery Plate");
    cy.contains("table.menu", "Mystery Plate").should("not.exist");
  });

  it("refuses a dish that contradicts itself", () => {
    openAddForm();
    cy.get(`${ADD} #new-name`).type("Vegan Bolognese");
    cy.get(`${ADD} #new-price`).type("12.00");
    cy.get(`${ADD} input[name="protein"][value="beef"]`).check();
    cy.get(`${ADD} input[name="cuisine"][value="italian"]`).check();
    cy.get(`${ADD} input[name="carb_base"][value="pasta"]`).check();
    cy.get(`${ADD} input[name="diet_tags"][value="vegan"]`).check();
    cy.get(ADD).contains("button", "Add to menu").click();

    cy.get(".alert").should("contain.text", "contradicts itself");
    cy.contains("table.menu", "Vegan Bolognese").should("not.exist");
  });

  it("edits one dish at a time, and unticking every box clears that tag", () => {
    cy.contains("table.menu tr", "Caprese Salad").contains("a", "Edit").click();

    cy.contains("h3", "Editing Caprese Salad").should("be.visible");
    cy.get(EDIT).should("have.length", 1);

    // Stored values arrive ticked, and a stored NULL is an empty field.
    cy.get(`${EDIT} input[name="cuisine"][value="italian"]`).should("be.checked");
    cy.get(`${EDIT} input[value="None"]`).should("not.exist");

    cy.get(`${EDIT} input[name="protein"]:checked`).uncheck({ multiple: true });
    cy.get(`${EDIT} input[name="flavor"]:checked`).uncheck({ multiple: true });
    cy.get(`${EDIT} input[name="protein"][value="legumes"]`).check();
    cy.get(EDIT).contains("button", "Save changes").click();

    cy.contains(".alert.good", "Changes saved").should("be.visible");
    cy.contains("table.menu tr", "Caprese Salad").should("contain.text", "legumes");
  });

  it("takes a dish off the menu and puts it back", () => {
    cy.contains("table.menu tr", "Classic Tiramisu").contains("button", "Take off").click();
    cy.contains("table.menu tr", "Classic Tiramisu").should("contain.text", "Off the menu");

    cy.contains("table.menu tr", "Classic Tiramisu").contains("button", "Put back").click();
    cy.contains("table.menu tr", "Classic Tiramisu").should("contain.text", "On the menu");
  });

  it("searches the menu, and keeps the search when a filter is clicked", () => {
    cy.get('input[name="q"]').type("penne{enter}");
    cy.contains("table.menu", "Penne Arrabbiata").should("be.visible");
    cy.contains("table.menu", "Margherita Pizza").should("not.exist");

    // A filter narrows what the search already found, rather than replacing it.
    cy.contains(".filters a", "Off the menu").click();
    cy.location("search").should("contain", "q=penne");
    cy.contains("Nothing here matches").should("be.visible");

    cy.contains("a", "Show the whole menu").click();
    cy.contains("table.menu", "Margherita Pizza").should("be.visible");
  });

  it("filters the list by whether a dish is being served", () => {
    cy.contains("table.menu tr", "Margherita Pizza").contains("button", "Take off").click();

    cy.contains(".filters a", "Off the menu").click();
    cy.contains("table.menu", "Margherita Pizza").should("be.visible");
    cy.contains("table.menu", "Penne Arrabbiata").should("not.exist");

    cy.contains(".filters a", "On the menu").click();
    cy.contains("table.menu", "Penne Arrabbiata").should("be.visible");
    cy.contains("table.menu", "Margherita Pizza").should("not.exist");
  });

  it("will not delete a dish that a diner has already planned", () => {
    // testuser@example.com's seeded plan names the first menu item.
    cy.on("window:confirm", () => true);
    cy.contains("table.menu tr", "Margherita Pizza").contains("button", "Delete").click();

    cy.get(".alert").should("contain.text", "out of stock instead");
    cy.contains("table.menu", "Margherita Pizza").should("be.visible");
  });

  it("serves a contract that matches the form", () => {
    cy.request("/api/restaurant/menu/schema").then((response) => {
      expect(response.status).to.eq(200);
      expect(response.body.required).to.include.members(["name", "price", "protein"]);

      // Every value the contract advertises is a box the form actually offers.
      response.body.fields.protein.values.forEach((value) => {
        cy.get(`${ADD} input[name="protein"][value="${value}"]`).should("exist");
      });
    });
  });
});
