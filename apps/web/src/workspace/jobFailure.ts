import type { Job, JobEvent, JobKind, ProjectWorkingDocument, StepStatus } from "../state/types";

function preservesValidCadgraph(kind: JobKind, working: ProjectWorkingDocument | null): boolean {
  if (kind !== "reconstruct" || working?.cadgraph === null || working?.cadgraph === undefined) return false;
  return working.cadgraph.validation.brepValid === true || working.validation?.brepValid === true;
}

export function failedStepStatus(kind: JobKind, working: ProjectWorkingDocument | null): StepStatus {
  return preservesValidCadgraph(kind, working) ? "complete" : "failed";
}

export function formatJobFailure(
  kind: JobKind,
  event: Pick<JobEvent, "message" | "detail" | "recommendedAction">,
  working: ProjectWorkingDocument | null,
): string {
  const summary = event.message ?? `${kind} failed`;
  const core = event.detail === undefined || event.detail === null || event.detail === summary
    ? summary
    : `${summary}: ${event.detail}`;
  const action = event.recommendedAction?.trim();
  const actionable = action === undefined || action === "" || core.includes(action)
    ? core
    : `${core}${/[.!?]$/.test(core) ? "" : "."} ${action}`;
  if (!preservesValidCadgraph(kind, working)) return actionable;
  const punctuation = /[.!?]$/.test(actionable) ? "" : ".";
  return `${actionable}${punctuation} Existing CADGraph preserved.`;
}

export function formatJobSnapshotFailure(
  snapshot: Job,
  working: ProjectWorkingDocument | null,
): string {
  return formatJobFailure(snapshot.kind, {
    message: snapshot.error?.summary ?? `${snapshot.kind} failed`,
    detail: snapshot.error?.detail ?? null,
    recommendedAction: snapshot.error?.recommendedAction ?? null,
  }, working);
}
