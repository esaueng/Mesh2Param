import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Styleguide } from "./Styleguide";

afterEach(cleanup);

describe("Styleguide (dev-only /styleguide)", () => {
  it("renders every control section", () => {
    render(<Styleguide />);
    expect(screen.getByTestId("styleguide")).toBeVisible();
    for (const heading of [
      "Color tokens",
      "Typography",
      "Buttons",
      "Icon buttons",
      "Fields",
      "Checkboxes",
      "Switches",
      "Badges",
      "Status glyphs",
      "Tabs",
      "Panel section",
      "Toasts",
      "Motion",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    }
  });

  it("shows control states: disabled, forced hover/active, and interactive toggles", async () => {
    const user = userEvent.setup();
    render(<Styleguide />);

    expect(screen.getAllByRole("button", { name: "Apply" })).toHaveLength(16);
    expect(screen.getAllByRole("switch")).toHaveLength(4);
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("validated")).toBeVisible();

    const offSwitch = screen.getByRole("switch", { name: "Off" });
    expect(offSwitch).toHaveAttribute("aria-checked", "false");
    await user.click(offSwitch);
    expect(offSwitch).toHaveAttribute("aria-checked", "true");

    const unchecked = screen.getByRole("checkbox", { name: "Unchecked" });
    await user.click(unchecked);
    expect(unchecked).toBeChecked();
  });

  it("includes an error toast using the alert role and a light-theme preview", async () => {
    const user = userEvent.setup();
    render(<Styleguide />);

    expect(screen.getByRole("alert")).toHaveTextContent("Rebuild failed");

    const root = screen.getByTestId("styleguide");
    expect(root).toHaveAttribute("data-theme", "dark");
    await user.click(screen.getByRole("button", { name: /Light/ }));
    expect(root).toHaveAttribute("data-theme", "light");
  });
});
