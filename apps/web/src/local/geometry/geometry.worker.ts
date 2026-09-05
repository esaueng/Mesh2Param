/**
 * The browser-local geometry worker.
 *
 * Everything geometric happens inside `@mesh2param/core-wasm` — the same Rust
 * reconstruction core the corpus scoreboard measures — so this file only
 * translates between the worker protocol and that package. The core is
 * synchronous and single-threaded once initialised, which is exactly why it
 * runs here and not on the main thread.
 */
import {
  analyze as coreAnalyze,
  init as coreInit,
  reconstruct as coreReconstruct,
  type ReconstructOptions,
  type ReconstructResult,
  type Stage,
} from "@mesh2param/core-wasm";
import wasmUrl from "@mesh2param/core-wasm/pkg/mesh2param_wasm_bg.wasm?url";

import { parseStlForDisplay } from "./sourceMesh";
import type {
  BrowserGeometryError,
  BrowserGeometryRequest,
  BrowserGeometryStage,
  BrowserMeshAnalysis,
  BrowserMeshFormat,
  BrowserReconstruction,
  GeometryResponse,
  ReconstructGeometryRequest,
} from "./types";

const workerScope = self as unknown as { postMessage(message: unknown, transfer?: Transferable[]): void };

/**
 * Share of a run each stage is worth, so the single progress number the job UI
 * shows is monotone. The core reports `fraction` *within* a stage; the weights
 * are the measured shape of a run (construction dominates), not equal slices.
 */
const STAGE_WEIGHTS: Record<Stage, number> = {
  parse: 0.04,
  weld: 0.04,
  segment: 0.16,
  topology: 0.06,
  build: 0.45,
  verify: 0.15,
  step: 0.10,
};

const STAGE_ORDER: Stage[] = ["parse", "weld", "segment", "topology", "build", "verify", "step"];

const STAGE_MESSAGES: Record<Stage, string> = {
  parse: "Reading the mesh",
  weld: "Welding vertices",
  segment: "Fitting surfaces to the mesh",
  topology: "Building topology",
  build: "Constructing the solid",
  verify: "Measuring the result against the mesh",
  step: "Writing the STEP file",
};

const CADGRAPH_UNSUPPORTED: BrowserGeometryError = {
  code: "unsupported",
  stage: "request",
  message: "Rebuilding a STEP file from a CADGraph is not available in browser mode. "
    + "The browser reconstruction core converts mesh bytes into a STEP file; it does not replay a "
    + "feature history. Run this project against the Mesh2Param service to rebuild it from its CADGraph.",
};

function overallFraction(stage: Stage, fraction: number): number {
  let completed = 0;
  for (const previous of STAGE_ORDER) {
    if (previous === stage) break;
    completed += STAGE_WEIGHTS[previous];
  }
  return Math.min(1, completed + STAGE_WEIGHTS[stage] * Math.min(1, Math.max(0, fraction)));
}

function progress(id: string, stage: Stage, fraction: number): void {
  workerScope.postMessage({
    id,
    progress: true,
    stage: stage as BrowserGeometryStage,
    fraction: overallFraction(stage, fraction),
    message: STAGE_MESSAGES[stage],
  } satisfies GeometryResponse);
}

let ready: Promise<void> | null = null;
function core(): Promise<void> {
  ready ??= coreInit(wasmUrl);
  return ready;
}

async function runAnalyze(bytes: ArrayBuffer, format: BrowserMeshFormat): Promise<BrowserMeshAnalysis> {
  await core();
  const stats = coreAnalyze(new Uint8Array(bytes), format);
  // The core reports statistics, not geometry. STL is parsed here for the
  // viewer's source layer; other containers reconstruct without a preview.
  const parsed = format === "stl" ? parseStlForDisplay(bytes) : null;
  return {
    mesh: parsed?.mesh ?? { positions: new Float32Array(0), normals: new Float32Array(0), indices: new Uint32Array(0), vertexCount: 0, triangleCount: 0 },
    triangleCount: stats.triangles,
    rawVertexCount: stats.triangles * 3,
    weldedVertexCount: stats.vertices,
    droppedTriangleCount: stats.droppedTriangles,
    nonManifoldEdgeCount: stats.nonManifoldEdges,
    watertight: stats.watertight,
    edgeManifold: stats.edgeManifold,
    bounds: [stats.bbox.min, stats.bbox.max],
    surfaceArea: parsed?.surfaceArea ?? 0,
    closedVolume: parsed !== null && stats.watertight ? parsed.signedVolume : null,
  };
}

