import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "../../tests/browser-cloudflare",
  fullyParallel: false,
  workers: 1,
  timeout: 3 * 60 * 1_000,
  expect: { timeout: 90_000 },
  reporter: "list",
  outputDir: "test-results-cloudflare",
  use: {
    baseURL: "http://127.0.0.1:8787",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
