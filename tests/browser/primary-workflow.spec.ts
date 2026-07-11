import { expect, test, type Page } from "@playwright/test";

async function waitForJob(page: Page, kind: string, timeout = 180_000) {
  const progress = page.locator(`[data-job-kind="${kind}"]`);
  await expect(progress).toBeVisible({ timeout: 30_000 });
  await expect(progress).toBeHidden({ timeout });
  await expect(page.getByRole("alert")).toHaveCount(0);
}

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

test("bracket sample converts, edits, validates, exports, and reopens", async ({ page }, testInfo) => {
  await openCleanStart(page);
  await page.getByRole("row", { name: "Open Bracket with holes sample" }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "sample_open");

  await page.getByRole("button", { name: "Confirm import" }).click();
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await waitForJob(page, "analyze");
  await page.locator('[data-workflow-step="import"]').click();
  await expect(page.getByText("Triangles", { exact: true })).toBeVisible();

  await page.locator('[data-workflow-step="repair"]').click();
  await page.getByRole("button", { name: "Apply repair" }).click();
  await waitForJob(page, "repair");
  await expect(page.getByText("Operations recorded")).toBeVisible();

  await page.locator('[data-workflow-step="surfaces"]').click();
  const cylinder = page.locator('[data-patch-type="cylinder"]').first();
  await expect(cylinder).toBeVisible();
  await cylinder.click();
  await expect(page.getByText(/Selected patch/)).toBeVisible();

  await page.locator('[data-workflow-step="features"]').click();
  await page
    .getByLabel("features inspector")
    .getByRole("button", { name: "Auto reconstruct" })
    .click();
  await waitForJob(page, "reconstruct", 240_000);
  const hole = page.locator('[data-feature-operation="hole"]').first();
  await expect(hole).toBeVisible();
  await hole.click();

  await page.locator('[data-workflow-step="refine"]').click();
  const diameter = page.getByLabel("Diameter");
  const original = Number(await diameter.inputValue());
  const edited = Number((original * 1.1).toFixed(4));
  const cadgraphUpdated = page.waitForResponse((response) =>
    response.request().method() === "PATCH" && response.url().includes("/cadgraph") && response.ok());
  await diameter.fill(String(edited));
  await diameter.press("Enter");
  await cadgraphUpdated;
  await page.getByRole("button", { name: "Rebuild", exact: true }).click();
  await waitForJob(page, "rebuild", 180_000);

  await page.locator('[data-workflow-step="validate"]').click();
  await page.getByRole("button", { name: "Run validation" }).click();
  await waitForJob(page, "validate", 180_000);
  await expect(page.locator('[data-validation-stage="brep"]')).toContainText("Valid");
  await expect(page.locator('[data-validation-stage="step-reimport"]')).toContainText("Successful");

  await page.locator('[data-workflow-step="export"]').click();
  const stepDownload = page.waitForEvent("download", { timeout: 30_000 });
  await page.locator('[data-artifact-name="model.step"]').click();
  expect((await stepDownload).suggestedFilename()).toBe("model.step");
  const graphDownload = page.waitForEvent("download", { timeout: 30_000 });
  await page.locator('[data-artifact-name="model.cadgraph.json"]').click();
  expect((await graphDownload).suggestedFilename()).toBe("model.cadgraph.json");
  const projectDownload = page.waitForEvent("download", { timeout: 30_000 });
  await page
    .getByLabel("export inspector")
    .getByRole("button", { name: "Save project" })
    .click();
  const savedProject = await projectDownload;
  const savedPath = testInfo.outputPath("saved-project.mesh2param.json");
  await savedProject.saveAs(savedPath);

  await page.reload();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await page.locator('[data-workflow-step="refine"]').click();
  await expect(page.getByLabel("Diameter")).toHaveValue(String(edited));

  await page.getByRole("button", { name: "Back to start screen" }).click();
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByLabel("Open Mesh2Param project file").setInputFiles(savedPath);
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await page.locator('[data-workflow-step="refine"]').click();
  await expect(page.getByLabel("Diameter")).toHaveValue(String(edited));
});

test("start and workspace stay usable at required responsive sizes", async ({ page }) => {
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 820, height: 900 },
    { width: 390, height: 844 },
  ];
  await openCleanStart(page);
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByTestId("start-screen")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow, `start ${viewport.width}x${viewport.height} has page-level horizontal overflow`).toBe(false);
  }

  await page.getByRole("row", { name: "Open Bracket with holes sample" }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "sample_open");
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow, `workspace ${viewport.width}x${viewport.height} has page-level horizontal overflow`).toBe(false);
  }
});
