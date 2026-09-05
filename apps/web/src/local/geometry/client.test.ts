import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BROWSER_TRIANGLE_BUDGET, BrowserGeometryFailure, browserGeometry } from "./client";
import type { BrowserGeometryRequest, GeometryResponse } from "./types";

/**
 * The worker's own behaviour is the core's, and `@mesh2param/core-wasm` tests
 * that. What is worth pinning here is the protocol: what the client puts on the
 * wire for each operation, and how it turns each kind of reply back into a
 * value or an error the workspace can act on.
 */

const posted: BrowserGeometryRequest[] = [];
let respond: (request: BrowserGeometryRequest, reply: (message: GeometryResponse) => void) => void;

class FakeWorker {
  onmessage: ((event: MessageEvent<GeometryResponse>) => void) | null = null;
  onerror: ((event: { message: string }) => void) | null = null;
  terminated = false;

  postMessage(request: BrowserGeometryRequest): void {
    posted.push(request);
    respond(request, (message) => {
      queueMicrotask(() => this.onmessage?.({ data: message } as MessageEvent<GeometryResponse>));
    });
  }

  terminate(): void {
    this.terminated = true;
  }
}

function stlBlob(): Blob {
  const bytes = new ArrayBuffer(84);
  new DataView(bytes).setUint32(80, 0, true);
  return new Blob([bytes]);
}

beforeEach(() => {
  posted.length = 0;
  respond = () => undefined;
  vi.stubGlobal("Worker", FakeWorker);
});

afterEach(() => {
  browserGeometry.cancelAll("test teardown");
  vi.unstubAllGlobals();
});

describe("browser geometry protocol", () => {
  it("sends an analyze request carrying the mesh bytes and format", async () => {
    respond = (request, reply) => {
      reply({ id: request.id, ok: true, result: { triangleCount: 12 } as never });
    };

    await expect(browserGeometry.analyze(stlBlob(), "stl")).resolves.toEqual({ triangleCount: 12 });
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ operation: "analyze", format: "stl" });
  });

  it("sends the requested mode, tolerance and triangle budget with a reconstruct request", async () => {
    respond = (request, reply) => {
      reply({ id: request.id, ok: true, result: { tier: "mixed" } as never });
    };

    await browserGeometry.reconstruct(stlBlob(), "stl", { mode: "faceted", tolerance: 0.05 });

    expect(posted[0]).toMatchObject({
      operation: "reconstruct",
      format: "stl",
      mode: "faceted",
      tolerance: 0.05,
      deflection: null,
      triangleBudget: BROWSER_TRIANGLE_BUDGET,
    });
  });

  it("forwards every progress message and settles only on the result", async () => {
    const seen: Array<{ stage: string; fraction: number; message: string }> = [];
    respond = (request, reply) => {
      reply({ id: request.id, progress: true, stage: "segment", fraction: 0.2, message: "Fitting surfaces to the mesh" });
      reply({ id: request.id, progress: true, stage: "build", fraction: 0.7, message: "Constructing the solid" });
      reply({ id: request.id, ok: true, result: { tier: "analytic" } as never });
    };

    const result = await browserGeometry.reconstruct(stlBlob(), "stl", {
      mode: "automatic",
      onProgress: (progress) => seen.push(progress),
    });

    expect(result).toEqual({ tier: "analytic" });
    expect(seen).toEqual([
      { stage: "segment", fraction: 0.2, message: "Fitting surfaces to the mesh" },
      { stage: "build", fraction: 0.7, message: "Constructing the solid" },
    ]);
  });

  it("rejects a CADGraph rebuild with the worker's structured refusal", async () => {
    respond = (request, reply) => {
      reply({
        id: request.id,
        ok: false,
        error: "not available in browser mode",
        structuredError: { code: "unsupported", stage: "request", message: "not available in browser mode" },
      });
    };

    const failure = await browserGeometry.compile({ units: "mm" } as never).catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(BrowserGeometryFailure);
    expect((failure as BrowserGeometryFailure).structured.code).toBe("unsupported");
    expect(posted[0]).toMatchObject({ operation: "cadgraph" });
  });

  it("keeps a triangle-budget refusal distinguishable from any other failure", async () => {
    respond = (request, reply) => {
      reply({
        id: request.id,
        ok: false,
        error: "mesh is over the triangle budget",
        structuredError: { code: "budget", stage: "parse", message: "mesh is over the triangle budget" },
      });
    };

    const failure = await browserGeometry.reconstruct(stlBlob(), "stl", { mode: "automatic" })
      .catch((cause: unknown) => cause);

    expect(failure).toBeInstanceOf(BrowserGeometryFailure);
    expect((failure as BrowserGeometryFailure).structured.code).toBe("budget");
  });

  it("reports an unstructured failure as a plain error", async () => {
    respond = (request, reply) => {
      reply({ id: request.id, ok: false, error: "the kernel could not build a solid" });
    };

    await expect(browserGeometry.reconstruct(stlBlob(), "stl", { mode: "automatic" }))
      .rejects.toThrow("the kernel could not build a solid");
  });

  it("rejects everything in flight when a run is cancelled", async () => {
    respond = () => undefined;
    const pending = browserGeometry.reconstruct(stlBlob(), "stl", { mode: "automatic" });
    // The blob read is async; wait for the request to reach the worker before
    // tearing it down, or there would be nothing in flight to cancel.
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    browserGeometry.cancelAll("cancelled by the user");

    await expect(pending).rejects.toThrow("cancelled by the user");
  });
});
