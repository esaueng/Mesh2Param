import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EditableProjectName } from "./EditableProjectName";

afterEach(cleanup);

describe("EditableProjectName", () => {
  it("commits a trimmed file name with Enter", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockResolvedValue(undefined);
    render(<EditableProjectName value="Bracket model" onCommit={onCommit} />);

    await user.click(screen.getByRole("button", { name: "Bracket model" }));
    const input = screen.getByRole("textbox", { name: "File name" });
    await user.clear(input);
    await user.type(input, "  Revised bracket.stl  {Enter}");

    expect(onCommit).toHaveBeenCalledWith("Revised bracket.stl");
    expect(screen.getByRole("button", { name: "Bracket model" })).toBeVisible();
  });

  it("commits on blur and cancels empty or escaped edits", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockResolvedValue(undefined);
    render(<EditableProjectName value="Bracket model" onCommit={onCommit} />);

    await user.click(screen.getByRole("button", { name: "Bracket model" }));
    await user.clear(screen.getByRole("textbox", { name: "File name" }));
    await user.tab();
    expect(onCommit).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Bracket model" }));
    await user.clear(screen.getByRole("textbox", { name: "File name" }));
    await user.type(screen.getByRole("textbox", { name: "File name" }), "Fixture plate");
    await user.tab();
    expect(onCommit).toHaveBeenCalledWith("Fixture plate");

    await user.click(screen.getByRole("button", { name: "Bracket model" }));
    await user.type(screen.getByRole("textbox", { name: "File name" }), " ignored{Escape}");
    expect(onCommit).toHaveBeenCalledTimes(1);
  });
});
