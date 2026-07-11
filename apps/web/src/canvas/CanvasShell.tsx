import { useCallback, useEffect, useRef } from "react";
import {
  Box,
  Download,
  FileArchive,
  FolderOpen,
  Focus,
  LoaderCircle,
  Moon,
  Rotate3D,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Sun,
} from "lucide-react";
import { apiClient } from "../api/client";
import { Mesh2ParamLogoMark } from "../start/Mesh2ParamLogoMark";
import { useWorkspaceSelector, workspaceStore } from "../state/store";
import type { ViewerMode } from "../state/types";
import { CadViewport } from "../viewer/CadViewport";
import type { ViewPreset } from "../viewer/cameraMath";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import {
  availableModes,
  humanPhase,
  isValidated,
  nextAction,
  type PipelineActionKind,
  stepArtifact,
} from "./pipeline";
import "./canvas.css";

export function CanvasShell({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const viewer = useWorkspaceSelector((state) => state.viewer);
  const theme = useWorkspaceSelector((state) => state.shell.theme);
  const fileRef = useRef<HTMLInputElement>(null);
  const revealedRef = useRef(false);

  const state = vm.project.state;
  const action = nextAction(vm);
  const modes = availableModes(vm.artifacts);
  const activeJob = vm.activeJob;

  const setMode = useCallback((mode: ViewerMode) => {
    const store = workspaceStore.getState();
    if (mode === "overlay") store.setViewerPreferences({ mode, sourceOpacity: 0.35, resultOpacity: 1 });
    else if (mode === "source") store.setViewerPreferences({ mode, sourceOpacity: 1 });
    else store.setViewerPreferences({ mode, resultOpacity: 1 });
  }, []);

  // Reveal the clean reconstructed result the first time it becomes available.
  useEffect(() => {
    const names = new Set(vm.artifacts.map((artifact) => artifact.name));
    if (revealedRef.current || !names.has("reconstructed.glb")) return;
    revealedRef.current = true;
    if (workspaceStore.getState().viewer.mode === "source") setMode("reconstructed");
  }, [vm.artifacts, setMode]);

  const fit = () => window.dispatchEvent(new Event("mesh2param:fit-view"));
  const view = (preset: ViewPreset) => window.dispatchEvent(new CustomEvent<ViewPreset>("mesh2param:view-preset", { detail: preset }));
  const toggleTheme = () => workspaceStore.getState().setShellState({ theme: theme === "dark" ? "light" : "dark" });

  const openFilePicker = () => fileRef.current?.click();

  const downloadStep = useCallback(() => {
    const step = stepArtifact(vm.artifacts);
    if (step === undefined) return;
    const anchor = document.createElement("a");
    anchor.href = apiClient.artifactUrl(vm.project.id, step.name, step.sha256);
    anchor.download = step.name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }, [vm.artifacts, vm.project.id]);

  const onPrimary = () => {
    if (action.kind === "open") openFilePicker();
    else if (action.kind === "download") downloadStep();
    else if (action.operation !== undefined) void actions.run(action.operation);
  };

  const status = conversionStatus(vm);
  const hasGeometry = vm.artifacts.some((artifact) => artifact.name.toLowerCase().endsWith(".glb"));
  // The "result" is a preserved-source facet proxy (not exact B-Rep) when reconstruction fell back to faceting.
  const sourceProxy = vm.artifacts.some((artifact) => artifact.name === "reconstructed.glb" && artifact.kind === "preserved-source-proxy");

  return (
    <main className={`canvas-shell ${theme === "light" ? "theme-light" : ""}`} data-theme={theme}>
      <a className="skip-link" href="#canvas-viewport">Skip to 3D viewport</a>
      <div id="canvas-viewport" className="canvas-stage">
        <CadViewport
          chrome="minimal"
          projectId={vm.project.id}
          artifacts={vm.artifacts}
          preferences={viewer}
          theme={theme}
          sourceProxyActive={sourceProxy}
          selectedPatchId={vm.selectedPatchId}
          onPreferences={(patch) => workspaceStore.getState().setViewerPreferences(patch)}
          onSelectPatch={actions.selectPatch}
        />
        {!hasGeometry && activeJob === null ? (
          <div className="canvas-empty">
            <Box size={40} strokeWidth={1.25} />
            {state.source === null ? (
              <>
                <strong>No mesh loaded</strong>
                <p>Open an STL, OBJ, or PLY to begin.</p>
                <button className="landing-secondary" onClick={openFilePicker}><FolderOpen size={16} />Open a mesh</button>
              </>
            ) : (
              <>
                <strong>Mesh loaded</strong>
                <p>Run <b>{action.label}</b> to view the {state.patches.length > 0 ? "geometry" : "mesh and its surfaces"}.</p>
              </>
            )}
          </div>
        ) : null}
      </div>

      <header className="canvas-topbar">
        <button className="canvas-brand" onClick={actions.openStart} aria-label="Back to start screen">
          <Mesh2ParamLogoMark aria-hidden />
          <strong>Mesh2Param</strong>
          <span className="canvas-badge">Beta</span>
        </button>
        {state.source !== null ? (
          <div className="canvas-file">
            <span className="canvas-file-name" title={state.source.originalFileName}>{state.source.originalFileName}</span>
            <span className="canvas-file-meta">{fileMeta(vm)}</span>
            {status !== null ? <span className={`canvas-chip ${status.tone}`}>{status.label}</span> : null}
          </div>
        ) : null}
      </header>

      {activeJob !== null ? (
        <div className="canvas-progress" role="status" aria-live="polite" data-job-kind={activeJob.job.kind} data-job-state={activeJob.job.status}>
          <LoaderCircle className="spin" size={15} />
          <span className="canvas-progress-phase">{humanPhase(activeJob.job.phase || activeJob.job.kind)}</span>
          <span className="canvas-progress-track"><span style={{ width: `${activeJob.job.progress}%` }} /></span>
          <span className="canvas-progress-pct">{Math.round(activeJob.job.progress)}%</span>
          {activeJob.job.status === "running" || activeJob.job.status === "queued" ? (
            <button className="canvas-progress-cancel" onClick={() => void actions.cancelJob()} disabled={activeJob.cancelling}>
              {activeJob.cancelling ? "Cancelling…" : "Cancel"}
            </button>
          ) : null}
        </div>
      ) : null}

      <nav className="canvas-dock" aria-label="Conversion commands">
        <button className="dock-btn" onClick={openFilePicker} title={state.source === null ? "Open a mesh" : "Replace the mesh"} aria-label={state.source === null ? "Open a mesh" : "Replace the mesh"}>
          <FolderOpen size={17} />
        </button>

        {modes.length >= 2 ? (
          <>
            <span className="dock-sep" />
            <div className="dock-modes" role="group" aria-label="Display mode">
              {modes.map((option) => (
                <button
                  key={option.mode}
                  className={viewer.mode === option.mode ? "active" : ""}
                  aria-pressed={viewer.mode === option.mode}
                  onClick={() => setMode(option.mode)}
                >
                  {option.mode === "reconstructed" && sourceProxy ? "Proxy" : option.label}
                </button>
              ))}
            </div>
          </>
        ) : null}

        <span className="dock-sep" />
        <button className="dock-btn" onClick={fit} title="Fit to view" aria-label="Fit to view"><Focus size={17} /></button>
        <button className="dock-btn" onClick={() => view("iso")} title="Isometric view" aria-label="Isometric view"><Rotate3D size={17} /></button>
        <button className="dock-btn" onClick={toggleTheme} title="Toggle theme" aria-label="Toggle light or dark theme">
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>

        <span className="dock-sep" />
        <button
          className="dock-primary"
          onClick={onPrimary}
          disabled={action.disabled}
          title={action.reason ?? action.hint}
          data-action={action.kind}
        >
          <PrimaryIcon kind={action.kind} />
          {action.label}
        </button>
      </nav>

      <input
        ref={fileRef}
        className="visually-hidden"
        aria-label="Choose source mesh"
        type="file"
        accept=".stl,.obj,.ply"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) void actions.upload(file, vm.project.units, 1);
        }}
      />
    </main>
  );
}

