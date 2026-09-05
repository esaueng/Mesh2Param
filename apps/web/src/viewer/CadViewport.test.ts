import { describe, expect, test } from "vitest";
import * as THREE from "three";
import { gridFloorSpec, viewerDpr } from "./CadViewport";

describe("CAD viewport rendering resolution", () => {
  test("uses a full HiDPI backing buffer for normal geometry", () => {
    expect(viewerDpr(false)).toBe(2);
  });

  test("keeps dense geometry above 1x while retaining a performance cap", () => {
    expect(viewerDpr(true)).toBe(1.5);
  });
});

describe("grid floor", () => {
  test("picks a decimal step from the footprint and sits just under the model", () => {
    const bounds = new THREE.Box3(new THREE.Vector3(-40, -20, 5), new THREE.Vector3(40, 20, 17));
    const spec = gridFloorSpec(bounds);
    expect(spec.step).toBe(10);
    expect(spec.size).toBeGreaterThanOrEqual(80 * 2.4);
    expect(spec.size % spec.step).toBe(0);
    expect(spec.z).toBeLessThan(5);
    expect(spec.z).toBeGreaterThan(4);
  });

  test("scales the step with small parts", () => {
    const bounds = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(2.3, 1.1, 0.4));
    expect(gridFloorSpec(bounds).step).toBe(0.2);
  });
});
