import { migrateCADGraph } from "@mesh2param/contracts";

import type {
  ArtifactDescriptor,
  DetailedValidationResult,
  EmbeddedBlob,
  JsonObject,
  LocalBlobReference,
  MeshDiagnostics,
  MeshStateMetrics,
  Mesh2ParamProjectFile,
  PersistedProjectUI,
  ProjectFileSource,
  ProjectSummary,
  ProjectVersionSnapshot,
  ProjectWorkingDocument,
  RepairOperation,
  RepairResult,
  SurfacePatch,
  Units,
} from "../state/types";
import { blobKey } from "./db";

export const PROJECT_FILE_FORMAT = "mesh2param-project";
export const PROJECT_FILE_VERSION = 1;
export const DEFAULT_PROJECT_FILENAME = "project.mesh2param.json";
export const MAX_EMBEDDED_SOURCE_BYTES = 16 * 1024 * 1024;
export const MAX_PROJECT_FILE_BYTES = 64 * 1024 * 1024;
export const MAX_PROJECT_FILE_VERSIONS = 1_000;
export const MAX_PROJECT_FILE_ARTIFACTS = 512;

const SHA256 = /^[a-f0-9]{64}$/;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const UNITS = new Set<Units>(["mm", "cm", "m", "in", "ft"]);
const SOURCE_FORMATS = new Set(["stl", "obj", "ply"]);
const PATCH_TYPES = new Set(["plane", "cylinder", "cone", "sphere", "freeform", "unknown"]);
const WORKFLOW_STEPS = new Set(["import", "repair", "surfaces", "features", "refine", "validate", "export"]);
const VIEWER_MODES = new Set(["source", "repaired", "analysis", "patches", "reconstructed", "residual", "overlay"]);

export class ProjectFileError extends TypeError {
  readonly code: string;

  constructor(code: string, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProjectFileError";
    this.code = code;
  }
}

export interface ParsedProjectFile {
  file: Mesh2ParamProjectFile;
  embeddedSource: {
    key: string;
    sha256: string;
    byteSize: number;
    mediaType: string;
    originalFileName: string;
    blob: Blob;
  } | null;
}

export interface ParseProjectFileOptions {
  maxFileBytes?: number;
  maxEmbeddedSourceBytes?: number;
}

export interface ProjectFileSourceInput {
  sha256: string;
  byteSize: number;
  mediaType: string;
  originalFileName: string;
  blob: Blob;
}

export interface ProjectFileSaveResult {
  method: "file-system-access" | "download";
  handle: ProjectFileHandle | null;
}

export interface ProjectFileWritable {
  write(data: string | Blob): Promise<void>;
  close(): Promise<void>;
}

export interface ProjectFileHandle {
  createWritable(): Promise<ProjectFileWritable>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function detachedRecord(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new ProjectFileError("invalid_root", "Project file must contain a JSON object.");
  try {
    return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  } catch (error) {
    throw new ProjectFileError("invalid_json_value", "Project file must contain only JSON values.", { cause: error });
  }
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new ProjectFileError("invalid_field", `${key} must be a non-empty string.`);
  }
  return value;
}

function nullableString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "string") throw new ProjectFileError("invalid_field", `${key} must be a string or null.`);
  return value;
}

function nonNegativeInteger(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new ProjectFileError("invalid_field", `${key} must be a non-negative integer.`);
  }
  return value as number;
}

function requiredBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    throw new ProjectFileError("invalid_ui", `${key} must be a boolean.`);
  }
  return value;
}

function boundedNumber(
  record: Record<string, unknown>,
  key: string,
  minimum: number,
  maximum: number,
): number {
  const value = record[key];
  if (
    typeof value !== "number"
    || !Number.isFinite(value)
    || value < minimum
    || value > maximum
  ) {
    throw new ProjectFileError(
      "invalid_ui",
      `${key} must be a finite number in [${minimum}, ${maximum}].`,
    );
  }
  return value;
}

function vector3Tuple(value: unknown, label: string): [number, number, number] {
  if (
    !Array.isArray(value)
    || value.length !== 3
    || !value.every((item) => typeof item === "number" && Number.isFinite(item))
  ) {
    throw new ProjectFileError("invalid_ui", `${label} must contain three finite numbers.`);
  }
  return [value[0] as number, value[1] as number, value[2] as number];
}

function defaultProjectFileUI(): PersistedProjectUI {
  return {
    activeStep: "import",
    selection: { patchId: null, featureId: null, sketchEntityId: null, hoverId: null },
    viewer: {
      mode: "source",
      visible: {
        source: true,
        repaired: false,
        analysis: false,
        patches: false,
        reconstructed: false,
        residual: false,
      },
      sourceOpacity: 1,
      resultOpacity: 1,
      projection: "perspective",
      shading: "shaded",
      edges: true,
    },
    shell: {
      theme: "dark",
      railCollapsed: false,
      inspectorExpanded: true,
      bottomDrawerExpanded: false,
      bottomDrawerHeight: 220,
      singleKeyShortcuts: true,
    },
    cameraPose: null,
  };
}

