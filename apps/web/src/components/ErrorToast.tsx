import { useEffect } from "react";
import { X } from "lucide-react";

export const ERROR_TOAST_DURATION_MS = 8_000;

export interface ErrorToastProps {
  message: string;
  onDismiss(): void;
  durationMs?: number;
}

export function ErrorToast({
  message,
  onDismiss,
  durationMs = ERROR_TOAST_DURATION_MS,
}: ErrorToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, message, onDismiss]);

  return (
    <div className="global-error" role="alert">
      <span>{message}</span>
      <button type="button" onClick={onDismiss} aria-label="Dismiss error">
        <X size={15} aria-hidden />
      </button>
    </div>
  );
}
