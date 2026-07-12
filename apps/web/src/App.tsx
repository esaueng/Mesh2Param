import { lazy, Suspense, useEffect, useState } from "react";
import { apiClient } from "./api/client";
import { normalizeApiError } from "./api/errors";
import { workspaceRepository } from "./persistence/repository";
import { CanvasLanding } from "./canvas/CanvasLanding";
import { workspaceStore } from "./state/store";
import type {
  Job,
  PersistedProjectUI,
  ProjectDetail,
  Readiness,
  SampleDescriptor,
  Units,
} from "./state/types";
import { normalizeProjectDetail } from "./workspace/normalize";

const WorkspaceController = lazy(async () => ({
  default: (await import("./workspace/WorkspaceController")).WorkspaceController,
}));

export default function App() {
  const [screen, setScreen] = useState<"start" | "workspace">("start");
  const [samples, setSamples] = useState<SampleDescriptor[]>([]);
  const [recentProjects, setRecentProjects] = useState<ProjectDetail[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [initialJob, setInitialJob] = useState<Job | null>(null);
  const [initialUpload, setInitialUpload] = useState<{ file: File; units: Units; scale: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const activeProjectId = sessionStorage.getItem("mesh2param-active-project");
    if (activeProjectId === null) return;
    let cancelled = false;
    void workspaceRepository.getWorkspace(activeProjectId).then(async (stored) => {
      if (cancelled || stored === null) return;
      await apiClient.listArtifacts(activeProjectId).catch(() => undefined);
      if (cancelled) return;
      hydrateStoredWorkspace(stored);
      setScreen("workspace");
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => workspaceRepository.attachVisibilityFlush(document), []);

  useEffect(() => {
    const controller = new AbortController();
    const check = () => void apiClient.ready(controller.signal)
      .then((result) => setReadiness(result.data))
      .catch(() => setReadiness({ status: "not-ready", database: false, storage: false, supervisor: false }));
    check();
    const timer = window.setInterval(check, 10_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (screen !== "start") return;
    const controller = new AbortController();
    void apiClient.listSamples(controller.signal).then((result) => setSamples(result.data.items)).catch((cause: unknown) => {
      const apiError = normalizeApiError(cause);
      if (apiError.code !== "request_aborted") setError(`Samples unavailable: ${apiError.detail}`);
    });
    void apiClient.listProjects(controller.signal).then((result) => {
      mergeRecents(setRecentProjects, result.data.items.map(normalizeProjectDetail));
    }).catch(() => {
      // Local IndexedDB workspaces remain available when the API is offline.
    });
    void workspaceRepository.listRecentProjects(10).then(async (records) => {
      const stored = await Promise.all(records.map((record) => workspaceRepository.getWorkspace(record.id)));
      const local = stored.flatMap((entry) => entry === null ? [] : [{
        id: entry.project.id,
        name: entry.project.name,
        units: entry.project.units,
        schemaVersion: entry.project.schemaVersion,
        revision: entry.project.revision,
        basedOnVersionId: entry.project.basedOnVersionId,
        createdAt: entry.project.createdAt,
        updatedAt: entry.project.updatedAt,
        state: entry.document.document,
      } satisfies ProjectDetail]);
      mergeRecents(setRecentProjects, local);
    }).catch(() => {
      // IndexedDB can be unavailable in private browser contexts; server recents still work.
    });
    return () => controller.abort();
  }, [screen]);

  function openWorkspace(
    project: ProjectDetail,
    job: Job | null = null,
    ui: PersistedProjectUI | null = null,
    upload: { file: File; units: Units; scale: number } | null = null,
  ) {
    workspaceStore.getState().hydrateProject(normalizeProjectDetail(project));
    if (ui !== null) {
      const state = workspaceStore.getState();
      state.setWorkflowStep(ui.activeStep);
      state.setSelection(ui.selection);
      state.setViewerPreferences(ui.viewer);
      state.setShellState(ui.shell);
    }
    sessionStorage.setItem("mesh2param-active-project", project.id);
    setInitialJob(job);
    setInitialUpload(upload);
    setError(null);
    setScreen("workspace");
  }

  async function withBusy(task: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (cause) {
      const apiError = normalizeApiError(cause);
      setError(`${apiError.summary}: ${apiError.detail}`);
    } finally {
      setBusy(false);
    }
  }

  if (screen === "workspace") {
    return (
      <Suspense fallback={<main className="workspace-loading" role="status">Loading CAD workspace…</main>}>
        <WorkspaceController
          workerReady={readiness?.status === "ready"}
          initialJob={initialJob}
          initialUpload={initialUpload}
          onOpenStart={() => {
            sessionStorage.removeItem("mesh2param-active-project");
            setInitialJob(null);
            setInitialUpload(null);
            setScreen("start");
          }}
        />
      </Suspense>
    );
  }

  return (
    <CanvasLanding
      samples={samples}
      recentProjects={recentProjects}
      readiness={readiness}
      busy={busy}
      error={error}
      onOpenMesh={(file) => void withBusy(async () => {
        const result = await apiClient.createProject(deriveProjectName(file.name), "mm");
        openWorkspace(result.data, null, null, { file, units: "mm", scale: 1 });
      })}
      onOpenProjectFile={(file) => void withBusy(async () => {
        const parsed = await workspaceRepository.importProjectFileBlob(file);
        const imported = { ...parsed.file.project, state: parsed.file.working };
        let regenerationJob: Job | null = null;
        if (parsed.file.artifactManifest.length > 0) {
          const operation = imported.state.cadgraph !== null
            ? "rebuild"
            : imported.state.source?.format === "stl"
              ? "analyze"
              : null;
          if (operation !== null) {
            regenerationJob = (await apiClient.startOperation(
              imported.id,
              operation,
              imported.revision,
              operation === "analyze" ? { settings: { importedProjectPreview: true } } : {},
            )).data;
          }
        }
        openWorkspace(
          imported,
          regenerationJob,
          parsed.file.ui,
        );
      })}
      onOpenRecent={(projectId) => void withBusy(async () => {
        try {
          const result = await apiClient.getProject(projectId);
          openWorkspace(result.data);
        } catch (cause) {
          const stored = await workspaceRepository.getWorkspace(projectId);
          if (stored === null) throw cause;
          await apiClient.listArtifacts(projectId).catch(() => undefined);
          hydrateStoredWorkspace(stored);
          sessionStorage.setItem("mesh2param-active-project", projectId);
          setInitialJob(null);
          setScreen("workspace");
        }
      })}
      onOpenSample={(sampleId) => void withBusy(async () => {
        const result = await apiClient.openSample(sampleId);
        openWorkspace(result.data.project, result.data.job);
      })}
    />
  );
}

function deriveProjectName(filename: string): string {
  return filename.replace(/\.[^.]+$/, "").trim() || "Untitled conversion";
}

function mergeRecents(
  set: React.Dispatch<React.SetStateAction<ProjectDetail[]>>,
  incoming: ProjectDetail[],
) {
  set((current) => {
    const byId = new Map(current.map((project) => [project.id, project]));
    for (const project of incoming) {
      const existing = byId.get(project.id);
      if (existing === undefined || project.updatedAt >= existing.updatedAt) byId.set(project.id, project);
    }
    return [...byId.values()].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  });
}

function hydrateStoredWorkspace(stored: NonNullable<Awaited<ReturnType<typeof workspaceRepository.getWorkspace>>>) {
  workspaceStore.getState().hydrateProject(normalizeProjectDetail({
    id: stored.project.id,
    name: stored.project.name,
    units: stored.project.units,
    schemaVersion: stored.project.schemaVersion,
    revision: stored.project.revision,
    basedOnVersionId: stored.project.basedOnVersionId,
    createdAt: stored.project.createdAt,
    updatedAt: stored.project.updatedAt,
    state: stored.document.document,
  }), {
    localRevision: stored.document.localRevision,
    lastAckedLocalRevision: stored.document.lastAckedLocalRevision,
    history: stored.history,
    syncState: stored.project.syncState === "conflict" || stored.project.syncState === "error"
      ? "offline"
      : stored.project.syncState,
  });
  if (stored.ui !== null) {
    const state = workspaceStore.getState();
    state.setWorkflowStep(stored.ui.state.activeStep);
    state.setSelection(stored.ui.state.selection);
    state.setViewerPreferences(stored.ui.state.viewer);
    state.setShellState(stored.ui.state.shell);
  }
}
