const { defineConfig } = require("cypress");
const { execSync } = require("child_process");
const path = require("path");

module.exports = defineConfig({
  e2e: {
    baseUrl: "http://127.0.0.1:5000",
    supportFile: "cypress/support/e2e.js",
    fixturesFolder: "cypress/fixtures",
    specPattern: "cypress/e2e/**/*.cy.js",
    viewportWidth: 1280,
    viewportHeight: 720,
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    video: false,
    screenshotOnRunFailure: true,
    setupNodeEvents(on, config) {
      on("task", {
        // Recreates the E2E database: $WEEKLIES_DATABASE, or proj2/instance/cypress.db.
        // Start the Flask server with the same WEEKLIES_DATABASE (see INSTALL.md); the
        // seed script refuses to overwrite the development database.
        seedDatabase() {
          const scriptPath = path.resolve(__dirname, "scripts", "cypress_seed.py");
          try {
            const output = execSync(`python "${scriptPath}"`, {
              encoding: "utf-8",
              cwd: path.resolve(__dirname),
            });
            return output.trim();
          } catch (err) {
            console.error("Database seeding failed:", err);
            throw err;
          }
        },
      });
      return config;
    },
  },
});
