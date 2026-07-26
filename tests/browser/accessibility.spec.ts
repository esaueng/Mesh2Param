import { expect, test, type Page } from "@playwright/test";

/** Describes whatever currently holds focus, including whether it is visible. */
async function focusedElement(page: Page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement)) return { tag: "none", label: "", width: 0, height: 0, inDialog: false };
    const box = element.getBoundingClientRect();
    return {
      tag: element.tagName.toLowerCase() + (element.getAttribute("type") === null ? "" : `[type=${element.getAttribute("type")}]`),
      label: element.getAttribute("aria-label") ?? element.textContent?.trim().slice(0, 40) ?? "",
      width: box.width,
      height: box.height,
      inDialog: element.closest("dialog") !== null,
    };
  });
}

async function openSampleWorkspace(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  // Keyboard assertions need a settled workspace: while the conversion job is
  // still running the panel re-renders continuously, and a keypress delivered
  // mid-commit lands somewhere other than the expected tab stop.
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
}

test("every landing tab stop is a visible control", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();

  const stops = [];
  for (let step = 0; step < 14; step += 1) {
    await page.keyboard.press("Tab");
    stops.push(await focusedElement(page));
  }

  // The file inputs are triggered by the visible buttons, so they must never
  // take focus themselves: a 1x1 clipped input reads as focus disappearing.
  expect(stops.filter((stop) => stop.tag === "input[type=file]")).toEqual([]);
  expect(stops.filter((stop) => stop.width <= 1 || stop.height <= 1)).toEqual([]);
});

test("the workspace replacement file input is not a tab stop", async ({ page }) => {
  await openSampleWorkspace(page);

  const replacementInput = page.getByLabel("Choose source mesh");
  await expect(replacementInput).toHaveAttribute("tabindex", "-1");
  // Still operable through the visible control that triggers it.
  await expect(page.getByRole("button", { name: /Replace mesh/i })).toBeVisible();
});

test("the skip link moves focus to the 3D viewport", async ({ page }) => {
  await openSampleWorkspace(page);

  // Start the tab sequence from the top of the document. Opening the sample
  // leaves Chromium's sequential-focus starting point on the landing button
  // that has since been unmounted, so focusing the body resets it; a skip link
  // is only useful as the first stop.
  await page.evaluate(() => {
    document.body.setAttribute("tabindex", "-1");
    document.body.focus();
    document.body.removeAttribute("tabindex");
  });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to 3D viewport" })).toBeFocused();

  await page.keyboard.press("Enter");

  await expect(page.locator("#canvas-viewport")).toBeFocused();
});

test("the shortcuts dialog keeps focus off the workspace behind it", async ({ page }) => {
  await openSampleWorkspace(page);

  await page.getByRole("button", { name: "Shortcuts" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("button", { name: "Close keyboard shortcuts" })).toBeFocused();

  // Chromium parks focus on the document between cycles of a single-control
  // dialog, which is a wrap-around rather than a leak; reaching a real control
  // behind the dialog — the reported defect — is what must not happen.
  const stops = [];
  for (let step = 0; step < 6; step += 1) {
    await page.keyboard.press("Tab");
    stops.push(await focusedElement(page));
  }

  expect(stops.filter((stop) => !stop.inDialog && stop.tag !== "body" && stop.tag !== "html")).toEqual([]);
});

test("Escape closes the shortcuts dialog and returns focus to its trigger", async ({ page }) => {
  await openSampleWorkspace(page);

  const trigger = page.getByRole("button", { name: "Shortcuts" });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("the shortcuts dialog makes the background inert", async ({ page }) => {
  await openSampleWorkspace(page);

  await page.getByRole("button", { name: "Shortcuts" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // A modal dialog is in the top layer, so nothing behind it is hit-testable.
  const backgroundIsInert = await page.evaluate(() => {
    const behind = document.querySelector<HTMLElement>(".panel-btn");
    if (behind === null) return false;
    const box = behind.getBoundingClientRect();
    const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return hit?.closest("dialog") !== null;
  });

  expect(backgroundIsInert).toBe(true);
});
