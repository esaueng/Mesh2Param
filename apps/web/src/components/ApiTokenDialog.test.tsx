import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiTokenDialog } from "./ApiTokenDialog";

afterEach(cleanup);

describe("ApiTokenDialog", () => {
  it("opens as a modal dialog focused on the token field", () => {
    render(<ApiTokenDialog onClose={vi.fn()} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAccessibleName("Enter API token");
    expect(screen.getByLabelText("Bearer token")).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<ApiTokenDialog onClose={onClose} />);

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps the dialog open when the scrim is pressed", async () => {
    const onClose = vi.fn();
    render(<ApiTokenDialog onClose={onClose} />);

    await userEvent.click(screen.getByRole("dialog"));

    expect(onClose).not.toHaveBeenCalled();
  });
});