function validatePersistedUI(value: unknown): PersistedProjectUI {
  if (!isRecord(value)) {
    throw new ProjectFileError("invalid_ui", "ui must be an object.");
  }
  const activeStep = requiredString(value, "activeStep");
  if (!WORKFLOW_STEPS.has(activeStep)) {
    throw new ProjectFileError("invalid_ui", "ui.activeStep is unsupported.");
  }
  if (
    !isRecord(value.selection)
    || !isRecord(value.viewer)
    || !isRecord(value.shell)
  ) {
    throw new ProjectFileError("invalid_ui", "ui selection, viewer, and shell are required.");
  }
  const selection = value.selection;
  const viewer = value.viewer;
  const shell = value.shell;
  if (!isRecord(viewer.visible)) {
    throw new ProjectFileError("invalid_ui", "ui viewer visibility is required.");
  }
  const visible = viewer.visible;
  const mode = requiredString(viewer, "mode");
  const projection = requiredString(viewer, "projection");
  const shading = requiredString(viewer, "shading");
  const theme = requiredString(shell, "theme");
  if (!VIEWER_MODES.has(mode) || !new Set(["perspective", "orthographic"]).has(projection)) {
    throw new ProjectFileError("invalid_ui", "ui viewer mode or projection is unsupported.");
  }
  if (!new Set(["shaded", "wireframe"]).has(shading) || !new Set(["dark", "light"]).has(theme)) {
    throw new ProjectFileError("invalid_ui", "ui shading or theme is unsupported.");
  }
  let cameraPose: PersistedProjectUI["cameraPose"] = null;
  if (value.cameraPose !== null) {
    if (!isRecord(value.cameraPose)) {
      throw new ProjectFileError("invalid_ui", "ui.cameraPose must be an object or null.");
    }
    const cameraProjection = requiredString(value.cameraPose, "projection");
    if (!new Set(["perspective", "orthographic"]).has(cameraProjection)) {
      throw new ProjectFileError("invalid_ui", "ui camera projection is unsupported.");
    }
    cameraPose = {
      projectId: requiredString(value.cameraPose, "projectId"),
      artifactBoundsHash: requiredString(value.cameraPose, "artifactBoundsHash"),
      position: vector3Tuple(value.cameraPose.position, "ui.cameraPose.position"),
      target: vector3Tuple(value.cameraPose.target, "ui.cameraPose.target"),
      up: vector3Tuple(value.cameraPose.up, "ui.cameraPose.up"),
      projection: cameraProjection as "perspective" | "orthographic",
      zoom: boundedNumber(value.cameraPose, "zoom", 0.000001, 1_000_000),
    };
  }
  return {
    activeStep: activeStep as PersistedProjectUI["activeStep"],
    selection: {
      patchId: nullableString(selection, "patchId"),
      featureId: nullableString(selection, "featureId"),
      sketchEntityId: nullableString(selection, "sketchEntityId"),
      hoverId: nullableString(selection, "hoverId"),
    },
    viewer: {
      mode: mode as PersistedProjectUI["viewer"]["mode"],
      visible: {
        source: requiredBoolean(visible, "source"),
        repaired: requiredBoolean(visible, "repaired"),
        analysis: requiredBoolean(visible, "analysis"),
        patches: requiredBoolean(visible, "patches"),
        reconstructed: requiredBoolean(visible, "reconstructed"),
        residual: requiredBoolean(visible, "residual"),
      },
      sourceOpacity: boundedNumber(viewer, "sourceOpacity", 0, 1),
      resultOpacity: boundedNumber(viewer, "resultOpacity", 0, 1),
      projection: projection as "perspective" | "orthographic",
      shading: shading as "shaded" | "wireframe",
      edges: requiredBoolean(viewer, "edges"),
    },
    shell: {
      theme: theme as "dark" | "light",
      railCollapsed: requiredBoolean(shell, "railCollapsed"),
      inspectorExpanded: requiredBoolean(shell, "inspectorExpanded"),
      bottomDrawerExpanded: requiredBoolean(shell, "bottomDrawerExpanded"),
      bottomDrawerHeight: boundedNumber(shell, "bottomDrawerHeight", 80, 2_000),
      singleKeyShortcuts: requiredBoolean(shell, "singleKeyShortcuts"),
    },
    cameraPose,
  };
}

function invalidNested(code: string, message: string): never {
  throw new ProjectFileError(code, message);
}

function nestedRecord(value: unknown, label: string, code = "invalid_working"): Record<string, unknown> {
  if (!isRecord(value)) invalidNested(code, `${label} must be an object.`);
  return value;
}

function nestedString(
  record: Record<string, unknown>,
  key: string,
  label: string,
  code = "invalid_working",
): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    invalidNested(code, `${label}.${key} must be a non-empty string.`);
  }
  return value;
}

