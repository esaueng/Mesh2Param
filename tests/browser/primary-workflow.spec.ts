import { expect, test, type Locator, type Page } from "@playwright/test";
import { resolve } from "node:path";

// `pnpm test:e2e` runs from apps/web; the sample meshes live at the repo root.
const SAMPLE_STL = resolve(process.cwd(), "../../samples/generated/l-bracket-with-holes/source-random.stl");
const SOFT_GABLE_STL = resolve(
  process.cwd(),
  "../../samples/curved-benchmark/bspline-soft-gable-plate/source.stl",
);

const primaryAction = (page: Page) => page.locator(".dock-primary");

async function expectPrimaryAction(page: Page, label: string, timeout = 240_000) {
  await expect(primaryAction(page)).toContainText(label, { timeout });
  await expect(page.getByRole("alert")).toHaveCount(0);
}
async function openCleanStart(page: Page) {
  await page.addInitScript(() => {
    Reflect.deleteProperty(globalThis, "showSaveFilePicker");
  });
  await page.goto("/");
  const origin = new URL(page.url()).origin;
  const devtools = await page.context().newCDPSession(page);
  await devtools.send("Storage.clearDataForOrigin", {
    origin,
    storageTypes: "all",
  });
  await devtools.detach();
  await page.reload();
  await expect(page.getByTestId("start-screen")).toBeVisible();
}

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
  await expectPrimaryAction(page, "Download STEP");

  // The supported sample arrives fully validated, so the guided action is a download.
  await expect(page.getByText("Validated")).toBeVisible();

  // Display modes: the reconstructed result is revealed; comparing overlays the source.
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Result", exact: true }).click();
  await expect(page.getByRole("button", { name: "Result", exact: true })).toHaveAttribute("aria-pressed", "true");

  // The identity strip occupies the same top row visually, but its empty grid
  // area must not intercept the viewport tools underneath it.
  const section = page.getByRole("button", { name: "Section", exact: true });
  await section.click({ timeout: 15_000 });
  await expect(page.getByTestId("section-controls")).toBeVisible();
  await section.click({ timeout: 15_000 });
  await expect(page.getByTestId("section-controls")).toHaveCount(0);
  const measure = page.getByRole("button", { name: "Measure", exact: true });
  await measure.click({ timeout: 15_000 });
  await expect(page.getByTestId("measurement-controls")).toBeVisible();
  await measure.click({ timeout: 15_000 });
  await expect(page.getByTestId("measurement-controls")).toHaveCount(0);

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
  await expect(page.locator(".canvas-shell")).toBeVisible({ timeout: 30_000 });

  // Ingest yields diagnostics only; analysis is the next guided step.
  await expectPrimaryAction(page, "Analyze mesh");
  await expect(page.getByText("Mesh loaded", { exact: true })).toBeVisible();
  await primaryAction(page).click();

  // Analysis produces the renderable source mesh and unlocks reconstruction.
  await expectPrimaryAction(page, "Reconstruct");
  await expect(page.getByText("Analyzed", { exact: true })).toBeVisible();
  await expect(page.getByTestId("cad-viewport")).toBeVisible();
  await primaryAction(page).click();

  await expectPrimaryAction(page, "Download STEP");
  const download = page.waitForEvent("download", { timeout: 30_000 });
  await primaryAction(page).click();
  expect((await download).suggestedFilename()).toMatch(/\.step$/i);
});

test("surface patch controls persist authoritative edits", async ({ page }) => {
  await openCleanStart(page);
  await page.getByLabel("Choose source mesh").setInputFiles(SOFT_GABLE_STL);
  await expect(page.locator(".canvas-shell")).toBeVisible({ timeout: 30_000 });

  await expectPrimaryAction(page, "Analyze mesh");
  await primaryAction(page).click();

  const patchItems = page.locator(".panel-patches > li");
  const freeformItems = patchItems.filter({ has: page.locator(".patch-kind-freeform") });
  const planeItems = patchItems.filter({ has: page.locator(".patch-kind-plane") });
  await expect(
    page.getByRole("heading", { name: "Patches (7)", exact: true }),
  ).toBeVisible({ timeout: 240_000 });
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(patchItems).toHaveCount(7);
  await expect(freeformItems).toHaveCount(2);
  await expect(planeItems).toHaveCount(5);

  const firstFreeformId = await patchId(freeformItems.nth(0));
  const secondFreeformId = await patchId(freeformItems.nth(1));
  const planeId = await patchId(planeItems.nth(0));

  // Hide/show is a viewport contract, not metadata-only state. Keep the second
  // patch selected so the screenshots differ only if the first patch's
  // triangles and edges actually leave the scene.
  await patchItem(page, secondFreeformId).locator(".panel-patch-row").click();
  const viewport = page.getByTestId("cad-viewport");
  const beforeHide = await viewport.screenshot();
  await expectPatch(page, firstFreeformId, { hidden: true }, () =>
    page.getByRole("button", { name: `Hide ${firstFreeformId}`, exact: true }).click());
  await expect(page.getByRole("button", { name: `Show ${firstFreeformId}`, exact: true })).toBeVisible();
  await expect(viewport).toHaveAttribute("data-hidden-patch-count", "1");
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
  const afterHide = await viewport.screenshot();
  expect(afterHide.equals(beforeHide), "hiding a patch should change the rendered viewport").toBe(false);
  await expectPatch(page, firstFreeformId, { hidden: false }, () =>
    page.getByRole("button", { name: `Show ${firstFreeformId}`, exact: true }).click());
  await expect(viewport).toHaveAttribute("data-hidden-patch-count", "0");

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
  await expectPrimaryAction(page, "Download STEP");
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    expect(await hasHOverflow(), `canvas ${viewport.width}x${viewport.height} overflows horizontally`).toBe(false);
    // From the top of the command panel, without scrolling it: the primary
    // conversion action has to be reachable rather than buried under the whole
    // display and feature tree.
    await page.locator(".canvas-panel").evaluate((panel) => { panel.scrollTop = 0; });
    await expect(
      page.locator(".dock-primary"),
      `primary action is out of view at ${viewport.width}x${viewport.height}`,
    ).toBeInViewport();
  }
});
