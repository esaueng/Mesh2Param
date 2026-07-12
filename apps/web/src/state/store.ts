import { applyPatches, enablePatches, produceWithPatches } from "immer";
import { useStore } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { createStore, type StoreApi } from "zustand/vanilla";

import {
  loadAppPreferences,
  persistedShellPreferences,
  saveAppPreferences,
  type AppPreferences,
} from "../persistence/appPreferences";

import type {
  ApiErrorDetails,
  HistoryEntry,
  HistoryScope,
  HistoryState,
  Job,
  JobConnectionState,
  JobEvent,
  JobKind,
  JobViewState,
  ProjectDetail,
  ProjectEditRecipe,
  ProjectSummary,
  ProjectWorkingDocument,
  SelectionState,
  ShellState,
  StepState,
  SyncState,
  ViewerPreferences,
  WorkflowState,
  WorkflowStep,
} from "./types";

enablePatches();

export const MAX_HISTORY_ENTRIES = 100;
export const MAX_HISTORY_BYTES = 4 * 1024 * 1024;
export const MAX_JOB_LOG_ENTRIES = 500;

export interface ProjectHydrationOptions {
  localRevision?: number;
  lastAckedLocalRevision?: number;
  history?: HistoryState;
  syncState?: "clean" | "saving" | "offline";
}

export interface ProjectEditOptions {
  requiresRebuild?: boolean;
}

export interface WorkspaceStore {
  project: ProjectSummary | null;
  working: ProjectWorkingDocument | null;
  localRevision: number;
  serverRevision: number | string | null;
  lastAckedLocalRevision: number;
  baseVersionId: string | null;
  sync: SyncState;
  workflow: WorkflowState;
  selection: SelectionState;
  viewer: ViewerPreferences;
  shell: ShellState;
  jobs: Partial<Record<JobKind, JobViewState>>;
  history: HistoryState;
  rebuildRequired: boolean;

  hydrateProject(project: ProjectDetail, options?: ProjectHydrationOptions): void;
  closeProject(): void;
  transactProjectEdit(
    label: string,
    scopes: HistoryScope[],
    recipe: ProjectEditRecipe,
    options?: ProjectEditOptions,
  ): HistoryEntry | null;
  commitServerOperation(
    label: string,
    document: ProjectWorkingDocument,
    serverRevision: number | string,
    scopes?: HistoryScope[],
    options?: ProjectEditOptions,
  ): HistoryEntry | null;
  undo(): boolean;
  redo(): boolean;
  acknowledgeServerRevision(sentLocalRevision: number, serverRevision: number | string): void;
  replaceWithServerCopy(project: ProjectDetail): void;
  setSyncState(sync: SyncState): void;
  rejectHistoryEntry(entryId: string, error: ApiErrorDetails): void;
  clearHistory(): void;
  setRebuildRequired(required: boolean): void;

  setWorkflowStep(step: WorkflowStep): void;
  setStepState(step: WorkflowStep, state: StepState): void;
  setSelection(selection: Partial<SelectionState>): void;
  clearSelection(): void;
  setViewerPreferences(preferences: Partial<ViewerPreferences>): void;
  setShellState(shell: Partial<ShellState>): void;

  setJob(job: Job, connection?: JobConnectionState): void;
  applyJobEvent(kind: JobKind, event: JobEvent): void;
  setJobConnection(kind: JobKind, connection: JobConnectionState): void;
  markJobCancelling(kind: JobKind, cancelling: boolean): void;
  clearJob(kind: JobKind): void;
}

const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  "import",
  "repair",
  "surfaces",
  "features",
  "refine",
  "validate",
  "export",
];

export const defaultViewerPreferences: ViewerPreferences = {
  mode: "source",
  visible: {
    source: true,
    repaired: false,
    analysis: false,
    patches: false,
    reconstructed: false,
    residual: false,
  },
  sourceOpacity: 1,
  resultOpacity: 1,
  projection: "perspective",
  shading: "shaded",
  edges: true,
};

