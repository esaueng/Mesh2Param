import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

test("opens persisted geometry and rebuilds an exact CADGraph in browser WASM", async ({ page }) => {
  const wasmResponses: number[] = [];
  page.on("response", (response) => {
    if (response.url().endsWith(".wasm")) wasmResponses.push(response.status());
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Try the L-bracket sample" })).toBeEnabled();
  await page.getByRole("button", { name: "Try the L-bracket sample" }).click();
  await expect(page.getByRole("button", { name: "Download STEP" })).toBeVisible();
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");

  await page.evaluate(async () => {
    const projectId = window.sessionStorage.getItem("mesh2param-active-project");
    if (projectId === null) throw new Error("No active browser-local project");
    const request = window.indexedDB.open("mesh2param-workspace");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const transaction = database.transaction("documents", "readwrite");
    const store = transaction.objectStore("documents");
    const documentRequest = store.get(projectId);
    const record = await new Promise<Record<string, unknown>>((resolve, reject) => {
      documentRequest.onsuccess = () => resolve(documentRequest.result as Record<string, unknown>);
      documentRequest.onerror = () => reject(documentRequest.error);
    });
    const document = record.document as { validation: unknown };
    document.validation = null;
    store.put(record);
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
    database.close();
  });

  await page.reload();
  await expect(page.getByRole("button", { name: "Validate" })).toBeVisible();
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("button", { name: "Download STEP" })).toBeVisible({ timeout: 120_000 });
  expect(wasmResponses).toContain(200);
  await expect(page.locator(".global-error")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
});

test("analyzes an uploaded STL and exports a browser-local faceted STEP", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(
    resolve(process.cwd(), "../../samples/generated/rectangular-block/source-high.stl"),
  );

  await expect(page.getByRole("button", { name: "Analyze mesh" })).toBeVisible();
  await page.getByRole("button", { name: "Analyze mesh" }).click();
  await expect(page.getByRole("button", { name: "Generate STEP" })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Generate STEP" }).click();
  await expect(page.getByRole("button", { name: "Download STEP" })).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".global-error")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
});
