import { describe, expect, it } from "vitest";
import type { BrowserMesh } from "./geometry/types";
import { meshToBinaryStl, meshToObj } from "./meshExports";

const triangle: BrowserMesh = {
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  vertexCount: 3,
  triangleCount: 1,
};

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Blob read failed"));
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.readAsArrayBuffer(blob);
  });
}

describe("browser mesh exports", () => {
  it("writes deterministic binary STL", async () => {
    const first = new Uint8Array(await readBlob(meshToBinaryStl(triangle)));
    const second = new Uint8Array(await readBlob(meshToBinaryStl(triangle)));
    expect(first).toEqual(second);
    expect(first.byteLength).toBe(134);
    expect(new DataView(first.buffer).getUint32(80, true)).toBe(1);
  });

  it("writes deterministic indexed OBJ with vertex normals", async () => {
    const output = new TextDecoder().decode(await readBlob(meshToObj(triangle)));
    expect(output).toContain("v 1 0 0\n");
    expect(output).toContain("vn 0 0 1\n");
    expect(output).toContain("f 1//1 2//2 3//3\n");
    expect(new TextDecoder().decode(await readBlob(meshToObj(triangle)))).toBe(output);
  });
});
