import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
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

test("reconstructs a spline spanner to parametric STEP locally and reloads offline", async ({ page, context }) => {
  const response = await page.goto("/");
  expect(response?.headers()["cross-origin-opener-policy"]).toBe("same-origin");
  expect(response?.headers()["cross-origin-embedder-policy"]).toBe("require-corp");
  await expect(page.getByText("Local OCCT-WASM · files stay in this browser")).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles(
    resolve(process.cwd(), "../../samples/general-parametric-benchmark/spanner-filleted/source.stl"),
  );
  await expect(page.getByRole("button", { name: "Analyze mesh" })).toBeVisible();
  await page.getByRole("button", { name: "Analyze mesh" }).click();
  await expect(page.getByRole("button", { name: "Reconstruct", exact: true })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Reconstruct", exact: true }).click();
  await expect(page.getByRole("button", { name: "Download STEP" })).toBeVisible({ timeout: 180_000 });

  const artifactNames = await page.evaluate(async () => {
    const request = window.indexedDB.open("mesh2param-workspace");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const transaction = database.transaction("blobs", "readonly");
    const records = await new Promise<Array<{ originalFileName?: string }>>((resolve, reject) => {
      const getAll = transaction.objectStore("blobs").getAll();
      getAll.onsuccess = () => resolve(getAll.result as Array<{ originalFileName?: string }>);
      getAll.onerror = () => reject(getAll.error);
    });
    database.close();
    return records.flatMap((record) => record.originalFileName === undefined ? [] : [record.originalFileName]);
  });
  expect(artifactNames).toEqual(expect.arrayContaining([
    "model.step", "model.cadgraph.json", "comparison.json", "surface-audit.json",
  ]));

  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("button", { name: "Download STEP" })).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".global-error")).toHaveCount(0);
  await context.setOffline(false);
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

  await page.evaluate(() => {
    Object.defineProperty(window, "showSaveFilePicker", { value: undefined, configurable: true });
  });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save project" }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (downloadPath === null) throw new Error("Saved project download was unavailable");
  const saved = JSON.parse(await readFile(downloadPath, "utf8")) as {
    working: { diagnostics: { closedVolume: number | null }; metrics: { volume?: number } | null };
  };
  if (saved.working.diagnostics.closedVolume !== null) {
    saved.working.diagnostics.closedVolume = -Math.abs(saved.working.diagnostics.closedVolume);
  }
  if (typeof saved.working.metrics?.volume === "number") {
    saved.working.metrics.volume = -Math.abs(saved.working.metrics.volume);
  }

  await page.getByRole("button", { name: "Back to start screen" }).click();
  await page.locator('input[type="file"]').nth(1).setInputFiles({
    name: "signed-volume.mesh2param.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(saved)),
  });

  await expect(page.getByText("source-high.stl", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate STEP" })).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".global-error")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
});