export const defaultShellState: ShellState = {
  theme: "dark",
  railCollapsed: false,
  inspectorExpanded: true,
  bottomDrawerExpanded: false,
  bottomDrawerHeight: 220,
  singleKeyShortcuts: true,
  activeDialog: null,
};

function initialWorkflow(): WorkflowState {
  return {
    active: "import",
    completion: Object.fromEntries(
      WORKFLOW_STEPS.map((step) => [step, { status: step === "import" ? "active" : "inactive" }]),
    ) as Record<WorkflowStep, StepState>,
  };
}

const EMPTY_SELECTION: SelectionState = {
  patchId: null,
  featureId: null,
  sketchEntityId: null,
  hoverId: null,
};

function cloneDocument(document: ProjectWorkingDocument): ProjectWorkingDocument {
  return structuredClone(document);
}

function summaryOf(project: ProjectDetail): ProjectSummary {
  return {
    id: project.id,
    name: project.name,
    units: project.units,
    schemaVersion: project.schemaVersion,
    revision: project.revision,
    basedOnVersionId: project.basedOnVersionId,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
  };
}

let fallbackHistoryId = 0;
function historyId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `history-${Date.now()}-${++fallbackHistoryId}`;
}

function patchBytes(forwardPatches: HistoryEntry["forwardPatches"], inversePatches: HistoryEntry["inversePatches"]): number {
  return new TextEncoder().encode(JSON.stringify([forwardPatches, inversePatches])).byteLength;
}

function trimHistory(entries: HistoryEntry[]): HistoryEntry[] {
  const result = entries.slice(-MAX_HISTORY_ENTRIES);
  let total = result.reduce((sum, entry) => sum + entry.serializedBytes, 0);
  while (result.length > 0 && total > MAX_HISTORY_BYTES) {
    total -= result.shift()?.serializedBytes ?? 0;
  }
  return result;
}

function makeHistoryEntry(
  label: string,
  scopes: HistoryScope[],
  beforeLocalRevision: number,
  afterLocalRevision: number,
  requiresRebuild: boolean,
  forwardPatches: HistoryEntry["forwardPatches"],
  inversePatches: HistoryEntry["inversePatches"],
): HistoryEntry {
  return {
    id: historyId(),
    label,
    timestamp: new Date().toISOString(),
    forwardPatches,
    inversePatches,
    scopes: [...new Set(scopes)],
    beforeLocalRevision,
    afterLocalRevision,
    requiresRebuild,
    serializedBytes: patchBytes(forwardPatches, inversePatches),
  };
}

function dirtySync(current: SyncState, revision: number): SyncState {
  if (current.state === "offline" || current.state === "conflict" || current.state === "error") {
    return { ...current, dirtyRevision: revision };
  }
  return { state: "saving", dirtyRevision: revision };
}

function plainError(error: ApiErrorDetails): ApiErrorDetails {
  return {
    status: error.status,
    code: error.code,
    summary: error.summary,
    detail: error.detail,
    phase: error.phase,
    projectId: error.projectId,
    jobId: error.jobId,
    recoverable: error.recoverable,
    recommendedAction: error.recommendedAction,
    requestId: error.requestId,
  };
}

function initialState(preferences: AppPreferences | null = null): Pick<
  WorkspaceStore,
  | "project"
  | "working"
  | "localRevision"
  | "serverRevision"
  | "lastAckedLocalRevision"
  | "baseVersionId"
  | "sync"
  | "workflow"
  | "selection"
  | "viewer"
  | "shell"
  | "jobs"
  | "history"
  | "rebuildRequired"
