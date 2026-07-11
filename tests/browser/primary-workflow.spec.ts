import { expect, test, type Page } from "@playwright/test";

async function waitForJob(page: Page, kind: string, timeout = 180_000) {
  const progress = page.locator(`[data-job-kind="${kind}"]`);
  await expect(progress).toBeVisible({ timeout: 30_000 });
  await expect(progress).toBeHidden({ timeout });
  await expect(page.getByRole("alert")).toHaveCount(0);
}

test("bracket sample converts, edits, validates, exports, and reopens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: "Open Bracket with holes sample" }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "sample_open");

  await page.getByRole("button", { name: "Confirm import" }).click();
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await waitForJob(page, "analyze");
  await page.getByRole("button", { name: /Import/ }).click();
  await expect(page.getByText("Triangles", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Repair/ }).click();
  await page.getByRole("button", { name: "Apply repair" }).click();
  await waitForJob(page, "repair");
  await expect(page.getByText("Operations recorded")).toBeVisible();

  await page.getByRole("button", { name: /Surfaces/ }).click();
  const cylinder = page.locator('[data-patch-type="cylinder"]').first();
  await expect(cylinder).toBeVisible();
  await cylinder.click();
  await expect(page.getByText(/Selected patch/)).toBeVisible();

  await page.getByRole("button", { name: /Features/ }).click();
  await page.getByRole("button", { name: "Auto reconstruct" }).click();
  await waitForJob(page, "reconstruct", 240_000);
  const hole = page.locator('[data-feature-operation="hole"]').first();
  await expect(hole).toBeVisible();
  await hole.click();

  await page.getByRole("button", { name: /Refine/ }).click();
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

  await page.getByRole("button", { name: /Validate/ }).click();
  await page.getByRole("button", { name: "Run validation" }).click();
  await waitForJob(page, "validate", 180_000);
  await expect(page.locator('[data-validation-stage="brep"]')).toContainText("Valid");
  await expect(page.locator('[data-validation-stage="step-reimport"]')).toContainText("Successful");

  await page.getByRole("button", { name: /Export/ }).click();
  const stepDownload = page.waitForEvent("download");
  await page.locator('[data-artifact-name="model.step"]').click();
  expect((await stepDownload).suggestedFilename()).toBe("model.step");
  const graphDownload = page.waitForEvent("download");
  await page.locator('[data-artifact-name="model.cadgraph.json"]').click();
  expect((await graphDownload).suggestedFilename()).toBe("model.cadgraph.json");
  const projectDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save project" }).last().click();
  const savedProject = await projectDownload;
  const savedPath = await savedProject.path();
  expect(savedPath).not.toBeNull();

  await page.reload();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Refine/ }).click();
  await expect(page.getByLabel("Diameter")).toHaveValue(String(edited));

  await page.getByRole("button", { name: "Back to start screen" }).click();
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByLabel("Open Mesh2Param project file").setInputFiles(savedPath!);
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Refine/ }).click();
  await expect(page.getByLabel("Diameter")).toHaveValue(String(edited));
});

test("start and workspace stay usable at required responsive sizes", async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 820, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByTestId("start-screen")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow, `${viewport.width}x${viewport.height} has page-level horizontal overflow`).toBe(false);
  }
});
