import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CADGraph } from "@mesh2param/contracts";
import { apiClient } from "../api/client";
import { normalizeApiError } from "../api/errors";
import { watchJob } from "../api/jobs";
import { saveProjectFile } from "../persistence/projectFile";
import { workspaceRepository } from "../persistence/repository";
import { useWorkspaceSelector, workspaceStore } from "../state/store";
import type {
  Job,
  JobKind,
  JsonObject,
  ProjectDetail,
  ProjectVersionSnapshot,
  Units,
  WorkflowStep,
} from "../state/types";
import { normalizeProjectDetail } from "./normalize";
import { WorkspaceShell } from "./WorkspaceShell";
import type { WorkspaceActions, WorkspaceViewModel } from "./types";

const COMPLETION_STEP: Partial<Record<JobKind, WorkflowStep>> = {
  upload: "import",
  repair: "repair",
  analyze: "surfaces",
  reconstruct: "features",
  rebuild: "refine",
  validate: "validate",
  export: "export",
  sample_open: "import",
};

interface WorkspaceControllerProps {
  workerReady: boolean;
  initialJob: Job | null;
  onOpenStart(): void;
}

export function WorkspaceController({ workerReady, initialJob, onOpenStart }: WorkspaceControllerProps) {
  const project = useWorkspaceSelector((state) => state.project);
  const working = useWorkspaceSelector((state) => state.working);
  const activeStep = useWorkspaceSelector((state) => state.workflow.active);
  const selectedPatchId = useWorkspaceSelector((state) => state.selection.patchId);
  const selectedFeatureId = useWorkspaceSelector((state) => state.selection.featureId);
  const jobs = useWorkspaceSelector((state) => state.jobs);
  const canUndo = useWorkspaceSelector((state) => state.history.past.length > 0);
  const canRedo = useWorkspaceSelector((state) => state.history.future.length > 0);
  const [versions, setVersions] = useState<ProjectVersionSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const streams = useRef(new Map<string, () => void>());

  const refreshProject = useCallback(async (label = "Refresh project") => {
    const current = workspaceStore.getState().project;
    if (current === null) return;
    const [projectResult, patches, artifacts, versionResult] = await Promise.all([
      apiClient.getProject(current.id),
      apiClient.listPatches(current.id),
      apiClient.listArtifacts(current.id),
      apiClient.listVersions(current.id),
    ]);
    if (workspaceStore.getState().project?.id !== current.id) return;
    const normalized = normalizeProjectDetail(projectResult.data);
    normalized.state.patches = patches.data.items;
    normalized.state.artifacts = artifacts.data.items;
    workspaceStore.getState().commitServerOperation(label, normalized.state, normalized.revision);
    setVersions(versionResult.data.items);
    await workspaceRepository.putVersions(versionResult.data.items);
    await cacheRemoteSource(normalized).catch(() => undefined);
    setError(null);
  }, []);

  const trackJob = useCallback((job: Job) => {
    streams.current.get(job.id)?.();
    workspaceStore.getState().setJob(job);
    const stop = watchJob(job, {
      onConnection: (connection) => workspaceStore.getState().setJobConnection(job.kind, connection),
      onEvent: (event) => {
        workspaceStore.getState().applyJobEvent(job.kind, event);
        if (event.type === "completed") {
          const step = COMPLETION_STEP[job.kind];
          if (step !== undefined) workspaceStore.getState().setStepState(step, { status: "complete" });
          void refreshProject(`${job.kind} completed`).catch((cause: unknown) => {
            setError(normalizeApiError(cause).detail);
          });
        } else if (event.type === "failed") {
          const step = COMPLETION_STEP[job.kind];
          if (step !== undefined) workspaceStore.getState().setStepState(step, { status: "failed" });
          setError(event.message ?? `${job.kind} failed`);
        }
      },
      onSnapshot: (snapshot) => {
        workspaceStore.getState().setJob(snapshot, snapshot.status === "running" ? "reconnecting" : "closed");
        if (snapshot.status === "completed") void refreshProject(`${job.kind} completed`);
      },
      onError: (cause) => setError(cause.detail),
      onInvalidEvent: (cause) => setError(`Invalid worker event: ${cause.message}`),
    });
    streams.current.set(job.id, stop);
  }, [refreshProject]);

  useEffect(() => {
    if (initialJob !== null) trackJob(initialJob);
  }, [initialJob, trackJob]);

  useEffect(() => () => {
    for (const stop of streams.current.values()) stop();
    streams.current.clear();
  }, []);

  useEffect(() => {
    void refreshProject("Open project").catch(async (cause: unknown) => {
      const apiError = normalizeApiError(cause);
      if (apiError.status === 404) {
        const projectId = workspaceStore.getState().project?.id;
        const stored = projectId === undefined ? null : await workspaceRepository.getWorkspace(projectId);
        if (stored !== null) setVersions(stored.versions);
      } else setError(apiError.detail);
    });
  }, [refreshProject]);

  useEffect(() => {
    const unsubscribe = workspaceStore.subscribe((next, previous) => {
      if (next.project === null || next.working === null || next.localRevision === previous.localRevision) return;
      void workspaceRepository.scheduleAutosave(snapshotForPersistence(next)).catch((cause: unknown) => {
        setError(`Local autosave failed: ${String(cause)}`);
      });
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const current = workspaceStore.getState();
    if (current.project === null || current.working === null) return;
    void workspaceRepository.saveWorkspace({ ...snapshotForPersistence(current), queueOutbox: false })
      .catch((cause: unknown) => setError(`Initial local save failed: ${String(cause)}`));
  }, [project?.id]);

  const requireServerWritable = useCallback(() => {
    const current = workspaceStore.getState();
    if (current.localRevision === current.lastAckedLocalRevision && current.sync.state === "clean") return true;
    setError("This workspace has local-only edits queued in IndexedDB. Server geometry operations are disabled until the divergence is resolved; no local edit was discarded.");
    return false;
  }, []);

  const syncHistoryCadgraph = useCallback(async (label: string) => {
    const current = workspaceStore.getState();
    if (current.project === null || current.serverRevision === null || current.working === null || current.working.cadgraph === null) {
      setError("The local history change is queued, but it cannot be synchronized without an editable CADGraph.");
      return;
    }
    try {
      const sentRevision = current.localRevision;
      const result = await apiClient.updateCadgraph(current.project.id, current.serverRevision, current.working.cadgraph);
      workspaceStore.getState().acknowledgeServerRevision(sentRevision, result.revision ?? Number(current.serverRevision) + 1);
      await workspaceRepository.flushAutosave();
      await workspaceRepository.saveWorkspace({ ...snapshotForPersistence(workspaceStore.getState()), queueOutbox: false });
      setError(null);
    } catch (cause) {
      const apiError = normalizeApiError(cause);
      workspaceStore.getState().setSyncState({
        state: apiError.status === 409 || apiError.status === 412 ? "conflict" : "error",
        dirtyRevision: workspaceStore.getState().localRevision,
        error: apiError,
      });
      setError(`${label} remains queued locally: ${apiError.detail}`);
    }
  }, []);

  const run = useCallback(async (
    operation: "repair" | "analyze" | "reconstruct" | "rebuild" | "validate" | "export",
    settings: JsonObject = {},
  ) => {
    const current = workspaceStore.getState();
    if (!workerReady) {
      setError("The geometry worker is not ready. No operation was queued; retry after readiness returns.");
      return;
    }
    if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
    setError(null);
    try {
      const result = await apiClient.startOperation(current.project.id, operation, current.serverRevision, { settings });
      trackJob(result.data);
    } catch (cause) {
      const apiError = normalizeApiError(cause);
      setError(`${apiError.summary}: ${apiError.detail}`);
      current.setSyncState({ state: apiError.status === 409 || apiError.status === 412 ? "conflict" : "error", error: apiError });
    }
  }, [requireServerWritable, trackJob, workerReady]);

  const actions = useMemo<WorkspaceActions>(() => ({
    setStep(step) {
      workspaceStore.getState().setWorkflowStep(step);
      if (window.matchMedia("(max-width: 900px)").matches) {
        workspaceStore.getState().setShellState({ inspectorExpanded: true });
      }
    },
    selectPatch(id) {
      workspaceStore.getState().setSelection({ patchId: id });
      if (id !== null) workspaceStore.getState().setViewerPreferences({ mode: "patches" });
    },
    selectFeature(id) {
      workspaceStore.getState().setSelection({ featureId: id });
    },
    async upload(file: File, units: Units, scale: number) {
      const current = workspaceStore.getState();
      if (!workerReady) { setError("The geometry worker is not ready. The source was not uploaded."); return; }
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        const result = await apiClient.uploadSource(current.project.id, current.serverRevision, file, {
          filename: file.name,
          units,
          unitsConfirmed: true,
          scaleFactor: scale,
        });
        await workspaceRepository.putBlob({
          projectId: current.project.id,
          kind: "source",
          sha256: result.data.source.sha256,
          byteSize: result.data.source.byteSize,
          mediaType: file.type || `model/${result.data.source.format}`,
          originalFileName: file.name,
          blob: file,
        });
        await refreshProject("Source accepted");
        trackJob(result.data.job);
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    confirmImport() {
      workspaceStore.getState().setStepState("import", { status: "complete", label: "Units confirmed" });
      workspaceStore.getState().setWorkflowStep("repair");
    },
    run,
    async cancelJob() {
      const active = findActiveJob(workspaceStore.getState().jobs);
      if (active === null) return;
      workspaceStore.getState().markJobCancelling(active.job.kind, true);
      try {
        const result = await apiClient.cancelJob(active.job.id);
        workspaceStore.getState().setJob(result.data, "open");
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    async updatePatch(patchId, patch) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        await apiClient.updatePatch(current.project.id, patchId, current.serverRevision, patch);
        await refreshProject("Update surface patch");
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    async mergePatches(patchIds) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        const result = await apiClient.mergePatches(current.project.id, patchIds, current.serverRevision);
        await refreshProject("Merge surface patches");
        workspaceStore.getState().setSelection({ patchId: result.data.id });
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    async updateCadgraph(graph: CADGraph, label: string) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      const entry = current.transactProjectEdit(label, ["cadgraph", "features"], (draft) => {
        draft.cadgraph = graph;
        draft.validation = null;
      }, { requiresRebuild: true });
      if (entry === null) return;
      try {
        const sentRevision = workspaceStore.getState().localRevision;
        const result = await apiClient.updateCadgraph(current.project.id, current.serverRevision, graph);
        workspaceStore.getState().acknowledgeServerRevision(sentRevision, result.revision ?? Number(current.serverRevision) + 1);
        await workspaceRepository.flushAutosave().catch((cause: unknown) => {
          setError(`Local outbox flush failed after the server accepted the edit: ${String(cause)}`);
        });
        await workspaceRepository.saveWorkspace({
          ...snapshotForPersistence(workspaceStore.getState()),
          queueOutbox: false,
        }).catch((cause: unknown) => {
          setError(`Local acknowledgement save failed: ${String(cause)}`);
        });
      } catch (cause) {
        const apiError = normalizeApiError(cause);
        workspaceStore.getState().rejectHistoryEntry(entry.id, apiError);
        setError(apiError.detail);
        throw apiError;
      }
    },
    undo() {
      const state = workspaceStore.getState();
      const entry = state.history.past.at(-1);
      if (!state.undo() || entry === undefined) return;
      if (entry.scopes.some((scope) => scope === "cadgraph" || scope === "features" || scope === "sketches" || scope === "constraints")) {
        void syncHistoryCadgraph("Undo");
      } else {
        setError("Undo is preserved locally and queued in IndexedDB. This server operation cannot be replaced wholesale, so further geometry jobs are blocked until the divergence is resolved.");
      }
    },
    redo() {
      const state = workspaceStore.getState();
      const entry = state.history.future.at(-1);
      if (!state.redo() || entry === undefined) return;
      if (entry.scopes.some((scope) => scope === "cadgraph" || scope === "features" || scope === "sketches" || scope === "constraints")) {
        void syncHistoryCadgraph("Redo");
      } else {
        setError("Redo is preserved locally and queued in IndexedDB. Further geometry jobs remain blocked until the divergence is resolved.");
      }
    },
    canUndo,
    canRedo,
    async renameProject(name) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        const result = await apiClient.updateProject(current.project.id, current.serverRevision, { name });
        workspaceStore.getState().replaceWithServerCopy(normalizeProjectDetail(result.data));
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    async saveProject() {
      const current = workspaceStore.getState();
      if (current.project === null || current.working === null) return;
      try {
        await workspaceRepository.saveWorkspace(snapshotForPersistence(current));
        const file = await workspaceRepository.exportProjectFile(current.project.id);
        await saveProjectFile(file, { suggestedName: `${safeFilename(current.project.name)}.mesh2param.json` });
      } catch (cause) {
        setError(`Project save failed: ${String(cause)}`);
      }
    },
    openStart() {
      for (const stop of streams.current.values()) stop();
      workspaceStore.getState().closeProject();
      onOpenStart();
    },
    async createVersion(label) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        await apiClient.createVersion(current.project.id, current.serverRevision, label.trim());
        const result = await apiClient.listVersions(current.project.id);
        setVersions(result.data.items);
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
    async restoreVersion(versionId) {
      const current = workspaceStore.getState();
      if (current.project === null || current.serverRevision === null || !requireServerWritable()) return;
      try {
        const result = await apiClient.restoreVersion(current.project.id, versionId, current.serverRevision);
        const next: ProjectDetail = normalizeProjectDetail({
          ...current.project,
          revision: result.data.revision,
          basedOnVersionId: versionId,
          state: result.data.state,
        });
        workspaceStore.getState().replaceWithServerCopy(next);
        await refreshProject("Restore version");
      } catch (cause) {
        setError(normalizeApiError(cause).detail);
      }
    },
  }), [canRedo, canUndo, onOpenStart, refreshProject, requireServerWritable, run, syncHistoryCadgraph, trackJob, workerReady]);

  useWorkspaceShortcuts(actions);

  if (project === null || working === null) return null;
  const activeJob = findActiveJob(jobs);
  const detail: ProjectDetail = { ...project, state: working };
  const vm: WorkspaceViewModel = {
    project: detail,
    activeStep,
    selectedPatchId,
    selectedFeatureId,
    activeJob,
    artifacts: working.artifacts,
    versions,
    workerReady,
    syncLabel: workspaceStore.getState().sync.state,
    serverWritable: workspaceStore.getState().sync.state === "clean"
      && workspaceStore.getState().localRevision === workspaceStore.getState().lastAckedLocalRevision,
    error,
  };
  return (
    <>
      <WorkspaceShell vm={vm} actions={actions} />
      {error === null ? null : <div className="global-error" role="alert">{error}</div>}
    </>
  );
}

function findActiveJob(jobs: ReturnType<typeof workspaceStore.getState>["jobs"]) {
  return Object.values(jobs).find((view) => view?.job.status === "queued" || view?.job.status === "running") ?? null;
}

function snapshotForPersistence(state: ReturnType<typeof workspaceStore.getState>) {
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

function safeFilename(value: string) {
  return value.trim().replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "") || "project";
}

async function cacheRemoteSource(project: ProjectDetail) {
  const source = project.state.source;
  if (source === null) return;
  const existing = await workspaceRepository.getBlob(`source:${source.sha256}`);
  if (existing !== undefined) return;
  const descriptor = project.state.artifacts.find((artifact) =>
    artifact.sha256 === source.sha256 || artifact.name === source.originalFileName);
  if (descriptor === undefined) return;
  const response = await fetch(apiClient.artifactUrl(project.id, descriptor.name, descriptor.sha256));
  if (!response.ok) return;
  await workspaceRepository.putBlob({
    projectId: project.id,
    kind: "source",
    sha256: source.sha256,
    byteSize: source.byteSize,
    mediaType: descriptor.mediaType,
    originalFileName: source.originalFileName,
    blob: await response.blob(),
  });
}

function useWorkspaceShortcuts(actions: WorkspaceActions) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      const state = workspaceStore.getState();
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === "s") { event.preventDefault(); void actions.saveProject(); return; }
      if (modifier && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) actions.redo();
        else actions.undo();
        return;
      }
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
      if (!state.shell.singleKeyShortcuts || modifier || event.altKey) return;
      const steps: WorkflowStep[] = ["import", "repair", "surfaces", "features", "refine", "validate", "export"];
      const numeric = Number(event.key);
      if (Number.isInteger(numeric) && numeric >= 1 && numeric <= 7) actions.setStep(steps[numeric - 1]!);
      else if (event.key.toLowerCase() === "n") {
        const index = steps.indexOf(state.workflow.active);
        if (index < steps.length - 1) actions.setStep(steps[index + 1]!);
      }
      else if (event.key.toLowerCase() === "b") {
        const index = steps.indexOf(state.workflow.active);
        if (index > 0) actions.setStep(steps[index - 1]!);
      }
      else if (event.key.toLowerCase() === "h") window.dispatchEvent(new Event("mesh2param:fit-view"));
      else if (event.key.toLowerCase() === "a") void actions.run("analyze");
      else if (event.key.toLowerCase() === "r") void actions.run("reconstruct");
      else if (event.key.toLowerCase() === "e") actions.setStep("export");
      else if (event.key === "Escape") {
        state.clearSelection();
        state.setShellState({ inspectorExpanded: false, activeDialog: null });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [actions]);
}
