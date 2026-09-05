/**
 * Typed wrapper over the Rust reconstruction core compiled to WebAssembly.
 *
 * The generated bindings in `../pkg` are build output with `any` at every
 * boundary; this module is the hand-written half that gives them types and a
 * single place to initialise the module from.
 *
 * Every call is synchronous once {@link init} has resolved. That is deliberate:
 * the core is pure and single-threaded, and the app runs it inside a worker,
 * where blocking is the correct behaviour.
 */

import initWasm, { analyze as analyzeRaw, reconstruct as reconstructRaw, version as versionRaw } from "../pkg/mesh2param_wasm.js";

/** Mesh container formats the core can be asked to read. */
export type MeshFormat = "stl" | "3mf" | "obj" | "ply";

/** Reconstruction tier the run landed at. */
export type Tier = "analytic" | "mixed" | "faceted";

/** A stage of a run, as reported to a progress callback. */
export type Stage = "parse" | "weld" | "segment" | "topology" | "build" | "verify" | "step";

/**
 * Called at stage boundaries and at a coarse per-pass granularity inside
 * segmentation and construction. `fraction` runs `0` to `1` within each stage,
 * not across the run; the run is finished when `"step"` reaches `1`.
 */
export type ProgressCallback = (stage: Stage, fraction: number) => void;

/** An axis-aligned bounding box in the mesh's own units. */
export interface Bbox {
  min: [number, number, number];
  max: [number, number, number];
}

/** What {@link analyze} reports. */
export interface MeshAnalysis {
  triangles: number;
  vertices: number;
  bbox: Bbox;
  /** Every edge has exactly two owning triangles. */
  watertight: boolean;
  /** No edge has more than two owning triangles. */
  edgeManifold: boolean;
  nonManifoldEdges: number;
  /** Triangles dropped as degenerate during welding. */
  droppedTriangles: number;
}

/** How far the result sits from the mesh it was reconstructed from. */
export interface Deviation {
  p95: number;
  max: number;
  samples: number;
}

/** Recognised surfaces, by type. */
export interface Inventory {
  plane: number;
  cylinder: number;
  cone: number;
  torus: number;
  sphere: number;
  unknown: number;
}

/** Per-stage wall clock, milliseconds, measured on the JavaScript side. */
export interface Timings {
  parseMs: number;
  segmentMs: number;
  topologyMs: number;
  buildMs: number;
  verifyMs: number;
  stepMs: number;
}

/** What {@link reconstruct} reports. */
export interface ReconstructResult {
  tier: Tier;
  /** The finished solid passes kernel validation with no errors. */
  valid: boolean;
  issues: string[];
  /** Why the run did not stay at the tier it was aiming for. */
  fallbackReason: string | null;
  facesAnalytic: number;
  facesTriangle: number;
  facesFinal: number;
  /** `null` when verification was off or the tessellation failed. */
  deviation: Deviation | null;
  volume: number;
  sourceVolume: number;
  stepBytes: number;
  /** The kernel's own reader read the STEP file back. */
  roundTripOk: boolean;
  timings: Timings;
  inventory: Inventory;
  /** Share of surface area no primitive was recognised on. */
  unknownAreaFraction: number;
  patches: number | null;
  edges: number | null;
  /** The AP203 STEP file. */
  step: Uint8Array;
  /** The result tessellation as binary glTF: positions and indices only. */
  glb: Uint8Array;
}

/**
 * Overrides on the core's defaults. Omit the object entirely for the defaults
 * the corpus scoreboard is measured at.
 */
export interface ReconstructOptions {
  /** Refuse meshes above this triangle count. Defaults to 200000. */
  triangleBudget?: number;
  /** Absolute construction tolerance. Omitted follows segmentation. */
  tolerance?: number;
  /** Chord deflection for the verification tessellation, which is also the GLB. */
  deflection?: number;
  /** Measure the result against the source mesh. Off leaves the GLB empty. */
  verify?: boolean;
  /** Merge same-surface adjacent faces before validating. */
  unify?: boolean;
  /** Cap on demote-and-rebuild rounds before the faceted fallback. */
  maxRounds?: number;
  /** Largest volume error a result may have and stay above the faceted tier. */
  maxVolumeError?: number;
  /** Largest deviation p95, as a fraction of the bounding-box diagonal. */
  maxDeviationFraction?: number;
  /** Dihedral threshold for the initial over-segmentation, in degrees. */
  angleDeg?: number;
}

/** The default triangle budget, restated so callers can show it. */
export const DEFAULT_TRIANGLE_BUDGET = 200_000;

/**
 * What {@link init} accepts: a URL to fetch the `.wasm` from, the bytes
 * themselves, or an already-compiled module. Omit it in a bundler that resolves
 * the module's own URL.
 */
export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

let ready: Promise<void> | null = null;

/**
 * Load and instantiate the WebAssembly module. Idempotent: later calls return
 * the first one's promise, so several callers may await it without racing.
 *
 * In Node, pass the bytes: `init(await readFile(wasmPath))`. In a bundler that
 * rewrites `import.meta.url`, call it with no argument.
 */
export function init(input?: InitInput): Promise<void> {
  ready ??= (async () => {
    await (input === undefined ? initWasm() : initWasm({ module_or_path: input }));
  })();
  return ready;
}

/** Mesh statistics, without reconstructing anything. Throws on unreadable bytes. */
export function analyze(bytes: Uint8Array, format: MeshFormat = "stl"): MeshAnalysis {
  return analyzeRaw(bytes, format) as MeshAnalysis;
}

/**
 * Run the whole ladder: mesh bytes in, a STEP file and a display mesh out.
 *
 * Throws an `Error` carrying the core's own message. A mesh over the triangle
 * budget throws with `name === "BudgetError"` and `code === "budget"`, which is
 * the one failure a caller can act on rather than only report.
 */
export function reconstruct(
  bytes: Uint8Array,
  format: MeshFormat = "stl",
  options: ReconstructOptions = {},
  onProgress?: ProgressCallback,
): ReconstructResult {
  return reconstructRaw(bytes, format, options, onProgress ?? null) as ReconstructResult;
}

/** This build's version, and the kernel revision behind it. */
export function version(): string {
  return versionRaw();
}
