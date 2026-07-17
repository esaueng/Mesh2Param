import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  cameraFitForBox,
  cameraFitForDirection,
  orthographicZoomForBox,
  scaleBarForPixelsPerUnit,
  shouldFitCamera,
} from "./cameraMath";

describe("scale bar", () => {
  it("snaps to a 1-2-5 decade length near the target width", () => {
    expect(scaleBarForPixelsPerUnit(9.4)).toEqual({ value: 10, width: 94 });
    expect(scaleBarForPixelsPerUnit(94)).toEqual({ value: 1, width: 94 });
    expect(scaleBarForPixelsPerUnit(4.7)).toEqual({ value: 20, width: 94 });
    expect(scaleBarForPixelsPerUnit(200)).toEqual({ value: 0.5, width: 100 });
  });

  it("rejects degenerate scales", () => {
    expect(scaleBarForPixelsPerUnit(0)).toBeNull();
    expect(scaleBarForPixelsPerUnit(-3)).toBeNull();
    expect(scaleBarForPixelsPerUnit(Number.NaN)).toBeNull();
    expect(scaleBarForPixelsPerUnit(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe("camera stability", () => {
  it("fits only for new content or an explicit fit command", () => {
    expect(shouldFitCamera("a", "a", 2, 2)).toBe(false);
    expect(shouldFitCamera("a", "b", 2, 2)).toBe(true);
    expect(shouldFitCamera("a", "a", 3, 2)).toBe(true);
  });

  it("centers a finite camera pose", () => {
    const fit = cameraFitForBox(
      new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(60, 40, 45)),
      42,
      16 / 9,
    );
    expect(fit.target.toArray()).toEqual([30, 20, 22.5]);
    expect(fit.position.toArray().every(Number.isFinite)).toBe(true);
  });

  it("preserves the requested direction when fitting", () => {
    const fit = cameraFitForDirection(
      new THREE.Box3(new THREE.Vector3(-10, -20, -30), new THREE.Vector3(10, 20, 30)),
      42,
      16 / 9,
      [-1, 0, 0],
    );
    expect(fit.position.clone().sub(fit.target).normalize().toArray()).toEqual([-1, 0, 0]);
  });

  it("computes orthographic zoom from the projected model extents", () => {
    const box = new THREE.Box3(new THREE.Vector3(-10, -20, -50), new THREE.Vector3(10, 20, 50));
    expect(orthographicZoomForBox(box, 1200, 600, [-1, 0, 0])).toBeCloseTo(5);
    expect(orthographicZoomForBox(box, 1200, 600, [0, 0, 1])).toBeCloseTo(25);
  });
});
