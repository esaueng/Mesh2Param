import { expect, test } from "@playwright/test";

test("saved project with unavailable artifact bytes does not mount a black viewer", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Reflect.deleteProperty(globalThis, "showSaveFilePicker");
  });
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();

  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  // Durable outcome instead of the transient progress bar: fast jobs finish
  // before a visibility assertion can attach (the same reason
  // primary-workflow.spec.ts waits on the primary action).
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
  // Save project is a main-thread operation (IndexedDB write, lazy codec
  // import, source re-hash). Clicking while the first reveal is still held
  // schedules it behind the reveal's shader compile, which on a GPU-less CI
  // runner is a multi-hundred-millisecond SwiftShader stall — see
  // docs/viewer-performance.md. Every other viewer spec waits for this
  // attribute; this one did not.
  await expect(page.getByTestId("cad-viewport"))
    .toHaveAttribute("data-viewer-preparing", "false", { timeout: 60_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);

  const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
  // A failing save raises an alert and never requests a download, which would
  // otherwise surface only as an unexplained waitForEvent timeout. Race the
  // two so the failure names itself.
  const saveAlert = page.getByRole("alert").first();
  const reportedSaveFailure = saveAlert
    .waitFor({ state: "visible", timeout: 30_000 })
    .then(async () => {
      throw new Error(`Save project reported: ${await saveAlert.innerText()}`);
    });
  reportedSaveFailure.catch(() => {/* only meaningful when it wins the race */});
  await page.getByRole("button", { name: "Save project", exact: true }).click();
  await Promise.race([downloadPromise, reportedSaveFailure]);
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
  await page.screenshot({ path: testInfo.outputPath("saved-project-reopen.png") });
});
