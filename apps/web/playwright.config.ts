import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function portFromEnvironment(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined) return fallback;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return port;
}

const apiDataDir = mkdtempSync(join(tmpdir(), "mesh2param-playwright-"));
const apiPort = portFromEnvironment("MESH2PARAM_E2E_API_PORT", 8000);
const webPort = portFromEnvironment("MESH2PARAM_E2E_WEB_PORT", 5173);
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const webOrigin = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "../../tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 8 * 60 * 1_000,
  expect: { timeout: 30_000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: "../../output/playwright/report", open: "never" }],
  ],
  outputDir: "../../output/playwright/test-results",
  use: {
    baseURL: webOrigin,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    acceptDownloads: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run --frozen mesh2param serve",
      cwd: "../..",
      url: `${apiOrigin}/ready`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        MESH2PARAM_ENVIRONMENT: "test",
        MESH2PARAM_DATA_DIR: apiDataDir,
        MESH2PARAM_DATABASE_URL: `sqlite:///${join(apiDataDir, "api.sqlite3")}`,
        MESH2PARAM_STORAGE_PATH: join(apiDataDir, "storage"),
        MESH2PARAM_CORS_ORIGINS: `http://localhost:${webPort},${webOrigin}`,
        MESH2PARAM_WORKER_COUNT: "1",
        MESH2PARAM_JOB_RUNNER_MODE: "embedded",
        MESH2PARAM_PORT: String(apiPort),
        MESH2PARAM_DEBUG: "false",
      },
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: [
        "pnpm --filter @mesh2param/contracts build",
        "pnpm --filter @mesh2param/ui build",
        "pnpm --filter @mesh2param/web build",
        `pnpm --filter @mesh2param/web exec vite preview --host 127.0.0.1 --port ${webPort}`,
      ].join(" && "),
      cwd: "../..",
      url: webOrigin,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        MESH2PARAM_API_PROXY: apiOrigin,
      },
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
