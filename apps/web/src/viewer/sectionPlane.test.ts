import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { sectionPlaneForBounds } from "./sectionPlane";

describe("section plane", () => {
  it("moves across the full projected bounds along an arbitrary normal", () => {
    const bounds = new THREE.Box3(new THREE.Vector3(-2, -4, -6), new THREE.Vector3(2, 4, 6));
    const direction = new THREE.Vector3(1, 1, 0).normalize();

    const middle = sectionPlaneForBounds(bounds, direction, 0);
    const high = sectionPlaneForBounds(bounds, direction, 1);

    expect(middle?.distanceToPoint(new THREE.Vector3(0, 0, 0))).toBeCloseTo(0, 12);
    expect(high?.distanceToPoint(new THREE.Vector3(2, 4, 0))).toBeCloseTo(0, 12);
  });

  it("rejects an empty model and zero-length normal", () => {
    expect(sectionPlaneForBounds(new THREE.Box3(), new THREE.Vector3(1, 0, 0), 0)).toBeNull();
    expect(sectionPlaneForBounds(
      new THREE.Box3(new THREE.Vector3(), new THREE.Vector3(1, 1, 1)),
      new THREE.Vector3(),
      0,
    )).toBeNull();
  });
});
