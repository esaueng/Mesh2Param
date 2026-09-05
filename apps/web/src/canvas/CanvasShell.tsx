import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  AlertTriangle,
  Box,
  ChevronUp,
  Download,
  FileArchive,
  FolderOpen,
  Focus,
  Keyboard,
  Layers,
  LoaderCircle,
  Moon,
  RefreshCw,
  Save,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Spline,
  Sun,
  TerminalSquare,
} from "lucide-react";
import { apiClient } from "../api/client";
import { apiFetch } from "../api/auth";
import { releaseAfterDownloadStarts } from "../persistence/objectUrl";
import { Mesh2ParamLogoMark } from "../start/Mesh2ParamLogoMark";
import { useWorkspaceSelector, workspaceStore } from "../state/store";
import type { ViewerMode } from "../state/types";
import { CadViewport } from "../viewer/CadViewport";
import { PatchPanel } from "./PatchPanel";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { debugLog, useDebugLog } from "./debugLog";
import { clampConsoleHeight, DebugConsole } from "./DebugConsole";
import { artifactDownloadName, stepDownloadName } from "./downloadFilename";
import { EditableProjectName } from "./EditableProjectName";
import { JobFailure, latestFailedJob } from "./JobFailure";
import { EmptyState, PanelSkeleton } from "./PanelStates";
import { NARROW_LAYOUT_QUERY, useMediaQuery } from "./useMediaQuery";
import { analysisMeta, diagnosticRows, fileMeta } from "./meshReadout";
import { panelLayoutStore, usePanelLayout } from "./panelLayout";
import { PanelResizeHandle } from "./PanelResizeHandle";
import { PanelSection } from "./PanelSection";
import { ShortcutHelp } from "./ShortcutHelp";
import { ViewSettings } from "./ViewSettings";
import {
  analysisRerunAction,
  availableModes,
  humanPhase,
  isValidated,
  nextAction,
  regenerationAction,
  reconstructedRevealPreferences,
  type PipelineActionKind,
  stepArtifact,
} from "./pipeline";
import "./canvas.css";

