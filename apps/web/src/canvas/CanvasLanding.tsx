import { useRef } from "react";
import { Clock, FolderOpen, LoaderCircle, Sparkles } from "lucide-react";
import { Mesh2ParamLogoMark, MeshTransitionHero } from "../start/Mesh2ParamLogoMark";
import type { ProjectDetail, Readiness, SampleDescriptor } from "../state/types";
import "./canvas.css";

const SUPPORTED_SAMPLE_ID = "l-bracket-with-holes";

export interface CanvasLandingProps {
  samples: SampleDescriptor[];
  recentProjects: ProjectDetail[];
  readiness: Readiness | null;
  busy: boolean;
  error: string | null;
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
  error,
  onOpenMesh,
  onOpenSample,
  onOpenProjectFile,
  onOpenRecent,
}: CanvasLandingProps) {
  const meshRef = useRef<HTMLInputElement>(null);
  const projectRef = useRef<HTMLInputElement>(null);
  const ready = readiness?.status === "ready";
  const sample =
    samples.find((item) => item.id === SUPPORTED_SAMPLE_ID) ??
    samples.find((item) => item.automaticReconstructionSupported) ??
    samples[0];

  return (
    <main className="canvas-landing" data-testid="start-screen">
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
        <p>Upload an STL, OBJ, or PLY file and Mesh2Param reconstructs an exact, kernel-validated STEP you can download.</p>

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

        <button className="landing-link" disabled={busy} onClick={() => projectRef.current?.click()}>
          Open a saved project (.mesh2param.json)
        </button>

        {recentProjects.length > 0 ? (
          <div className="landing-recents">
            <span className="landing-recents-label"><Clock size={13} /> Recent</span>
            <div className="landing-recents-chips">
              {recentProjects.slice(0, 6).map((project) => (
                <button key={project.id} disabled={busy} onClick={() => onOpenRecent(project.id)} title={project.name}>
                  {project.name}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <footer className="landing-status">
        <span className={`landing-worker ${ready ? "up" : "down"}`}>
          <span className="dot" /> Worker {ready ? "ready" : readiness === null ? "connecting…" : "unavailable"}
        </span>
        <span className="landing-backend">OCCT backend</span>
      </footer>

      {error !== null ? <div className="global-error" role="alert">{error}</div> : null}

      <input
        ref={meshRef}
        className="visually-hidden"
        aria-label="Choose source mesh"
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
