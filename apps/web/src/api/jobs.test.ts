import { describe, expect, it } from "vitest";
import { parseJobEvent } from "./jobs";

describe("parseJobEvent", () => {
  it("preserves actionable terminal failure detail", () => {
    const event = parseJobEvent({
      jobId: "job-1",
      type: "failed",
      phase: "coordinate-frame",
      progress: 42,
      level: "error",
      message: "Automatic reconstruction could not complete",
      detail: "dominant-plane frame requires at least six plane patches; found 3",
      code: "ambiguous-frame",
      timestamp: "2026-07-11T00:00:00Z",
    });
    expect(event.detail).toBe("dominant-plane frame requires at least six plane patches; found 3");
  });
});
