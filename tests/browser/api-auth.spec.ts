import { expect, test } from "@playwright/test";

test("protected API geometry renders after entering the token", async ({ page }, testInfo) => {
  const token = "browser-regression-token";
  const geometryCredentials: Array<string | undefined> = [];
  const errors: string[] = [];
  let connected = false;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (connected && message.type() === "error") errors.push(message.text());
  });
  // Gate the native API responses as a protected deployment would, while retaining
  // real sample jobs, artifact bytes, and GLTF rendering behind the gate.
  await page.route("**/api/**", async (route) => {
    const credential = route.request().headers()["authorization"];
    if (new URL(route.request().url()).pathname.endsWith(".glb")) geometryCredentials.push(credential);
    if (credential !== `Bearer ${token}`) {
      await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({
        error: { code: "authentication_required", summary: "API authentication is required", detail: "Enter the API token.", recoverable: true },
      }) });
      return;
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(page).toHaveTitle(/Mesh2Param/);
  await page.getByLabel("Bearer token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Enter API token" })).toHaveCount(0);
  connected = true;
  await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
  const viewport = page.getByTestId("cad-viewport");
  await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
  await expect(viewport).toHaveAttribute("data-viewer-preparing", "false");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(viewport).toHaveAttribute("data-viewer-preparing", "false");
  await expect.poll(() => geometryCredentials.length).toBeGreaterThanOrEqual(2);
  expect(geometryCredentials.every((credential) => credential === `Bearer ${token}`)).toBe(true);
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("authenticated-geometry.png") });
});
