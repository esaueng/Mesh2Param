import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "../../tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 8 * 60 * 1_000,
  expect: { timeout: 30_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    acceptDownloads: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev",
    cwd: "../..",
    url: "http://127.0.0.1:5173",
    timeout: 120_000,
    reuseExistingServer: true,
    stdout: "pipe",
    stderr: "pipe",
  },
});
