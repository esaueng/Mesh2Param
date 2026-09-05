import type { MeshDiagnostics } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";

/** Top-bar and Analysis-section readouts derived from project state. */

const measure = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const count = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

export function fileMeta(vm: WorkspaceViewModel): string {
  const state = vm.project.state;
  const parts: string[] = [];
  if (state.diagnostics !== null) {
    const [width, depth, height] = state.diagnostics.boundingDimensions;
    parts.push(`${count.format(state.diagnostics.triangleCount)} tris`);
    parts.push(`${measure.format(width)} × ${measure.format(depth)} × ${measure.format(height)} ${vm.project.units}`);
  } else {
    parts.push(vm.project.units);
  }
  if (state.cadgraph !== null) parts.push(`${state.cadgraph.features.length} features`);
  return parts.join(" · ");
}

export function analysisMeta(vm: WorkspaceViewModel): string | undefined {
  const state = vm.project.state;
  if (state.cadgraph !== null) return `${state.cadgraph.features.length} features`;
  if (state.patches.length > 0) return `${state.patches.length} patches`;
  return undefined;
}

interface ReadoutRow {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}

/** Mesh health, straight from the ingest diagnostics; nothing here is inferred. */
export function diagnosticRows(diagnostics: MeshDiagnostics, units: string): ReadoutRow[] {
  const rows: ReadoutRow[] = [
    { label: "Triangles", value: count.format(diagnostics.triangleCount) },
    {
      label: "Vertices",
      value: diagnostics.duplicateVertexCount > 0
        ? `${count.format(diagnostics.weldedVertexCount)} (${count.format(diagnostics.rawVertexCount)} raw)`
        : count.format(diagnostics.weldedVertexCount),
    },
    // A measurement only gets a row when the engine that produced these
    // diagnostics actually made it; a missing one is never shown as passing.
    ...(diagnostics.connectedComponentCount === null ? [] : [{
      label: "Bodies",
      value: count.format(diagnostics.connectedComponentCount),
      ...(diagnostics.connectedComponentCount > 1 ? { tone: "warn" as const } : {}),
    }]),
    { label: "Watertight", value: diagnostics.watertight ? "yes" : "no", tone: diagnostics.watertight ? "ok" : "warn" },
    ...(diagnostics.windingConsistent === null ? [] : [{
      label: "Winding",
      value: diagnostics.windingConsistent ? "consistent" : "inconsistent",
      tone: diagnostics.windingConsistent ? "ok" as const : "warn" as const,
    }]),
  ];
  if (diagnostics.openBoundaryEdgeCount !== null && diagnostics.openBoundaryEdgeCount > 0) {
    rows.push({ label: "Open edges", value: count.format(diagnostics.openBoundaryEdgeCount), tone: "warn" });
  }
  if (diagnostics.nonManifoldEdgeCount > 0) rows.push({ label: "Non-manifold", value: count.format(diagnostics.nonManifoldEdgeCount), tone: "warn" });
  if (diagnostics.degenerateTriangleCount > 0) rows.push({ label: "Degenerate", value: count.format(diagnostics.degenerateTriangleCount), tone: "warn" });
  rows.push({ label: "Area", value: `${measure.format(diagnostics.surfaceArea)} ${units}²` });
  rows.push({ label: "Volume", value: diagnostics.closedVolume === null ? "— (open mesh)" : `${measure.format(diagnostics.closedVolume)} ${units}³` });
  return rows;
}
