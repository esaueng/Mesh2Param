import { useState } from "react";
import { AlertOctagon, ChevronDown, RotateCcw, X } from "lucide-react";
import type { JobKind, JobViewState } from "../state/types";
import { humanPhase } from "./pipeline";

/** The operations the workspace can re-run directly; the rest have no single retry. */
const RETRYABLE: ReadonlySet<string> = new Set(["repair", "analyze", "reconstruct", "rebuild", "validate", "export"]);
export type RetryableOperation = "repair" | "analyze" | "reconstruct" | "rebuild" | "validate" | "export";

export function retryOperation(kind: JobKind): RetryableOperation | null {
  return RETRYABLE.has(kind) ? (kind as RetryableOperation) : null;
}

/** The most recently finished failed job, if any; the one the footer should explain. */
export function latestFailedJob(jobs: Partial<Record<JobKind, JobViewState>>): JobViewState | null {
  let latest: JobViewState | null = null;
  for (const view of Object.values(jobs)) {
    if (view === undefined || view.job.status !== "failed") continue;
    const stamp = view.job.finishedAt ?? view.lastEventAt ?? view.job.createdAt;
    const best = latest === null ? null : (latest.job.finishedAt ?? latest.lastEventAt ?? latest.job.createdAt);
    if (best === null || stamp > best) latest = view;
  }
  return latest;
}

export interface JobFailureProps {
  view: JobViewState;
  /** Whether a retry can be queued right now (worker ready, nothing running). */
  canRetry: boolean;
  onRetry(operation: RetryableOperation): void;
  onDismiss(): void;
}

/**
 * The honest failure surface: what failed, in which phase, the worker's own
 * explanation, and its recommended action as the button that performs the
 * only recovery the UI can offer, re-running the operation. Nothing here is
 * inferred; a job without an explanation says so.
 */
export function JobFailure({ view, canRetry, onRetry, onDismiss }: JobFailureProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const { job } = view;
  const error = job.error;
  const summary = error?.summary?.trim() || `${humanPhase(job.kind)} failed`;
  const detail = error?.detail?.trim();
  const action = error?.recommendedAction?.trim();
  const operation = retryOperation(job.kind);
  const phase = job.phase.trim();
  return (
    <section className="job-failure" aria-label="Job failure" data-testid="job-failure" data-job-kind={job.kind}>
      <header className="job-failure-head">
        <AlertOctagon size={15} aria-hidden />
        <div className="job-failure-copy">
          <strong>{humanPhase(job.kind)} failed{phase !== "" && phase !== job.kind ? ` · ${humanPhase(phase)}` : ""}</strong>
          <p>{summary}</p>
          {error?.recoverable === false ? <p className="job-failure-note">The worker reports this failure as not recoverable by retrying.</p> : null}
        </div>
        <button type="button" className="job-failure-close" onClick={onDismiss} aria-label="Dismiss job failure"><X size={14} aria-hidden /></button>
      </header>
      {detail !== undefined && detail !== "" && detail !== summary ? (
        <div className="job-failure-detail">
          <button type="button" className="job-failure-detail-toggle" aria-expanded={detailOpen} onClick={() => setDetailOpen((open) => !open)}>
            <ChevronDown size={13} aria-hidden className={detailOpen ? "open" : ""} />
            Details
          </button>
          {detailOpen ? <pre>{detail}</pre> : null}
        </div>
      ) : null}
      <div className="job-failure-actions">
        {operation !== null ? (
          <button
            type="button"
            className="panel-btn job-failure-retry"
            disabled={!canRetry}
            title={canRetry ? `Re-run ${humanPhase(job.kind).toLowerCase()}` : "Wait for the worker and the running job"}
            onClick={() => onRetry(operation)}
          >
            <RotateCcw size={14} aria-hidden />
            {action !== undefined && action !== "" ? action : `Retry ${humanPhase(job.kind).toLowerCase()}`}
          </button>
        ) : action !== undefined && action !== "" ? (
          <p className="job-failure-hint">{action}</p>
        ) : null}
      </div>
    </section>
  );
}
