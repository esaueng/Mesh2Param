import { useRef, useState, type DragEvent } from "react";
import { Box, Boxes, ChevronRight, Clock, FileJson, FolderOpen, LoaderCircle, ScanSearch, ShieldCheck, Sparkles, UploadCloud } from "lucide-react";
import { Mesh2ParamLogoMark, MeshTransitionHero } from "../start/Mesh2ParamLogoMark";
import type { ProjectDetail, Readiness, SampleDescriptor } from "../state/types";
import "./canvas.css";

const SUPPORTED_SAMPLE_ID = "l-bracket-with-holes";
const RECENT_DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const COUNT = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const MESH_EXTENSIONS = [".stl", ".obj", ".ply"];

/** What a dropped file would open as, by extension; null means "not a file we open". */
export function droppedFileKind(name: string): "mesh" | "project" | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".mesh2param.json") || lower.endsWith(".json")) return "project";
  if (MESH_EXTENSIONS.some((extension) => lower.endsWith(extension))) return "mesh";
  return null;
}

export type ProjectStage = "loaded" | "analyzed" | "reconstructed" | "validated";

/** How far a saved project got, read straight from its working document. */
export function projectStage(project: Pick<ProjectDetail, "state"> | { state?: undefined }): ProjectStage {
  // A summary that never carried a working document reads as merely loaded.
  const state = project.state as ProjectDetail["state"] | undefined;
  if (state === undefined) return "loaded";
  if (state.validation !== null && state.cadgraph !== null) return "validated";
  if (state.cadgraph !== null) return "reconstructed";
  if ((state.patches?.length ?? 0) > 0) return "analyzed";
  return "loaded";
}

const STAGE_LABEL: Record<ProjectStage, string> = {
  loaded: "Loaded",
  analyzed: "Analyzed",
  reconstructed: "Reconstructed",
  validated: "Validated",
};

export interface CanvasLandingProps {
  samples: SampleDescriptor[];
  recentProjects: ProjectDetail[];
  readiness: Readiness | null;
  busy: boolean;
  onOpenMesh(file: File): void;
  onOpenSample(sampleId: string): void;
  onOpenProjectFile(file: File): void;
  onOpenRecent(projectId: string): void;
}

