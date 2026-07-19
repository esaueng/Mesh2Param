import type { CADGraph } from "@mesh2param/contracts";

import type {
  BrowserCadResult,
  BrowserGeometryResult,
  BrowserParametricProbe,
  BrowserGeometryStage,
  BrowserParametricResult,
  CurvedStlGeometryRequest,
  GeometryRequest,
  GeometryResponse,
  ParametricStlGeometryRequest,
  ParametricProbeGeometryRequest,
  StlGeometryRequest,
} from "./types";

interface ParametricSource {
  sha256: string;
  originalFileName: string;
  byteSize: number;
  declaredUnits: CADGraph["units"];
  scaleFactor: number;
}

interface GeometryProgress {
  stage: BrowserGeometryStage;
  fraction: number;
  message: string;
}

class BrowserGeometryClient {
  private workerInstance: Worker | null = null;
  private readonly pending = new Map<string, {
    resolve(value: BrowserGeometryResult): void;
    reject(reason: Error): void;
    onProgress?: (progress: GeometryProgress) => void;
  }>();

  private worker(): Worker {
    if (this.workerInstance !== null) return this.workerInstance;
    const worker = new Worker(new URL("./geometry.worker.ts", import.meta.url), { type: "module", name: "mesh2param-occt" });
    worker.onmessage = (event: MessageEvent<GeometryResponse>) => {
      const pending = this.pending.get(event.data.id);
      if (pending === undefined) return;
      if ("progress" in event.data) {
        pending.onProgress?.({ stage: event.data.stage, fraction: event.data.fraction, message: event.data.message });
        return;
      }
      this.pending.delete(event.data.id);
      if (event.data.ok) pending.resolve(event.data.result);
      else pending.reject(new Error(event.data.structuredError === undefined
        ? event.data.error
        : `${event.data.structuredError.stage} (${event.data.structuredError.code}): ${event.data.error}`));
    };
    worker.onerror = (event) => {
      for (const pending of this.pending.values()) pending.reject(new Error(event.message || "The browser CAD worker stopped"));
      this.pending.clear();
      this.workerInstance = null;
    };
    this.workerInstance = worker;
    return worker;
  }

  compile(graph: CADGraph): Promise<BrowserCadResult> {
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: (value) => resolve(value as BrowserCadResult), reject });
      this.worker().postMessage({ id, operation: "cadgraph", graph: structuredClone(graph) } satisfies GeometryRequest);
    });
  }

  async compileStl(
    blob: Blob,
    tolerance: number,
    options: { solidify?: boolean; validateStep?: boolean } = {},
  ): Promise<BrowserCadResult> {
    const id = crypto.randomUUID();
    const bytes = await blob.arrayBuffer();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: (value) => resolve(value as BrowserCadResult), reject });
      this.worker().postMessage({
        id,
        operation: "stl",
        bytes,
        tolerance,
        solidify: options.solidify ?? true,
        validateStep: options.validateStep ?? true,
      } satisfies StlGeometryRequest, [bytes]);
    });
  }

  async compileCurvedStl(blob: Blob, tolerance: number): Promise<BrowserCadResult> {
    const id = crypto.randomUUID();
    const bytes = await blob.arrayBuffer();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: (value) => resolve(value as BrowserCadResult), reject });
      this.worker().postMessage({
        id,
        operation: "curved-stl",
        bytes,
        tolerance,
      } satisfies CurvedStlGeometryRequest, [bytes]);
    });
  }

  async reconstructParametricStl(
    blob: Blob,
    source: ParametricSource,
    units: CADGraph["units"],
    options: {
      tolerance: number;
      detailMode?: "functional" | "full";
      deterministicSeed?: number;
      onProgress?: (progress: GeometryProgress) => void;
    },
  ): Promise<BrowserParametricResult> {
    const id = crypto.randomUUID();
    const bytes = await blob.arrayBuffer();
    return new Promise((resolve, reject) => {
      this.pending.set(id, {
        resolve: (value) => resolve(value as BrowserParametricResult),
        reject,
        ...(options.onProgress === undefined ? {} : { onProgress: options.onProgress }),
      });
      this.worker().postMessage({
        id,
        operation: "parametric-stl",
        bytes,
        source,
        units,
        tolerance: options.tolerance,
        detailMode: options.detailMode ?? "functional",
        deterministicSeed: options.deterministicSeed ?? 0x4d325006,
      } satisfies ParametricStlGeometryRequest, [bytes]);
    });
  }

  async probeParametricStl(blob: Blob, scaleFactor: number, tolerance: number): Promise<BrowserParametricProbe> {
    const id = crypto.randomUUID();
    const bytes = await blob.arrayBuffer();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: (value) => resolve(value as BrowserParametricProbe), reject });
      this.worker().postMessage({
        id,
        operation: "parametric-probe",
        bytes,
        scaleFactor,
        tolerance,
      } satisfies ParametricProbeGeometryRequest, [bytes]);
    });
  }

  cancelAll(reason = "Browser geometry operation cancelled"): void {
    this.workerInstance?.terminate();
    this.workerInstance = null;
    for (const pending of this.pending.values()) pending.reject(new Error(reason));
    this.pending.clear();
  }
}

export const browserGeometry = new BrowserGeometryClient();