function nestedBoolean(
  record: Record<string, unknown>,
  key: string,
  label: string,
  code = "invalid_working",
): boolean {
  const value = record[key];
  if (typeof value !== "boolean") invalidNested(code, `${label}.${key} must be a boolean.`);
  return value;
}

function nestedNumber(
  record: Record<string, unknown>,
  key: string,
  label: string,
  options: { minimum?: number; maximum?: number; integer?: boolean; nullable?: boolean } = {},
  code = "invalid_working",
): number | null {
  const value = record[key];
  if (options.nullable === true && value === null) return null;
  if (
    typeof value !== "number"
    || !Number.isFinite(value)
    || (options.integer === true && !Number.isInteger(value))
    || (options.minimum !== undefined && value < options.minimum)
    || (options.maximum !== undefined && value > options.maximum)
  ) {
    invalidNested(code, `${label}.${key} must be a valid finite number.`);
  }
  return value;
}

function nestedArray(
  value: unknown,
  label: string,
  code = "invalid_working",
): unknown[] {
  if (!Array.isArray(value)) invalidNested(code, `${label} must be an array.`);
  return value;
}

function nestedStringArray(
  value: unknown,
  label: string,
  code = "invalid_working",
): string[] {
  const items = nestedArray(value, label, code);
  if (!items.every((item) => typeof item === "string")) {
    invalidNested(code, `${label} must contain only strings.`);
  }
  return items as string[];
}

function nestedIntegerArray(value: unknown, label: string): number[] {
  const items = nestedArray(value, label);
  if (!items.every((item) => Number.isSafeInteger(item) && (item as number) >= 0)) {
    invalidNested("invalid_working", `${label} must contain non-negative integers.`);
  }
  return items as number[];
}

function nestedVector3(value: unknown, label: string): [number, number, number] {
  if (
    !Array.isArray(value)
    || value.length !== 3
    || !value.every((item) => typeof item === "number" && Number.isFinite(item))
  ) {
    invalidNested("invalid_working", `${label} must contain three finite numbers.`);
  }
  return value as [number, number, number];
}

function validateIsoTimestamp(value: unknown, label: string, code = "invalid_timestamp"): string {
  if (
    typeof value !== "string"
    || !ISO_TIMESTAMP.test(value)
    || !Number.isFinite(Date.parse(value))
  ) {
    invalidNested(code, `${label} must be an ISO-8601 timestamp with a timezone.`);
  }
  return value;
}

function validateJsonObject(value: unknown, label: string, code = "invalid_working"): JsonObject {
  if (!isRecord(value)) invalidNested(code, `${label} must be a JSON object.`);
  return value as JsonObject;
}

function validateNullableJsonObject(value: unknown, label: string): JsonObject | null {
  return value === null ? null : validateJsonObject(value, label);
}

function validateMeshDiagnostics(value: unknown, label: string): MeshDiagnostics {
  const diagnostics = nestedRecord(value, label);
  const format = nestedString(diagnostics, "format", label);
  if (!SOURCE_FORMATS.has(format)) invalidNested("invalid_working", `${label}.format is unsupported.`);
  nestedString(diagnostics, "encoding", label);
  validateSha256(nestedString(diagnostics, "sha256", label));
  for (const key of [
    "byteSize",
    "rawVertexCount",
    "weldedVertexCount",
    "duplicateVertexCount",
    "triangleCount",
    "connectedComponentCount",
    "degenerateTriangleCount",
    "duplicateFaceCount",
    "nonManifoldEdgeCount",
    "openBoundaryEdgeCount",
    "openBoundaryCount",
  ]) {
    nestedNumber(diagnostics, key, label, { integer: true, minimum: 0 });
  }
  const bounds = nestedArray(diagnostics.bounds, `${label}.bounds`);
  if (bounds.length !== 2) invalidNested("invalid_working", `${label}.bounds must contain two vectors.`);
  nestedVector3(bounds[0], `${label}.bounds[0]`);
  nestedVector3(bounds[1], `${label}.bounds[1]`);
  nestedVector3(diagnostics.boundingDimensions, `${label}.boundingDimensions`);
  const coordinateRange = nestedArray(diagnostics.coordinateRange, `${label}.coordinateRange`);
  if (
    coordinateRange.length !== 2
    || !coordinateRange.every((item) => typeof item === "number" && Number.isFinite(item))
  ) {
    invalidNested("invalid_working", `${label}.coordinateRange must contain two finite numbers.`);
  }
  nestedNumber(diagnostics, "surfaceArea", label, { minimum: 0 });
  nestedNumber(diagnostics, "closedVolume", label, { minimum: 0, nullable: true });
  nestedBoolean(diagnostics, "watertight", label);
  nestedBoolean(diagnostics, "windingConsistent", label);
  nestedString(diagnostics, "selfIntersectionStatus", label);
  for (const [index, warningValue] of nestedArray(diagnostics.warnings, `${label}.warnings`).entries()) {
    const warningLabel = `${label}.warnings[${index}]`;
    const warning = nestedRecord(warningValue, warningLabel);
    nestedString(warning, "code", warningLabel);
    nestedString(warning, "message", warningLabel);
    if (warning.severity !== "warning") {
      invalidNested("invalid_working", `${warningLabel}.severity must be warning.`);
    }
  }
  return diagnostics as unknown as MeshDiagnostics;
}

