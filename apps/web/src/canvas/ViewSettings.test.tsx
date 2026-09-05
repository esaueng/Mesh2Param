import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewSettings } from "./ViewSettings";

afterEach(cleanup);

describe("ViewSettings", () => {
  it("keeps display materials visible and exposes the selected state", async () => {
    const user = userEvent.setup();
    const onPreferences = vi.fn();
    render(<ViewSettings shading="shaded" edges onPreferences={onPreferences} />);

    expect(screen.getByLabelText("View settings")).toBeVisible();
    expect(screen.getByRole("radio", { name: /Shaded/ })).toHaveAttribute("aria-checked", "true");

    await user.click(screen.getByRole("radio", { name: /X-Ray/ }));
    expect(onPreferences).toHaveBeenCalledWith({ shading: "xray" });
    expect(screen.getByLabelText("View settings")).toBeVisible();
  });

  it("toggles the grid through its own callback so it never enters viewer preferences", async () => {
    const user = userEvent.setup();
    const onPreferences = vi.fn();
    const onGridChange = vi.fn();
    render(<ViewSettings shading="shaded" edges grid={false} onPreferences={onPreferences} onGridChange={onGridChange} />);

    const grid = screen.getByRole("switch", { name: "Show grid" });
    expect(grid).toHaveAttribute("aria-checked", "false");
    await user.click(grid);

    expect(onGridChange).toHaveBeenCalledWith(true);
    expect(onPreferences).not.toHaveBeenCalled();
  });

  it("names every mode so narrow layouts can hide the text", () => {
    render(<ViewSettings shading="zebra" edges onPreferences={() => {}} />);
    for (const name of ["Shaded", "Wireframe", "X-Ray", "Surface normals", "Zebra"]) {
      expect(screen.getByRole("radio", { name })).toBeTruthy();
    }
    expect(screen.getByRole("radio", { name: "Zebra" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("toolbar", { name: "View settings" })).toBeTruthy();
  });

  it("toggles edge visibility without hiding the settings", async () => {
    const user = userEvent.setup();
    const onPreferences = vi.fn();
    render(<ViewSettings shading="shaded" edges={false} onPreferences={onPreferences} />);

    await user.click(screen.getByRole("switch", { name: "Show edges" }));

    expect(onPreferences).toHaveBeenCalledWith({ edges: true });
    expect(screen.getByLabelText("View settings")).toBeVisible();
  });
});
