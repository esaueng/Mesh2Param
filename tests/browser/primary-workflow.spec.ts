import { expect, test, type Locator, type Page } from "@playwright/test";
import { resolve } from "node:path";

// `pnpm test:e2e` runs from apps/web; the sample meshes live at the repo root.
const SAMPLE_STL = resolve(process.cwd(), "../../samples/generated/l-bracket-with-holes/source-random.stl");
const SOFT_GABLE_STL = resolve(
  process.cwd(),
  "../../samples/curved-benchmark/bspline-soft-gable-plate/source.stl",
);

async function waitForJob(page: Page, kind: string, timeout = 240_000) {
  const progress = page.locator(`.canvas-progress[data-job-kind="${kind}"]`);
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

const primaryAction = (page: Page) => page.locator(".dock-primary");

async function patchId(item: Locator) {
  const label = await item.locator('input[type="checkbox"]').getAttribute("aria-label");
  const match = /^Select (.+) for merge$/.exec(label ?? "");
  expect(match, `merge checkbox should expose its patch id, got ${String(label)}`).not.toBeNull();
  return match![1]!;
}

function patchItem(page: Page, id: string) {
  return page.locator(".panel-patches > li").filter({
    has: page.getByRole("checkbox", { name: `Select ${id} for merge`, exact: true }),
  });
}

async function expectPatch(
  page: Page,
  id: string,
  body: Record<string, unknown>,
  action: () => Promise<unknown>,
) {
  const responsePromise = page.waitForResponse((response) => {
    const request = response.request();
    return request.method() === "PATCH"
      && new URL(response.url()).pathname.endsWith(`/patches/${encodeURIComponent(id)}`);
  });
  await action();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON()).toMatchObject(body);
}

async function reloadWithPatches(page: Page) {
  const patchesPromise = page.waitForResponse((response) =>
    response.request().method() === "GET"
      && /\/api\/projects\/[^/]+\/patches$/.test(new URL(response.url()).pathname)
      && response.ok());
  await page.reload();
  await patchesPromise;
  await expect(page.getByRole("alert")).toHaveCount(0);
}

