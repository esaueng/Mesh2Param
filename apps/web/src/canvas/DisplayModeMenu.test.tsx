import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DisplayModeMenu } from "./DisplayModeMenu";

afterEach(cleanup);

describe("DisplayModeMenu", () => {
  it("selects a display material and exposes the selected state", async () => {
    const user = userEvent.setup();
    const onPreferences = vi.fn();
    render(<DisplayModeMenu shading="shaded" edges theme="dark" onPreferences={onPreferences} />);

    await user.click(screen.getByRole("button", { name: "Display settings" }));
    expect(screen.getByRole("menuitemradio", { name: /Shaded/ })).toHaveAttribute("aria-checked", "true");

    await user.click(screen.getByRole("menuitemradio", { name: /X-Ray/ }));
    expect(onPreferences).toHaveBeenCalledWith({ shading: "xray" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("toggles edge visibility without closing the menu", async () => {
    const user = userEvent.setup();
    const onPreferences = vi.fn();
    render(<DisplayModeMenu shading="shaded" edges={false} theme="dark" onPreferences={onPreferences} />);

    await user.click(screen.getByRole("button", { name: "Display settings" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Show edges" }));

    expect(onPreferences).toHaveBeenCalledWith({ edges: true });
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });
});
