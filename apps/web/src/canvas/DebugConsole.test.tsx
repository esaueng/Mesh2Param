import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clampConsoleHeight, CONSOLE_HEIGHT, DebugConsole } from "./DebugConsole";
import { debugLog } from "./debugLog";

beforeEach(() => {
  debugLog.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "debug").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  debugLog.clear();
});

function renderConsole(overrides: Partial<Parameters<typeof DebugConsole>[0]> = {}) {
  const props = {
    docked: true,
    height: 220,
    onDockedChange: vi.fn(),
    onHeightChange: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<DebugConsole {...props} />);
  return props;
}

describe("DebugConsole", () => {
  it("filters entries by severity with additive chips", async () => {
    const user = userEvent.setup();
    debugLog.error("export", "Download failed");
    debugLog.warn("pipeline", "Analyze unavailable");
    debugLog.info("export", "Downloaded model.step");
    debugLog.debug("view", "Display mode -> shaded");
    renderConsole();

    const log = screen.getByRole("log", { name: "Log entries" });
    expect(within(log).getAllByText(/failed|unavailable|Downloaded|Display mode/).length).toBe(4);

    const filters = screen.getByRole("group", { name: "Severity filter" });
    await user.click(within(filters).getByRole("button", { name: /^Info/ }));
    await user.click(within(filters).getByRole("button", { name: /^Debug/ }));

    expect(within(log).queryByText("Downloaded model.step")).toBeNull();
    expect(within(log).queryByText("Display mode -> shaded")).toBeNull();
    expect(within(log).getByText("Download failed")).toBeTruthy();
    expect(within(log).getByText("Analyze unavailable")).toBeTruthy();
    expect(within(filters).getByRole("button", { name: /^Info/ }).getAttribute("aria-pressed")).toBe("false");

    await user.click(within(filters).getByRole("button", { name: "All" }));
    expect(within(log).getByText("Downloaded model.step")).toBeTruthy();
  });

  it("explains an empty view differently for no entries and a filter that hides them all", async () => {
    const user = userEvent.setup();
    renderConsole();
    expect(screen.getByText("No log entries yet.")).toBeTruthy();

    debugLog.info("view", "hello");
    await user.click(screen.getByRole("button", { name: /^Info/ }));
    expect(screen.getByText("No entries match the severity filter.")).toBeTruthy();
  });

  it("toggles docking and closes through its controls", async () => {
    const user = userEvent.setup();
    const props = renderConsole({ docked: true });
    await user.click(screen.getByRole("button", { name: "Float console over the viewport" }));
    expect(props.onDockedChange).toHaveBeenCalledWith(false);
    await user.click(screen.getByRole("button", { name: "Close console" }));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("resizes from the keyboard and clamps the height", () => {
    const props = renderConsole({ height: CONSOLE_HEIGHT.min });
    const handle = screen.getByRole("separator", { name: "Resize console" });
    fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(props.onHeightChange).toHaveBeenLastCalledWith(CONSOLE_HEIGHT.min + CONSOLE_HEIGHT.step);
    fireEvent.keyDown(handle, { key: "ArrowDown" });
    expect(props.onHeightChange).toHaveBeenLastCalledWith(CONSOLE_HEIGHT.min);
    expect(clampConsoleHeight(5)).toBe(CONSOLE_HEIGHT.min);
    expect(clampConsoleHeight(5_000)).toBe(CONSOLE_HEIGHT.max);
    expect(clampConsoleHeight(Number.NaN)).toBe(220);
  });
});