test("L-bracket sample opens validated and exports a STEP", async ({ page }) => {
  await openCleanStart(page);
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "sample_open");

  // The supported sample arrives fully validated, so the guided action is a download.
  await expect(page.getByText("Validated")).toBeVisible();
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

test("uploaded mesh advances through analyze, reconstruct, and download", async ({ page }) => {
  await openCleanStart(page);
  await page.getByLabel("Choose source mesh").setInputFiles(SAMPLE_STL);
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await waitForJob(page, "upload");

  // Ingest yields diagnostics only; analysis is the next guided step.
  await expect(primaryAction(page)).toContainText("Analyze mesh");
  await primaryAction(page).click();
  await waitForJob(page, "analyze");

  // Analysis produces the renderable source mesh and unlocks reconstruction.
  await expect(page.getByText("Analyzed")).toBeVisible();
  await expect(primaryAction(page)).toContainText("Reconstruct");
  await primaryAction(page).click();
  await waitForJob(page, "reconstruct");

  await expect(primaryAction(page)).toContainText("Download STEP", { timeout: 60_000 });
  const download = page.waitForEvent("download", { timeout: 30_000 });
  await primaryAction(page).click();
  expect((await download).suggestedFilename()).toMatch(/\.step$/i);
});

test("surface patch controls persist authoritative edits", async ({ page }) => {
  await openCleanStart(page);
  await page.getByLabel("Choose source mesh").setInputFiles(SOFT_GABLE_STL);
  await waitForJob(page, "upload");

  await expect(primaryAction(page)).toContainText("Analyze mesh");
  await primaryAction(page).click();
  await waitForJob(page, "analyze");
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });

  const patchItems = page.locator(".panel-patches > li");
  const freeformItems = patchItems.filter({ has: page.locator(".patch-kind-freeform") });
  const planeItems = patchItems.filter({ has: page.locator(".patch-kind-plane") });
  await expect(page.getByRole("heading", { name: "Patches (7)", exact: true })).toBeVisible();
  await expect(patchItems).toHaveCount(7);
  await expect(freeformItems).toHaveCount(2);
  await expect(planeItems).toHaveCount(5);

  const firstFreeformId = await patchId(freeformItems.nth(0));
  const secondFreeformId = await patchId(freeformItems.nth(1));
  const planeId = await patchId(planeItems.nth(0));

  await expectPatch(page, planeId, { locked: true }, () =>
    page.getByRole("button", { name: `Lock ${planeId}`, exact: true }).click());
  await expect(page.getByRole("button", { name: `Unlock ${planeId}`, exact: true })).toBeVisible();
  await reloadWithPatches(page);
  await expect(page.getByRole("button", { name: `Unlock ${planeId}`, exact: true })).toBeVisible();
  await expectPatch(page, planeId, { locked: false }, () =>
    page.getByRole("button", { name: `Unlock ${planeId}`, exact: true }).click());

  await patchItem(page, planeId).locator(".panel-patch-row").click();
  const reclassify = page.getByRole("combobox", { name: "Reclassify selected patch", exact: true });
  await expect(reclassify).toHaveValue("plane");
  await expectPatch(page, planeId, { classification: "unknown" }, () => reclassify.selectOption("unknown"));
  await expect(reclassify).toHaveValue("unknown");
  await expectPatch(page, planeId, { classification: "plane" }, () => reclassify.selectOption("plane"));
  await expect(reclassify).toHaveValue("plane");

  const merge = page.getByRole("button", { name: "Merge", exact: true });
  const firstFreeformMerge = page.getByRole("checkbox", {
    name: `Select ${firstFreeformId} for merge`,
    exact: true,
  });
  const secondFreeformMerge = page.getByRole("checkbox", {
    name: `Select ${secondFreeformId} for merge`,
    exact: true,
  });
  const planeMerge = page.getByRole("checkbox", { name: `Select ${planeId} for merge`, exact: true });
  await expect(merge).toBeDisabled();
  await firstFreeformMerge.check();
  await secondFreeformMerge.check();
  await expect(merge).toBeEnabled();
  await secondFreeformMerge.uncheck();
  await planeMerge.check();
  await expect(merge).toBeDisabled();
  await expect(merge).toHaveAttribute("title", /same classification/i);
  await planeMerge.uncheck();

  const split = page.getByRole("button", { name: "Split", exact: true });
  await expect(split).toBeDisabled();
  await expect(split).toHaveAttribute("title", /not implemented/i);

  await patchItem(page, firstFreeformId).locator(".panel-patch-row").click();
  const firstContinuity = page.getByRole("combobox", {
    name: `Boundary continuity to ${secondFreeformId}`,
    exact: true,
  });
  await expect(firstContinuity).toHaveValue("crease");
  await expectPatch(page, firstFreeformId, { smoothBoundaryIds: [secondFreeformId] }, () =>
    firstContinuity.selectOption("smooth"));
  await expect(firstContinuity).toHaveValue("smooth");

  await reloadWithPatches(page);
  const firstRow = patchItem(page, firstFreeformId).locator(".panel-patch-row");
  if (await firstRow.getAttribute("aria-selected") !== "true") await firstRow.click();
  await expect(page.getByRole("combobox", {
    name: `Boundary continuity to ${secondFreeformId}`,
    exact: true,
  })).toHaveValue("smooth");

  await patchItem(page, secondFreeformId).locator(".panel-patch-row").click();
  await expect(page.getByRole("combobox", {
    name: `Boundary continuity to ${firstFreeformId}`,
    exact: true,
  })).toHaveValue("smooth");
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
  await waitForJob(page, "sample_open");
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    expect(await hasHOverflow(), `canvas ${viewport.width}x${viewport.height} overflows horizontally`).toBe(false);
  }
});
