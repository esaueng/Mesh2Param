import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { apiClient } from "./api/client";
import { normalizeApiError } from "./api/errors";
import { ErrorToast } from "./components/ErrorToast";
import { ApiTokenDialog } from "./components/ApiTokenDialog";
import { workspaceRepository } from "./persistence/repository";
import { loadAppPreferences } from "./persistence/appPreferences";
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
import { geometryToWarm, prefetchGeometry } from "./viewer/geometryPrefetch";
import { normalizeProjectDetail } from "./workspace/normalize";

const WORKSPACE_LOADING_LABEL = "Loading CAD workspace…";

const importWorkspaceController = () => import("./workspace/WorkspaceController");
const WorkspaceController = lazy(async () => ({
  default: (await importWorkspaceController()).WorkspaceController,
}));

// Dev-only control gallery (U1 deliverable). The import.meta.env.DEV guard makes
// the chunk unreachable in production builds, so Rollup drops it entirely.
const Styleguide = import.meta.env.DEV
  ? lazy(async () => ({ default: (await import("./styleguide/Styleguide")).Styleguide }))
  : null;

export default function App() {
  // sessionStorage is synchronous, so a reload can tell on the very first render
  // whether a project was open. Starting at "start" instead would paint the whole
  // landing page — and fire its samples/projects requests — for the length of the
  // IndexedDB read plus the artifacts round-trip below, which reads as a flash.
  const [screen, setScreen] = useState<"start" | "restoring" | "workspace">(
    () => sessionStorage.getItem("mesh2param-active-project") === null ? "start" : "restoring",
  );
  const [samples, setSamples] = useState<SampleDescriptor[]>([]);
  const [recentProjects, setRecentProjects] = useState<ProjectDetail[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [initialJob, setInitialJob] = useState<Job | null>(null);
  const [initialUpload, setInitialUpload] = useState<{ file: File; units: Units; scale: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const dismissError = useCallback(() => setError(null), []);

  useEffect(() => {
    const activeProjectId = sessionStorage.getItem("mesh2param-active-project");
    if (activeProjectId === null) return;
    // `lazy` only starts fetching when the component renders, which here is after
    // the IndexedDB read below. The destination is already known, so the chunk —
    // the largest asset in the app — downloads alongside that read instead.
    void importWorkspaceController();
    let cancelled = false;
    void workspaceRepository.getWorkspace(activeProjectId).then(async (stored) => {
      if (cancelled) return;
      // No stored copy (never flushed, or IndexedDB was cleared): fall back to the
      // landing rather than leaving the restore placeholder up forever.
      if (stored === null) { setScreen("start"); return; }
      hydrateStoredWorkspace(stored);
      setScreen("workspace");
      // Not awaited: the artifact list decides what geometry to warm, not whether
      // the workspace can open. Awaiting it here put a whole round-trip in front
      // of the first workspace paint and then discarded the response, which
      // WorkspaceController goes on to fetch again for itself.
      void warmRestoredGeometry(activeProjectId);
    }).catch(() => {
      // IndexedDB is unavailable in some private-browsing contexts.
      if (!cancelled) setScreen("start");
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => workspaceRepository.attachVisibilityFlush(document), []);
  useEffect(() => {
    const requireAuth = () => setAuthRequired(true);
    window.addEventListener("mesh2param:api-auth-required", requireAuth);
    return () => window.removeEventListener("mesh2param:api-auth-required", requireAuth);
  }, []);

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

  if (import.meta.env.DEV && window.location.pathname === "/styleguide" && Styleguide !== null) {
    return (
      <Suspense fallback={<main className="workspace-loading" role="status">Loading styleguide…</main>}>
        <Styleguide />
      </Suspense>
    );
  }

  // Same copy as the Suspense fallback below on purpose: restoring runs straight
  // into the chunk load, and giving the two stages different wording made a
  // reload read as two separate loads rather than one.
  if (screen === "restoring") {
    return <main className="workspace-loading" role="status">{WORKSPACE_LOADING_LABEL}</main>;
  }

  if (screen === "workspace") {
    return (
      <>
      <Suspense fallback={<main className="workspace-loading" role="status">{WORKSPACE_LOADING_LABEL}</main>}>
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
      {authRequired ? <ApiTokenDialog onClose={() => setAuthRequired(false)} /> : null}
      </>
    );
  }

  return (
    <>
      <CanvasLanding
        samples={samples}
        recentProjects={recentProjects}
        readiness={readiness}
        busy={busy}
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
              try {
                regenerationJob = (await apiClient.startOperation(
                  imported.id,
                  operation,
                  imported.revision,
                  operation === "analyze" ? { settings: { importedProjectPreview: true } } : {},
                )).data;
              } catch (cause) {
                // The server project may no longer exist (e.g. a saved file shared after deletion).
                // Open the workspace from the file alone so the source mesh is still available.
                console.warn("Could not regenerate artifacts for imported project; opening file state.", cause);
              }
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
      {error === null ? null : <ErrorToast message={error} onDismiss={dismissError} />}
      {authRequired ? <ApiTokenDialog onClose={() => setAuthRequired(false)} /> : null}
    </>
  );
}

/**
 * Starts the geometry download for a restored project while the viewer chunk is
 * still being fetched and parsed, instead of after. Best-effort throughout: a
 * failure here costs nothing, because the viewer issues the same request itself.
 */
async function warmRestoredGeometry(projectId: string): Promise<void> {
  try {
    const artifacts = (await apiClient.listArtifacts(projectId)).data.items;
    const available = new Set(artifacts.map((artifact) => artifact.name));
    const wanted = geometryToWarm(workspaceStore.getState().viewer.mode, available);
    prefetchGeometry(wanted.flatMap((name) => {
      const artifact = artifacts.find((candidate) => candidate.name === name);
      return artifact === undefined ? [] : [apiClient.artifactUrl(projectId, artifact.name, artifact.sha256)];
    }));
  } catch {
    // Offline, or the project is server-side gone: the stored workspace still opens.
  }
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
  // localStorage is synchronous and therefore captures even the final preference
  // change immediately before a reload. Keep it authoritative over an older,
  // asynchronously flushed per-project UI record.
  const appPreferences = loadAppPreferences();
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
  if (appPreferences !== null) {
    const state = workspaceStore.getState();
    state.setViewerPreferences(appPreferences.viewer);
    state.setShellState(appPreferences.shell);
  }
}
