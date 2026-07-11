import { FileBox, FilePlus2, FolderOpen, LoaderCircle } from "lucide-react";
import { useRef } from "react";
import type { ProjectDetail, Readiness, SampleDescriptor } from "../state/types";
import { PRODUCT } from "../config/product";
import { Mesh2ParamLogoMark, MeshTransitionHero } from "./Mesh2ParamLogoMark";
import "./start.css";

const SAMPLE_ORDER = ["l-bracket-with-holes", "pocketed-mounting-plate", "flange", "shaft-collar", "stepped-turned-part"];
const PRESENTATION_NAMES: Record<string, string> = { "l-bracket-with-holes": "Bracket with holes" };

export interface StartScreenProps {
  samples: SampleDescriptor[];
  recentProjects: ProjectDetail[];
  readiness: Readiness | null;
  busy: boolean;
  error: string | null;
  onNew(): void;
  onOpen(file: File): void;
  onOpenRecent(projectId: string): void;
  onOpenSample(sampleId: string): void;
}

export function StartScreen({ samples, recentProjects, readiness, busy, error, onNew, onOpen, onOpenRecent, onOpenSample }: StartScreenProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  const featured = SAMPLE_ORDER.flatMap((id) => {
    const found = samples.find((item) => item.id === id);
    return found ? [found] : [];
  });
  return (
    <main className="start-screen" data-testid="start-screen" onKeyDown={(event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") { event.preventDefault(); onNew(); }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "o") { event.preventDefault(); fileRef.current?.click(); }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "l") { event.preventDefault(); tableRef.current?.focus(); }
    }}>
      <section className="start-main" aria-labelledby="mesh2param-title">
        <div className="start-brand">
          <MeshTransitionHero />
          <div className="start-title-row"><Mesh2ParamLogoMark/><h1 id="mesh2param-title">{PRODUCT.name}</h1></div>
          <p>{PRODUCT.tagline}</p>
        </div>
        <div className="start-content">
          <div className="start-left-column">
            <div className="start-actions" aria-label="Project actions">
              <button className="start-action primary" onClick={onNew} disabled={busy}><FilePlus2 aria-hidden="true"/><strong>New conversion</strong><kbd>Ctrl+N</kbd></button>
              <button className="start-action" onClick={() => fileRef.current?.click()} disabled={busy}><FolderOpen aria-hidden="true"/><strong>Open project</strong><kbd>Ctrl+O</kbd></button>
              <button className="start-action" onClick={() => tableRef.current?.focus()} disabled={!featured.length || busy || readiness?.status !== "ready"}><FileBox aria-hidden="true"/><strong>Load sample</strong><kbd>Ctrl+L</kbd></button>
              <input ref={fileRef} className="visually-hidden" type="file" accept=".mesh2param.json,.json,application/json" aria-label="Open Mesh2Param project file" onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) onOpen(file); }}/>
            </div>
            <section className="recent-list" aria-labelledby="recent-title">
              <h2 id="recent-title">Recent projects</h2>
              {recentProjects.slice(0, 3).map((project) => <button key={project.id} onClick={() => onOpenRecent(project.id)}><FileBox aria-hidden="true"/><span><strong>{project.name}</strong><small>{new Date(project.updatedAt).toLocaleString()}</small></span><span className="recent-state">Local</span></button>)}
              {!recentProjects.length ? <p>No recent projects</p> : null}
            </section>
            {error ? <p className="start-error" role="alert">{error}</p> : null}
          </div>
          <section className="sample-panel" aria-labelledby="sample-title">
            <h2 id="sample-title">Load sample</h2>
            <div className="sample-table" role="table" aria-label="Procedural samples" ref={tableRef} tabIndex={-1}>
              <div role="row" className="sample-header"><span role="columnheader">Name</span><span role="columnheader">Triangles</span><span role="columnheader">Intended operations</span><span role="columnheader">Tolerance</span></div>
              {featured.map((sample) => <SampleRow key={sample.id} sample={sample} disabled={busy || readiness?.status !== "ready"} onOpen={() => onOpenSample(sample.id)}/>) }
              {!featured.length ? <div className="sample-loading" role="status"><LoaderCircle aria-hidden="true"/>Loading real samples…</div> : null}
            </div>
          </section>
        </div>
      </section>
      <footer className="start-footer">
        <div><span>Version {PRODUCT.version}</span><span>Schema {PRODUCT.schemaVersion}</span></div>
        <div><span>Local first</span><span>No login</span></div>
        <div><span>CAD backend: {PRODUCT.cadBackend}</span><span className={readiness?.status === "ready" ? "ready" : "checking"}>{readiness?.status === "ready" ? "Worker ready" : readiness ? "Worker unavailable" : "Checking worker"}</span></div>
      </footer>
    </main>
  );
}

function SampleRow({ sample, disabled, onOpen }: { sample: SampleDescriptor; disabled: boolean; onOpen(): void }) {
  const name = PRESENTATION_NAMES[sample.id] ?? sample.name;
  const triangles = sample.triangleCount.toLocaleString();
  const operations = sample.intendedOperations.join(", ");
  const tolerance = `${sample.toleranceMm.toFixed(2)} mm`;
  return <button className="sample-row" role="row" aria-label={`Open ${name} sample`} onClick={onOpen} disabled={disabled}>
    <span role="cell" className="sample-name"><img src={sample.thumbnailUrl} alt=""/><strong>{name}</strong></span>
    <span role="cell" className="mono">{triangles}</span><span role="cell">{operations}</span><span role="cell" className="mono">{tolerance}</span>
  </button>;
}
