import { Check, Circle, LoaderCircle, X } from "lucide-react";
import type { JobViewState } from "../state/types";

export function TechnicalRows({ rows }: { rows: Array<[string, string | number | boolean | null | undefined]> }) {
  return <dl className="technical-rows">{rows.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value === null || value === undefined ? "—" : typeof value === "boolean" ? (value ? "Yes" : "No") : value}</dd></div>)}</dl>;
}

export function JobProgress({ state, onCancel }: { state: JobViewState; onCancel(): void }) {
  const { job } = state;
  const complete = job.status === "completed";
  const failed = job.status === "failed";
  return <section className="job-progress" data-job-kind={job.kind} data-job-state={job.status} aria-label={`${job.kind} job`} aria-live="polite">
    <div className="job-title">{complete ? <Check/> : failed ? <X/> : <LoaderCircle className="spin"/>}<strong>{humanPhase(job.phase)}</strong><span>{Math.round(job.progress)}%</span></div>
    <div className="progress-track" role="progressbar" aria-label={`${job.kind} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}><span style={{width:`${job.progress}%`}}/></div>
    <div className="job-meta"><span>{state.connection === "reconnecting" ? "Reconnecting" : job.status}</span>{job.status === "running" || job.status === "queued" ? <button onClick={onCancel} disabled={state.cancelling}>{state.cancelling ? "Cancelling…" : "Cancel"}</button> : null}</div>
    <ol className="job-timeline">{[...state.logs.slice(-8)].reverse().map((log,index) => <li key={`${log.timestamp}-${index}`}>{log.level === "error" ? <X/> : log.phase === job.phase && !complete ? <Circle/> : <Check/>}<time>{new Date(log.timestamp).toLocaleTimeString([], {hour12:false})}</time><span>{log.message}</span></li>)}</ol>
    {job.error ? <p className="inline-error" role="alert"><strong>{job.error.summary}</strong>{job.error.detail}{job.error.recommendedAction ? ` ${job.error.recommendedAction}` : ""}</p> : null}
  </section>;
}

export function humanPhase(value: string): string { return value.split(/[-_ ]+/).filter(Boolean).map(word => word[0]?.toUpperCase()+word.slice(1)).join(" "); }
