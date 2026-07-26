/**
 * jsdom 29 ships `<dialog>` markup but not its modal behaviour: `showModal`,
 * `close`, and the Escape close request are all absent. Components built on the
 * native element would throw here, so the pieces our tests depend on are
 * installed once per suite.
 *
 * This deliberately does NOT emulate focus containment or background inertness
 * — jsdom has no top layer, so those cannot be faked convincingly. They are
 * covered against a real browser in tests/browser/accessibility.spec.ts.
 */
export function installDialogPolyfill(): void {
  const proto = globalThis.HTMLDialogElement?.prototype;
  if (proto === undefined || typeof proto.showModal === "function") return;

  const openDialogs = new Set<HTMLDialogElement>();

  proto.showModal = function showModal(this: HTMLDialogElement) {
    if (this.open) return;
    this.setAttribute("open", "");
    openDialogs.add(this);
    const autofocus = this.querySelector<HTMLElement>("[autofocus]");
    (autofocus ?? focusableIn(this))?.focus();
  };

  proto.show = function show(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };

  proto.close = function close(this: HTMLDialogElement, returnValue?: string) {
    if (!this.open) return;
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.removeAttribute("open");
    openDialogs.delete(this);
    this.dispatchEvent(new Event("close"));
  };

  // Escape is a "close request" on the topmost modal dialog: `cancel` first,
  // and unless that is cancelled, the dialog closes.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const topmost = [...openDialogs].pop();
    if (topmost === undefined) return;
    const cancel = new Event("cancel", { cancelable: true });
    if (topmost.dispatchEvent(cancel)) topmost.close();
  });
}

function focusableIn(root: HTMLElement): HTMLElement | null {
  return root.querySelector<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
}
