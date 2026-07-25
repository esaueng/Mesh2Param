import { useEffect, useRef, useState, type ReactNode } from "react";

interface ModalProps {
  /** Id of the element naming the dialog; becomes the dialog's accessible name. */
  labelledBy: string;
  /** Applied alongside `modal-surface`, which supplies the full-viewport scrim. */
  className?: string;
  /** Called for every dismissal route: Escape, the close control, backdrop click. */
  onClose(): void;
  /** Clicking the scrim outside the panel dismisses. Off for dialogs that must be answered. */
  dismissOnBackdrop?: boolean;
  children: ReactNode;
}

/**
 * Modal dialog built on the native `<dialog>` element, which supplies focus
 * containment, Escape dismissal, and an inert background from the platform
 * rather than from hand-rolled key handling. Focus restoration is ours: the
 * element is not restored reliably across browsers, so the activeElement at
 * mount is captured and refocused on unmount.
 */
export function Modal({ labelledBy, className, onClose, dismissOnBackdrop = true, children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  // Kept in a ref so the mount effect never re-runs when a parent re-renders
  // with a fresh closure; re-running it would reopen an already-open dialog.
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });
  // Captured during the first render, not in the effect below: React applies
  // `autoFocus` during commit, so by the time a passive effect runs the
  // activeElement is already inside the dialog and the trigger is lost.
  const [restore] = useState(() => (document.activeElement instanceof HTMLElement ? document.activeElement : null));

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    // `close` covers every native dismissal, including Escape (which fires
    // `cancel` first) and any programmatic close during unmount.
    const onNativeClose = () => closeRef.current();
    dialog.addEventListener("close", onNativeClose);
    if (!dialog.open) dialog.showModal();
    return () => {
      dialog.removeEventListener("close", onNativeClose);
      if (dialog.open) dialog.close();
      restore?.focus();
    };
  }, [restore]);

  return (
    <dialog
      ref={ref}
      className={className === undefined ? "modal-surface" : `modal-surface ${className}`}
      aria-labelledby={labelledBy}
      onMouseDown={(event) => {
        // The scrim is the dialog element itself; the panel is a child, so a
        // press landing on the dialog is a press outside the panel.
        if (dismissOnBackdrop && event.target === ref.current) onClose();
      }}
    >
      {children}
    </dialog>
  );
}
