import type { JsonValue, ProjectWorkingDocument } from "../state/types";

const SUPPORTED_SAMPLE_ID = "l-bracket-with-holes";
const SAMPLE_EXTENSION = "mesh2param.dev/sample";
const FACETED_EXTENSION = "mesh2param.dev/facetedFallback";
export const AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE =
  "Automatic inference currently supports only the L-bracket with four through holes. This exact sample already includes an editable CADGraph.";

export interface AutomaticReconstructionCapability {
  supported: boolean;
  sampleId?: string;
  reason?: string;
}

function isRecord(value: unknown): value is Record<string, JsonValue> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function finiteNumber(value: unknown, minimum: number, maximum: number, openMinimum = false, openMaximum = false): boolean {
  if (typeof value !== "number" || !Number.isFinite(value)) return false;
  return (openMinimum ? value > minimum : value >= minimum)
    && (openMaximum ? value < maximum : value <= maximum);
}

function hasReplayableAnalysisSettings(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return finiteNumber(value.smoothAngleDeg, 0, 90, true, true)
    && finiteNumber(value.planarFitToleranceMm, 0, 1_000_000, true)
    && finiteNumber(value.cylinderFitToleranceMm, 0, 1_000_000, true)
    && finiteNumber(value.minimumCylinderCoverageDeg, 0, 360, true)
    && finiteNumber(value.maximumCylinderAxisNormalComponent, 0, 1)
    && finiteNumber(value.minimumPatchAreaMm2, 0, 1_000_000_000_000)
    && finiteNumber(value.stableIdResolutionMm, 0, 1_000_000, true);
}

export function automaticReconstructionCapability(
  document: Pick<ProjectWorkingDocument, "analysis" | "cadgraph" | "settings" | "source">,
): AutomaticReconstructionCapability {
  const sample = document.cadgraph?.extensions?.[SAMPLE_EXTENSION];
  const sampleId = isRecord(sample) && typeof sample.slug === "string" ? sample.slug : undefined;
  if (sampleId === undefined) {
    if (isRecord(document.cadgraph?.extensions?.[FACETED_EXTENSION])) {
      return {
        supported: false,
        reason: "This project already uses a non-parametric faceted fallback. Adjust its sewing tolerance or rebuild that source-bound feature instead.",
      };
    }
    if (document.source === null || document.source === undefined) return { supported: false, reason: "Upload a source mesh first." };
    const analysis = document.analysis;
    const analyzedPatches = isRecord(analysis) ? analysis.patches : undefined;
    if (!isRecord(analysis) || !hasReplayableAnalysisSettings(analysis.settings) || !Array.isArray(analyzedPatches) || analyzedPatches.length === 0) {
      return {
        supported: false,
        reason: "Run surface analysis again so Mesh2Param can replay the exact settings used by the bounded parametric solver.",
      };
    }
    const patches = analyzedPatches.filter(isRecord);
    if (patches.length !== analyzedPatches.length) {
      return {
        supported: false,
        reason: "Run surface analysis again because its persisted patch evidence is incomplete.",
      };
    }
    const unsupported = patches.filter((patch) => patch.type !== "plane" && patch.type !== "cylinder");
    if (unsupported.length > 0) {
      let unsupportedArea = 0;
      let totalArea = 0;
      for (const patch of patches) {
        const area = typeof patch.areaMm2 === "number" && Number.isFinite(patch.areaMm2) && patch.areaMm2 > 0 ? patch.areaMm2 : 0;
        totalArea += area;
        if (patch.type !== "plane" && patch.type !== "cylinder") unsupportedArea += area;
      }
      const coverage = totalArea > 0 ? ` covering ${(unsupportedArea / totalArea * 100).toFixed(1)}% of the surface` : "";
      return {
        supported: false,
        reason: `Automatic parametric inference is unavailable because analysis found ${unsupported.length} non-plane/cylinder patches${coverage}. Use the explicit faceted STEP fallback for this geometry.`,
      };
    }
    return { supported: true };
  }

  const configured = document.settings.automaticReconstruction;
  const matchingConfiguration: { supported: boolean; reason?: string } | null = (
    isRecord(configured)
    && typeof configured.supported === "boolean"
    && (configured.sampleId === undefined || configured.sampleId === sampleId)
  ) ? {
      supported: configured.supported,
      ...(typeof configured.reason === "string" ? { reason: configured.reason } : {}),
    } : null;
  if (sampleId !== SUPPORTED_SAMPLE_ID) {
    const reason = matchingConfiguration?.supported === false
      && typeof matchingConfiguration.reason === "string"
      && matchingConfiguration.reason.trim()
      ? matchingConfiguration.reason
      : AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE;
    return { supported: false, sampleId, reason };
  }

  if (matchingConfiguration !== null) {
    const reason = typeof matchingConfiguration.reason === "string" && matchingConfiguration.reason.trim()
      ? matchingConfiguration.reason
      : matchingConfiguration.supported ? undefined : AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE;
    return {
      supported: matchingConfiguration.supported,
      sampleId,
      ...(reason === undefined ? {} : { reason }),
    };
  }
  return {
    supported: true,
    sampleId,
  };
}