export function CanvasShell({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const viewer = useWorkspaceSelector((state) => state.viewer);
  const shell = useWorkspaceSelector((state) => state.shell);
  const theme = shell.theme;
  // The console reuses the shell's persisted bottom-drawer slots, so its open
  // state and height survive a reload like any other docked tool window.
  const consoleOpen = shell.bottomDrawerExpanded;
  const consoleHeight = clampConsoleHeight(shell.bottomDrawerHeight);
  const layout = usePanelLayout();
  const jobs = useWorkspaceSelector((state) => state.jobs);
  const narrow = useMediaQuery(NARROW_LAYOUT_QUERY);
  // Narrow layout: the panel is a bottom sheet that peeks its Convert footer
  // and opens over the viewport on demand. Not persisted; a sheet reopening
  // itself on every reload would cover the model.
  const [sheetOpen, setSheetOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const revealedKey = `mesh2param-revealed-${vm.project.id}`;
  const revealed = sessionStorage.getItem(revealedKey) === "1";
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  // Pointer hover over a patch, shared by the viewport and the patch list so
  // each mirrors the other. Rendering only; selection stays in the store.
  const [hoveredPatchId, setHoveredPatchId] = useState<string | null>(null);
  const [recoverFullDetailsProject, setRecoverFullDetailsProject] = useState<string | null>(null);
  const recoverFullDetails = recoverFullDetailsProject === vm.project.id;
  const logs = useDebugLog();
  const issueCount = logs.filter((entry) => entry.level === "error" || entry.level === "warn").length;

  const state = vm.project.state;
  const action = nextAction(vm);
  const rerunAnalysis = analysisRerunAction(vm);
  const regenerate = regenerationAction(vm);
  const modes = availableModes(vm.artifacts);
  const activeJob = vm.activeJob;
  const hiddenPatchIds = useMemo(
    () => state.patches.filter((patch) => patch.hidden === true).map((patch) => patch.id).sort(),
    [state.patches],
  );

  const setMode = useCallback((mode: ViewerMode) => {
    debugLog.debug("view", `Display mode -> ${mode}`);
    const store = workspaceStore.getState();
    if (mode === "overlay") store.setViewerPreferences({ mode, sourceOpacity: 0.35, resultOpacity: 1 });
    else if (mode === "source") store.setViewerPreferences({ mode, sourceOpacity: 1 });
    else store.setViewerPreferences({ mode, resultOpacity: 1 });
  }, []);

  // Trace the guided pipeline stage (and why it's blocked) into the console.
  useEffect(() => {
    debugLog.debug("pipeline", `Stage: ${action.label}${action.disabled ? " (unavailable)" : ""}`);
  }, [action.label, action.disabled]);
  useEffect(() => {
    if (action.disabled && action.reason) debugLog.warn("pipeline", `${action.label} unavailable`, action.reason);
  }, [action.disabled, action.reason, action.label]);
  useEffect(() => {
    const open = () => setShortcutsOpen(true);
    window.addEventListener("mesh2param:shortcut-help", open);
    return () => window.removeEventListener("mesh2param:shortcut-help", open);
  }, []);

  // Reveal the clean reconstructed result the first time it becomes available.
  // Persist the "already revealed" flag per project in sessionStorage so a reload
  // does not clobber user-customized viewer preferences (mode, shading, edges).
  useEffect(() => {
    const names = new Set(vm.artifacts.map((artifact) => artifact.name));
    if (revealed || !names.has("reconstructed.glb")) return;
    sessionStorage.setItem(revealedKey, "1");
    const store = workspaceStore.getState();
    debugLog.debug("view", "Showing reconstructed result as shaded analytic CAD");
    store.setViewerPreferences(reconstructedRevealPreferences());
  }, [vm.artifacts, revealed, revealedKey]);

  const fit = () => window.dispatchEvent(new Event("mesh2param:fit-view"));
  const toggleTheme = () => workspaceStore.getState().setShellState({ theme: theme === "dark" ? "light" : "dark" });
  const setConsoleOpen = (open: boolean) => workspaceStore.getState().setShellState({ bottomDrawerExpanded: open });
  const setConsoleHeight = (height: number) => workspaceStore.getState().setShellState({ bottomDrawerHeight: height });

  const openFilePicker = () => fileRef.current?.click();

  const downloadArtifact = useCallback(async (artifactName: string) => {
    const artifact = vm.artifacts.find((candidate) => candidate.name === artifactName);
    if (artifact === undefined) return;
    const filename = artifactName === stepArtifact(vm.artifacts)?.name
      ? stepDownloadName(vm.project.name, artifact.name)
      : artifactDownloadName(vm.project.name, artifact.name);
    // Fetch as a blob so our project-derived filename wins over the server's
    // Content-Disposition (which names every export "model.step").
    try {
      const response = await apiFetch(apiClient.artifactUrl(vm.project.id, artifact.name, artifact.sha256));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      releaseAfterDownloadStarts(objectUrl);
      debugLog.info("export", `Downloaded ${filename}`, { bytes: blob.size, artifact: artifact.name });
    } catch (cause) {
      debugLog.error("export", `Download failed: ${filename}`, cause);
    }
  }, [vm.artifacts, vm.project.id, vm.project.name]);

  const downloadStep = useCallback(async () => {
    const step = stepArtifact(vm.artifacts);
    if (step !== undefined) await downloadArtifact(step.name);
  }, [downloadArtifact, vm.artifacts]);

  const onPrimary = () => {
    if (action.kind === "open") openFilePicker();
    else if (action.kind === "download") void downloadStep();
    else if (action.operation !== undefined) {
      const settings = action.kind === "reconstruct"
        && action.settings === undefined
        && recoverFullDetails
        ? { detailMode: "full" }
        : action.settings;
      void actions.run(action.operation, settings);
    }
  };

  const onRegenerate = () => {
    if (regenerate?.operation !== undefined) void actions.run(regenerate.operation, regenerate.settings);
  };

  const onRerunAnalysis = () => {
    if (rerunAnalysis?.operation !== undefined) void actions.run(rerunAnalysis.operation, rerunAnalysis.settings);
  };

  const status = conversionStatus(vm);
  const failedJob = activeJob === null ? latestFailedJob(jobs) : null;
  const analyzing = activeJob !== null && (activeJob.job.kind === "analyze" || activeJob.job.kind === "upload" || activeJob.job.kind === "sample_open");
  const canAnalyze = state.source !== null && activeJob === null && vm.workerReady;
  const hasGeometry = vm.artifacts.some((artifact) => artifact.name.toLowerCase().endsWith(".glb"));
  // The "result" is a preserved-source facet proxy (not exact B-Rep) when reconstruction fell back to faceting.
  const sourceProxy = vm.artifacts.some((artifact) => artifact.name === "reconstructed.glb" && artifact.kind === "preserved-source-proxy");

  return (
    <main
      className={`canvas-shell ${theme === "light" ? "theme-light" : ""}`}
      data-theme={theme}
      style={{ "--panel-width": `${layout.width}px` } as CSSProperties}
    >
      <a
        className="skip-link"
        href="#canvas-viewport"
        onClick={() => {
          // Fragment navigation alone only moves focus when the target is
          // focusable, and Safari does not move it even then.
          document.getElementById("canvas-viewport")?.focus();
        }}
      >
        Skip to 3D viewport
      </a>
      <header className="canvas-topbar">
        <button className="canvas-brand" onClick={actions.openStart} aria-label="Back to start screen">
          <Mesh2ParamLogoMark aria-hidden />
          <strong>Mesh2Param</strong>
          <span className="canvas-badge">Beta</span>
        </button>
        {state.source !== null ? (
          <div className="canvas-file">
            <EditableProjectName value={vm.project.name} onCommit={actions.renameProject} />
            {status !== null ? <span className={`canvas-chip ${status.tone}`}>{status.label}</span> : null}
          </div>
        ) : null}
        {state.source !== null ? <span className="canvas-file-meta">{fileMeta(vm)}</span> : null}
      </header>

      <div
        className={`canvas-main ${consoleOpen && layout.consoleDocked ? "console-docked" : ""}`}
        style={{ "--console-height": `${consoleHeight}px` } as CSSProperties}
      >
        <div id="canvas-viewport" className="canvas-stage" tabIndex={-1}>
          {hasGeometry ? (
            <CadViewport
              chrome="minimal"
              projectId={vm.project.id}
              units={vm.project.units}
              artifacts={vm.artifacts}
              preferences={viewer}
              theme={theme}
              denseMesh={(state.diagnostics?.triangleCount ?? 0) > 20_000}
              sourceProxyActive={sourceProxy}
              hiddenPatchIds={hiddenPatchIds}
              selectedPatchId={vm.selectedPatchId}
              hoveredPatchId={hoveredPatchId}
              grid={layout.grid}
              onPreferences={(patch) => workspaceStore.getState().setViewerPreferences(patch)}
              onSelectPatch={actions.selectPatch}
              onHoverPatch={setHoveredPatchId}
            />
          ) : (
            <div
              className={`canvas-empty ${activeJob !== null ? "canvas-empty-loading" : ""}`}
              role={activeJob !== null ? "status" : undefined}
              aria-live={activeJob !== null ? "polite" : undefined}
            >
              {activeJob !== null ? (
                <>
                  <LoaderCircle className="spin" size={40} strokeWidth={1.25} />
                  <strong>{humanPhase(activeJob.job.phase || activeJob.job.kind)}</strong>
                  <p>Preparing the 3D preview…</p>
                </>
              ) : state.source === null ? (
                <>
                  <Box size={40} strokeWidth={1.25} />
                  <strong>No mesh loaded</strong>
                  <p>Open an STL, OBJ, or PLY to begin.</p>
                  <button className="landing-secondary" onClick={openFilePicker}><FolderOpen size={16} />Open a mesh</button>
                </>
              ) : (
                <>
                  <Box size={40} strokeWidth={1.25} />
                  <strong>Mesh loaded</strong>
                  <p>Run <b>{action.label}</b> to view the {state.patches.length > 0 ? "geometry" : "mesh and its surfaces"}.</p>
                </>
              )}
            </div>
          )}
          {hasGeometry ? (
            <div className="viewport-display-toolbar">
              <ViewSettings
                shading={viewer.shading}
                edges={viewer.edges}
                grid={layout.grid}
                onPreferences={(patch) => workspaceStore.getState().setViewerPreferences(patch)}
                onGridChange={(grid) => panelLayoutStore.setGrid(grid)}
              />
            </div>
          ) : null}
          {activeJob !== null ? (
            <div
              className="canvas-progress canvas-progress-viewport"
              role="status"
              aria-live="polite"
              data-job-kind={activeJob.job.kind}
              data-job-state={activeJob.job.status}
            >
              <span className="canvas-progress-track"><span style={{ width: `${activeJob.job.progress}%` }} /></span>
              <div className="canvas-progress-pill">
                <LoaderCircle className="spin" size={14} />
                <span className="canvas-progress-phase">{humanPhase(activeJob.job.phase || activeJob.job.kind)}</span>
                <span className="canvas-progress-pct">{Math.round(activeJob.job.progress)}%</span>
                {activeJob.job.status === "running" || activeJob.job.status === "queued" ? (
                  <button className="canvas-progress-cancel" onClick={() => void actions.cancelJob()} disabled={activeJob.cancelling}>
                    {activeJob.cancelling ? "Cancelling…" : "Cancel"}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        {consoleOpen ? (
          <DebugConsole
            docked={layout.consoleDocked}
            height={consoleHeight}
            onDockedChange={(docked) => panelLayoutStore.setConsoleDocked(docked)}
            onHeightChange={setConsoleHeight}
            onClose={() => setConsoleOpen(false)}
          />
        ) : null}
        {shortcutsOpen ? <ShortcutHelp onClose={() => setShortcutsOpen(false)} /> : null}
      </div>

      <nav
        className={`canvas-panel ${narrow ? "sheet" : ""} ${narrow && sheetOpen ? "open" : ""}`.trim()}
        aria-label="Conversion commands"
        data-sheet={narrow ? (sheetOpen ? "open" : "peek") : undefined}
      >
        <PanelResizeHandle />
        {narrow ? (
          <button
            type="button"
            className="panel-sheet-handle"
            aria-expanded={sheetOpen}
            aria-controls="panel-scroll"
            onClick={() => setSheetOpen((open) => !open)}
          >
            <span className="panel-sheet-grip" aria-hidden />
            <ChevronUp size={14} aria-hidden className="panel-sheet-chevron" />
            {sheetOpen ? "Hide tools" : "Show tools"}
          </button>
        ) : null}
        <div className="panel-scroll" id="panel-scroll" hidden={narrow && !sheetOpen}>
        <PanelSection id="file" title="File">
          <button className="panel-btn" onClick={openFilePicker} title={state.source === null ? "Open a mesh" : "Replace the mesh"}>
            <FolderOpen size={16} />
            {state.source === null ? "Open a mesh…" : "Replace mesh…"}
          </button>
          <button className="panel-btn" onClick={() => void actions.saveProject()} title="Save project">
            <Save size={16} />
            Save project
          </button>
        </PanelSection>

        <PanelSection id="view" title="View" className="panel-view-group">
          {modes.length >= 2 ? (
            <div className="panel-modes" role="group" aria-label="Display">
              {modes.map((option) => (
                <button
                  key={option.mode}
                  className={viewer.mode === option.mode ? "active" : ""}
                  aria-pressed={viewer.mode === option.mode}
                  onClick={() => setMode(option.mode)}
                >
                  {option.mode === "reconstructed" && sourceProxy ? "Converted" : option.label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="panel-view-grid">
            <button className="panel-btn" onClick={fit} title="Fit to view"><Focus size={16} />Fit view</button>
            <button className="panel-btn" onClick={toggleTheme} title="Toggle light or dark theme" aria-label="Toggle light or dark theme">
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <button
              className={`panel-btn ${consoleOpen ? "active" : ""} ${issueCount > 0 ? "has-issues" : ""}`}
              onClick={() => setConsoleOpen(!consoleOpen)}
              title="Toggle debug console"
              aria-pressed={consoleOpen}
            >
              <TerminalSquare size={16} />
              Console
              {issueCount > 0 ? <span className="panel-count">{issueCount > 99 ? "99+" : issueCount}</span> : null}
            </button>
            <button className="panel-btn" onClick={() => setShortcutsOpen(true)} title="Keyboard shortcuts">
              <Keyboard size={16} />
              Shortcuts
            </button>
          </div>
        </PanelSection>

        {state.source !== null && state.diagnostics === null && state.cadgraph === null ? (
          <PanelSection id="analysis" title="Analysis" className={analyzing ? "is-busy" : ""}>
            {analyzing ? (
              <PanelSkeleton rows={6} label={`${humanPhase(activeJob?.job.phase || "analyze")}…`} />
            ) : (
              <EmptyState
                icon={<ScanSearch size={22} />}
                title="Not analyzed yet"
                hint="Mesh health, surface patches, and fit residuals appear here after analysis."
                action={{
                  label: "Analyze mesh",
                  onClick: () => void actions.run("analyze"),
                  disabled: !canAnalyze,
                  title: canAnalyze ? "Run the analysis job" : "Wait for the worker and the running job",
                }}
                testId="analysis-empty"
              />
            )}
          </PanelSection>
        ) : null}
        {state.diagnostics !== null || state.cadgraph !== null ? (
          <PanelSection id="analysis" title="Analysis" meta={analysisMeta(vm)} className={analyzing ? "is-busy" : ""}>
            {state.diagnostics !== null ? (
              <dl className="panel-readout" aria-label="Mesh diagnostics">
                {diagnosticRows(state.diagnostics, vm.project.units).map((row) => (
                  <div key={row.label} className={row.tone === undefined ? undefined : `tone-${row.tone}`}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {state.diagnostics !== null && state.diagnostics.warnings.length > 0 ? (
              <ul className="panel-warnings" aria-label="Mesh warnings">
                {state.diagnostics.warnings.map((warning) => (
                  <li key={warning.code} className="panel-hint warn">
                    <AlertTriangle size={13} />
                    <span>{warning.message}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {state.cadgraph !== null ? (
              <div className="panel-feature-list" role="group" aria-label="Features">
                {[...state.cadgraph.features]
                  .sort((left, right) => left.order - right.order)
                  .map((feature) => (
                    <button
                      key={feature.id}
                      className={vm.selectedFeatureId === feature.id ? "active" : ""}
                      aria-pressed={vm.selectedFeatureId === feature.id}
                      aria-label={`${feature.name}, ${humanPhase(feature.operation)}, step ${feature.order + 1}`}
                      onClick={() => actions.selectFeature(feature.id)}
                    >
                      <span>{feature.order + 1}</span>
                      <strong>{feature.name}</strong>
                      <small>{humanPhase(feature.operation)}</small>
                    </button>
                  ))}
              </div>
            ) : null}
            {state.cadgraph !== null && detailEvidence(state.cadgraph.extensions) !== null ? (
              <p className="panel-hint info" role="note" data-testid="detail-evidence">
                <Layers size={13} />
                <span>{detailEvidence(state.cadgraph.extensions)}</span>
              </p>
            ) : null}
          </PanelSection>
        ) : null}

        {state.patches.length === 0 && state.cadgraph === null && state.diagnostics !== null ? (
          <PanelSection id="patches" title="Patches" className={analyzing ? "is-busy" : ""}>
            {analyzing ? (
              <PanelSkeleton rows={5} label="Segmenting surfaces…" />
            ) : (
              <EmptyState
                icon={<ScanSearch size={22} />}
                title="Not analyzed yet"
                hint="Surface patches, their fits, and residuals appear here after analysis."
                action={{
                  label: "Analyze mesh",
                  onClick: () => void actions.run("analyze"),
                  disabled: !canAnalyze,
                  title: canAnalyze ? "Run the analysis job" : "Wait for the worker and the running job",
                }}
                testId="patches-empty"
              />
            )}
          </PanelSection>
        ) : null}
        {state.patches.length > 0 && state.cadgraph === null ? (
          <PatchPanel
            patches={state.patches}
            selectedPatchId={vm.selectedPatchId}
            hoveredPatchId={hoveredPatchId}
            disabled={activeJob !== null}
            onSelect={actions.selectPatch}
            onHover={setHoveredPatchId}
            onUpdate={(patchId, patch) => void actions.updatePatch(patchId, patch)}
            onMerge={(patchIds) => void actions.mergePatches(patchIds)}
          />
        ) : null}

        </div>

        <PanelSection id="convert" title="Convert" className="panel-convert" meta={activeJob !== null ? `${Math.round(activeJob.job.progress)}%` : undefined}>
          {(collapsed) => (
          <>
          {failedJob !== null && !collapsed ? (
            <JobFailure
              view={failedJob}
              canRetry={vm.workerReady && activeJob === null}
              onRetry={(operation) => {
                workspaceStore.getState().clearJob(failedJob.job.kind);
                void actions.run(operation);
              }}
              onDismiss={() => workspaceStore.getState().clearJob(failedJob.job.kind)}
            />
          ) : null}
          {activeJob !== null ? (
            <button className="dock-primary" disabled data-action={action.kind} data-job-kind={activeJob.job.kind}>
              <LoaderCircle className="spin" size={16} />
              {humanPhase(activeJob.job.phase || activeJob.job.kind)}…
            </button>
          ) : (
            <>
              {!collapsed && action.kind === "reconstruct" && action.settings === undefined ? (
                <button
                  className={`panel-btn ${recoverFullDetails ? "active" : ""}`}
                  aria-pressed={recoverFullDetails}
                  onClick={() => setRecoverFullDetailsProject((projectId) => (
                    projectId === vm.project.id ? null : vm.project.id
                  ))}
                  title="Recover qualifying cap-attached loops as editable shallow features"
                >
                  <Layers size={14} />
                  Full detail recovery
                </button>
              ) : null}
              {!collapsed && (rerunAnalysis !== null || regenerate !== null) ? (
                <div className="panel-secondary-grid">
                  {rerunAnalysis !== null ? (
                    <button
                      className="panel-btn"
                      onClick={onRerunAnalysis}
                      disabled={rerunAnalysis.disabled}
                      title={rerunAnalysis.reason ?? rerunAnalysis.hint}
                    >
                      <ScanSearch size={14} />
                      Analysis
                    </button>
                  ) : null}
                  {regenerate !== null ? (
                    <button
                      className="panel-btn"
                      onClick={onRegenerate}
                      disabled={regenerate.disabled}
                      title={regenerate.reason ?? regenerate.hint}
                    >
                      <RefreshCw size={14} />
                      STEP
                    </button>
                  ) : null}
                </div>
              ) : null}
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
              {!collapsed && action.alternate !== undefined ? (
                <button
                  className="panel-btn"
                  onClick={() => {
                    const alternate = action.alternate;
                    if (alternate?.operation !== undefined) void actions.run(alternate.operation, alternate.settings);
                  }}
                  disabled={action.alternate.disabled}
                  title={action.alternate.reason ?? action.alternate.hint}
                  data-action={action.alternate.kind}
                >
                  <PrimaryIcon kind={action.alternate.kind} />
                  {action.alternate.label}
                </button>
              ) : null}
              {!collapsed && (action.reason !== undefined || action.kind === "faceted" || action.kind === "curved") ? (
                <p className={`panel-hint ${action.disabled ? "warn" : "info"}`} role="status">
                  <AlertTriangle size={13} />
                  <span>{action.reason ?? action.hint}</span>
                </p>
              ) : null}
              {!collapsed && curvedEvidence(state) !== null ? (
                <p className="panel-hint info" role="note" data-testid="curved-evidence">
                  <Spline size={13} />
                  <span>{curvedEvidence(state)}</span>
                </p>
              ) : null}
            </>
          )}
          {!collapsed && action.kind === "download" ? (
            <div className="panel-export-group">
              <span className="panel-export-label">Mesh downloads</span>
              <div className="panel-export-formats" role="group" aria-label="Mesh export formats">
                {(["glb", "stl", "obj"] as const).map((format) => {
                  const name = `reconstructed.${format}`;
                  const label = `Download ${format.toUpperCase()}`;
                  if (!vm.artifacts.some((artifact) => artifact.name === name)) return null;
                  return (
                    <button
                      key={format}
                      className="panel-btn"
                      aria-label={label}
                      title={label}
                      onClick={() => void downloadArtifact(name)}
                    >
                      <Download size={14} />
                      <span>{format.toUpperCase()}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          </>
          )}
        </PanelSection>
      </nav>

      <input
        ref={fileRef}
        className="visually-hidden"
        aria-label="Choose source mesh"
        tabIndex={-1}
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
  if (kind === "curved") return <Spline size={size} />;
  if (kind === "faceted") return <Layers size={size} />;
  if (kind === "validate") return <ShieldCheck size={size} />;
  if (kind === "export") return <FileArchive size={size} />;
  return <Download size={size} />;
}

export function conversionStatus(vm: WorkspaceViewModel): { label: string; tone: "ok" | "warn" | "info" } | null {
  const state = vm.project.state;
  if (isValidated(state) && state.validation?.toleranceSatisfied === false) {
    return { label: "Validated · functional approximation", tone: "warn" };
  }
  if (vm.artifacts.some((artifact) => (
    artifact.name === "reconstructed.glb" && artifact.kind === "preserved-source-proxy"
  ))) return { label: "Faceted STEP", tone: "warn" };
  if (vm.artifacts.some((artifact) => (
    artifact.name === "reconstructed.glb" && artifact.kind === "reconstructed-curved"
  ))) return isValidated(state)
      ? { label: "Validated · approximate curved", tone: "ok" }
      : { label: "Approximate curved B-Rep", tone: "info" };
  const operation = state.cadgraph?.features[0]?.operation;
  const flavor = operation === "reconstructedSurfaceNetwork"
    ? " · approximate curved"
    : operation === "importedFaceted"
      ? " · faceted"
      : "";
  if (isValidated(state)) return { label: `Validated${flavor}`, tone: "ok" };
  if (state.cadgraph !== null) {
    if (operation === "reconstructedSurfaceNetwork") {
      return { label: "Approximate curved B-Rep", tone: "info" };
    }
    if (operation === "importedFaceted") {
      return { label: "Faceted (non-parametric)", tone: "info" };
    }
    return { label: "Reconstructed", tone: "info" };
  }
  if (state.patches.length > 0) return { label: "Analyzed", tone: "info" };
  return { label: "Loaded", tone: "info" };
}

/** A one-line evidence summary for a completed approximate curved reconstruction. */
function curvedEvidence(state: WorkspaceViewModel["project"]["state"]): string | null {
  const raw = state.settings["curvedReconstruction"];
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const record = raw as { faceSurfaces?: unknown; residualMaximumMm?: unknown };
  const faces = record.faceSurfaces;
  const residual = record.residualMaximumMm;
  if (faces === null || typeof faces !== "object" || typeof residual !== "number") return null;
  const counts = Object.entries(faces as Record<string, unknown>)
    .filter(([, count]) => typeof count === "number" && count > 0)
    .map(([kind, count]) => `${String(count)} ${kind}`)
    .join(", ");
  return `Approximate curved B-Rep: ${counts} faces · max deviation ${residual.toFixed(3)} mm. Design history is not recovered.`;
}

function detailEvidence(extensions: unknown): string | null {
  if (extensions === null || typeof extensions !== "object" || Array.isArray(extensions)) return null;
  const raw = (extensions as Record<string, unknown>)["mesh2param.dev/prismaticReconstruction"];
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const record = raw as Record<string, unknown>;
  const recovery = record.detailRecovery;
  if (recovery !== null && typeof recovery === "object" && !Array.isArray(recovery)) {
    const regions = (recovery as Record<string, unknown>).regions;
    if (Array.isArray(regions) && regions.length > 0) {
      return `${regions.length} shallow additive ${regions.length === 1 ? "detail" : "details"} recovered from bounded loop evidence.`;
    }
  }
  const suppressed = record.suppressedRegions;
  if (Array.isArray(suppressed) && suppressed.length > 0) {
    return `${suppressed.length} shallow ${suppressed.length === 1 ? "region" : "regions"} suppressed for functional validation; use the Suppressed view to inspect residuals.`;
  }
  return null;
}
