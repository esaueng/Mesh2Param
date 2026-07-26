import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const SAMPLE_STL = resolve(process.cwd(), "../../samples/generated/l-bracket-with-holes/source-random.stl");

/**
 * The project-file codec carries the generated CADGraph schema validator, the
 * single largest piece of the app's JavaScript. It must stay off the path to
 * first paint and load only when a project file is actually saved or opened —
 * a static import anywhere upstream would silently put it back.
 */
test("the landing page does not load the project-file codec", async ({ page }) => {
  const scripts: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(new URL(request.url()).pathname);
  });

  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await expect(page.getByRole("button", { name: /Try the L-bracket sample/i })).toBeEnabled();

  expect(scripts.filter((path) => /projectFile/.test(path))).toEqual([]);
  expect(scripts.filter((path) => /WorkspaceController/.test(path))).toEqual([]);
});

test("saving a project loads the codec on demand and produces a readable file", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Reflect.deleteProperty(globalThis, "showSaveFilePicker");
  });
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  // Ingest only: this test is about when the codec loads, not about
  // reconstruction, and a second full CAD job here would queue behind the
  // single embedded worker and starve the specs that follow.
  await page.getByLabel("Choose source mesh").setInputFiles(SAMPLE_STL);
  await expect(page.locator(".canvas-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Analyze mesh", { timeout: 240_000 });

  const codecRequests: string[] = [];
  page.on("request", (request) => {
    if (/projectFile/.test(request.url())) codecRequests.push(request.url());
  });

  const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
  await page.getByRole("button", { name: "Save project", exact: true }).click();
  const saved = testInfo.outputPath("deferred-codec.mesh2param.json");
  await (await downloadPromise).saveAs(saved);

  // Fetched at save time, not at startup, and the deferred module still works.
  expect(codecRequests.length).toBeGreaterThan(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Back to start screen", exact: true }).click();
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByLabel("Open saved project file").setInputFiles(saved);
  await expect(page.locator(".canvas-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
});
