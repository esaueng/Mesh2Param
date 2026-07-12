import { OcctKernel } from "occt-wasm";
import wasmUrl from "occt-wasm/dist/occt-wasm.wasm?url";

import { compileCadGraph, compileStl } from "./compiler";
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
    return request.operation === "cadgraph"
      ? compileCadGraph(value, request.graph)
      : compileStl(value, request.bytes, request.tolerance, request.solidify, request.validateStep);
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
