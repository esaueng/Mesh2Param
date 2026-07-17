import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ERROR_TOAST_DURATION_MS, ErrorToast } from "./ErrorToast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ErrorToast", () => {
  it("can be dismissed immediately", () => {
    const onDismiss = vi.fn();
    render(<ErrorToast message="Conversion failed" onDismiss={onDismiss} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Conversion failed");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss error" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("auto-dismisses and restarts the timer for a new message", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    const { rerender } = render(<ErrorToast message="First error" onDismiss={onDismiss} />);

    act(() => vi.advanceTimersByTime(ERROR_TOAST_DURATION_MS - 1_000));
    rerender(<ErrorToast message="Second error" onDismiss={onDismiss} />);
    act(() => vi.advanceTimersByTime(ERROR_TOAST_DURATION_MS - 1_000));
    expect(onDismiss).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1_000));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
