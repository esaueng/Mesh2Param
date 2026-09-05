/**
 * The message protocol between the browser-mode API client and the geometry
 * worker. The worker is a thin envelope around `@mesh2param/core-wasm`: the
 * Rust reconstruction core does the geometry, so this file describes transport
 * shapes only and deliberately holds no geometric knowledge of its own.
 */
import type { CADGraph } from "@mesh2param/contracts";

/** A renderable triangle soup. Only the source preview is built in JavaScript. */
export interface BrowserMesh {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
  vertexCount: number;
  triangleCount: number;
}

export interface BrowserEdgeLines {
  positions: Float32Array;
  indices: Uint32Array;
  segmentCount: number;
}

/** Mesh containers the core reads. */
export type BrowserMeshFormat = "stl" | "3mf" | "obj" | "ply";

/** Stages the core reports, in the order it runs them. */
export type BrowserGeometryStage = "parse" | "weld" | "segment" | "topology" | "build" | "verify" | "step";

/** The tier a reconstruction landed at. Reported, never asserted. */
export type BrowserReconstructionTier = "analytic" | "mixed" | "faceted";

/**
 * Which reconstruction the UI asked for. The core runs one ladder and reports
 * the tier it reached; `faceted` only pins the triangle budget, it cannot force
 * a tier, so all three modes report their measured tier back.
 */
export type BrowserReconstructionMode = "automatic" | "curved" | "faceted";

/**
 * What `analyze` reports. Everything except `mesh`, `bounds`, `surfaceArea`
 * and `closedVolume` comes from the core; those four are measured while the
 * source bytes are parsed for display, because the core's analysis returns
 * statistics rather than geometry. Fields the core does not measure are absent
 * rather than guessed.
 */
export interface BrowserMeshAnalysis {
  mesh: BrowserMesh;
  triangleCount: number;
  /** Unwelded vertices, i.e. three per triangle. */
  rawVertexCount: number;
  /** Distinct vertices after the core's weld. */
  weldedVertexCount: number;
  /** Triangles the core dropped as degenerate while welding. */
  droppedTriangleCount: number;
  nonManifoldEdgeCount: number;
  /** Every edge has exactly two owning triangles. */
  watertight: boolean;
  /** No edge has more than two owning triangles. */
  edgeManifold: boolean;
  bounds: [[number, number, number], [number, number, number]];
  surfaceArea: number;
  /** Divergence-theorem volume; `null` when the mesh is not closed. */
  closedVolume: number | null;
}

/** How far the result sits from the mesh it was reconstructed from. */
export interface BrowserDeviation {
  p95: number;
  max: number;
  samples: number;
}

/** Recognised surfaces in the finished solid, by type. */
export interface BrowserSurfaceInventory {
  plane: number;
  cylinder: number;
  cone: number;
  torus: number;
  sphere: number;
  unknown: number;
}

/** What `reconstruct` reports, plus the two files it produced. */
export interface BrowserReconstruction {
  tier: BrowserReconstructionTier;
  /** The finished solid passes kernel validation with no errors. */
  valid: boolean;
  issues: string[];
  /** Why the run did not stay at the tier it was aiming for. */
  fallbackReason: string | null;
  facesAnalytic: number;
  facesTriangle: number;
  facesFinal: number;
  /** `null` when verification was off or the tessellation failed. */
  deviation: BrowserDeviation | null;
  volume: number;
  sourceVolume: number;
  stepBytes: number;
  /** The kernel's own reader read the STEP file back. */
  roundTripOk: boolean;
  inventory: BrowserSurfaceInventory;
  /** Share of surface area no primitive was recognised on. */
  unknownAreaFraction: number;
  patches: number | null;
  edges: number | null;
  /** The AP203 STEP file. */
  step: ArrayBuffer;
  /** The result tessellation as binary glTF. */
  glb: ArrayBuffer;
}

/** A failure the UI can distinguish, rather than only display. */
export interface BrowserGeometryError {
  code: "budget" | "unsupported" | "geometry";
  stage: BrowserGeometryStage | "request";
  message: string;
}

export interface AnalyzeGeometryRequest {
  id: string;
  operation: "analyze";
  bytes: ArrayBuffer;
  format: BrowserMeshFormat;
}

export interface ReconstructGeometryRequest {
  id: string;
  operation: "reconstruct";
  bytes: ArrayBuffer;
  format: BrowserMeshFormat;
  mode: BrowserReconstructionMode;
  tolerance: number | null;
  deflection: number | null;
  triangleBudget: number;
}

/**
 * Rebuilding a STEP file from a CADGraph. The core takes mesh bytes, not a
 * feature history, so the worker answers this with a structured refusal; the
 * request stays in the protocol so the refusal is a defined answer rather than
 * an unrecognised message.
 */
export interface CadgraphGeometryRequest {
  id: string;
  operation: "cadgraph";
  graph: CADGraph;
}

export type BrowserGeometryRequest = AnalyzeGeometryRequest | ReconstructGeometryRequest | CadgraphGeometryRequest;

export type BrowserGeometryResult = BrowserMeshAnalysis | BrowserReconstruction;

export type GeometryResponse =
  | { id: string; ok: true; result: BrowserGeometryResult }
  | { id: string; ok: false; error: string; structuredError?: BrowserGeometryError }
  | { id: string; progress: true; stage: BrowserGeometryStage; fraction: number; message: string };
