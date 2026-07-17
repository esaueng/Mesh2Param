import { describe, expect, it } from "vitest";

import { createWorkspaceStore, MAX_HISTORY_ENTRIES } from "./store";
import type { ProjectDetail, ProjectWorkingDocument } from "./types";
import { hasPersistedWorkspaceChanges } from "../persistence/workspaceState";

function workingDocument(overrides: Partial<ProjectWorkingDocument> = {}): ProjectWorkingDocument {
  return {
    schemaVersion: "1.0.0",
    projectId: "project-1",
    name: "Test project",
    units: "mm",
    source: null,
    diagnostics: null,
    repair: null,
    analysis: null,
    patches: [],
    cadgraph: null,
    validation: null,
    metrics: null,
    artifactSetId: null,
    artifacts: [],
    currentVersionId: null,
    settings: {},
    ...overrides,
  };
}

function project(state = workingDocument()): ProjectDetail {
  return {
    id: state.projectId,
    name: state.name,
    units: state.units,
    schemaVersion: state.schemaVersion,
    revision: 10,
    basedOnVersionId: null,
    createdAt: "2026-07-11T12:00:00Z",
    updatedAt: "2026-07-11T12:00:00Z",
    state,
  };
}

describe("workspace unified history", () => {
  it("undoes and redoes project edits from one bounded stack", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project());

    store.getState().transactProjectEdit("Change tolerance", ["settings"], (draft) => {
      draft.settings.surfaceTolerance = 0.1;
    }, { requiresRebuild: true });
    store.getState().transactProjectEdit("Rename project", ["project"], (draft) => {
      draft.name = "Renamed project";
    });

    expect(store.getState().history.past.map((entry) => entry.label)).toEqual([
      "Change tolerance",
      "Rename project",
    ]);
    expect(store.getState().working?.name).toBe("Renamed project");
    expect(store.getState().rebuildRequired).toBe(true);
    expect(store.getState().undo()).toBe(true);
    expect(store.getState().working?.name).toBe("Test project");
    expect(store.getState().undo()).toBe(true);
    expect(store.getState().working?.settings.surfaceTolerance).toBeUndefined();
    expect(store.getState().redo()).toBe(true);
    expect(store.getState().working?.settings.surfaceTolerance).toBe(0.1);
  });

  it("keeps in-flight server acknowledgements separate from newer local edits", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project(), { localRevision: 5, lastAckedLocalRevision: 5 });
    store.getState().transactProjectEdit("First edit", ["settings"], (draft) => {
      draft.settings.first = true;
    });
    const sentRevision = store.getState().localRevision;
    store.getState().transactProjectEdit("Second edit", ["settings"], (draft) => {
      draft.settings.second = true;
    });

    store.getState().acknowledgeServerRevision(sentRevision, 11);

    expect(store.getState().serverRevision).toBe(11);
    expect(store.getState().lastAckedLocalRevision).toBe(6);
    expect(store.getState().localRevision).toBe(7);
    expect(store.getState().working?.settings).toMatchObject({ first: true, second: true });
    expect(store.getState().sync).toEqual({ state: "saving", dirtyRevision: 7 });
  });

  it("does not put ephemeral UI changes in project history", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project());
    store.getState().setSelection({ patchId: "patch.1" });
    store.getState().setWorkflowStep("repair");
    store.getState().setShellState({ theme: "light" });
    store.getState().setViewerPreferences({ sourceOpacity: 0.5 });

    expect(store.getState().history).toEqual({ past: [], future: [] });
    expect(store.getState().localRevision).toBe(0);
  });

  it("marks display and shell-only changes for workspace persistence", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project());
    const before = store.getState();

    store.getState().setViewerPreferences({ shading: "xray", edges: false });
    const afterDisplay = store.getState();
    expect(hasPersistedWorkspaceChanges(afterDisplay, before)).toBe(true);

    store.getState().setShellState({ theme: "light" });
    expect(hasPersistedWorkspaceChanges(store.getState(), afterDisplay)).toBe(true);
  });

  it("evicts the oldest whole entries at the count bound", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project());
    for (let index = 0; index < MAX_HISTORY_ENTRIES + 5; index += 1) {
      store.getState().transactProjectEdit(`Edit ${index}`, ["settings"], (draft) => {
        draft.settings.counter = index;
      });
    }

    expect(store.getState().history.past).toHaveLength(MAX_HISTORY_ENTRIES);
    expect(store.getState().history.past[0]?.label).toBe("Edit 5");
    expect(store.getState().history.past.at(-1)?.label).toBe("Edit 104");
  });

  it("records one history entry for a completed server operation", () => {
    const store = createWorkspaceStore();
    store.getState().hydrateProject(project());
    const completed = workingDocument({
      patches: [{ id: "patch.1", type: "plane", triangleCount: 20, confidence: 0.95, locked: false }],
    });

    store.getState().commitServerOperation("Analyze mesh", completed, 11, ["segmentation", "patches"]);

    expect(store.getState().history.past).toHaveLength(1);
    expect(store.getState().history.past[0]?.scopes).toEqual(["segmentation", "patches"]);
    expect(store.getState().serverRevision).toBe(11);
    expect(store.getState().sync.state).toBe("clean");
  });
});