function bytesOf(value: Uint8Array): ArrayBuffer {
  // wasm-bindgen hands back a view onto the module's own memory; copy it out so
  // the buffer can be transferred and outlive the next call.
  return value.slice().buffer as ArrayBuffer;
}

/**
 * `serde_wasm_bindgen` omits `None` fields rather than emitting `null`, and the
 * workspace document's canonical serialization refuses `undefined`. Every
 * optional field is normalised to `null` here, at the one boundary where the
 * difference appears.
 */
function toReconstruction(result: ReconstructResult): BrowserReconstruction {
  return {
    tier: result.tier,
    valid: result.valid,
    issues: result.issues ?? [],
    fallbackReason: result.fallbackReason ?? null,
    facesAnalytic: result.facesAnalytic,
    facesTriangle: result.facesTriangle,
    facesFinal: result.facesFinal,
    deviation: result.deviation ?? null,
    volume: result.volume,
    sourceVolume: result.sourceVolume,
    stepBytes: result.stepBytes,
    roundTripOk: result.roundTripOk,
    inventory: result.inventory,
    unknownAreaFraction: result.unknownAreaFraction,
    patches: result.patches ?? null,
    edges: result.edges ?? null,
    step: bytesOf(result.step),
    glb: bytesOf(result.glb),
  };
}

/**
 * `request.mode` is what the UI asked for, and the client records it as the
 * requested mode. It deliberately does not change what runs: the core exposes
 * no way to force a tier, so pretending a "faceted" request produced a faceted
 * result would be a claim the core never made. The tier in the reply is the one
 * the ladder actually reached.
 */
async function runReconstruct(request: ReconstructGeometryRequest): Promise<BrowserReconstruction> {
  await core();
  const options: ReconstructOptions = {
    triangleBudget: request.triangleBudget,
    ...(request.tolerance === null ? {} : { tolerance: request.tolerance }),
    ...(request.deflection === null ? {} : { deflection: request.deflection }),
  };
  return toReconstruction(coreReconstruct(
    new Uint8Array(request.bytes),
    request.format,
    options,
    (stage, fraction) => { progress(request.id, stage, fraction); },
  ));
}

function structuredError(cause: unknown): BrowserGeometryError | null {
  if (!(cause instanceof Error)) return null;
  if (cause.name === "BudgetError") return { code: "budget", stage: "parse", message: cause.message };
  return null;
}

async function processRequest(request: BrowserGeometryRequest): Promise<void> {
  try {
    if (request.operation === "cadgraph") {
      workerScope.postMessage({
        id: request.id,
        ok: false,
        error: CADGRAPH_UNSUPPORTED.message,
        structuredError: CADGRAPH_UNSUPPORTED,
      } satisfies GeometryResponse);
      return;
    }
    if (request.operation === "analyze") {
      const result = await runAnalyze(request.bytes, request.format);
      workerScope.postMessage(
        { id: request.id, ok: true, result } satisfies GeometryResponse,
        [result.mesh.positions.buffer as ArrayBuffer, result.mesh.normals.buffer as ArrayBuffer, result.mesh.indices.buffer as ArrayBuffer],
      );
      return;
    }
    const result = await runReconstruct(request);
    workerScope.postMessage(
      { id: request.id, ok: true, result } satisfies GeometryResponse,
      [result.step, result.glb],
    );
  } catch (cause) {
    const structured = structuredError(cause);
    workerScope.postMessage({
      id: request.id,
      ok: false,
      error: cause instanceof Error ? cause.message : String(cause),
      ...(structured === null ? {} : { structuredError: structured }),
    } satisfies GeometryResponse);
  }
}

let queue = Promise.resolve();
self.onmessage = (event: MessageEvent<BrowserGeometryRequest>) => {
  const request = event.data;
  queue = queue.then(() => processRequest(request), () => processRequest(request));
};
