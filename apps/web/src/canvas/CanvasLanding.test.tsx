import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "../state/types";
import { CanvasLanding } from "./CanvasLanding";

afterEach(cleanup);

function recentProject(id: string, name: string, revision: number, updatedAt: string): ProjectDetail {
  return {
    id,
    name,
    units: "mm",
    schemaVersion: "1.0.0",
    revision,
    basedOnVersionId: null,
    createdAt: "2026-07-10T10:00:00.000Z",
    updatedAt,
    state: {} as ProjectDetail["state"],
  };
}

describe("CanvasLanding recent projects", () => {
  it("renders recent projects as detailed list rows and opens the selected project", async () => {
    const user = userEvent.setup();
    const onOpenRecent = vi.fn();
    render(
      <CanvasLanding
        samples={[]}
        recentProjects={[
          recentProject("project-a", "L-bracket with mounting holes", 4, "2026-07-12T14:35:00.000Z"),
          recentProject("project-b", "Fixture plate", 2, "2026-07-11T09:10:00.000Z"),
        ]}
        readiness={{ status: "ready", database: true, storage: true, supervisor: true }}
        busy={false}
        error={null}
        onOpenMesh={vi.fn()}
        onOpenSample={vi.fn()}
        onOpenProjectFile={vi.fn()}
        onOpenRecent={onOpenRecent}
      />,
    );

    const list = screen.getByRole("list", { name: "Recent projects" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    const projectButton = within(list).getByTitle("Open L-bracket with mounting holes");
    expect(projectButton).toHaveTextContent(/Updated Jul 12, 2026/);
    expect(projectButton).toHaveTextContent("Revision 4");

    await user.click(projectButton);
    expect(onOpenRecent).toHaveBeenCalledWith("project-a");
  });
});
