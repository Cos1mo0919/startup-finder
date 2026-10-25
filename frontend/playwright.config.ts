import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";
// A fresh admin key for every test run; the browser server and specs read it
// from the environment, so no fixed key lives in the repository.
process.env.TEST_ADMIN_KEY ||= randomBytes(18).toString("base64url");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  // On GitHub Actions failures also become check annotations.
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8011",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath:
        process.env.CHROMIUM_PATH ||
        (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
      args: ["--no-sandbox"],
    },
  },
  webServer: {
    command: ".venv/bin/python -m tests.browser_server",
    cwd: "..",
    url: "http://127.0.0.1:8011/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
});
