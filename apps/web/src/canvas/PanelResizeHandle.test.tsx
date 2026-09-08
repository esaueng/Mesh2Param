import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { clampPanelWidth, PANEL_LAYOUT_KEY, PANEL_WIDTH, panelLayoutStore } from "./panelLayout";
import { PanelResizeHandle } from "./PanelResizeHandle";

beforeEach(() => {
  localStorage.removeItem(PANEL_LAYOUT_KEY);
  panelLayoutStore.reload();
});
afterEach(() => {
  cleanup();
  localStorage.removeItem(PANEL_LAYOUT_KEY);
  panelLayoutStore.reload();
});

describe("PanelResizeHandle", () => {
  it("exposes the width as a separator value and steps it from the keyboard", () => {
    render(<PanelResizeHandle />);
    const handle = screen.getByRole("separator", { name: "Resize command panel" });
    expect(handle.getAttribute("aria-valuenow")).toBe(String(PANEL_WIDTH.default));

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default + PANEL_WIDTH.step);
    fireEvent.keyDown(handle, { key: "ArrowRight", shiftKey: true });
    expect(panelLayoutStore.snapshot().width).toBe(clampPanelWidth(PANEL_WIDTH.default + PANEL_WIDTH.step - PANEL_WIDTH.step * 4));
    fireEvent.keyDown(handle, { key: "End" });
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.min);
    fireEvent.keyDown(handle, { key: "Enter" });
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default);
    expect(handle.getAttribute("aria-valuenow")).toBe(String(PANEL_WIDTH.default));
  });

  it("widens the panel when dragged towards the viewport", () => {
    render(<PanelResizeHandle />);
    const handle = screen.getByRole("separator", { name: "Resize command panel" });
    // jsdom has no pointer capture; the handle must tolerate that.
    handle.setPointerCapture = () => {};
    handle.hasPointerCapture = () => false;
    fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientX: 1000 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 940 });
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default + 60);
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: 940 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 500 });
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default + 60);
  });

  it("resets on double click", () => {
    panelLayoutStore.setWidth(PANEL_WIDTH.max);
    render(<PanelResizeHandle />);
    fireEvent.doubleClick(screen.getByRole("separator", { name: "Resize command panel" }));
    expect(panelLayoutStore.snapshot().width).toBe(PANEL_WIDTH.default);
  });
});