function validateMeshStateMetrics(value: unknown, label: string): MeshStateMetrics {
  const metrics = nestedRecord(value, label);
  nestedString(metrics, "versionId", label);
  for (const key of [
    "vertexCount",
    "triangleCount",
    "connectedComponentCount",
    "degenerateTriangleCount",
    "duplicateFaceCount",
    "nonManifoldEdgeCount",
    "openBoundaryEdgeCount",
    "openBoundaryCount",
  ]) {
    nestedNumber(metrics, key, label, { integer: true, minimum: 0 });
  }
  nestedNumber(metrics, "surfaceArea", label, { minimum: 0 });
  nestedNumber(metrics, "closedVolume", label, { minimum: 0, nullable: true });
  nestedBoolean(metrics, "watertight", label);
  nestedBoolean(metrics, "windingConsistent", label);
  return metrics as unknown as MeshStateMetrics;
}

function validateRepairOperation(value: unknown, label: string): RepairOperation {
  const operation = nestedRecord(value, label);
  nestedString(operation, "id", label);
  nestedNumber(operation, "order", label, { integer: true, minimum: 0 });
  nestedString(operation, "operation", label);
  nestedBoolean(operation, "enabled", label);
  validateJsonObject(operation.parameters, `${label}.parameters`);
  nestedString(operation, "sourceVersionId", label);
  nestedString(operation, "resultVersionId", label);
  validateMeshStateMetrics(operation.before, `${label}.before`);
  validateMeshStateMetrics(operation.after, `${label}.after`);
  nestedStringArray(operation.warnings, `${label}.warnings`);
  nestedBoolean(operation, "reversible", label);
  validateIsoTimestamp(operation.timestamp, `${label}.timestamp`, "invalid_working");
  nestedBoolean(operation, "changed", label);
  return operation as unknown as RepairOperation;
}

function validateRepairResult(value: unknown, label: string): RepairResult {
  const repair = nestedRecord(value, label);
  nestedString(repair, "sourceId", label);
  nestedString(repair, "resultId", label);
  if (repair.sourceSha256 !== null) {
    validateSha256(nestedString(repair, "sourceSha256", label));
  }
  validateJsonObject(repair.settings, `${label}.settings`);
  nestedArray(repair.operations, `${label}.operations`).forEach((operation, index) => {
    validateRepairOperation(operation, `${label}.operations[${index}]`);
  });
  validateMeshStateMetrics(repair.sourceMetrics, `${label}.sourceMetrics`);
  validateMeshStateMetrics(repair.resultMetrics, `${label}.resultMetrics`);
  validateMeshDiagnostics(repair.diagnostics, `${label}.diagnostics`);
  nestedStringArray(repair.warnings, `${label}.warnings`);
  return repair as unknown as RepairResult;
}

function validateSurfacePatch(value: unknown, label: string): SurfacePatch {
  const patch = nestedRecord(value, label);
  nestedString(patch, "id", label);
  const type = nestedString(patch, "type", label);
  if (!PATCH_TYPES.has(type)) invalidNested("invalid_working", `${label}.type is unsupported.`);
  if (patch.name !== undefined && typeof patch.name !== "string") {
    invalidNested("invalid_working", `${label}.name must be a string.`);
  }
  nestedNumber(patch, "triangleCount", label, { integer: true, minimum: 0, nullable: true });
  nestedNumber(patch, "confidence", label, { minimum: 0, maximum: 1, nullable: true });
  nestedBoolean(patch, "locked", label);
  if (patch.triangleIds !== undefined) nestedIntegerArray(patch.triangleIds, `${label}.triangleIds`);
  if (patch.vertexCount !== undefined) {
    nestedNumber(patch, "vertexCount", label, { integer: true, minimum: 0 });
  }
  if (patch.areaMm2 !== undefined) nestedNumber(patch, "areaMm2", label, { minimum: 0 });
  if (patch.centroid !== undefined) nestedVector3(patch.centroid, `${label}.centroid`);
  if (patch.residualsMm !== undefined) {
    const residuals = nestedRecord(patch.residualsMm, `${label}.residualsMm`);
    for (const key of ["rms", "median", "p95", "max"]) {
      nestedNumber(residuals, key, `${label}.residualsMm`, { minimum: 0 });
    }
  }
  if (patch.neighborIds !== undefined) nestedStringArray(patch.neighborIds, `${label}.neighborIds`);
  if (patch.boundaryLoops !== undefined) {
    nestedArray(patch.boundaryLoops, `${label}.boundaryLoops`).forEach((loopValue, index) => {
      const loopLabel = `${label}.boundaryLoops[${index}]`;
      const loop = nestedRecord(loopValue, loopLabel);
      nestedIntegerArray(loop.vertexIds, `${loopLabel}.vertexIds`);
      nestedBoolean(loop, "closed", loopLabel);
    });
  }
  if (patch.fit !== undefined) validateJsonObject(patch.fit, `${label}.fit`);
  for (const key of ["userOverriddenClassification", "hidden"]) {
    if (patch[key] !== undefined) nestedBoolean(patch, key, label);
  }
  if (patch.excludedTriangleIds !== undefined) {
    nestedIntegerArray(patch.excludedTriangleIds, `${label}.excludedTriangleIds`);
  }
  if (patch.mergedFrom !== undefined) nestedStringArray(patch.mergedFrom, `${label}.mergedFrom`);
  return patch as unknown as SurfacePatch;
}

