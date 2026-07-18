import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "../state/types";
import { CanvasLanding } from "./CanvasLanding";

afterEach(cleanup);

function recentProject(
  id: string,
  name: string,
  updatedAt: string,
  units: "mm" | "inch" = "mm",
  revision = 1,
) {
  return { id, name, updatedAt, units, revision } as ProjectDetail;
}

describe("CanvasLanding recent projects", () => {
  it("renders recent projects as a newest-first ordered list with useful metadata", () => {
    render(
      <CanvasLanding
        samples={[]}
        recentProjects={[
          recentProject("older", "Older bracket", "2026-07-11T10:30:00Z"),
          recentProject("newest", "Newest bracket", "2026-07-13T14:45:00Z", "inch", 4),
          recentProject("middle", "Middle bracket", "2026-07-12T12:15:00Z"),
        ]}
        readiness={{ status: "ready", database: true, storage: true, supervisor: true }}
        busy={false}
        onOpenMesh={vi.fn()}
        onOpenSample={vi.fn()}
        onOpenProjectFile={vi.fn()}
        onOpenRecent={vi.fn()}
      />,
    );

    const list = screen.getByRole("list", { name: "Recent projects" });
    const items = within(list).getAllByRole("listitem");
    const newest = items[0];

    expect(items).toHaveLength(3);
    expect(newest).toBeDefined();
    expect(items.map((item) => within(item).getByRole("button").textContent)).toEqual([
      expect.stringContaining("Newest bracket"),
      expect.stringContaining("Middle bracket"),
      expect.stringContaining("Older bracket"),
    ]);
    if (newest === undefined) throw new Error("Expected a newest recent project");
    expect(within(newest).getByText("inch")).toBeVisible();
    expect(within(newest).getByText("01")).toBeVisible();
    expect(within(newest).getByText("Revision 4")).toBeVisible();
    expect(newest.querySelector("time")).toHaveAttribute("datetime", "2026-07-13T14:45:00Z");
  });

  it("opens the project selected from the organized list", async () => {
    const user = userEvent.setup();
    const onOpenRecent = vi.fn();
    render(
      <CanvasLanding
        samples={[]}
        recentProjects={[recentProject("fixture", "Fixture plate", "2026-07-13T14:45:00Z")]}
        readiness={{ status: "ready", database: true, storage: true, supervisor: true }}
        busy={false}
        onOpenMesh={vi.fn()}
        onOpenSample={vi.fn()}
        onOpenProjectFile={vi.fn()}
        onOpenRecent={onOpenRecent}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Fixture plate/ }));

    expect(onOpenRecent).toHaveBeenCalledOnce();
    expect(onOpenRecent).toHaveBeenCalledWith("fixture");
  });
});
