import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

const SAMPLE_STL = resolve(process.cwd(), "../../samples/generated/l-bracket-with-holes/source-random.stl");

/**
 * Guards the cost of ArtifactLayer's scene build — the clone, creased normals,
 * display materials, and edge overlays it produces for each display state.
 *
 * Deliberately not a long-task assertion: long tasks during a viewer reveal are
 * dominated by WebGL shader compilation, which is SwiftShader-bound in headless
 * CI and effectively absent on a real GPU, so they measure the driver rather
 * than this codebase. The scene build is pure CPU work and is the part a code
 * change can actually regress. See docs/viewer-performance.md.
 */
const BUILD_BUDGET_MS = 100;

async function sceneBuilds(page: Page) {
  return page.evaluate(() =>
    performance.getEntriesByName("mesh2param:artifact-build", "measure").map((entry) => entry.duration));
}

async function assertBuildsWithinBudget(page: Page, context: string) {
  const builds = await sceneBuilds(page);
  expect(builds.length, `${context} should have built at least one display scene`).toBeGreaterThan(0);
  const slowest = Math.max(...builds);
  expect(slowest, `${context}: slowest scene build was ${slowest.toFixed(1)} ms across ${builds.length} builds`)
    .toBeLessThan(BUILD_BUDGET_MS);
}

test("building a display scene stays cheap for the sample", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });

  await assertBuildsWithinBudget(page, "sample reveal");

  // Every display state rebuilds the scene; the creased-normal and edge-overlay
  // paths differ between them, so exercise more than the default.
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Source", exact: true }).click();
  await expect(page.getByRole("button", { name: "Source", exact: true })).toHaveAttribute("aria-pressed", "true");

  await assertBuildsWithinBudget(page, "after switching display modes");
});

test("building a display scene stays cheap for an uploaded source mesh", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByLabel("Choose source mesh").setInputFiles(SAMPLE_STL);
  await expect(page.locator(".canvas-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Analyze mesh", { timeout: 240_000 });
  await page.locator(".dock-primary").click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 240_000 });

  await assertBuildsWithinBudget(page, "analyzed source mesh");
});
