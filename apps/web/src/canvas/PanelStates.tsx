import type { ReactNode } from "react";

/**
 * Designed empty state for a panel region: a glyph, a one-line title, a
 * hint that says what would fill the region, and at most one action. The
 * copy states what has not happened yet rather than dressing it up.
 */
export function EmptyState({
  icon,
  title,
  hint,
  action,
  testId,
}: {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: { label: string; onClick(): void; disabled?: boolean; title?: string };
  testId?: string;
}) {
  return (
    <div className="panel-empty" data-testid={testId}>
      <span className="panel-empty-icon" aria-hidden>{icon}</span>
      <strong>{title}</strong>
      {hint !== undefined ? <p>{hint}</p> : null}
      {action !== undefined ? (
        <button type="button" className="panel-btn" onClick={action.onClick} disabled={action.disabled} title={action.title}>
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

/**
 * Placeholder rows while a job is producing what a region will show. Purely
 * decorative: the section carries aria-busy and the progress bar is the
 * announced status, so the skeleton itself is hidden from assistive tech.
 */
export function PanelSkeleton({ rows = 4, label }: { rows?: number; label?: string }) {
  return (
    <div className="panel-skeleton" aria-hidden data-testid="panel-skeleton">
      {label !== undefined ? <span className="panel-skeleton-label">{label}</span> : null}
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className="panel-skeleton-row" style={{ width: `${[92, 68, 84, 58, 76, 64][index % 6]}%` }} />
      ))}
    </div>
  );
}