> {
  return {
    project: null,
    working: null,
    localRevision: 0,
    serverRevision: null,
    lastAckedLocalRevision: 0,
    baseVersionId: null,
    sync: { state: "clean" },
    workflow: initialWorkflow(),
    selection: { ...EMPTY_SELECTION },
    viewer: structuredClone(preferences?.viewer ?? defaultViewerPreferences),
    shell: { ...defaultShellState, ...preferences?.shell },
    jobs: {},
    history: { past: [], future: [] },
    rebuildRequired: false,
  };
}

export function createWorkspaceStore(preferences: AppPreferences | null = null): StoreApi<WorkspaceStore> {
  return createStore<WorkspaceStore>()(
    subscribeWithSelector((set, get) => ({
      ...initialState(preferences),

      hydrateProject(project, options = {}) {
        const localRevision = options.localRevision ?? 0;
        const lastAckedLocalRevision = options.lastAckedLocalRevision ?? localRevision;
        const syncState = options.syncState ?? (
          localRevision > lastAckedLocalRevision ? "saving" : "clean"
        );
        set({
          project: summaryOf(project),
          working: cloneDocument(project.state),
          localRevision,
          serverRevision: project.revision,
          lastAckedLocalRevision,
          baseVersionId: project.basedOnVersionId,
          sync: syncState === "clean" ? { state: "clean" } : { state: syncState, dirtyRevision: localRevision },
          history: options.history ?? { past: [], future: [] },
          jobs: {},
          selection: { ...EMPTY_SELECTION },
          rebuildRequired: false,
        });
      },

      closeProject() {
        set(initialState());
      },

      transactProjectEdit(label, scopes, recipe, options = {}) {
        const current = get();
        if (current.working === null) return null;
        const [working, forwardPatches, inversePatches] = produceWithPatches(current.working, recipe);
        if (forwardPatches.length === 0) return null;
        const nextRevision = current.localRevision + 1;
        const requiresRebuild = options.requiresRebuild ?? false;
        const entry = makeHistoryEntry(
          label,
          scopes,
          current.localRevision,
          nextRevision,
          requiresRebuild,
          forwardPatches,
          inversePatches,
        );
        set({
          working,
          project: current.project === null
            ? null
            : { ...current.project, name: working.name, units: working.units },
          localRevision: nextRevision,
          sync: dirtySync(current.sync, nextRevision),
          history: { past: trimHistory([...current.history.past, entry]), future: [] },
          rebuildRequired: current.rebuildRequired || requiresRebuild,
        });
        return entry;
      },

      commitServerOperation(label, document, serverRevision, scopes = ["project"], options = {}) {
        const current = get();
        if (current.working === null) return null;
        const replacement = cloneDocument(document);
        const [working, forwardPatches, inversePatches] = produceWithPatches(
          current.working,
          () => replacement,
        );
        const numericServerRevision = typeof serverRevision === "number" ? serverRevision : Number(serverRevision);
        const project = current.project === null
          ? null
          : {
              ...current.project,
              name: working.name,
              units: working.units,
              ...(Number.isSafeInteger(numericServerRevision) ? { revision: numericServerRevision } : {}),
            };
        if (forwardPatches.length === 0) {
          set({ project, serverRevision, sync: { state: "clean" } });
          return null;
        }
        const nextRevision = current.localRevision + 1;
        const requiresRebuild = options.requiresRebuild ?? false;
        const entry = makeHistoryEntry(
          label,
          scopes,
          current.localRevision,
          nextRevision,
          requiresRebuild,
          forwardPatches,
          inversePatches,
        );
        set({
          project,
          working,
          localRevision: nextRevision,
          serverRevision,
          lastAckedLocalRevision: nextRevision,
          baseVersionId: document.currentVersionId,
          sync: { state: "clean" },
          history: { past: trimHistory([...current.history.past, entry]), future: [] },
          rebuildRequired: current.rebuildRequired || requiresRebuild,
        });
        return entry;
      },

      undo() {
        const current = get();
        const entry = current.history.past.at(-1);
        if (current.working === null || entry === undefined) return false;
        const nextRevision = current.localRevision + 1;
        const working = applyPatches(current.working, entry.inversePatches);
        set({
          working,
          project: current.project === null
            ? null
            : { ...current.project, name: working.name, units: working.units },
          localRevision: nextRevision,
          sync: dirtySync(current.sync, nextRevision),
          history: {
            past: current.history.past.slice(0, -1),
            future: [...current.history.future, entry],
          },
          rebuildRequired: current.rebuildRequired || entry.requiresRebuild,
        });
        return true;
      },

      redo() {
        const current = get();
        const entry = current.history.future.at(-1);
        if (current.working === null || entry === undefined) return false;
        const nextRevision = current.localRevision + 1;
        const working = applyPatches(current.working, entry.forwardPatches);
        set({
          working,
          project: current.project === null
            ? null
            : { ...current.project, name: working.name, units: working.units },
          localRevision: nextRevision,
          sync: dirtySync(current.sync, nextRevision),
          history: {
            past: trimHistory([...current.history.past, entry]),
            future: current.history.future.slice(0, -1),
          },
          rebuildRequired: current.rebuildRequired || entry.requiresRebuild,
        });
        return true;
      },

      acknowledgeServerRevision(sentLocalRevision, serverRevision) {
        const current = get();
        if (sentLocalRevision < current.lastAckedLocalRevision || sentLocalRevision > current.localRevision) return;
        const fullyAcknowledged = sentLocalRevision === current.localRevision;
        const numericRevision = typeof serverRevision === "number" ? serverRevision : Number(serverRevision);
        set({
          serverRevision,
          lastAckedLocalRevision: sentLocalRevision,
          project: current.project === null || !Number.isSafeInteger(numericRevision)
            ? current.project
            : { ...current.project, revision: numericRevision },
          sync: fullyAcknowledged
            ? { state: "clean" }
            : { state: current.sync.state === "offline" ? "offline" : "saving", dirtyRevision: current.localRevision },
        });
      },

      replaceWithServerCopy(project) {
        const current = get();
        set({
          project: summaryOf(project),
          working: cloneDocument(project.state),
          serverRevision: project.revision,
          lastAckedLocalRevision: current.localRevision,
          baseVersionId: project.basedOnVersionId,
          sync: { state: "clean" },
          history: { past: [], future: [] },
          selection: { ...EMPTY_SELECTION },
          rebuildRequired: false,
        });
      },

      setSyncState(sync) {
        set({ sync });
      },

      rejectHistoryEntry(entryId, error) {
        const current = get();
        const rejection = plainError(error);
        set({
          history: {
            ...current.history,
            past: current.history.past.map((entry) =>
              entry.id === entryId ? { ...entry, rejected: rejection } : entry,
            ),
          },
          sync: {
            state: error.status === 409 || error.status === 412 ? "conflict" : "error",
            dirtyRevision: current.localRevision,
            error: rejection,
          },
        });
      },

      clearHistory() {
        set({ history: { past: [], future: [] } });
      },

      setRebuildRequired(required) {
        set({ rebuildRequired: required });
      },

      setWorkflowStep(step) {
        const workflow = get().workflow;
        set({
          workflow: {
            active: step,
            completion: Object.fromEntries(
              WORKFLOW_STEPS.map((candidate) => [
                candidate,
                {
                  ...workflow.completion[candidate],
                  status:
                    candidate === step
                      ? "active"
                      : workflow.completion[candidate].status === "active"
                        ? "inactive"
                        : workflow.completion[candidate].status,
                },
              ]),
            ) as Record<WorkflowStep, StepState>,
          },
        });
      },

      setStepState(step, state) {
        const workflow = get().workflow;
        set({ workflow: { ...workflow, completion: { ...workflow.completion, [step]: state } } });
      },

      setSelection(selection) {
        set({ selection: { ...get().selection, ...selection } });
      },

      clearSelection() {
        set({ selection: { ...EMPTY_SELECTION } });
      },

      setViewerPreferences(preferences) {
        const viewer = get().viewer;
        set({
          viewer: {
            ...viewer,
            ...preferences,
            visible: preferences.visible === undefined ? viewer.visible : { ...viewer.visible, ...preferences.visible },
          },
        });
      },

      setShellState(shell) {
        set({ shell: { ...get().shell, ...shell } });
      },

      setJob(job, connection = "connecting") {
        const jobs = get().jobs;
        const previous = jobs[job.kind];
        set({
          jobs: {
            ...jobs,
            [job.kind]: {
              job,
              connection,
              logs: previous?.job.id === job.id ? previous.logs : [],
              cancelling: job.cancelRequestedAt !== null,
              lastEventAt: previous?.job.id === job.id ? previous.lastEventAt : null,
            },
          },
        });
      },

      applyJobEvent(kind, event) {
        const jobs = get().jobs;
        const view = jobs[kind];
        if (view === undefined || view.job.id !== event.jobId) return;
        if (event.progress !== null && event.progress < view.job.progress) return;
        const terminalStatus = event.type === "completed" || event.type === "cancelled" || event.type === "failed"
          ? event.type
          : undefined;
        const message = event.message;
        const logs = message === null
          ? view.logs
          : [...view.logs, {
              timestamp: event.timestamp,
              phase: event.phase,
              level: event.level,
              message,
              code: event.code,
            }].slice(-MAX_JOB_LOG_ENTRIES);
        set({
          jobs: {
            ...jobs,
            [kind]: {
              ...view,
              job: {
                ...view.job,
                phase: event.phase,
                ...(event.progress === null ? {} : { progress: event.progress }),
                ...(event.result === undefined ? {} : { result: event.result }),
                ...(event.status === undefined && terminalStatus === undefined
                  ? {}
                  : { status: event.status ?? terminalStatus }),
                ...(terminalStatus === undefined ? {} : { finishedAt: event.timestamp }),
              },
              connection: terminalStatus === undefined ? view.connection : "closed",
              cancelling: terminalStatus === undefined ? view.cancelling : false,
              lastEventAt: event.timestamp,
              logs,
            },
          },
        });
      },

      setJobConnection(kind, connection) {
        const jobs = get().jobs;
        const view = jobs[kind];
        if (view !== undefined) set({ jobs: { ...jobs, [kind]: { ...view, connection } } });
      },

      markJobCancelling(kind, cancelling) {
        const jobs = get().jobs;
        const view = jobs[kind];
        if (view !== undefined) set({ jobs: { ...jobs, [kind]: { ...view, cancelling } } });
      },

      clearJob(kind) {
        const jobs = { ...get().jobs };
        delete jobs[kind];
        set({ jobs });
      },
    })),
  );
}

const savedAppPreferences = loadAppPreferences();
export const workspaceStore = createWorkspaceStore(savedAppPreferences);

workspaceStore.subscribe((next, previous) => {
  if (next.viewer === previous.viewer && next.shell === previous.shell) return;
  saveAppPreferences({
    viewer: next.viewer,
    shell: persistedShellPreferences(next.shell),
  });
});

export function useWorkspaceSelector<T>(selector: (state: WorkspaceStore) => T): T {
  return useStore(workspaceStore, selector);
}

export const workspaceSelectors = {
  project: (state: WorkspaceStore) => state.project,
  working: (state: WorkspaceStore) => state.working,
  activeStep: (state: WorkspaceStore) => state.workflow.active,
  selection: (state: WorkspaceStore) => state.selection,
  viewer: (state: WorkspaceStore) => state.viewer,
  shell: (state: WorkspaceStore) => state.shell,
  sync: (state: WorkspaceStore) => state.sync,
  canUndo: (state: WorkspaceStore) => state.history.past.length > 0,
  canRedo: (state: WorkspaceStore) => state.history.future.length > 0,
  rebuildRequired: (state: WorkspaceStore) => state.rebuildRequired,
} as const;