export function CanvasLanding({
  samples,
  recentProjects,
  readiness,
  busy,
  onOpenMesh,
  onOpenSample,
  onOpenProjectFile,
  onOpenRecent,
}: CanvasLandingProps) {
  const meshRef = useRef<HTMLInputElement>(null);
  const projectRef = useRef<HTMLInputElement>(null);
  // Drag enter/leave fire for every child crossed, so a depth counter tells
  // "left the page" apart from "moved onto a button".
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [dropRejected, setDropRejected] = useState<string | null>(null);
  const ready = readiness?.status === "ready";
  const browserLocal = readiness?.executionMode === "browser-local";
  const sample =
    samples.find((item) => item.id === SUPPORTED_SAMPLE_ID) ??
    samples.find((item) => item.automaticReconstructionSupported) ??
    samples[0];
  const visibleRecentProjects = recentProjects
    .slice()
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .slice(0, 6);

  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const onDragEnter = (event: DragEvent<HTMLElement>) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragOver = (event: DragEvent<HTMLElement>) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = busy || !ready ? "none" : "copy";
  };
  const onDragLeave = (event: DragEvent<HTMLElement>) => {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = (event: DragEvent<HTMLElement>) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file === undefined || busy) return;
    const kind = droppedFileKind(file.name);
    if (kind === "project") { setDropRejected(null); onOpenProjectFile(file); return; }
    if (kind === "mesh" && ready) { setDropRejected(null); onOpenMesh(file); return; }
    setDropRejected(kind === null
      ? `${file.name} is not an STL, OBJ, PLY, or .mesh2param.json file.`
      : "The worker is not ready yet; try again once it reports ready.");
  };

  return (
    <main
      className={`canvas-landing ${dragging ? "dragging" : ""}`}
      data-testid="start-screen"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <header className="canvas-topbar">
        <div className="canvas-brand">
          <Mesh2ParamLogoMark aria-hidden />
          <strong>Mesh2Param</strong>
          <span className="canvas-badge">Beta</span>
        </div>
      </header>

      <div className="landing-center">
        <MeshTransitionHero />
        <span className="landing-eyebrow">Mesh to parametric CAD</span>
        <h1>Turn a triangle mesh into an editable CAD model.</h1>
        <p>Upload an STL, OBJ, or PLY file and Mesh2Param reconstructs a kernel-validated STEP — editable parameters where the geometry is recognized, fitted curved surfaces or a faceted fallback otherwise.</p>

        <div className="landing-actions">
          <button className="landing-primary" disabled={busy || !ready} onClick={() => meshRef.current?.click()}>
            {busy ? <LoaderCircle className="spin" size={17} /> : <FolderOpen size={17} />}
            Open a mesh
          </button>
          <button className="landing-secondary" disabled={busy || !ready || sample === undefined} onClick={() => sample && onOpenSample(sample.id)}>
            <Sparkles size={16} />
            Try the L-bracket sample
          </button>
        </div>
        <p className="landing-drop-hint" aria-hidden><UploadCloud size={14} /> or drop a mesh anywhere on this page</p>

        <button className="landing-link" disabled={busy} onClick={() => projectRef.current?.click()}>
          Open a saved project (.mesh2param.json)
        </button>
        {dropRejected !== null ? (
          <p className="landing-drop-rejected" role="status">{dropRejected}</p>
        ) : null}

        {visibleRecentProjects.length > 0 ? (
          <section className="landing-recents" aria-labelledby="recent-projects-heading">
            <h2 id="recent-projects-heading" className="landing-recents-label">
              <Clock size={13} /> Recent projects
            </h2>
            <ol className="landing-recents-list" aria-labelledby="recent-projects-heading">
              {visibleRecentProjects.map((project, index) => {
                const stage = projectStage(project);
                const diagnostics = project.state?.diagnostics ?? null;
                const featureCount = project.state?.cadgraph?.features.length ?? null;
                return (
                  <li key={project.id} className="landing-card" data-stage={stage}>
                    <button
                      disabled={busy}
                      onClick={() => onOpenRecent(project.id)}
                      title={`Open ${project.name}`}
                    >
                      <span className="landing-card-glyph" aria-hidden="true">
                        <StageGlyph stage={stage} />
                        <span className="landing-recent-index">{String(index + 1).padStart(2, "0")}</span>
                      </span>
                      <span className="landing-recent-copy">
                        <span className="landing-recent-name">{project.name}</span>
                        <span className="landing-recent-meta">
                          <span>{project.units}</span>
                          <span aria-hidden="true">·</span>
                          <time dateTime={project.updatedAt}>{formatRecentTimestamp(project.updatedAt)}</time>
                          <span aria-hidden="true">·</span>
                          <span>Revision {project.revision}</span>
                        </span>
                        <span className="landing-card-stats">
                          <span className={`canvas-chip ${stage === "validated" ? "ok" : "info"}`}>{STAGE_LABEL[stage]}</span>
                          {diagnostics !== null ? <span className="landing-card-tris">{COUNT.format(diagnostics.triangleCount)} tris</span> : null}
                          {featureCount !== null ? <span className="landing-card-tris">{featureCount} features</span> : null}
                        </span>
                      </span>
                      <ChevronRight aria-hidden="true" size={15} />
                    </button>
                  </li>
                );
              })}
            </ol>
          </section>
        ) : (
          <p className="landing-no-recents">Projects you open will be listed here.</p>
        )}
      </div>

      <footer className="landing-status">
        <span className={`landing-worker ${ready ? "up" : "down"}`}>
          <span className="dot" /> Worker {ready ? "ready" : readiness === null ? "connecting…" : "unavailable"}
        </span>
        <span className="landing-backend">
          {browserLocal ? "Local Mesh2Param core · files stay in this browser" : "OCCT backend"}
        </span>
      </footer>

      {dragging ? (
        <div className="landing-drop" aria-hidden>
          <div className="landing-drop-card">
            {busy || !ready ? <FileJson size={34} /> : <UploadCloud size={34} />}
            <strong>{busy ? "Busy opening a project" : ready ? "Drop to open" : "Worker not ready"}</strong>
            <span>STL, OBJ, PLY, or a .mesh2param.json project</span>
          </div>
        </div>
      ) : null}

      <input
        ref={meshRef}
        className="visually-hidden"
        aria-label="Choose source mesh"
        tabIndex={-1}
        type="file"
        accept=".stl,.obj,.ply"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) onOpenMesh(file);
        }}
      />
      <input
        ref={projectRef}
        className="visually-hidden"
        aria-label="Open saved project file"
        tabIndex={-1}
        type="file"
        accept=".json,application/json"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) onOpenProjectFile(file);
        }}
      />
    </main>
  );
}

function StageGlyph({ stage }: { stage: ProjectStage }) {
  if (stage === "validated") return <ShieldCheck size={20} />;
  if (stage === "reconstructed") return <Box size={20} />;
  if (stage === "analyzed") return <ScanSearch size={20} />;
  return <Boxes size={20} />;
}

function formatRecentTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "Update time unavailable" : RECENT_DATE_FORMATTER.format(date);
}
