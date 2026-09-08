import { describe, expect, it } from "vitest";
import { createWorkspaceStore } from "./store";
import type { Job } from "./types";

function job(): Job {
  return {
    id: "reconstruct-1",
    projectId: "p",
    kind: "reconstruct",
    status: "running",
    progress: 40,
    phase: "fit surfaces",
    inputRevision: 1,
    attempt: 1,
    maxAttempts: 1,
    createdAt: "2026-09-05T00:00:00Z",
    startedAt: "2026-09-05T00:00:01Z",
    heartbeatAt: null,
    finishedAt: null,
    eventsUrl: "/api/jobs/demo/events",
    cancelRequestedAt: null,
    error: null,
    result: null,
  };
}

describe("failed job events", () => {
  it("keeps the failure explanation on the job so the footer can show it after the stream closes", () => {
    const store = createWorkspaceStore();
    store.getState().setJob(job(), "open");
    store.getState().applyJobEvent("reconstruct", {
      jobId: "reconstruct-1",
      type: "failed",
      phase: "fit surfaces",
      progress: null,
      level: "error",
      message: "No single extrusion axis covers the side walls.",
      detail: "Best axis covered 61%.",
      code: "no_extrusion_axis",
      timestamp: "2026-09-05T00:00:09Z",
      recoverable: true,
      recommendedAction: "Generate a curved STEP instead.",
    });
    const view = store.getState().jobs.reconstruct;
    expect(view?.job.status).toBe("failed");
    expect(view?.job.error).toEqual({
      code: "no_extrusion_axis",
      summary: "No single extrusion axis covers the side walls.",
      detail: "Best axis covered 61%.",
      phase: "fit surfaces",
      projectId: "p",
      jobId: "reconstruct-1",
      recoverable: true,
      recommendedAction: "Generate a curved STEP instead.",
    });
  });

  it("does not overwrite an explanation that a snapshot already provided", () => {
    const store = createWorkspaceStore();
    const snapshot = { ...job(), error: { code: "kept", summary: "Kept", detail: null, phase: "x", projectId: "p", jobId: "reconstruct-1", recoverable: false, recommendedAction: null } };
    store.getState().setJob(snapshot, "open");
    store.getState().applyJobEvent("reconstruct", {
      jobId: "reconstruct-1", type: "failed", phase: "x", progress: null, level: "error", message: "Other", code: "other", timestamp: "2026-09-05T00:00:09Z",
    });
    expect(store.getState().jobs.reconstruct?.job.error?.code).toBe("kept");
  });
});
