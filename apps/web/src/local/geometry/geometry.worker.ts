import { OcctKernel } from "occt-wasm";
import wasmUrl from "occt-wasm/dist/occt-wasm.wasm?url";

import { compileCadGraph, compileCurvedStl, compileStl } from "./compiler";
import { ParametricReconstructionFailure, probeParametricStl, reconstructParametricStl } from "./reconstruction";
import { analyzeStl } from "./stl";
import type { BrowserGeometryRequest, BrowserGeometryStage, BrowserMesh, GeometryResponse } from "./types";

let kernelPromise: Promise<OcctKernel> | null = null;
const workerScope = self as unknown as { postMessage(message: unknown, transfer?: Transferable[]): void };

function kernel(): Promise<OcctKernel> {
  kernelPromise ??= OcctKernel.init({ wasm: wasmUrl });
  return kernelPromise;
}

function progress(id: string, stage: BrowserGeometryStage, fraction: number, message: string): void {
  workerScope.postMessage({ id, progress: true, stage, fraction, message } satisfies GeometryResponse);
}

async function processRequest(request: BrowserGeometryRequest): Promise<void> {
  const operation = request.operation === "stl" && !request.solidify && !request.validateStep
    ? Promise.resolve(analyzeStl(request.bytes))
    : request.operation === "parametric-probe"
      ? Promise.resolve(probeParametricStl(request.bytes, request.scaleFactor, request.tolerance))
    : kernel().then((value) => {
    value.releaseAll();
    if (request.operation === "cadgraph") return compileCadGraph(value, request.graph);
    if (request.operation === "curved-stl") return compileCurvedStl(value, request.bytes, request.tolerance);
    if (request.operation === "parametric-stl") {
      return reconstructParametricStl(value, request, (stage, fraction, message) => {
        progress(request.id, stage, fraction, message);
      });
    }
    return compileStl(value, request.bytes, request.tolerance, request.solidify, request.validateStep);
  });
  await operation.then((result) => {
    const response: GeometryResponse = { id: request.id, ok: true, result };
    if ("mesh" in result) {
      const transfer: Transferable[] = [
        result.mesh.positions.buffer as ArrayBuffer,
        result.mesh.normals.buffer as ArrayBuffer,
        result.mesh.indices.buffer as ArrayBuffer,
      ];
      if (result.edgeLines !== undefined) {
        transfer.push(
          result.edgeLines.positions.buffer as ArrayBuffer,
          result.edgeLines.indices.buffer as ArrayBuffer,
        );
      }
      if (result.exportMesh !== undefined) {
        transfer.push(
          result.exportMesh.positions.buffer as ArrayBuffer,
          result.exportMesh.normals.buffer as ArrayBuffer,
          result.exportMesh.indices.buffer as ArrayBuffer,
        );
      }
      const suppressed = "suppressedMesh" in result ? result.suppressedMesh as BrowserMesh | null : null;
      if (suppressed !== null) {
        transfer.push(
          suppressed.positions.buffer as ArrayBuffer,
          suppressed.normals.buffer as ArrayBuffer,
          suppressed.indices.buffer as ArrayBuffer,
        );
      }
      workerScope.postMessage(response, transfer);
    } else workerScope.postMessage(response);
  }).catch((cause: unknown) => {
    const response: GeometryResponse = {
      id: request.id,
      ok: false,
      error: cause instanceof Error ? cause.message : String(cause),
      ...(cause instanceof ParametricReconstructionFailure ? { structuredError: cause.structured } : {}),
    };
    workerScope.postMessage(response);
  });
}

let queue = Promise.resolve();
self.onmessage = (event: MessageEvent<BrowserGeometryRequest>) => {
  const request = event.data;
  queue = queue.then(() => processRequest(request), () => processRequest(request));
};
