import type { CADGraph, JsonValue, Units } from "@mesh2param/contracts";
import type { Patch } from "immer";

export type { JsonValue, Units };

export type JsonObject = { [key: string]: JsonValue };
export type IsoTimestamp = string;
export type Sha256 = string;

export interface ApiMeta {
  requestId: string;
}

export interface SuccessEnvelope<T> {
  data: T;
  meta: ApiMeta;
}

export interface ApiErrorDetails {
  status: number;
  code: string;
  summary: string;
  detail: string;
  phase: string | null;
  projectId: string | null;
  jobId: string | null;
  recoverable: boolean;
  recommendedAction: string | null;
  requestId: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  units: Units;
  schemaVersion: string;
  revision: number;
  basedOnVersionId: string | null;
  createdAt: IsoTimestamp;
  updatedAt: IsoTimestamp;
}

export interface SourceAssetDescriptor {
  id: string;
  originalFileName: string;
  format: "stl" | "obj" | "ply" | string;
  encoding: string;
  sha256: Sha256;
  byteSize: number;
  declaredUnits: Units;
  unitsConfirmed: boolean;
  scaleFactor: number;
  state: string;
}

export interface DiagnosticWarning {
  code: string;
  message: string;
  severity: "warning";
}

export interface MeshDiagnostics {
  format: "stl" | "obj" | "ply";
  encoding: string;
  byteSize: number;
  sha256: Sha256;
  rawVertexCount: number;
  weldedVertexCount: number;
  duplicateVertexCount: number;
  triangleCount: number;
  connectedComponentCount: number;
  bounds: [[number, number, number], [number, number, number]];
  boundingDimensions: [number, number, number];
  coordinateRange: [number, number];
  surfaceArea: number;
  closedVolume: number | null;
  watertight: boolean;
  windingConsistent: boolean;
  degenerateTriangleCount: number;
  duplicateFaceCount: number;
  nonManifoldEdgeCount: number;
  openBoundaryEdgeCount: number;
  openBoundaryCount: number;
  selfIntersectionStatus: string;
  warnings: DiagnosticWarning[];
}

export interface MeshStateMetrics {
  versionId: string;
  vertexCount: number;
  triangleCount: number;
  connectedComponentCount: number;
  surfaceArea: number;
  closedVolume: number | null;
  watertight: boolean;
  windingConsistent: boolean;
  degenerateTriangleCount: number;
  duplicateFaceCount: number;
  nonManifoldEdgeCount: number;
  openBoundaryEdgeCount: number;
  openBoundaryCount: number;
}

export interface RepairOperation {
  id: string;
  order: number;
  operation: string;
  enabled: boolean;
  parameters: JsonObject;
  sourceVersionId: string;
  resultVersionId: string;
  before: MeshStateMetrics;
  after: MeshStateMetrics;
  warnings: string[];
  reversible: boolean;
  timestamp: IsoTimestamp;
  changed: boolean;
}

export interface RepairResult {
  sourceId: string;
  resultId: string;
  sourceSha256: Sha256 | null;
  settings: JsonObject;
  operations: RepairOperation[];
  sourceMetrics: MeshStateMetrics;
  resultMetrics: MeshStateMetrics;
  diagnostics: MeshDiagnostics;
  warnings: string[];
}

export interface ResidualStats {
  rms: number;
  median: number;
  p95: number;
  max: number;
}

export type PatchClassification =
  | "plane"
  | "cylinder"
  | "cone"
  | "sphere"
  | "torus"
  | "freeform"
  | "unknown";

export interface SurfacePatch {
  id: string;
  type: PatchClassification;
  name?: string;
  triangleCount: number | null;
  triangleIds?: number[];
  vertexCount?: number;
  areaMm2?: number;
  centroid?: [number, number, number];
  residualsMm?: ResidualStats;
  confidence: number | null;
  neighborIds?: string[];
  boundaryLoops?: Array<{ vertexIds: number[]; closed: boolean }>;
  fit?: JsonObject;
  userOverriddenClassification?: boolean;
  /** Neighbor ids whose shared boundary the user declared a smooth join. */
  smoothBoundaryIds?: string[];
  locked: boolean;
  hidden?: boolean;
  excludedTriangleIds?: number[];
  mergedFrom?: string[];
}

