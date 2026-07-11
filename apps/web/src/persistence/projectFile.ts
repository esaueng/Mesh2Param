import { migrateCADGraph } from "@mesh2param/contracts";

import type {
  ArtifactDescriptor,
  EmbeddedBlob,
  LocalBlobReference,
  Mesh2ParamProjectFile,
  ProjectFileSource,
  ProjectSummary,
  ProjectVersionSnapshot,
  ProjectWorkingDocument,
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
const UNITS = new Set<Units>(["mm", "cm", "m", "in", "ft"]);

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
    createdAt: requiredString(value, "createdAt"),
    updatedAt: requiredString(value, "updatedAt"),
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
  if (typeof value.id === "string") descriptor.id = value.id;
  if (typeof value.kind === "string") descriptor.kind = value.kind;
  if (typeof value.storageKey === "string") descriptor.storageKey = value.storageKey;
  if (isRecord(value.metadata)) descriptor.metadata = value.metadata as NonNullable<ArtifactDescriptor["metadata"]>;
  if (typeof value.createdAt === "string") descriptor.createdAt = value.createdAt;
  return descriptor;
}

function validateSourceAsset(value: unknown): ProjectWorkingDocument["source"] {
  if (value === null) return null;
  if (!isRecord(value)) throw new ProjectFileError("invalid_source", "working.source must be an object or null.");
  const units = requiredString(value, "declaredUnits") as Units;
  if (!UNITS.has(units)) throw new ProjectFileError("invalid_units", "source declaredUnits is unsupported.");
  const scaleFactor = value.scaleFactor;
  if (typeof scaleFactor !== "number" || !Number.isFinite(scaleFactor) || scaleFactor <= 0) {
    throw new ProjectFileError("invalid_source", "source scaleFactor must be finite and positive.");
  }
  return {
    id: requiredString(value, "id"),
    originalFileName: requiredString(value, "originalFileName"),
    format: requiredString(value, "format"),
    encoding: requiredString(value, "encoding"),
    sha256: validateSha256(requiredString(value, "sha256")),
    byteSize: nonNegativeInteger(value, "byteSize"),
    declaredUnits: units,
    unitsConfirmed: value.unitsConfirmed === true,
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
  return {
    schemaVersion: requiredString(value, "schemaVersion"),
    projectId: requiredString(value, "projectId"),
    name: requiredString(value, "name"),
    units,
    source: validateSourceAsset(value.source),
    diagnostics: value.diagnostics as ProjectWorkingDocument["diagnostics"],
    repair: value.repair as ProjectWorkingDocument["repair"],
    analysis: value.analysis as ProjectWorkingDocument["analysis"],
    patches: value.patches as ProjectWorkingDocument["patches"],
    cadgraph,
    validation: value.validation as ProjectWorkingDocument["validation"],
    metrics: value.metrics as ProjectWorkingDocument["metrics"],
    artifactSetId: nullableString(value, "artifactSetId"),
    artifacts: value.artifacts.map(validateArtifact),
    currentVersionId: nullableString(value, "currentVersionId"),
    settings: value.settings as ProjectWorkingDocument["settings"],
  };
}

function validateVersion(value: unknown): ProjectVersionSnapshot {
  if (!isRecord(value)) throw new ProjectFileError("invalid_version", "version snapshot must be an object.");
  return {
    id: requiredString(value, "id"),
    projectId: requiredString(value, "projectId"),
    parentId: nullableString(value, "parentId"),
    label: requiredString(value, "label"),
    state: validateWorking(value.state),
    sourceSha256: value.sourceSha256 === null ? null : validateSha256(requiredString(value, "sourceSha256")),
    validationStatus: requiredString(value, "validationStatus"),
    metrics: value.metrics as ProjectVersionSnapshot["metrics"],
    artifactSetId: nullableString(value, "artifactSetId"),
    engineVersion: requiredString(value, "engineVersion"),
    dependencyVersions: isRecord(value.dependencyVersions)
      ? value.dependencyVersions as ProjectVersionSnapshot["dependencyVersions"]
      : {},
    createdAt: requiredString(value, "createdAt"),
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
  if (document.fileVersion === PROJECT_FILE_VERSION) return document;
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
    savedAt: requiredString(document, "savedAt"),
    project,
    working,
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
