import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // The per-mesh time budget in the test *is* the assertion, so the runner
    // must never be the thing that cuts a case short: this sits above the
    // largest of those budgets (90 s, the hammer holder's 70k-triangle
    // export).
    testTimeout: 180_000,
    hookTimeout: 180_000,
  },
});
