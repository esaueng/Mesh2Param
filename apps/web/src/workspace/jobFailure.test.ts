import { describe, expect, it } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import baseGraphDocument from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import type { Job, JobEvent, ProjectWorkingDocument } from "../state/types";
import { failedStepStatus, formatJobFailure, formatJobSnapshotFailure } from "./jobFailure";

const failedEvent = {
  jobId: "job-1",
  type: "failed",
  phase: "coordinate-frame",
  progress: 42,
  level: "error",
  message: "Automatic reconstruction could not complete",
  detail: "dominant-plane frame requires at least six plane patches; found 3",
  code: "ambiguous-frame",
  timestamp: "2026-07-11T00:00:00Z",
} satisfies JobEvent;

describe("job failure presentation", () => {
  it("preserves a valid existing feature stage when new inference fails", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    graph.validation.brepValid = true;
    const working = { cadgraph: graph, validation: null } as unknown as ProjectWorkingDocument;
    expect(failedStepStatus("reconstruct", working)).toBe("complete");
    expect(formatJobFailure("reconstruct", failedEvent, working)).toBe(
      "Automatic reconstruction could not complete: dominant-plane frame requires at least six plane patches; found 3. Existing CADGraph preserved.",
    );
  });

  it("still reports other failed stages as failed", () => {
    const working = { cadgraph: null, validation: null } as unknown as ProjectWorkingDocument;
    expect(failedStepStatus("analyze", working)).toBe("failed");
    expect(formatJobFailure("analyze", failedEvent, working)).not.toMatch(/preserved/i);
  });

  it("includes the worker's recommended recovery action", () => {
    const working = { cadgraph: null, validation: null } as unknown as ProjectWorkingDocument;
    expect(formatJobFailure("reconstruct", {
      ...failedEvent,
      recommendedAction: "Use the explicit faceted STEP fallback.",
    }, working)).toMatch(/Use the explicit faceted STEP fallback\.$/);
  });

  it("uses authoritative detail when a reconnect returns a failed snapshot", () => {
    const graph = structuredClone(baseGraphDocument) as unknown as CADGraph;
    graph.validation.brepValid = true;
    const working = { cadgraph: graph, validation: null } as unknown as ProjectWorkingDocument;
    const snapshot = {
      kind: "reconstruct",
      status: "failed",
      error: {
        summary: "Automatic reconstruction could not complete",
        detail: "dominant-plane frame requires at least six plane patches; found 3",
      },
    } as unknown as Job;
    expect(formatJobSnapshotFailure(snapshot, working)).toMatch(
      /found 3\. Existing CADGraph preserved\.$/,
    );
  });
});