function PrimaryIcon({ kind }: { kind: PipelineActionKind }) {
  const size = 16;
  if (kind === "open") return <FolderOpen size={size} />;
  if (kind === "analyze") return <ScanSearch size={size} />;
  if (kind === "reconstruct") return <Sparkles size={size} />;
  if (kind === "validate") return <ShieldCheck size={size} />;
  if (kind === "export") return <FileArchive size={size} />;
  return <Download size={size} />;
}

function fileMeta(vm: WorkspaceViewModel): string {
  const state = vm.project.state;
  const parts: string[] = [];
  if (state.diagnostics !== null) parts.push(`${state.diagnostics.triangleCount.toLocaleString()} tris`);
  if (state.cadgraph !== null) parts.push(`${state.cadgraph.features.length} features`);
  parts.push(vm.project.units);
  return parts.join(" · ");
}

function conversionStatus(vm: WorkspaceViewModel): { label: string; tone: "ok" | "warn" | "info" } | null {
  const state = vm.project.state;
  if (isValidated(state)) return { label: "Validated", tone: "ok" };
  if (state.cadgraph !== null) return { label: "Reconstructed", tone: "info" };
  if (state.patches.length > 0) return { label: "Analyzed", tone: "info" };
  return { label: "Loaded", tone: "info" };
}
