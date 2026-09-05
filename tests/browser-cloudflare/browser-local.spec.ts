import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const samples = resolve(process.cwd(), "../../samples");

/**
 * The dock's primary command. Addressed by its action rather than its label
 * because side panels can offer a button with the same accessible name.
 */
function primary(page: Page, action: string) {
  return page.locator(`.dock-primary[data-action="${action}"]`);
}

/** Artifact names persisted for the active browser-local project. */
async function storedArtifactNames(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
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
}

test("reports the browser-local Worker deployment as healthy without an API origin", async ({ request }) => {
  const response = await request.get("/health");

  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toBe("no-store");
  expect(response.headers()["x-request-id"]).toBeTruthy();
  await expect(response.json()).resolves.toEqual({
    status: "ok",
    service: "mesh2param-worker",
    executionMode: "browser-local",
    apiProxy: "not-configured",
  });
});

test("reconstructs an uploaded mesh in the browser core and downloads its STEP", async ({ page }) => {
  const wasmResponses: number[] = [];
  page.on("response", (response) => {
    if (response.url().endsWith(".wasm")) wasmResponses.push(response.status());
  });

  const response = await page.goto("/");
  expect(response?.headers()["cross-origin-opener-policy"]).toBe("same-origin");
  expect(response?.headers()["cross-origin-embedder-policy"]).toBe("require-corp");
  await expect(page.getByText("Local Mesh2Param core · files stay in this browser")).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles(
    resolve(samples, "real/hammer-holder/mesh-coarse.stl"),
  );
  await expect(primary(page, "analyze")).toBeVisible();
  await primary(page, "analyze").click();

  await expect(primary(page, "reconstruct")).toBeVisible({ timeout: 120_000 });
  await primary(page, "reconstruct").click();
  await expect(primary(page, "download")).toBeVisible({ timeout: 180_000 });

  // The tier the core reached has to be visible, not merely recorded.
  const evidence = page.getByTestId("curved-evidence");
  await expect(evidence).toBeVisible();
  await expect(evidence).toContainText(/(Analytic|Mixed|Faceted) tier/);
  await expect(evidence).toContainText("Design history is not recovered");

  expect(await storedArtifactNames(page)).toEqual(expect.arrayContaining([
    "model.step", "reconstructed.glb", "reconstruction.json", "source.glb",
  ]));
  expect(wasmResponses).toContain(200);

  const downloadPromise = page.waitForEvent("download");
  await primary(page, "download").click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (downloadPath === null) throw new Error("The STEP download was unavailable");
  const step = await readFile(downloadPath, "utf8");
  expect(step.startsWith("ISO-10303-21;")).toBe(true);
  expect(step).toContain("MANIFOLD_SOLID_BREP");

  await expect(page.locator(".global-error")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
});

test("keeps a browser-local reconstruction across an offline reload", async ({ page, context }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(
    resolve(samples, "generated/rectangular-block/source-high.stl"),
  );
  await primary(page, "analyze").click();
  await expect(primary(page, "reconstruct")).toBeVisible({ timeout: 120_000 });
  await primary(page, "reconstruct").click();
  await expect(primary(page, "download")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("curved-evidence")).toContainText("Analytic tier");

  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await context.setOffline(true);
  await page.reload();
  await expect(primary(page, "download")).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".global-error")).toHaveCount(0);
  await context.setOffline(false);
});

test("serves the bundled sample from its precomputed artifacts and refuses a CADGraph rebuild", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Try the L-bracket sample" })).toBeEnabled();
  await page.getByRole("button", { name: "Try the L-bracket sample" }).click();
  await expect(primary(page, "download")).toBeVisible();
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
  await expect(page.locator(".global-error")).toHaveCount(0);

  // Drop the recorded validation so the workspace offers the CADGraph rebuild
  // the browser core has no equivalent for.
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
    (record.document as { validation: unknown }).validation = null;
    store.put(record);
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
    database.close();
  });

  await page.reload();
  await expect(primary(page, "validate")).toBeVisible();
  await primary(page, "validate").click();

  const alert = page.locator(".global-error");
  await expect(alert).toBeVisible({ timeout: 60_000 });
  await expect(alert).toContainText("not available in browser mode");
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await expect(alert).toHaveCount(0);
  // The precomputed artifacts survive the refused rebuild.
  expect(await storedArtifactNames(page)).toEqual(expect.arrayContaining(["model.step", "reconstructed.glb"]));
});

test("round-trips a saved browser-local project file", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(
    resolve(samples, "generated/rectangular-block/source-high.stl"),
  );
  await primary(page, "analyze").click();
  await expect(primary(page, "reconstruct")).toBeVisible({ timeout: 120_000 });

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
  // A pre-July-2026 browser build could persist a signed volume; the opener
  // still has to normalize it.
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

  await expect(page.getByRole("heading", { name: "Patches (1)" })).toBeVisible({ timeout: 120_000 });
  await expect(primary(page, "reconstruct")).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".global-error")).toHaveCount(0);

  // The signed magnitudes the file carried are normalized on open.
  const restored = await page.evaluate(async () => {
    const projectId = window.sessionStorage.getItem("mesh2param-active-project");
    if (projectId === null) throw new Error("No active browser-local project");
    const request = window.indexedDB.open("mesh2param-workspace");
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const get = database.transaction("documents", "readonly").objectStore("documents").get(projectId);
    const record = await new Promise<{ document: { diagnostics: { closedVolume: number | null }; metrics: { volume?: number } | null } }>((resolve, reject) => {
      get.onsuccess = () => resolve(get.result as never);
      get.onerror = () => reject(get.error);
    });
    database.close();
    return { closedVolume: record.document.diagnostics.closedVolume, volume: record.document.metrics?.volume ?? null };
  });
  expect(restored.closedVolume).toBeGreaterThan(0);
  expect(restored.volume).toBeGreaterThan(0);
  await expect(page.getByRole("region", { name: "3D CAD viewer" })).not.toContainText("Viewer could not load geometry");
});
