import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { JobKind, JobViewState } from "../state/types";
import { JobFailure, latestFailedJob, retryOperation } from "./JobFailure";

function view(kind: JobKind, status: JobViewState["job"]["status"], finishedAt: string | null, error: JobViewState["job"]["error"] = null): JobViewState {
  return {
    job: {
      id: `${kind}-1`,
      projectId: "p",
      kind,
      status,
      progress: 40,
      phase: "fit surfaces",
      inputRevision: 1,
      attempt: 1,
      maxAttempts: 1,
      createdAt: "2026-09-05T00:00:00Z",
      startedAt: "2026-09-05T00:00:01Z",
      heartbeatAt: null,
      finishedAt,
      eventsUrl: "/api/jobs/demo/events",
      cancelRequestedAt: null,
      error,
      result: null,
    },
    connection: "closed",
    logs: [],
    cancelling: false,
    lastEventAt: finishedAt,
  };
}

afterEach(cleanup);

describe("latestFailedJob", () => {
  it("returns the most recently finished failed job and ignores the rest", () => {
    const jobs = {
      analyze: view("analyze", "failed", "2026-09-05T00:01:00Z"),
      reconstruct: view("reconstruct", "failed", "2026-09-05T00:03:00Z"),
      validate: view("validate", "completed", "2026-09-05T00:05:00Z"),
    };
    expect(latestFailedJob(jobs)?.job.kind).toBe("reconstruct");
    expect(latestFailedJob({ validate: jobs.validate })).toBeNull();
    expect(latestFailedJob({})).toBeNull();
  });
});

describe("retryOperation", () => {
  it("maps only the operations the workspace can re-run", () => {
    expect(retryOperation("analyze")).toBe("analyze");
    expect(retryOperation("export")).toBe("export");
    expect(retryOperation("sample_open")).toBeNull();
    expect(retryOperation("upload")).toBeNull();
  });
});

describe("JobFailure", () => {
  it("shows the worker's explanation and uses its recommended action as the retry button", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(
      <JobFailure
        view={view("reconstruct", "failed", "2026-09-05T00:03:00Z", {
          code: "no_extrusion_axis",
          summary: "No single extrusion axis was found.",
          detail: "Best axis covered 61% of side walls; 98% is required.",
          phase: "fit surfaces",
          projectId: "p",
          jobId: "reconstruct-1",
          recoverable: true,
          recommendedAction: "Generate a curved STEP instead.",
        })}
        canRetry
        onRetry={onRetry}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByRole("region", { name: "Job failure" })).toBeTruthy();
    expect(screen.getByText("No single extrusion axis was found.")).toBeTruthy();
    expect(screen.queryByText(/61% of side walls/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText(/61% of side walls/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Generate a curved STEP instead." }));
    expect(onRetry).toHaveBeenCalledWith("reconstruct");
    await user.click(screen.getByRole("button", { name: "Dismiss job failure" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("falls back to an honest generic summary and a plain retry when the worker gave none", () => {
    render(<JobFailure view={view("analyze", "failed", null)} canRetry={false} onRetry={() => {}} onDismiss={() => {}} />);
    expect(screen.getAllByText("Analyze failed").length).toBeGreaterThan(0);
    const retry = screen.getByRole("button", { name: "Retry analyze" });
    expect(retry).toBeDisabled();
  });

  it("offers no retry for operations the workspace cannot re-run", () => {
    render(
      <JobFailure
        view={view("sample_open", "failed", null, {
          code: "x", summary: "Sample unavailable", detail: null, phase: "open", projectId: "p", jobId: "j", recoverable: false, recommendedAction: "Pick another sample.",
        })}
        canRetry
        onRetry={() => {}}
        onDismiss={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /Pick another sample/ })).toBeNull();
    expect(screen.getByText("Pick another sample.")).toBeTruthy();
    expect(screen.getByText(/not recoverable by retrying/)).toBeTruthy();
  });
});
