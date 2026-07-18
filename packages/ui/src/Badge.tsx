import type { PropsWithChildren } from "react";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "error";

export function Badge({
  tone = "neutral",
  className = "",
  children,
}: PropsWithChildren<{ tone?: BadgeTone; className?: string }>) {
  return <span className={`ui-badge ui-badge--${tone} ${className}`.trim()}>{children}</span>;
}