function validateDetailedValidation(value: unknown, label: string): DetailedValidationResult {
  const validation = nestedRecord(value, label);
  nestedString(validation, "status", label);
  for (const key of ["brepValid", "stepReimportValid", "toleranceSatisfied"]) {
    if (validation[key] !== null) nestedBoolean(validation, key, label);
  }
  if (validation.issues !== undefined) nestedArray(validation.issues, `${label}.issues`);
  if (validation.step !== undefined) validateJsonObject(validation.step, `${label}.step`);
  if (validation.compilation !== undefined) {
    validateJsonObject(validation.compilation, `${label}.compilation`);
  }
  return validation as unknown as DetailedValidationResult;
}

function validateSha256(value: string, field = "sha256"): string {
  if (!SHA256.test(value)) throw new ProjectFileError("invalid_hash", `${field} must be a lowercase SHA-256 digest.`);
  return value;
}

function validateProjectSummary(value: unknown): ProjectSummary {
  if (!isRecord(value)) throw new ProjectFileError("invalid_project", "project must be an object.");
  const units = requiredString(value, "units") as Units;
  if (!UNITS.has(units)) throw new ProjectFileError("invalid_units", "project.units is unsupported.");
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    units,
    schemaVersion: requiredString(value, "schemaVersion"),
    revision: nonNegativeInteger(value, "revision"),
    basedOnVersionId: nullableString(value, "basedOnVersionId"),
    createdAt: validateIsoTimestamp(value.createdAt, "project.createdAt"),
    updatedAt: validateIsoTimestamp(value.updatedAt, "project.updatedAt"),
  };
}

function validateArtifact(value: unknown): ArtifactDescriptor {
  if (!isRecord(value)) throw new ProjectFileError("invalid_artifact", "artifact descriptor must be an object.");
  const byteSize = nonNegativeInteger(value, "byteSize");
  const descriptor: ArtifactDescriptor = {
    name: requiredString(value, "name"),
    sha256: validateSha256(requiredString(value, "sha256")),
    byteSize,
    mediaType: requiredString(value, "mediaType"),
  };
  for (const key of ["id", "kind", "storageKey"] as const) {
    if (value[key] !== undefined) {
      if (typeof value[key] !== "string") {
        throw new ProjectFileError("invalid_artifact", `artifact.${key} must be a string.`);
      }
      descriptor[key] = value[key];
    }
  }
  if (value.metadata !== undefined) {
    if (!isRecord(value.metadata)) {
      throw new ProjectFileError("invalid_artifact", "artifact.metadata must be an object.");
    }
    descriptor.metadata = value.metadata as NonNullable<ArtifactDescriptor["metadata"]>;
  }
  if (value.createdAt !== undefined) {
    descriptor.createdAt = validateIsoTimestamp(value.createdAt, "artifact.createdAt");
  }
  return descriptor;
}

function validateSourceAsset(value: unknown): ProjectWorkingDocument["source"] {
  if (value === null) return null;
  if (!isRecord(value)) throw new ProjectFileError("invalid_source", "working.source must be an object or null.");
  const units = requiredString(value, "declaredUnits") as Units;
  if (!UNITS.has(units)) throw new ProjectFileError("invalid_units", "source declaredUnits is unsupported.");
  const format = requiredString(value, "format");
  if (!SOURCE_FORMATS.has(format)) {
    throw new ProjectFileError("invalid_source", "source format is unsupported.");
  }
  const scaleFactor = value.scaleFactor;
  if (typeof scaleFactor !== "number" || !Number.isFinite(scaleFactor) || scaleFactor <= 0) {
    throw new ProjectFileError("invalid_source", "source scaleFactor must be finite and positive.");
  }
  if (typeof value.unitsConfirmed !== "boolean") {
    throw new ProjectFileError("invalid_source", "source unitsConfirmed must be a boolean.");
  }
  return {
    id: requiredString(value, "id"),
    originalFileName: requiredString(value, "originalFileName"),
    format,
    encoding: requiredString(value, "encoding"),
    sha256: validateSha256(requiredString(value, "sha256")),
    byteSize: nonNegativeInteger(value, "byteSize"),
    declaredUnits: units,
    unitsConfirmed: value.unitsConfirmed,
    scaleFactor,
    state: requiredString(value, "state"),
  };
}

