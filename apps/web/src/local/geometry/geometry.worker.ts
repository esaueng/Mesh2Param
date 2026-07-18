import { OcctKernel } from "occt-wasm";
import wasmUrl from "occt-wasm/dist/occt-wasm.wasm?url";

import { compileCadGraph, compileCurvedStl, compileStl } from "./compiler";
import { analyzeStl } from "./stl";
import type { BrowserGeometryRequest, GeometryResponse } from "./types";

let kernelPromise: Promise<OcctKernel> | null = null;
const workerScope = self as unknown as { postMessage(message: unknown, transfer?: Transferable[]): void };

function kernel(): Promise<OcctKernel> {
  kernelPromise ??= OcctKernel.init({ wasm: wasmUrl });
  return kernelPromise;
}

self.onmessage = (event: MessageEvent<BrowserGeometryRequest>) => {
  const request = event.data;
  const operation = request.operation === "stl" && !request.solidify && !request.validateStep
    ? Promise.resolve(analyzeStl(request.bytes))
    : kernel().then((value) => {
    value.releaseAll();
    if (request.operation === "cadgraph") return compileCadGraph(value, request.graph);
    if (request.operation === "curved-stl") return compileCurvedStl(value, request.bytes, request.tolerance);
    return compileStl(value, request.bytes, request.tolerance, request.solidify, request.validateStep);
  });
  void operation.then((result) => {
    const response: GeometryResponse = { id: request.id, ok: true, result };
    workerScope.postMessage(response, [
      result.mesh.positions.buffer as ArrayBuffer,
      result.mesh.normals.buffer as ArrayBuffer,
      result.mesh.indices.buffer as ArrayBuffer,
    ]);
  }).catch((cause: unknown) => {
    const response: GeometryResponse = { id: request.id, ok: false, error: cause instanceof Error ? cause.message : String(cause) };
    workerScope.postMessage(response);
  });
};
