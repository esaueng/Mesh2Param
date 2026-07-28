import type { CADGraph, JsonValue, Units } from "@mesh2param/contracts";

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

export interface BrowserMeshDiagnostics {
  rawVertexCount: number;
  weldedVertexCount: number;
  duplicateVertexCount: number;
  connectedComponentCount: number;
  degenerateTriangleCount: number;
  duplicateFaceCount: number;
  nonManifoldEdgeCount: number;
  openBoundaryEdgeCount: number;
  openBoundaryCount: number;
  watertight: boolean;
  windingConsistent: boolean;
}

export interface BrowserCadResult {
  step: string;
  mesh: BrowserMesh;
  edgeLines?: BrowserEdgeLines;
  valid: boolean;
  solid: boolean;
  stepReimportValid: boolean;
  volume: number;
  surfaceArea: number;
  bounds: [[number, number, number], [number, number, number]];
  featureCount: number;
  surfaceCounts?: Record<string, number>;
  topologyCounts?: Record<string, number>;
  reimportSurfaceCounts?: Record<string, number>;
  reimportTopologyCounts?: Record<string, number>;
  stepReimportRelativeVolumeDelta?: number | null;
  diagnostics?: BrowserMeshDiagnostics;
  curvedReconstruction?: {
    scope: "axis-aligned layered approximate curved B-Rep";
    axisIndex: 0 | 1 | 2;
    sectionCount: number;
    outerProfileCount: number;
    holeTrackCount: number;
    sourceTriangleCount: number;
    reconstructionMode: "smooth-loft" | "representative-extrusion";
    sourceVolume: number;
    resultVolume: number;
    relativeVolumeDelta: number;
    maximumBoundsDelta: number;
    faceSurfaces: Record<string, number>;
  };
}

export type BrowserGeometryStage =
  | "ingest"
  | "sections"
  | "profile-fitting"
  | "candidate-build"
  | "occt-compile"
  | "comparison"
  | "step-roundtrip"
  | "complete";

export interface BrowserReconstructionError {
  stage: BrowserGeometryStage;
  code: string;
  message: string;
  measured: Record<string, number | string>;
  sourceTriangleIds: number[];
}

export interface BrowserComparisonReport {
  sampleCountEachDirection: number;
  distance: { rms: number; median: number; p95: number; p99: number; maximum: number };
  normals: { meanAgreement: number; p95AngleDeg: number };
  relativeVolumeDelta: number | null;
  tolerance: number;
  toleranceSurfaceCoverage: number;
}

export interface BrowserParametricEvidence {
  family: "general-parametric-prismatic";
  detailMode: "functional" | "full";
  acceptance: "strict" | "functional-approximation";
  toleranceSatisfied: boolean;
  featureSequence: string[];
  axis: [number, number, number];
  thickness: number;
  filletRadius: number | null;
  chamferWidth: number | null;
  surfaceCounts: Record<string, number>;
  comparison: BrowserComparisonReport;
  diagnostics: BrowserReconstructionError[];
  timingsMs: Record<string, number>;
}

export interface BrowserParametricResult extends BrowserCadResult {
  graph: CADGraph;
  parametricReconstruction: BrowserParametricEvidence;
  candidates: Array<{
    label: string;
    accepted: boolean;
    score: number | null;
    reason: BrowserReconstructionError | null;
  }>;
  suppressedRegions: Array<Record<string, JsonValue>>;
  suppressedMesh: BrowserMesh | null;
}

export interface BrowserParametricProbe {
  supported: boolean;
  family: "general-parametric-prismatic";
  triangleCount: number;
  featureHints: string[];
  detailDetected: boolean;
  analysis: Record<string, unknown>;
  error: BrowserReconstructionError | null;
}

export interface GeometryRequest {
  id: string;
  operation: "cadgraph";
  graph: CADGraph;
}

export interface StlGeometryRequest {
  id: string;
  operation: "stl";
  bytes: ArrayBuffer;
  tolerance: number;
  solidify: boolean;
  validateStep: boolean;
}

export interface CurvedStlGeometryRequest {
  id: string;
  operation: "curved-stl";
  bytes: ArrayBuffer;
  tolerance: number;
}

export interface ParametricStlGeometryRequest {
  id: string;
  operation: "parametric-stl";
  bytes: ArrayBuffer;
  source: {
    sha256: string;
    originalFileName: string;
    byteSize: number;
    declaredUnits: Units;
    scaleFactor: number;
  };
  units: Units;
  tolerance: number;
  detailMode: "functional" | "full";
  deterministicSeed: number;
}

export interface ParametricProbeGeometryRequest {
  id: string;
  operation: "parametric-probe";
  bytes: ArrayBuffer;
  scaleFactor: number;
  tolerance: number;
}

export type BrowserGeometryRequest = GeometryRequest | StlGeometryRequest | CurvedStlGeometryRequest | ParametricStlGeometryRequest | ParametricProbeGeometryRequest;

export type BrowserGeometryResult = BrowserCadResult | BrowserParametricProbe;

export type GeometryResponse =
  | { id: string; ok: true; result: BrowserGeometryResult }
  | { id: string; ok: false; error: string; structuredError?: BrowserReconstructionError }
  | { id: string; progress: true; stage: BrowserGeometryStage; fraction: number; message: string };
