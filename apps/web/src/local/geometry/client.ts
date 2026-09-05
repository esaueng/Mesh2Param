import type { CADGraph } from "@mesh2param/contracts";

import type {
  AnalyzeGeometryRequest,
  BrowserGeometryError,
  BrowserGeometryRequest,
  BrowserGeometryResult,
  BrowserGeometryStage,
  BrowserMeshAnalysis,
  BrowserMeshFormat,
  BrowserReconstruction,
  BrowserReconstructionMode,
  CadgraphGeometryRequest,
  GeometryResponse,
  ReconstructGeometryRequest,
} from "./types";

export interface GeometryProgress {
  stage: BrowserGeometryStage;
  /** Share of the whole run, 0 to 1. */
  fraction: number;
  message: string;
}

/** An error the worker described rather than only reported. */
export class BrowserGeometryFailure extends Error {
  readonly structured: BrowserGeometryError;

  constructor(structured: BrowserGeometryError) {
    super(structured.message);
    this.name = "BrowserGeometryFailure";
    this.structured = structured;
  }
}

export interface ReconstructRequestOptions {
  mode: BrowserReconstructionMode;
  tolerance?: number | null;
  deflection?: number | null;
  triangleBudget?: number;
  onProgress?: (progress: GeometryProgress) => void;
}

/** The core's own default, restated so a caller can show it. */
export const BROWSER_TRIANGLE_BUDGET = 200_000;

class BrowserGeometryClient {
  private workerInstance: Worker | null = null;
  private readonly pending = new Map<string, {
    resolve(value: BrowserGeometryResult): void;
    reject(reason: Error): void;
    onProgress?: (progress: GeometryProgress) => void;
  }>();

  private worker(): Worker {
    if (this.workerInstance !== null) return this.workerInstance;
    const worker = new Worker(new URL("./geometry.worker.ts", import.meta.url), { type: "module", name: "mesh2param-core" });
    worker.onmessage = (event: MessageEvent<GeometryResponse>) => {
      const pending = this.pending.get(event.data.id);
      if (pending === undefined) return;
      if ("progress" in event.data) {
        pending.onProgress?.({ stage: event.data.stage, fraction: event.data.fraction, message: event.data.message });
        return;
      }
      this.pending.delete(event.data.id);
      if (event.data.ok) pending.resolve(event.data.result);
      else pending.reject(event.data.structuredError === undefined
        ? new Error(event.data.error)
        : new BrowserGeometryFailure(event.data.structuredError));
    };
    worker.onerror = (event) => {
      for (const pending of this.pending.values()) pending.reject(new Error(event.message || "The browser CAD worker stopped"));
      this.pending.clear();
      this.workerInstance = null;
    };
    this.workerInstance = worker;
    return worker;
  }

  private send<T extends BrowserGeometryResult>(
    request: BrowserGeometryRequest,
    transfer: Transferable[],
    onProgress?: (progress: GeometryProgress) => void,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.pending.set(request.id, {
        resolve: (value) => resolve(value as T),
        reject,
        ...(onProgress === undefined ? {} : { onProgress }),
      });
      this.worker().postMessage(request, transfer);
    });
  }

  async analyze(blob: Blob, format: BrowserMeshFormat = "stl"): Promise<BrowserMeshAnalysis> {
    const bytes = await blob.arrayBuffer();
    return this.send<BrowserMeshAnalysis>(
      { id: crypto.randomUUID(), operation: "analyze", bytes, format } satisfies AnalyzeGeometryRequest,
      [bytes],
    );
  }

  async reconstruct(
    blob: Blob,
    format: BrowserMeshFormat,
    options: ReconstructRequestOptions,
  ): Promise<BrowserReconstruction> {
    const bytes = await blob.arrayBuffer();
    return this.send<BrowserReconstruction>({
      id: crypto.randomUUID(),
      operation: "reconstruct",
      bytes,
      format,
      mode: options.mode,
      tolerance: options.tolerance ?? null,
      deflection: options.deflection ?? null,
      triangleBudget: options.triangleBudget ?? BROWSER_TRIANGLE_BUDGET,
    } satisfies ReconstructGeometryRequest, [bytes], options.onProgress);
  }

  /**
   * Rebuild a STEP file from a CADGraph. The browser core has no equivalent, so
   * this always rejects with the worker's structured refusal; it stays on the
   * client so browser and server modes present the same surface.
   */
  compile(graph: CADGraph): Promise<never> {
    return this.send<BrowserGeometryResult>(
      { id: crypto.randomUUID(), operation: "cadgraph", graph: structuredClone(graph) } satisfies CadgraphGeometryRequest,
      [],
    ) as Promise<never>;
  }

  cancelAll(reason = "Browser geometry operation cancelled"): void {
    this.workerInstance?.terminate();
    this.workerInstance = null;
    for (const pending of this.pending.values()) pending.reject(new Error(reason));
    this.pending.clear();
  }
}

export const browserGeometry = new BrowserGeometryClient();
