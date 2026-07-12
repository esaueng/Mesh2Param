import type { WorkspaceSnapshot } from "./repository";
import type { WorkspaceStore } from "../state/store";

export function hasPersistedWorkspaceChanges(next: WorkspaceStore, previous: WorkspaceStore): boolean {
  return next.project !== previous.project
    || next.working !== previous.working
    || next.localRevision !== previous.localRevision
    || next.serverRevision !== previous.serverRevision
    || next.lastAckedLocalRevision !== previous.lastAckedLocalRevision
    || next.baseVersionId !== previous.baseVersionId
    || next.sync !== previous.sync
    || next.workflow.active !== previous.workflow.active
    || next.selection !== previous.selection
    || next.viewer !== previous.viewer
    || next.shell !== previous.shell
    || next.history !== previous.history;
}

export function snapshotForPersistence(state: WorkspaceStore): WorkspaceSnapshot {
  if (state.project === null || state.working === null) throw new Error("No project is open");
  return {
    project: state.project,
    working: state.working,
    localRevision: state.localRevision,
    serverRevision: state.serverRevision,
    lastAckedLocalRevision: state.lastAckedLocalRevision,
    baseVersionId: state.baseVersionId,
    syncState: state.sync.state,
    ui: {
      activeStep: state.workflow.active,
      selection: state.selection,
      viewer: state.viewer,
      shell: {
        theme: state.shell.theme,
        railCollapsed: state.shell.railCollapsed,
        inspectorExpanded: state.shell.inspectorExpanded,
        bottomDrawerExpanded: state.shell.bottomDrawerExpanded,
        bottomDrawerHeight: state.shell.bottomDrawerHeight,
        singleKeyShortcuts: state.shell.singleKeyShortcuts,
      },
      cameraPose: null,
    },
    history: state.history,
  };
}
