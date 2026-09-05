import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PANEL_LAYOUT_KEY, panelLayoutStore } from "./panelLayout";
import { PanelSection } from "./PanelSection";

beforeEach(() => {
  localStorage.removeItem(PANEL_LAYOUT_KEY);
  panelLayoutStore.reload();
});
afterEach(() => {
  cleanup();
  localStorage.removeItem(PANEL_LAYOUT_KEY);
  panelLayoutStore.reload();
});

describe("PanelSection", () => {
  it("keeps the section heading addressable and toggles its body", async () => {
    const user = userEvent.setup();
    render(
      <PanelSection id="patches" title="Patches (7)">
        <button>Merge</button>
      </PanelSection>,
    );

    expect(screen.getByRole("heading", { name: "Patches (7)" })).toBeTruthy();
    const toggle = screen.getByRole("button", { name: "Patches (7)" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: "Merge" })).toBeTruthy();

    await user.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "Merge" })).toBeNull();
    expect(panelLayoutStore.snapshot().collapsed.patches).toBe(true);

    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Merge" })).toBeTruthy();
  });

  it("restores a persisted collapsed state", () => {
    localStorage.setItem(PANEL_LAYOUT_KEY, JSON.stringify({ collapsed: { view: true } }));
    panelLayoutStore.reload();
    render(
      <PanelSection id="view" title="View">
        <button>Fit view</button>
      </PanelSection>,
    );
    expect(screen.getByRole("button", { name: "View" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "Fit view" })).toBeNull();
  });

  it("keeps render-function children mounted while collapsed and tells them so", async () => {
    const user = userEvent.setup();
    render(
      <PanelSection id="convert" title="Convert">
        {(collapsed) => (
          <>
            <button className="dock-primary">Download STEP</button>
            {collapsed ? null : <button>Regenerate</button>}
          </>
        )}
      </PanelSection>,
    );

    await user.click(screen.getByRole("button", { name: "Convert" }));

    expect(screen.getByRole("button", { name: "Download STEP" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
  });
});