export interface CandidateHistory {
  label: string;
  score: number;
  valid: boolean;
  rejectionReason: string | null;
  featureCount: number;
  cadgraph?: CADGraph;
  kernel: JsonObject;
  comparison: JsonObject | null;
}

export type DetailedValidationStatus =
  | "not-run"
  | "running"
  | "valid"
  | "valid-with-warnings"
  | "invalid-brep"
  | "step-export-failed"
  | "step-reimport-failed"
  | "outside-tolerance"
  | string;

export interface DetailedValidationResult {
  status: DetailedValidationStatus;
  brepValid: boolean | null;
  stepReimportValid: boolean | null;
  toleranceSatisfied: boolean | null;
  issues?: JsonValue[];
  step?: JsonObject;
  compilation?: JsonObject;
}

export interface ArtifactDescriptor {
  id?: string;
  name: string;
  kind?: string;
  sha256: Sha256;
  byteSize: number;
  mediaType: string;
  storageKey?: string;
  metadata?: JsonObject;
  createdAt?: IsoTimestamp;
}

export interface ProjectWorkingDocument {
  schemaVersion: string;
  projectId: string;
  name: string;
  units: Units;
  source: SourceAssetDescriptor | null;
  diagnostics: MeshDiagnostics | null;
  repair: RepairResult | null;
  analysis: JsonObject | null;
  patches: SurfacePatch[];
  cadgraph: CADGraph | null;
  validation: DetailedValidationResult | null;
  metrics: JsonObject | null;
  artifactSetId: string | null;
  artifacts: ArtifactDescriptor[];
  currentVersionId: string | null;
  settings: JsonObject;
}

export interface ProjectDetail extends ProjectSummary {
  state: ProjectWorkingDocument;
}

export interface ProjectVersionSnapshot {
  id: string;
  projectId: string;
  parentId: string | null;
  label: string;
  state: ProjectWorkingDocument;
  sourceSha256: Sha256 | null;
  validationStatus: string;
  metrics: JsonObject | null;
  artifactSetId: string | null;
  engineVersion: string;
  dependencyVersions: JsonObject;
  createdAt: IsoTimestamp;
}

export type JobKind =
  | "upload"
  | "repair"
  | "analyze"
  | "reconstruct"
  | "rebuild"
  | "validate"
  | "export"
  | "sample_open"
  | (string & {});

export type JobStatus = "queued" | "running" | "completed" | "cancelled" | "failed";
export type JobEventType = "progress" | "heartbeat" | "log" | "completed" | "cancelled" | "failed";

export interface JobError {
  code: string;
  summary: string | null;
  detail: string | null;
  phase: string;
  projectId: string;
  jobId: string;
  recoverable: boolean;
  recommendedAction: string | null;
}

export interface Job {
  id: string;
  projectId: string;
  kind: JobKind;
  status: JobStatus;
  progress: number;
  phase: string;
  inputRevision: number;
  attempt: number;
  maxAttempts: number;
  createdAt: IsoTimestamp;
  startedAt: IsoTimestamp | null;
  heartbeatAt: IsoTimestamp | null;
  finishedAt: IsoTimestamp | null;
  cancelRequestedAt: IsoTimestamp | null;
  error: JobError | null;
  result: JsonObject | null;
  eventsUrl: string;
}

export interface JobEvent {
  jobId: string;
  type: JobEventType;
  phase: string;
  progress: number | null;
  level: "debug" | "info" | "warning" | "error";
  message: string | null;
  detail?: string | null;
  code: string | null;
  timestamp: IsoTimestamp;
  status?: JobStatus;
  result?: JsonObject;
  recoverable?: boolean;
  recommendedAction?: string | null;
  previousPhase?: string;
  previousPhaseDurationMs?: number;
}

export interface JobLogEntry {
  timestamp: IsoTimestamp;
  phase: string;
  level: JobEvent["level"];
  message: string;
  code: string | null;
}

export type JobConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface JobViewState {
  job: Job;
  connection: JobConnectionState;
  logs: JobLogEntry[];
  cancelling: boolean;
  lastEventAt: IsoTimestamp | null;
}

export interface ProjectList {
  items: ProjectDetail[];
  total: number;
}

export interface PatchPage {
  items: SurfacePatch[];
  total: number;
}

export interface ArtifactPage {
  items: ArtifactDescriptor[];
  total: number;
}

export interface VersionPage {
  items: ProjectVersionSnapshot[];
  total: number;
}