function validateWorking(value: unknown): ProjectWorkingDocument {
  if (!isRecord(value)) throw new ProjectFileError("invalid_working", "working must be an object.");
  const units = requiredString(value, "units") as Units;
  if (!UNITS.has(units)) throw new ProjectFileError("invalid_units", "working.units is unsupported.");
  if (!Array.isArray(value.patches) || !Array.isArray(value.artifacts) || !isRecord(value.settings)) {
    throw new ProjectFileError("invalid_working", "working patches, artifacts, or settings are malformed.");
  }
  let cadgraph: ProjectWorkingDocument["cadgraph"] = null;
  if (value.cadgraph !== null) {
    try {
      cadgraph = migrateCADGraph(value.cadgraph);
    } catch (error) {
      throw new ProjectFileError("invalid_cadgraph", "Project CADGraph could not be migrated or validated.", {
        cause: error,
      });
    }
  }
  const diagnostics = value.diagnostics === null
    ? null
    : validateMeshDiagnostics(value.diagnostics, "working.diagnostics");
  const repair = value.repair === null
    ? null
    : validateRepairResult(value.repair, "working.repair");
  const analysis = validateNullableJsonObject(value.analysis, "working.analysis");
  const patches = value.patches.map((patch, index) => (
    validateSurfacePatch(patch, `working.patches[${index}]`)
  ));
  const validation = value.validation === null
    ? null
    : validateDetailedValidation(value.validation, "working.validation");
  const metrics = validateNullableJsonObject(value.metrics, "working.metrics");
  const settings = validateJsonObject(value.settings, "working.settings");
  return {
    schemaVersion: requiredString(value, "schemaVersion"),
    projectId: requiredString(value, "projectId"),
    name: requiredString(value, "name"),
    units,
    source: validateSourceAsset(value.source),
    diagnostics,
    repair,
    analysis,
    patches,
    cadgraph,
    validation,
    metrics,
    artifactSetId: nullableString(value, "artifactSetId"),
    artifacts: value.artifacts.map(validateArtifact),
    currentVersionId: nullableString(value, "currentVersionId"),
    settings,
  };
}

function validateVersion(value: unknown): ProjectVersionSnapshot {
  if (!isRecord(value)) throw new ProjectFileError("invalid_version", "version snapshot must be an object.");
  const metrics = value.metrics === null || value.metrics === undefined
    ? null
    : validateJsonObject(value.metrics, "version.metrics", "invalid_version");
  const dependencyVersions = value.dependencyVersions === undefined
    ? {}
    : validateJsonObject(
        value.dependencyVersions,
        "version.dependencyVersions",
        "invalid_version",
      );
  return {
    id: requiredString(value, "id"),
    projectId: requiredString(value, "projectId"),
    parentId: nullableString(value, "parentId"),
    label: requiredString(value, "label"),
    state: validateWorking(value.state),
    sourceSha256: value.sourceSha256 === null ? null : validateSha256(requiredString(value, "sourceSha256")),
    validationStatus: requiredString(value, "validationStatus"),
    metrics,
    artifactSetId: nullableString(value, "artifactSetId"),
    engineVersion: requiredString(value, "engineVersion"),
    dependencyVersions,
    createdAt: validateIsoTimestamp(value.createdAt, "version.createdAt", "invalid_version"),
  };
}

function validateProjectFileSource(value: unknown): ProjectFileSource | null {
  if (value === null) return null;
  if (!isRecord(value)) throw new ProjectFileError("invalid_source", "source must be an object or null.");
  const common = {
    sha256: validateSha256(requiredString(value, "sha256")),
    byteSize: nonNegativeInteger(value, "byteSize"),
    mediaType: requiredString(value, "mediaType"),
    originalFileName: requiredString(value, "originalFileName"),
  };
  if (value.kind === "embedded") {
    return { kind: "embedded", ...common, dataBase64: requiredString(value, "dataBase64") };
  }
  if (value.kind === "local-reference") {
    return { kind: "local-reference", ...common, blobKey: requiredString(value, "blobKey") };
  }
  throw new ProjectFileError("invalid_source", "source.kind is unsupported.");
}

