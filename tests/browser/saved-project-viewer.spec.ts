import { expect, test, type Page } from "@playwright/test";

async function waitForJob(page: Page, kind: string, timeout = 240_000) {
  const progress = page.locator(`.canvas-progress[data-job-kind="${kind}"]`);
  await expect(progress).toBeVisible({ timeout: 30_000 });
  await expect(progress).toBeHidden({ timeout });
  await expect(page.getByRole("alert")).toHaveCount(0);
}

test("saved project with unavailable artifact bytes does not mount a black viewer", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Reflect.deleteProperty(globalThis, "showSaveFilePicker");
  });
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();

  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "sample_open");

  const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
  await page.getByRole("button", { name: "Save project", exact: true }).click();
  const savedProject = testInfo.outputPath("l-bracket.mesh2param.json");
  await (await downloadPromise).saveAs(savedProject);

  const projectId = await page.evaluate(() => sessionStorage.getItem("mesh2param-active-project"));
  expect(projectId).not.toBeNull();
  const projectResponse = await page.request.get(`/api/projects/${projectId!}`);
  expect(projectResponse.ok()).toBe(true);
  const etag = projectResponse.headers()["etag"];
  expect(etag).toBeDefined();
  const deleted = await page.request.delete(`/api/projects/${projectId!}`, {
    headers: { "If-Match": etag! },
  });
  expect(deleted.status()).toBe(204);

  await page.getByRole("button", { name: "Back to start screen", exact: true }).click();
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByLabel("Open saved project file").setInputFiles(savedProject);

  await expect(page.getByText("Mesh loaded", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("cad-viewport")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  await page.screenshot({ path: "/private/tmp/mesh2param-saved-project-repro.png" });
});
