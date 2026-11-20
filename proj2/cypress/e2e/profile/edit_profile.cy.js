describe("Profile Editing & Password Change", () => {
  beforeEach(() => {
    cy.seedDatabase();
    cy.loginAsUser("testuser@example.com", "password123");
  });

  it("updates user phone number and allergies from the edit pop-up", () => {
    cy.visit("/profile");
    cy.get("#openEditBtn").click();
    cy.get("#editModal").should("be.visible");

    // Change phone number
    cy.get('input[name="phone"]').clear().type("9195557788");

    // Select additional allergy (e.g. Soy)
    cy.get('input[type="checkbox"][value="Soy"]').check();

    cy.get('#editProfileForm').submit();

    // Redirects back to profile
    cy.location("pathname").should("eq", "/profile");
    cy.contains("9195557788").should("be.visible");
    cy.get('[aria-label="Allergies"]').should("contain.text", "Soy");
  });

  it("successfully changes user password via modal", () => {
    cy.visit("/profile");

    // Open change password modal
    cy.get("#openChangePwBtn").click();
    cy.get("#pwModal").should("be.visible");

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

    cy.get("#openChangePwBtn").click();
    cy.get("#pwCurrent").type("wrongpassword");
    cy.get("#pwNew").type("newSecret456");
    cy.get("#pwConfirm").type("newSecret456");

    cy.get("#submitPwBtn").should("not.be.disabled").click();

    cy.location("search").should("include", "pw_error=incorrect_current");
    cy.get(".flash.danger, .error").should("exist");
  });
});
