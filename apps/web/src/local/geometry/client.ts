import type { CADGraph } from "@mesh2param/contracts";

import type {
  BrowserCadResult,
  CurvedStlGeometryRequest,
  GeometryRequest,
  GeometryResponse,
  StlGeometryRequest,
} from "./types";

class BrowserGeometryClient {
  private workerInstance: Worker | null = null;
  private readonly pending = new Map<string, { resolve(value: BrowserCadResult): void; reject(reason: Error): void }>();

  private worker(): Worker {
    if (this.workerInstance !== null) return this.workerInstance;
    const worker = new Worker(new URL("./geometry.worker.ts", import.meta.url), { type: "module", name: "mesh2param-occt" });
    worker.onmessage = (event: MessageEvent<GeometryResponse>) => {
      const pending = this.pending.get(event.data.id);
      if (pending === undefined) return;
      this.pending.delete(event.data.id);
      if (event.data.ok) pending.resolve(event.data.result);
      else pending.reject(new Error(event.data.error));
    };
    worker.onerror = (event) => {
      for (const pending of this.pending.values()) pending.reject(new Error(event.message || "The browser CAD worker stopped"));
      this.pending.clear();
    };
    this.workerInstance = worker;
    return worker;
  }

  compile(graph: CADGraph): Promise<BrowserCadResult> {
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
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
      this.pending.set(id, { resolve, reject });
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
      this.pending.set(id, { resolve, reject });
      this.worker().postMessage({
        id,
        operation: "curved-stl",
        bytes,
        tolerance,
      } satisfies CurvedStlGeometryRequest, [bytes]);
    });
  }
}

export const browserGeometry = new BrowserGeometryClient();
