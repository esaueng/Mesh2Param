import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // The hammer holder is a 30k-triangle reconstruction; the assertion that it
    // finishes inside 30 s is the test, so the runner must not cut it short
    // first.
    testTimeout: 120_000,
    hookTimeout: 120_000,
  },
});