export interface SampleDescriptor {
  id: string;
  name: string;
  seed: number;
  expectedBoundingBox: number[];
  expectedVolume: number;
  expectedPlanarFaces: number;
  expectedCylindricalFaces: number;
  automaticReconstructionSupported: boolean;
  triangleCount: number;
  intendedOperations: string[];
  toleranceMm: number;
  thumbnailUrl: string;
}

export interface SamplePage {
  items: SampleDescriptor[];
  total: number;
}

export interface Readiness {
  status: "ready" | "not-ready";
  database: boolean;
  storage: boolean;
  supervisor: boolean;
}

export type WorkflowStep = "import" | "repair" | "surfaces" | "features" | "refine" | "validate" | "export";
export type StepStatus = "inactive" | "active" | "complete" | "warning" | "failed" | "disabled";

export interface StepState {
  status: StepStatus;
  label?: string;
  detail?: string;
}

export interface WorkflowState {
  active: WorkflowStep;
  completion: Record<WorkflowStep, StepState>;
}

export interface SelectionState {
  patchId: string | null;
  featureId: string | null;
  sketchEntityId: string | null;
  hoverId: string | null;
}

export type ViewerLayer = "source" | "repaired" | "analysis" | "patches" | "reconstructed" | "residual";
export type ViewerMode = ViewerLayer | "overlay";
export type ViewerShading = "shaded" | "wireframe" | "xray" | "normals" | "zebra";

export interface ViewerPreferences {
  mode: ViewerMode;
  visible: Record<ViewerLayer, boolean>;
  sourceOpacity: number;
  resultOpacity: number;
  projection: "perspective" | "orthographic";
  shading: ViewerShading;
  edges: boolean;
}

export interface CameraPose {
  projectId: string;
  artifactBoundsHash: string;
  position: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
  projection: ViewerPreferences["projection"];
  zoom: number;
}

export interface ShellState {
  theme: "dark" | "light";
  railCollapsed: boolean;
  inspectorExpanded: boolean;
  bottomDrawerExpanded: boolean;
  bottomDrawerHeight: number;
  singleKeyShortcuts: boolean;
  activeDialog: "conflict" | "versions" | "project-units" | null;
}

export interface PersistedProjectUI {
  activeStep: WorkflowStep;
  selection: SelectionState;
  viewer: ViewerPreferences;
  shell: Pick<
    ShellState,
    "theme" | "railCollapsed" | "inspectorExpanded" | "bottomDrawerExpanded" | "bottomDrawerHeight" | "singleKeyShortcuts"
  >;
  cameraPose: CameraPose | null;
}

export type SyncStateName = "clean" | "saving" | "offline" | "conflict" | "error";

export interface SyncState {
  state: SyncStateName;
  dirtyRevision?: number;
  error?: ApiErrorDetails;
}

export type HistoryScope =
  | "project"
  | "settings"
  | "repair"
  | "segmentation"
  | "patches"
  | "cadgraph"
  | "features"
  | "sketches"
  | "constraints"
  | "validation";

export interface HistoryEntry {
  id: string;
  label: string;
  timestamp: IsoTimestamp;
  forwardPatches: Patch[];
  inversePatches: Patch[];
  scopes: HistoryScope[];
  beforeLocalRevision: number;
  afterLocalRevision: number;
  requiresRebuild: boolean;
  serializedBytes: number;
  rejected?: ApiErrorDetails;
}

export interface HistoryState {
  past: HistoryEntry[];
  future: HistoryEntry[];
}

export type ProjectEditRecipe = (draft: ProjectWorkingDocument) => void;

export interface EmbeddedBlob {
  kind: "embedded";
  sha256: Sha256;
  byteSize: number;
  mediaType: string;
  originalFileName: string;
  dataBase64: string;
}

export interface LocalBlobReference {
  kind: "local-reference";
  blobKey: string;
  sha256: Sha256;
  byteSize: number;
  mediaType: string;
  originalFileName: string;
}

export type ProjectFileSource = EmbeddedBlob | LocalBlobReference;

export interface Mesh2ParamProjectFile {
  format: "mesh2param-project";
  fileVersion: 1;
  savedAt: IsoTimestamp;
  project: ProjectSummary;
  working: ProjectWorkingDocument;
  ui: PersistedProjectUI;
  versions: ProjectVersionSnapshot[];
  source: ProjectFileSource | null;
  artifactManifest: ArtifactDescriptor[];
}
