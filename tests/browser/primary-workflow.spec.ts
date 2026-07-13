import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

// `pnpm test:e2e` runs from apps/web; the sample meshes live at the repo root.
const SAMPLE_STL = resolve(process.cwd(), "../../samples/generated/l-bracket-with-holes/source-random.stl");

async function openCleanStart(page: Page) {
  await page.addInitScript(() => {
    Reflect.deleteProperty(globalThis, "showSaveFilePicker");
  });
  const devtools = await page.context().newCDPSession(page);
  await devtools.send("Storage.clearDataForOrigin", {
    origin: "http://127.0.0.1:5173",
    storageTypes: "all",
  });
  await devtools.detach();
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
}

const primaryAction = (page: Page) => page.locator(".dock-primary");

test("L-bracket sample opens validated and exports a STEP", async ({ page }) => {
  await openCleanStart(page);
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });

  // The supported sample arrives fully validated, so the guided action is a download.
  await expect(page.getByText("Validated")).toBeVisible({ timeout: 60_000 });
  await expect(primaryAction(page)).toContainText("Download STEP", { timeout: 60_000 });

  // Display modes: the reconstructed result is revealed; comparing overlays the source.
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Result", exact: true }).click();
  await expect(page.getByRole("button", { name: "Result", exact: true })).toHaveAttribute("aria-pressed", "true");

  const download = page.waitForEvent("download", { timeout: 30_000 });
  await primaryAction(page).click();
  expect((await download).suggestedFilename()).toMatch(/\.step$/i);

  await page.getByRole("button", { name: "Back to start screen" }).click();
  await expect(page.getByTestId("start-screen")).toBeVisible();
});

test("display preferences survive a page reload", async ({ page }) => {
  await openCleanStart(page);
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(primaryAction(page)).toContainText("Download STEP", { timeout: 60_000 });

  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByLabel("View settings")).toBeVisible();
  await page.getByRole("radio", { name: /X-Ray/i }).click();
  await page.getByRole("switch", { name: "Show edges" }).click();
  await page.getByRole("button", { name: "Toggle light or dark theme" }).click();

  await page.reload();

  await expect(page.getByTestId("cad-viewport")).toHaveAttribute("data-display-mode", "xray");
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".canvas-shell")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("switch", { name: "Show edges" })).toHaveAttribute("aria-checked", "false");
});

test("uploaded mesh advances through analyze, reconstruct, and download", async ({ page }) => {
  await openCleanStart(page);
  await page.getByLabel("Choose source mesh").setInputFiles(SAMPLE_STL);

  // Ingest yields diagnostics only; analysis is the next guided step.
  await expect(primaryAction(page)).toContainText("Analyze mesh", { timeout: 60_000 });
  await primaryAction(page).click();

  // Analysis produces the renderable source mesh and unlocks reconstruction.
  await expect(page.getByText("Analyzed")).toBeVisible({ timeout: 240_000 });
  await expect(page.getByTestId("cad-viewport")).toBeVisible();
  await expect(primaryAction(page)).toContainText("Reconstruct", { timeout: 240_000 });
  await primaryAction(page).click();

  await expect(primaryAction(page)).toContainText("Download STEP", { timeout: 240_000 });
  const download = page.waitForEvent("download", { timeout: 30_000 });
  await primaryAction(page).click();
  expect((await download).suggestedFilename()).toMatch(/\.step$/i);
});

test("start and canvas stay usable at required responsive sizes", async ({ page }) => {
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 820, height: 900 },
    { width: 390, height: 844 },
  ];
  const hasHOverflow = () => page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth);

  await openCleanStart(page);
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByTestId("start-screen")).toBeVisible();
    expect(await hasHOverflow(), `landing ${viewport.width}x${viewport.height} overflows horizontally`).toBe(false);
  }

  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(primaryAction(page)).toContainText("Download STEP", { timeout: 60_000 });
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    expect(await hasHOverflow(), `canvas ${viewport.width}x${viewport.height} overflows horizontally`).toBe(false);
  }
});
