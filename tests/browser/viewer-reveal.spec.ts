import { expect, test, type Page } from "@playwright/test";

/**
 * Records every value `data-viewer-preparing` takes, compacted to transitions.
 *
 * A MutationObserver rather than polling on purpose: the reveal is held across
 * a main-thread stall while the first frame's shaders compile, and page-side
 * polling cannot run during it. The observer's records are queued and delivered
 * once the thread frees, so the sequence survives the stall intact.
 */
const RECORD_REVEAL = () => {
  const store: { states: string[] } = { states: [] };
  (globalThis as unknown as { __reveal: typeof store }).__reveal = store;
  const sample = () => {
    const viewport = document.querySelector('[data-testid="cad-viewport"]');
    const value = viewport?.getAttribute("data-viewer-preparing");
    if (value !== undefined && value !== null && store.states.at(-1) !== value) store.states.push(value);
  };
  const observer = new MutationObserver(sample);
  const begin = () => observer.observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, attributeFilter: ["data-viewer-preparing"],
  });
  if (document.documentElement !== null) begin();
  else document.addEventListener("readystatechange", begin, { once: true });
};

async function revealStates(page: Page) {
  return page.evaluate(() => (globalThis as unknown as { __reveal: { states: string[] } }).__reveal.states);
}

test("the viewport is held until its first frame is painted", async ({ page }) => {
  await page.addInitScript(RECORD_REVEAL);
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });

  await expect(page.getByTestId("cad-viewport")).toHaveAttribute("data-viewer-preparing", "false", { timeout: 30_000 });
  await expect(page.locator(".viewer-preparing")).toHaveCount(0);

  // The viewport must have announced the wait before clearing it, rather than
  // presenting an empty canvas as a finished result.
  expect(await revealStates(page)).toEqual(["true", "false"]);
});

test("redrawing an already-visible model does not re-enter the held state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
  await expect(page.getByTestId("cad-viewport")).toHaveAttribute("data-viewer-preparing", "false", { timeout: 30_000 });

  // Start recording only once the model is up, so anything captured below is a
  // regression: the canvas already holds a usable frame, and covering it with a
  // placeholder would replace context with less.
  await page.evaluate(RECORD_REVEAL);
  for (const name of ["Compare", "Source", "Result", "Compare"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByRole("button", { name, exact: true })).toHaveAttribute("aria-pressed", "true");
  }
  await page.getByRole("button", { name: "Toggle light or dark theme" }).click();
  await expect(page.locator(".canvas-shell")).toHaveAttribute("data-theme", "light");

  // The recorder samples the current value on its first mutation, so a leading
  // "false" is expected; any "true" is the regression.
  expect((await revealStates(page)).filter((state) => state === "true")).toEqual([]);
  await expect(page.locator(".viewer-preparing")).toHaveCount(0);
});
