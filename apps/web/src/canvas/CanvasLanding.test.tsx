import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "../state/types";
import { CanvasLanding, droppedFileKind, projectStage } from "./CanvasLanding";

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

describe("CanvasLanding drop zone", () => {
  it("routes dropped files by extension and rejects the rest", () => {
    expect(droppedFileKind("part.STL")).toBe("mesh");
    expect(droppedFileKind("scan.ply")).toBe("mesh");
    expect(droppedFileKind("bracket.mesh2param.json")).toBe("project");
    expect(droppedFileKind("notes.txt")).toBeNull();
  });

  it("opens a dropped mesh, shows the overlay while dragging, and explains a rejected file", () => {
    const onOpenMesh = vi.fn();
    const onOpenProjectFile = vi.fn();
    render(
      <CanvasLanding
        samples={[]}
        recentProjects={[]}
        readiness={{ status: "ready", database: true, storage: true, supervisor: true }}
        busy={false}
        onOpenMesh={onOpenMesh}
        onOpenSample={vi.fn()}
        onOpenProjectFile={onOpenProjectFile}
        onOpenRecent={vi.fn()}
      />,
    );
    const landing = screen.getByTestId("start-screen");
    const transfer = (files: File[]) => ({ dataTransfer: { types: ["Files"], files, dropEffect: "none" } });

    fireEvent.dragEnter(landing, transfer([]));
    expect(landing.querySelector(".landing-drop")).not.toBeNull();
    fireEvent.dragLeave(landing, transfer([]));
    expect(landing.querySelector(".landing-drop")).toBeNull();

    const mesh = new File(["solid"], "bracket.stl");
    fireEvent.dragEnter(landing, transfer([mesh]));
    fireEvent.drop(landing, transfer([mesh]));
    expect(onOpenMesh).toHaveBeenCalledWith(mesh);
    expect(landing.querySelector(".landing-drop")).toBeNull();

    const project = new File(["{}"], "saved.mesh2param.json");
    fireEvent.drop(landing, transfer([project]));
    expect(onOpenProjectFile).toHaveBeenCalledWith(project);

    fireEvent.drop(landing, transfer([new File(["x"], "notes.txt")]));
    expect(screen.getByRole("status").textContent).toContain("notes.txt is not an STL");
    expect(onOpenMesh).toHaveBeenCalledTimes(1);
  });

  it("says when there is nothing recent instead of showing an empty list", () => {
    render(
      <CanvasLanding samples={[]} recentProjects={[]} readiness={null} busy={false} onOpenMesh={vi.fn()} onOpenSample={vi.fn()} onOpenProjectFile={vi.fn()} onOpenRecent={vi.fn()} />,
    );
    expect(screen.queryByRole("list", { name: "Recent projects" })).toBeNull();
    expect(screen.getByText("Projects you open will be listed here.")).toBeTruthy();
  });
});

describe("projectStage", () => {
  const base = { source: null, diagnostics: null, patches: [], cadgraph: null, validation: null };
  it("reads how far a project got from its working document", () => {
    expect(projectStage({ state: undefined })).toBe("loaded");
    expect(projectStage({ state: base as never })).toBe("loaded");
    expect(projectStage({ state: { ...base, patches: [{}] } as never })).toBe("analyzed");
    expect(projectStage({ state: { ...base, cadgraph: { features: [] } } as never })).toBe("reconstructed");
    expect(projectStage({ state: { ...base, cadgraph: { features: [] }, validation: {} } as never })).toBe("validated");
  });

  it("shows the stage chip and triangle count on a recent card", () => {
    render(
      <CanvasLanding
        samples={[]}
        recentProjects={[{
          id: "v", name: "Validated bracket", updatedAt: "2026-09-05T00:00:00Z", units: "mm", revision: 3,
          state: { ...base, cadgraph: { features: [1, 2] }, validation: {}, diagnostics: { triangleCount: 2400 } },
        } as never]}
        readiness={{ status: "ready", database: true, storage: true, supervisor: true }}
        busy={false}
        onOpenMesh={vi.fn()}
        onOpenSample={vi.fn()}
        onOpenProjectFile={vi.fn()}
        onOpenRecent={vi.fn()}
      />,
    );
    const card = screen.getByRole("listitem");
    expect(card.getAttribute("data-stage")).toBe("validated");
    expect(within(card).getByText("Validated")).toBeTruthy();
    expect(within(card).getByText("2,400 tris")).toBeTruthy();
    expect(within(card).getByText("2 features")).toBeTruthy();
  });
});
