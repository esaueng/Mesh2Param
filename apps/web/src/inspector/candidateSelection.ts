import { isCADGraph, type CADGraph } from "@mesh2param/contracts";
import type { CandidateHistory, JsonObject } from "../state/types";

const RECONSTRUCTION_EXTENSION = "mesh2param.dev/reconstruction";

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function jsonObject(value: unknown): JsonObject | null {
  return isObject(value) ? value as JsonObject : null;
}

export function candidatesFromSettings(value: unknown): CandidateHistory[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry) => {
    if (!isObject(entry)
      || typeof entry.label !== "string"
      || typeof entry.score !== "number"
      || !Number.isFinite(entry.score)
      || typeof entry.valid !== "boolean"
      || typeof entry.featureCount !== "number"
      || !Number.isInteger(entry.featureCount)
      || entry.featureCount < 0) return [];
    const kernel = jsonObject(entry.kernel);
    const comparison = entry.comparison === null ? null : jsonObject(entry.comparison);
    if (kernel === null || (entry.comparison !== null && comparison === null)) return [];
    const candidate: CandidateHistory = {
      label: entry.label,
      score: entry.score,
      valid: entry.valid,
      rejectionReason: typeof entry.rejectionReason === "string" ? entry.rejectionReason : null,
      featureCount: entry.featureCount,
      kernel,
      comparison,
    };
    if (isCADGraph(entry.cadgraph)) candidate.cadgraph = entry.cadgraph;
    return [candidate];
  });
}

export function selectedCandidateLabel(graph: CADGraph | null, settings: JsonObject): string | null {
  const reconstruction = graph?.extensions?.[RECONSTRUCTION_EXTENSION];
  if (isObject(reconstruction) && typeof reconstruction.candidate === "string") {
    return reconstruction.candidate;
  }
  const selected = settings.selectedCandidate;
  return typeof selected === "string" ? selected : null;
}

export function selectableCandidateGraph(candidate: CandidateHistory): CADGraph {
  if (!candidate.valid) throw new Error(`${candidate.label} was rejected by the CAD kernel.`);
  if (candidate.cadgraph === undefined) {
    throw new Error(`${candidate.label} does not include an editable CADGraph snapshot.`);
  }
  return structuredClone(candidate.cadgraph);
}
