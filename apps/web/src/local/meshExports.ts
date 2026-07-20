import type { BrowserMesh } from "./geometry/types";

function vertex(mesh: BrowserMesh, index: number): readonly [number, number, number] {
  const offset = index * 3;
  return [mesh.positions[offset]!, mesh.positions[offset + 1]!, mesh.positions[offset + 2]!];
}

function faceNormal(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
  c: readonly [number, number, number],
): readonly [number, number, number] {
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]] as const;
  const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]] as const;
  const raw = [
    ab[1] * ac[2] - ab[2] * ac[1],
    ab[2] * ac[0] - ab[0] * ac[2],
    ab[0] * ac[1] - ab[1] * ac[0],
  ] as const;
  const magnitude = Math.hypot(...raw);
  return magnitude <= 1e-30 ? [0, 0, 0] : raw.map((value) => value / magnitude) as [number, number, number];
}

export function meshToBinaryStl(mesh: BrowserMesh): Blob {
  const buffer = new ArrayBuffer(84 + mesh.triangleCount * 50);
  const bytes = new Uint8Array(buffer);
  const header = new TextEncoder().encode("Mesh2Param browser deterministic binary STL");
  bytes.set(header.subarray(0, 80));
  const view = new DataView(buffer);
  view.setUint32(80, mesh.triangleCount, true);
  let offset = 84;
  for (let face = 0; face < mesh.indices.length; face += 3) {
    const a = vertex(mesh, mesh.indices[face]!);
    const b = vertex(mesh, mesh.indices[face + 1]!);
    const c = vertex(mesh, mesh.indices[face + 2]!);
    const values = [...faceNormal(a, b, c), ...a, ...b, ...c];
    for (const value of values) {
      view.setFloat32(offset, value, true);
      offset += 4;
    }
    view.setUint16(offset, 0, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "model/stl" });
}

function objNumber(value: number): string {
  const normalized = value + 0;
  return normalized.toPrecision(9).replace(/(?:\.0+|(?:(\.\d*?)0+))(?=e|$)/, "$1");
}

export function meshToObj(mesh: BrowserMesh): Blob {
  const lines = ["# Mesh2Param browser deterministic OBJ", "o Mesh2Param_result"];
  for (let index = 0; index < mesh.positions.length; index += 3) {
    lines.push(`v ${objNumber(mesh.positions[index]!)} ${objNumber(mesh.positions[index + 1]!)} ${objNumber(mesh.positions[index + 2]!)}`);
  }
  for (let index = 0; index < mesh.normals.length; index += 3) {
    lines.push(`vn ${objNumber(mesh.normals[index]!)} ${objNumber(mesh.normals[index + 1]!)} ${objNumber(mesh.normals[index + 2]!)}`);
  }
  for (let index = 0; index < mesh.indices.length; index += 3) {
    const a = mesh.indices[index]! + 1;
    const b = mesh.indices[index + 1]! + 1;
    const c = mesh.indices[index + 2]! + 1;
    lines.push(`f ${a}//${a} ${b}//${b} ${c}//${c}`);
  }
  return new Blob([`${lines.join("\n")}\n`], { type: "model/obj" });
}
