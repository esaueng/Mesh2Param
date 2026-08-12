import { expect, test } from "@playwright/test";

test("the CAD viewport renders and changes display mode without the deprecated Three Clock", async ({ page }) => {
  const legacyClockWarnings: string[] = [];
  page.on("console", (message) => {
    if (/Clock.*deprecated|deprecated.*Clock/i.test(message.text())) {
      legacyClockWarnings.push(message.text());
    }
  });

  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();

  const viewport = page.getByTestId("cad-viewport");
  await expect(viewport).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
  await expect(viewport).toHaveAttribute("data-viewer-preparing", "false");
  await expect(viewport.locator("canvas").first()).toBeVisible();

  await page.getByRole("radio", { name: /Wireframe/ }).click();
  await expect(viewport).toHaveAttribute("data-display-mode", "wireframe");
  await page.getByRole("radio", { name: /Shaded/ }).click();
  await expect(viewport).toHaveAttribute("data-display-mode", "shaded");
  await page.getByRole("button", { name: "Fit view", exact: true }).click();
  await expect(viewport).toHaveAttribute("data-camera-view", "iso");

  expect(legacyClockWarnings).toEqual([]);
});
