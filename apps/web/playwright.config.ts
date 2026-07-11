import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const apiDataDir = mkdtempSync(join(tmpdir(), "mesh2param-playwright-"));

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
  webServer: [
    {
      command: "pnpm dev:api",
      cwd: "../..",
      url: "http://127.0.0.1:8000/ready",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        MESH2PARAM_ENVIRONMENT: "test",
        MESH2PARAM_DATA_DIR: apiDataDir,
        MESH2PARAM_DATABASE_URL: `sqlite:///${join(apiDataDir, "api.sqlite3")}`,
        MESH2PARAM_STORAGE_PATH: join(apiDataDir, "storage"),
        MESH2PARAM_CORS_ORIGINS:
          "http://localhost:5173,http://127.0.0.1:5173",
        MESH2PARAM_WORKER_COUNT: "1",
        MESH2PARAM_JOB_RUNNER_MODE: "embedded",
        MESH2PARAM_DEBUG: "false",
      },
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "pnpm dev:web",
      cwd: "../..",
      url: "http://127.0.0.1:5173",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
