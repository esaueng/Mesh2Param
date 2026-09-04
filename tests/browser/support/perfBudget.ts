/**
 * Scales a viewer performance budget for the machine the suite runs on.
 *
 * The budgets are written for a developer machine with a real GPU. GitHub's
 * ubuntu-24.04 runners have none: headless Chromium falls back to SwiftShader,
 * a CPU rasterizer that shares the main thread with the very JavaScript these
 * budgets measure, on top of shared vCPUs. docs/viewer-performance.md records
 * the measured spread — the same reveal that produces no long task on hardware
 * produces 600-1,000 ms of them under SwiftShader.
 *
 * Scaling rather than skipping keeps the gate real in both places: a regression
 * that doubles a scene build still fails on CI, and the tight local number
 * still catches it first. `MESH2PARAM_E2E_PERF_SCALE` is set by the browser
 * task in .github/workflows/ci.yml.
 */
export function perfBudgetMs(budgetMs: number): number {
  const raw = process.env.MESH2PARAM_E2E_PERF_SCALE ?? "1";
  const scale = Number(raw);
  if (!Number.isFinite(scale) || scale < 1) {
    throw new Error(`MESH2PARAM_E2E_PERF_SCALE must be a finite number >= 1, got ${raw}`);
  }
  return budgetMs * scale;
}
