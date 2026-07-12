import type { ArtifactDescriptor, JsonObject, ProjectWorkingDocument, ViewerMode } from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import { automaticReconstructionCapability } from "../workspace/automaticReconstruction";

/**
 * Canvas-First reduces the seven-step workflow to a single guided "next action".
 * The primary command in the dock advances the conversion one stage at a time,
 * derived purely from the current project state.
 */
export type PipelineActionKind = "open" | "analyze" | "reconstruct" | "faceted" | "validate" | "export" | "download";

export type RunOperation = "analyze" | "reconstruct" | "validate" | "export";

export interface PipelineAction {
  kind: PipelineActionKind;
  label: string;
  hint: string;
  disabled: boolean;
  reason?: string;
  /** The geometry operation to run, when this action drives a worker job. */
  operation?: RunOperation;
  /** Extra settings forwarded to the worker operation (e.g. the faceted fallback mode). */
  settings?: JsonObject;
}

/**
 * The source-bound faceted STEP fallback is offered when exact parametric inference is
 * unavailable. The worker requires an STL source at project units and unit scale.
 */
export function facetedApplicable(state: ProjectWorkingDocument): boolean {
  const source = state.source;
  return state.cadgraph === null
    && source !== null
    && source.format === "stl"
    && source.scaleFactor === 1
    && source.declaredUnits === state.units;
}

export function isValidated(state: ProjectWorkingDocument): boolean {
  return state.validation?.brepValid === true && state.validation?.stepReimportValid === true;
}

export function stepArtifact(artifacts: readonly ArtifactDescriptor[]): ArtifactDescriptor | undefined {
  return artifacts.find((artifact) => /\.(step|stp)$/i.test(artifact.name));
}

export function nextAction(vm: WorkspaceViewModel): PipelineAction {
  const state = vm.project.state;
  const runBlocked = !vm.workerReady
    ? "The geometry worker is not ready yet."
    : !vm.serverWritable
      ? "Resolve queued local edits before running geometry jobs."
      : vm.activeJob !== null
        ? "A job is already running."
        : null;

  if (state.source === null) {
    return { kind: "open", label: "Open a mesh", hint: "Load an STL, OBJ, or PLY file", disabled: false };
  }

  if (isValidated(state) && stepArtifact(vm.artifacts) !== undefined) {
    return { kind: "download", label: "Download STEP", hint: "Save the validated STEP file", disabled: false };
  }

  if (state.cadgraph === null) {
    // `analyze` (not the upload/ingest step) is what produces surface patches and the
    // renderable source.glb, so patches — not mesh-health diagnostics — mark it done.
    const analyzed = state.patches.length > 0;
    if (!analyzed) {
      return {
        kind: "analyze",
        operation: "analyze",
        label: "Analyze mesh",
        hint: "Measure mesh health and find surfaces",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
      };
    }
    const capability = automaticReconstructionCapability(state);
    if (capability.supported) {
      return {
        kind: "reconstruct",
        operation: "reconstruct",
        label: "Reconstruct",
        hint: "Build an exact, editable parametric model",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
      };
    }
    // Exact inference is unavailable; offer the source-bound faceted STEP fallback when it applies.
    if (facetedApplicable(state)) {
      return {
        kind: "faceted",
        operation: "reconstruct",
        settings: { mode: "faceted" },
        label: "Generate STEP",
        hint: capability.reason
          ? `Exact inference unavailable. ${capability.reason}`
          : "Build a source-bound faceted STEP (not an exact parametric model)",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
      };
    }
    return {
      kind: "reconstruct",
      operation: "reconstruct",
      label: "Reconstruct",
      hint: "Build an exact, editable parametric model",
      disabled: true,
      ...(capability.reason !== undefined ? { reason: capability.reason } : {}),
    };
  }

  if (!isValidated(state)) {
    return {
      kind: "validate",
      operation: "validate",
      label: "Validate",
      hint: "Prove B-Rep and STEP reimport validity",
      disabled: runBlocked !== null,
      ...(runBlocked !== null ? { reason: runBlocked } : {}),
    };
  }

  if (stepArtifact(vm.artifacts) === undefined) {
    return {
      kind: "export",
      operation: "export",
      label: "Export STEP",
      hint: "Build the validated STEP file",
      disabled: runBlocked !== null,
      ...(runBlocked !== null ? { reason: runBlocked } : {}),
    };
  }

  return { kind: "download", label: "Download STEP", hint: "Save the validated STEP file", disabled: false };
}

export interface ModeOption {
  mode: ViewerMode;
  label: string;
}

/** The display modes worth surfacing in a minimal viewer, filtered to those that have artifacts. */
export function availableModes(artifacts: readonly ArtifactDescriptor[]): ModeOption[] {
  const names = new Set(artifacts.map((artifact) => artifact.name));
  const options: ModeOption[] = [];
  if (names.has("source.glb")) options.push({ mode: "source", label: "Source" });
  if (names.has("reconstructed.glb")) options.push({ mode: "reconstructed", label: "Result" });
  if (names.has("source.glb") && names.has("reconstructed.glb")) options.push({ mode: "overlay", label: "Compare" });
  return options;
}

export function humanPhase(value: string): string {
  return value
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((word) => (word[0]?.toUpperCase() ?? "") + word.slice(1))
    .join(" ");
}
