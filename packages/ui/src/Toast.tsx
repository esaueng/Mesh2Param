import { X } from "lucide-react";
import type { ReactNode } from "react";

export type ToastTone = "info" | "success" | "warning" | "error";

export interface ToastProps {
  tone?: ToastTone;
  message: ReactNode;
  action?: ReactNode;
  onDismiss?(): void;
  className?: string;
}

export function Toast({ tone = "info", message, action, onDismiss, className = "" }: ToastProps) {
  return (
    <div className={`ui-toast ui-toast--${tone} ${className}`.trim()} role={tone === "error" ? "alert" : "status"}>
      <span className="ui-toast__message">{message}</span>
      {action}
      {onDismiss === undefined ? null : (
        <button type="button" className="ui-toast__dismiss" onClick={onDismiss} aria-label="Dismiss notification">
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}
