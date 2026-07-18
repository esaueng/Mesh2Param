import type {
  ArtifactDescriptor,
  JsonObject,
  ProjectWorkingDocument,
  ViewerMode,
  ViewerPreferences,
} from "../state/types";
import type { WorkspaceViewModel } from "../workspace/types";
import { automaticReconstructionCapability } from "../workspace/automaticReconstruction";

/**
 * Canvas-First reduces the seven-step workflow to a single guided "next action".
 * The primary command in the dock advances the conversion one stage at a time,
 * derived purely from the current project state.
 */
export type PipelineActionKind = "open" | "analyze" | "reconstruct" | "curved" | "faceted" | "validate" | "export" | "download";

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
  /** A secondary conversion the user may prefer (e.g. faceted instead of curved). */
  alternate?: PipelineAction;
}

/**
 * A reconstructed CAD result should first appear as a shaded solid. Carrying a
 * source-mesh wireframe preference into this view exposes the GLB display
 * tessellation and makes analytic cylinders and arcs look like faceted STEP
 * geometry even though the underlying B-Rep is smooth.
 */
export function reconstructedRevealPreferences(): Partial<ViewerPreferences> {
  return {
    mode: "reconstructed",
    resultOpacity: 1,
    shading: "shaded",
    edges: true,
  };
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

function operationBlockReason(vm: WorkspaceViewModel): string | null {
  return !vm.workerReady
    ? "The geometry worker is not ready yet."
    : !vm.serverWritable
      ? "Resolve queued local edits before running geometry jobs."
      : vm.activeJob !== null
        ? "A job is already running."
        : null;
}

/**
 * Regenerate an existing STEP from the project's authoritative geometry.
 * Browser-local faceted projects do not carry a CADGraph. Regeneration gives
 * the bounded analytic solver another chance from the preserved source rather
 * than silently repeating the faceted conversion.
 */
export function regenerationAction(vm: WorkspaceViewModel): PipelineAction | null {
  const state = vm.project.state;
  if (!isValidated(state) || stepArtifact(vm.artifacts) === undefined) return null;

  const runBlocked = operationBlockReason(vm);
  if (state.cadgraph !== null) {
    return {
      kind: "export",
      operation: "export",
      label: "Regenerate STEP",
      hint: "Rebuild the STEP file from the current project model",
      disabled: runBlocked !== null,
      ...(runBlocked !== null ? { reason: runBlocked } : {}),
    };
  }

  if (!facetedApplicable(state)) return null;
  return {
    kind: "reconstruct",
    operation: "reconstruct",
    label: "Recover smooth STEP",
    hint: "Re-analyze the preserved source and rebuild it with analytic lines and curves",
    disabled: runBlocked !== null,
    ...(runBlocked !== null ? { reason: runBlocked } : {}),
  };
}

/** Offer a non-destructive analysis refresh once a project has analysis or CAD output. */
export function analysisRerunAction(vm: WorkspaceViewModel): PipelineAction | null {
  const state = vm.project.state;
  const hasExistingWork = state.analysis !== null
    || state.patches.length > 0
    || state.cadgraph !== null
    || stepArtifact(vm.artifacts) !== undefined;
  if (state.source === null || !hasExistingWork) return null;

  const runBlocked = operationBlockReason(vm);
  return {
    kind: "analyze",
    operation: "analyze",
    label: "Rerun analysis",
    hint: "Recheck mesh health and surface evidence without discarding the current STEP",
    disabled: runBlocked !== null,
    ...(runBlocked !== null ? { reason: runBlocked } : {}),
  };
}

export function nextAction(vm: WorkspaceViewModel): PipelineAction {
  const state = vm.project.state;
  const runBlocked = operationBlockReason(vm);

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
      if (capability.approximate === true) {
        // Freeform patches present: the automatic path recovers a parametric
        // feature model (sketch + extrude + fillet) where the engine's
        // candidate evaluation permits, and fails closed otherwise. The
        // curved plate path stays one click away as the standing alternate.
        return {
          kind: "reconstruct",
          operation: "reconstruct",
          label: "Reconstruct",
          hint: "Recover an editable parametric feature model (approximate where freeform)",
          disabled: runBlocked !== null,
          ...(runBlocked !== null ? { reason: runBlocked } : {}),
          alternate: {
            kind: "curved",
            operation: "reconstruct",
            settings: { mode: "curved" },
            label: "Generate curved STEP",
            hint: "Fit an approximate curved B-Rep to the mesh within tolerance (not recovered design history)",
            disabled: runBlocked !== null,
            ...(runBlocked !== null ? { reason: runBlocked } : {}),
          },
        };
      }
      return {
        kind: "reconstruct",
        operation: "reconstruct",
        label: "Reconstruct",
        hint: "Build an exact, editable parametric model",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
      };
    }
    // Exact inference is unavailable; offer the approximate curved B-Rep first and
    // the source-bound faceted STEP as the explicit alternative. Both are labeled
    // for what they are: neither recovers the original design history.
    if (facetedApplicable(state)) {
      const faceted: PipelineAction = {
        kind: "faceted",
        operation: "reconstruct",
        settings: { mode: "faceted" },
        label: "Generate faceted STEP",
        hint: capability.reason
          ? `Source-bound fallback: ${capability.reason}`
          : "Build a source-bound faceted STEP (one planar face per source triangle)",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
      };
      return {
        kind: "curved",
        operation: "reconstruct",
        settings: { mode: "curved" },
        label: "Generate curved STEP",
        hint: "Fit an approximate curved B-Rep to the mesh within tolerance (not recovered design history)",
        disabled: runBlocked !== null,
        ...(runBlocked !== null ? { reason: runBlocked } : {}),
        alternate: faceted,
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
  if (names.has("residual.glb")) {
    options.push({
      mode: "residual",
      label: names.has("suppressed-regions.json") ? "Suppressed" : "Residual",
    });
  }
  return options;
}

export function humanPhase(value: string): string {
  return value
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((word) => (word[0]?.toUpperCase() ?? "") + word.slice(1))
    .join(" ");
}