/** Migrate only the project-file envelope; CADGraph migration is handled separately. */
export function migrateProjectFileDocument(value: unknown): Record<string, unknown> {
  const document = detachedRecord(value);
  if (document.format !== PROJECT_FILE_FORMAT) {
    throw new ProjectFileError("invalid_format", "This is not a Mesh2Param project file.");
  }
  if (document.fileVersion === PROJECT_FILE_VERSION) {
    document.ui ??= defaultProjectFileUI();
    return document;
  }
  if (document.fileVersion === 0 || document.fileVersion === undefined) {
    document.fileVersion = PROJECT_FILE_VERSION;
    if (isRecord(document.working)) {
      document.working.source ??= null;
      document.working.diagnostics ??= null;
      document.working.repair ??= null;
      document.working.analysis ??= null;
      document.working.patches ??= [];
      document.working.cadgraph ??= null;
      document.working.validation ??= null;
      document.working.metrics ??= null;
      document.working.artifactSetId ??= null;
      document.working.artifacts ??= [];
      document.working.currentVersionId ??= null;
      document.working.settings ??= {};
    }
    document.versions ??= [];
    document.ui ??= defaultProjectFileUI();
    document.source ??= null;
    document.artifactManifest ??= isRecord(document.working) && Array.isArray(document.working.artifacts)
      ? document.working.artifacts
      : [];
    if (document.savedAt === undefined && isRecord(document.project)) {
      document.savedAt = document.project.updatedAt;
    }
    return document;
  }
  throw new ProjectFileError("unsupported_version", `Unsupported project file version: ${String(document.fileVersion)}.`);
}

function validateProjectFile(value: unknown): Mesh2ParamProjectFile {
  const document = migrateProjectFileDocument(value);
  const project = validateProjectSummary(document.project);
  const working = validateWorking(document.working);
  const ui = validatePersistedUI(document.ui);
  if (project.id !== working.projectId) {
    throw new ProjectFileError("project_mismatch", "project.id does not match working.projectId.");
  }
  if (!Array.isArray(document.versions) || document.versions.length > MAX_PROJECT_FILE_VERSIONS) {
    throw new ProjectFileError("version_limit", "Project file contains too many versions.");
  }
  if (!Array.isArray(document.artifactManifest) || document.artifactManifest.length > MAX_PROJECT_FILE_ARTIFACTS) {
    throw new ProjectFileError("artifact_limit", "Project file contains too many artifact descriptors.");
  }
  const versions = document.versions.map(validateVersion);
  if (versions.some((version) => version.projectId !== project.id || version.state.projectId !== project.id)) {
    throw new ProjectFileError("project_mismatch", "A version belongs to another project.");
  }
  const source = validateProjectFileSource(document.source);
  if (source !== null && working.source !== null && source.sha256 !== working.source.sha256) {
    throw new ProjectFileError("source_mismatch", "Embedded source hash does not match the working document.");
  }
  return {
    format: PROJECT_FILE_FORMAT,
    fileVersion: PROJECT_FILE_VERSION,
    savedAt: validateIsoTimestamp(document.savedAt, "savedAt"),
    project,
    working,
    ui,
    versions,
    source,
    artifactManifest: document.artifactManifest.map(validateArtifact),
  };
}

function decodedByteLength(base64: string): number {
  if (base64.length === 0 || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(base64)) {
    throw new ProjectFileError("invalid_base64", "Embedded source is not valid base64.");
  }
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return (base64.length / 4) * 3 - padding;
}

export function decodeBase64(base64: string, maximumBytes = MAX_EMBEDDED_SOURCE_BYTES): Uint8Array {
  const byteLength = decodedByteLength(base64);
  if (byteLength > maximumBytes) {
    throw new ProjectFileError("embedded_source_too_large", "Embedded source exceeds the configured size limit.");
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

export function encodeBase64(bytes: Uint8Array): string {
  const chunks: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 0x8000)));
  }
  return btoa(chunks.join(""));
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (globalThis.crypto?.subtle === undefined) {
    throw new ProjectFileError("crypto_unavailable", "SHA-256 verification is unavailable in this browser.");
  }
  const detached = Uint8Array.from(bytes).buffer;
  const digest = await globalThis.crypto.subtle.digest("SHA-256", detached);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function readBlobBytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === "function") return new Uint8Array(await blob.arrayBuffer());
  if (typeof FileReader === "undefined") {
    throw new ProjectFileError("blob_read_unavailable", "Blob content cannot be read in this environment.");
  }
  const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Blob read failed"));
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error("Blob reader did not return binary data"));
    };
    reader.readAsArrayBuffer(blob);
  });
  return new Uint8Array(buffer);
}

export async function parseProjectFile(
  text: string,
  options: ParseProjectFileOptions = {},
): Promise<ParsedProjectFile> {
  const maxFileBytes = options.maxFileBytes ?? MAX_PROJECT_FILE_BYTES;
  if (new TextEncoder().encode(text).byteLength > maxFileBytes) {
    throw new ProjectFileError("project_file_too_large", "Project file exceeds the configured size limit.");
  }
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    throw new ProjectFileError("invalid_json", "Project file is not valid JSON.", { cause: error });
  }
  const file = validateProjectFile(raw);
  if (file.source?.kind !== "embedded") return { file, embeddedSource: null };

  const maxEmbedded = options.maxEmbeddedSourceBytes ?? MAX_EMBEDDED_SOURCE_BYTES;
  if (file.source.byteSize > maxEmbedded) {
    throw new ProjectFileError("embedded_source_too_large", "Embedded source exceeds the configured size limit.");
  }
  const bytes = decodeBase64(file.source.dataBase64, maxEmbedded);
  if (bytes.byteLength !== file.source.byteSize) {
    throw new ProjectFileError("source_size_mismatch", "Embedded source byte size does not match its descriptor.");
  }
  if (await sha256Hex(bytes) !== file.source.sha256) {
    throw new ProjectFileError("source_hash_mismatch", "Embedded source failed SHA-256 verification.");
  }
  return {
    file,
    embeddedSource: {
      key: blobKey("source", file.source.sha256),
      sha256: file.source.sha256,
      byteSize: file.source.byteSize,
      mediaType: file.source.mediaType,
      originalFileName: file.source.originalFileName,
      blob: new Blob([Uint8Array.from(bytes).buffer], { type: file.source.mediaType }),
    },
  };
}

