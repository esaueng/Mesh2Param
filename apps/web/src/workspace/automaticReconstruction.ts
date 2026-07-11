import type { ProjectWorkingDocument } from "../state/types";

const SUPPORTED_SAMPLE_ID = "l-bracket-with-holes";
const SAMPLE_EXTENSION = "mesh2param.dev/sample";
export const AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE =
  "Automatic inference currently supports only the L-bracket with four through holes. This exact sample already includes an editable CADGraph.";

export interface AutomaticReconstructionCapability {
  supported: boolean;
  sampleId?: string;
  reason?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function automaticReconstructionCapability(
  document: Pick<ProjectWorkingDocument, "cadgraph" | "settings">,
): AutomaticReconstructionCapability {
  const sample = document.cadgraph?.extensions?.[SAMPLE_EXTENSION];
  const sampleId = isRecord(sample) && typeof sample.slug === "string" ? sample.slug : undefined;
  if (sampleId === undefined) return { supported: true };

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
