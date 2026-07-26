import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

afterEach(cleanup);

function Harness({ onClose, dismissOnBackdrop }: { onClose?(): void; dismissOnBackdrop?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Shortcuts</button>
      <button type="button">Replace mesh…</button>
      {open ? (
        <Modal
          labelledBy="harness-title"
          dismissOnBackdrop={dismissOnBackdrop ?? true}
          onClose={() => { setOpen(false); onClose?.(); }}
        >
          <section>
            <h2 id="harness-title">Keyboard shortcuts</h2>
            <button autoFocus type="button" aria-label="Close keyboard shortcuts">×</button>
          </section>
        </Modal>
      ) : null}
    </>
  );
}

describe("Modal", () => {
  it("opens as a modal dialog named by its heading", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Shortcuts" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAccessibleName("Keyboard shortcuts");
  });

  it("moves initial focus into the dialog", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Shortcuts" }));

    expect(screen.getByRole("button", { name: "Close keyboard shortcuts" })).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Shortcuts" }));

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("restores focus to the trigger after closing", async () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Shortcuts" });
    await userEvent.click(trigger);
    await userEvent.keyboard("{Escape}");

    expect(trigger).toHaveFocus();
  });

  it("closes when the scrim outside the panel is pressed", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Shortcuts" }));

    await userEvent.click(screen.getByRole("dialog"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores scrim presses when backdrop dismissal is disabled", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} dismissOnBackdrop={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Shortcuts" }));

    await userEvent.click(screen.getByRole("dialog"));

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("does not report a close when it unmounts for an unrelated reason", () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <Modal labelledBy="unmount-title" onClose={onClose}>
        <h2 id="unmount-title">Keyboard shortcuts</h2>
      </Modal>,
    );

    unmount();

    expect(onClose).not.toHaveBeenCalled();
  });
});