export async function openProjectFile(
  file: Blob & { name?: string },
  options: ParseProjectFileOptions = {},
): Promise<ParsedProjectFile> {
  if (file.name !== undefined && !file.name.toLowerCase().endsWith(".mesh2param.json")) {
    throw new ProjectFileError("unsupported_extension", "Open a .mesh2param.json project file.");
  }
  const maxFileBytes = options.maxFileBytes ?? MAX_PROJECT_FILE_BYTES;
  if (file.size > maxFileBytes) {
    throw new ProjectFileError("project_file_too_large", "Project file exceeds the configured size limit.");
  }
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(await readBlobBytes(file));
  } catch (error) {
    if (error instanceof ProjectFileError) throw error;
    throw new ProjectFileError("invalid_encoding", "Project file must be valid UTF-8.", { cause: error });
  }
  return parseProjectFile(text, options);
}

export async function projectFileSourceFromBlob(
  input: ProjectFileSourceInput,
  maximumEmbeddedBytes = MAX_EMBEDDED_SOURCE_BYTES,
): Promise<ProjectFileSource> {
  validateSha256(input.sha256);
  if (input.blob.size !== input.byteSize) {
    throw new ProjectFileError("source_size_mismatch", "Source Blob size does not match its descriptor.");
  }
  if (input.byteSize > maximumEmbeddedBytes) {
    return {
      kind: "local-reference",
      blobKey: blobKey("source", input.sha256),
      sha256: input.sha256,
      byteSize: input.byteSize,
      mediaType: input.mediaType,
      originalFileName: input.originalFileName,
    } satisfies LocalBlobReference;
  }
  const bytes = await readBlobBytes(input.blob);
  if (await sha256Hex(bytes) !== input.sha256) {
    throw new ProjectFileError("source_hash_mismatch", "Source Blob failed SHA-256 verification.");
  }
  return {
    kind: "embedded",
    sha256: input.sha256,
    byteSize: input.byteSize,
    mediaType: input.mediaType,
    originalFileName: input.originalFileName,
    dataBase64: encodeBase64(bytes),
  } satisfies EmbeddedBlob;
}

export function createProjectFile(input: Omit<Mesh2ParamProjectFile, "format" | "fileVersion" | "savedAt"> & {
  savedAt?: string;
}): Mesh2ParamProjectFile {
  return {
    format: PROJECT_FILE_FORMAT,
    fileVersion: PROJECT_FILE_VERSION,
    savedAt: input.savedAt ?? new Date().toISOString(),
    project: input.project,
    working: input.working,
    ui: input.ui,
    versions: input.versions,
    source: input.source,
    artifactManifest: input.artifactManifest,
  };
}

export function serializeProjectFile(file: Mesh2ParamProjectFile): string {
  return `${JSON.stringify(file, null, 2)}\n`;
}

export async function saveProjectFile(
  file: Mesh2ParamProjectFile,
  options: { handle?: ProjectFileHandle; suggestedName?: string; preferFileSystemAccess?: boolean } = {},
): Promise<ProjectFileSaveResult> {
  const serialized = serializeProjectFile(file);
  let handle = options.handle ?? null;
  const picker = (globalThis as typeof globalThis & {
    showSaveFilePicker?: (options: unknown) => Promise<ProjectFileHandle>;
  }).showSaveFilePicker;
  if (handle === null && options.preferFileSystemAccess !== false && picker !== undefined) {
    handle = await picker({
      suggestedName: options.suggestedName ?? DEFAULT_PROJECT_FILENAME,
      types: [{ description: "Mesh2Param project", accept: { "application/json": [".mesh2param.json"] } }],
    });
  }
  if (handle !== null) {
    const writable = await handle.createWritable();
    await writable.write(serialized);
    await writable.close();
    return { method: "file-system-access", handle };
  }
  if (typeof document === "undefined" || typeof URL.createObjectURL !== "function") {
    throw new ProjectFileError("download_unavailable", "Browser download is unavailable.");
  }
  const url = URL.createObjectURL(new Blob([serialized], { type: "application/json" }));
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = options.suggestedName ?? DEFAULT_PROJECT_FILENAME;
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
  return { method: "download", handle: null };
}
