describe("Profile Editing & Password Change", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("updates the phone in its pop-up and allergies in the Diet section", () => {
    cy.visit("/profile");
    cy.get("#particulars .js-open-edit").click();
    cy.get("#editModal").should("be.visible");

    // Change phone number
    cy.get('input[name="phone"]').clear().type("9195557788");

    cy.get("#editProfileForm").submit();

    // Redirects back to profile
    cy.location("pathname").should("eq", "/profile");
    cy.contains("9195557788").should("be.visible");
    cy.get('#diet input[value="Soy"]').check();
    cy.get("#dietProfileForm").submit();
    cy.location("hash").should("eq", "#diet");
    cy.get("#dietSummary").should("contain.text", "Soy");
  });

  it("saves a spending cap, a required diet, and a slider together", () => {
    cy.visit("/profile#diet");
    cy.get('#diet input[value="vegan"]').check();
    cy.get("#profile-weekly-cap").clear().type("50.25");
    cy.get("#cost-priority").invoke("val", "75").trigger("input");
    cy.get('output[for="cost-priority"]').should("have.text", "75");
    cy.get("#dietProfileForm").submit();
    cy.get('#diet input[value="vegan"]').should("be.checked");
    cy.get("#profile-weekly-cap").should("have.value", "50.25");
    cy.get("#cost-priority").should("have.value", "75");
    cy.get("#cost-priority").invoke("val", "0").trigger("input");
    cy.get("#dietProfileForm").submit();
    cy.get("#cost-priority").should("have.value", "0");
  });

  it("successfully changes user password from the Password chapter", () => {
    cy.visit("/profile");
    cy.get('a[href="#password"]').click();

    // Enter passwords
    cy.get("#pwCurrent").type("password123");
    cy.get("#pwNew").type("newSecret456");
    cy.get("#pwConfirm").type("newSecret456");

    // Submit password form
    cy.get("#submitPwBtn").should("not.be.disabled").click();

    // Verify redirected with success parameter
    cy.location("search").should("include", "pw_updated=1");
    cy.get(".flash.success, .toast-success, .success").should("exist");

    // Verify we can log in with new password
    cy.logoutUser();
    cy.visit("/login");
    cy.get('input[name="email"]').type("testuser@example.com");
    cy.get('input[name="password"]').type("newSecret456");
    cy.get('input[type="submit"]').click();
    cy.location("pathname").should("eq", "/");
  });

  it("shows an error when current password is wrong during password change", () => {
    cy.visit("/profile");

    cy.get("#pwCurrent").type("wrongpassword");
    cy.get("#pwNew").type("newSecret456");
    cy.get("#pwConfirm").type("newSecret456");

    cy.get("#submitPwBtn").should("not.be.disabled").click();

    cy.location("search").should("include", "pw_error=incorrect_current");
    cy.get(".flash.danger, .error").should("exist");
  });
});
