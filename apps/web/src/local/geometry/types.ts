import type { CADGraph } from "@mesh2param/contracts";

export interface BrowserMesh {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
  vertexCount: number;
  triangleCount: number;
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
  valid: boolean;
  solid: boolean;
  stepReimportValid: boolean;
  volume: number;
  surfaceArea: number;
  bounds: [[number, number, number], [number, number, number]];
  featureCount: number;
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

export type BrowserGeometryRequest = GeometryRequest | StlGeometryRequest | CurvedStlGeometryRequest;

export type GeometryResponse =
  | { id: string; ok: true; result: BrowserCadResult }
  | { id: string; ok: false; error: string };
