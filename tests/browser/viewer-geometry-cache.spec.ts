import { expect, test, type Locator, type Page } from "@playwright/test";

async function selectMode(mode: Locator) {
  await mode.click();
  await expect(mode).toHaveAttribute("aria-pressed", "true");
}

async function openSettledSample(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("start-screen")).toBeVisible();
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  await expect(page.getByTestId("cad-viewport")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
}

test("switching display modes does not refetch content-addressed geometry", async ({ page }) => {
  await openSettledSample(page);

  const result = page.getByRole("button", { name: /^(Result|Converted)$/ });
  const compare = page.getByRole("button", { name: "Compare", exact: true });
  await expect(compare).toBeVisible();

  // Prime both modes so every GLB has been fetched at least once.
  await selectMode(compare);
  await selectMode(result);

  const geometryRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(".glb")) geometryRequests.push(new URL(request.url()).pathname);
  });

  for (let pass = 0; pass < 5; pass += 1) {
    await selectMode(compare);
    await selectMode(result);
  }

  // The GLB URLs are SHA-256 addressed and therefore immutable: once loaded,
  // a display-mode change must not go back to the network for them.
  expect(geometryRequests).toEqual([]);
  // Reusing a cached GLTF must still render: the layers clone it rather than
  // consuming it, so the viewport stays alive across every switch.
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
