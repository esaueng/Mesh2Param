import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { perfBudgetMs } from "./support/perfBudget";

interface GlbAccessor {
  componentType: number;
  count: number;
  min?: number[];
  max?: number[];
  normalized?: boolean;
}

interface GlbDocument {
  accessors: GlbAccessor[];
  extensionsRequired?: string[];
  meshes: Array<{
    primitives: Array<{
      attributes: { NORMAL?: number; POSITION: number };
      indices: number;
      mode?: number;
      extras?: { mesh2paramAnalyticEdges?: boolean };
    }>;
  }>;
  nodes: Array<{ scale?: number[]; translation?: number[] }>;
}

// Same scene-build gate as viewer-scene-build.spec.ts, scaled for the GPU-less
// CI runner. See docs/viewer-performance.md.
const SCENE_BUILD_BUDGET_MS = perfBudgetMs(100);

const CYLINDER_SAMPLES = [
  { id: "spacer", diameter: 24, maxGlbBytes: 100_000 },
  { id: "shaft-collar", diameter: 36, maxGlbBytes: 230_000 },
  { id: "flange", diameter: 70, maxGlbBytes: 420_000 },
] as const;

async function selectOnlySample(page: Page, sampleId: string) {
  await page.route("**/api/samples", async (route) => {
    const response = await route.fetch();
    const envelope = await response.json() as {
      data: { items: Array<{ id: string }>; total: number };
    };
    const selected = envelope.data.items.find((item) => item.id === sampleId);
    expect(selected, `sample catalog should contain ${sampleId}`).toBeDefined();
    envelope.data.items = [selected!];
    envelope.data.total = 1;
    await route.fulfill({ response, json: envelope });
  });
}

function parseGlb(payload: Buffer): GlbDocument {
  expect(payload.readUInt32LE(0)).toBe(0x46546c67);
  const jsonLength = payload.readUInt32LE(12);
  return JSON.parse(payload.subarray(20, 20 + jsonLength).toString("utf8").trim()) as GlbDocument;
}

async function assertDisplayArtifact(
  page: Page,
  expectedDiameter: number,
  maxGlbBytes: number,
) {
  const projectId = await page.evaluate(() => sessionStorage.getItem("mesh2param-active-project"));
  expect(projectId).not.toBeNull();
  const artifactsResponse = await page.request.get(`/api/projects/${projectId!}/artifacts`);
  expect(artifactsResponse.ok()).toBe(true);
  const artifacts = await artifactsResponse.json() as {
    data: { items: Array<{ name: string; sha256: string }> };
  };
  const result = artifacts.data.items.find((artifact) => artifact.name === "reconstructed.glb");
  expect(result).toBeDefined();
  const resultResponse = await page.request.get(
    `/api/projects/${projectId!}/artifacts/reconstructed.glb?sha256=${result!.sha256}`,
  );
  expect(resultResponse.ok()).toBe(true);
  const payload = await resultResponse.body();
  expect(payload.byteLength).toBeLessThan(maxGlbBytes);
  const document = parseGlb(payload);
  const primitives = document.meshes[0]!.primitives;
  const surface = primitives.find((primitive) => (primitive.mode ?? 4) === 4);
  const edges = primitives.find((primitive) => primitive.mode === 1);

  expect(surface).toBeDefined();
  expect(edges).toMatchObject({
    mode: 1,
    extras: { mesh2paramAnalyticEdges: true },
  });
  expect(document.extensionsRequired).toEqual(["KHR_mesh_quantization"]);
  expect(document.accessors[surface!.attributes.POSITION]).toMatchObject({
    componentType: 5123,
    normalized: true,
  });
  expect(document.accessors[edges!.attributes.POSITION]).toMatchObject({
    componentType: 5123,
    normalized: true,
  });
  expect(document.accessors[surface!.indices]!.count / 3).toBeGreaterThan(2_000);
  expect(document.accessors[edges!.indices]!.count / 2).toBeGreaterThan(700);
  const surfacePositions = document.accessors[surface!.attributes.POSITION]!;
  const decodedXSpan = (
    surfacePositions.max![0]! - surfacePositions.min![0]!
  ) / 0xffff * document.nodes[0]!.scale![0]!;
  expect(decodedXSpan).toBeCloseTo(expectedDiameter, 3);
}

async function assertNormalAndCloseRender(
  page: Page,
  testInfo: TestInfo,
  sampleId: string,
) {
  const viewport = page.getByTestId("cad-viewport");
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("mesh2param:view-preset", { detail: "top" }));
  });
  await expect(viewport).toHaveAttribute("data-camera-view", "top");
  const normal = await viewport.screenshot();
  await testInfo.attach(`${sampleId}-normal.png`, { body: normal, contentType: "image/png" });

  const canvas = viewport.locator("canvas").first();
  await canvas.hover();
  await page.mouse.wheel(0, -2_400);
  await page.waitForTimeout(300);
  const close = await viewport.screenshot();
  await testInfo.attach(`${sampleId}-close.png`, { body: close, contentType: "image/png" });
  expect(close.equals(normal), "close zoom should render a distinct frame").toBe(false);

  const analyticSegmentCounts = await page.evaluate(() =>
    performance.getEntriesByName("mesh2param:analytic-edge-overlay", "mark")
      .map((entry) => (entry as PerformanceMark).detail as { segmentCount?: number })
      .map((detail) => detail.segmentCount ?? 0));
  expect(Math.max(...analyticSegmentCounts)).toBeGreaterThan(700);
  const sceneBuilds = await page.evaluate(() =>
    performance.getEntriesByName("mesh2param:artifact-build", "measure")
      .map((entry) => entry.duration));
  expect(sceneBuilds.length).toBeGreaterThan(0);
  expect(Math.max(...sceneBuilds)).toBeLessThan(SCENE_BUILD_BUDGET_MS);
}

test("exact cylinders stay smooth across diameters at normal and close zoom", async ({
  context,
}, testInfo) => {
  for (const sample of CYLINDER_SAMPLES) {
    const page = await context.newPage();
    await selectOnlySample(page, sample.id);
    await page.goto("/");
    await expect(page.getByTestId("start-screen")).toBeVisible();
    await page.getByRole("button", { name: /Try the L-bracket sample/i }).click();
    await expect(page.locator(".dock-primary")).toContainText("Download STEP", { timeout: 240_000 });
    await expect(page.getByTestId("cad-viewport"))
      .toHaveAttribute("data-viewer-preparing", "false", { timeout: 60_000 });
    await assertDisplayArtifact(page, sample.diameter, sample.maxGlbBytes);
    await assertNormalAndCloseRender(page, testInfo, sample.id);
    await page.close();
  }
});
