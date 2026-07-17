import { describe, expect, test } from "vitest";
import * as THREE from "three";
import {
  getViewCubeCornerDescriptors,
  getViewCubeFaceDescriptors,
  shouldShowViewCubeFaceLabel,
  VIEWER_GIZMO_ALIGNMENT,
  VIEWER_GIZMO_AXIS_LENGTH,
  VIEWER_GIZMO_DPR,
  VIEWER_GIZMO_LABEL_DISTANCE,
  VIEWER_GIZMO_MARGIN,
  VIEWER_GIZMO_SCALE,
  VIEWER_VIEW_CUBE_SIZE,
  viewCubeFaceToGizmoView,
  viewerGizmoLayout,
} from "./OrientationGizmo";

describe("OpenCAE orientation gizmo", () => {
  test("keeps the exact OpenCAE layout and placement", () => {
    expect(VIEWER_GIZMO_ALIGNMENT).toBe("bottom-right");
    expect(VIEWER_GIZMO_MARGIN).toEqual([112, 112]);
    expect(VIEWER_GIZMO_DPR).toEqual([2, 3]);
    expect(VIEWER_GIZMO_SCALE).toBe(40);
    expect(VIEWER_GIZMO_AXIS_LENGTH).toBe(1.75);
    expect(VIEWER_GIZMO_LABEL_DISTANCE).toBe(1.9);
    expect(VIEWER_VIEW_CUBE_SIZE).toBe(1.2);
    expect(viewerGizmoLayout()).toMatchObject({
      origin: [0, 0, 0],
      cubeMin: [0, 0, 0],
      cubeMax: [1.2, 1.2, 1.2],
      cubeCenter: [0.6, 0.6, 0.6],
      contentCenter: [0.95, 0.95, 0.95],
      contentOffset: [-0.95, -0.95, -0.95],
    });
  });

  test("defines all six labeled faces and eight clickable corners", () => {
    expect(getViewCubeFaceDescriptors().map((face) => face.label).sort()).toEqual(["Back", "Bottom", "Front", "Left", "Right", "Top"]);
    const corners = getViewCubeCornerDescriptors();
    expect(corners).toHaveLength(8);
    expect(new Set(corners.map((corner) => corner.direction.join(","))).size).toBe(8);
    expect(corners.find((corner) => corner.direction.join(",") === "1,1,1")?.title).toBe("View +X +Y +Z");
  });

  test("uses the same positive-axis camera requests and face-label culling", () => {
    expect(viewCubeFaceToGizmoView("Front")).toBe("y");
    expect(viewCubeFaceToGizmoView("Back")).toBe("y");
    expect(viewCubeFaceToGizmoView("Left")).toBe("x");
    expect(viewCubeFaceToGizmoView("Right")).toBe("x");
    expect(viewCubeFaceToGizmoView("Top")).toBe("z");
    expect(viewCubeFaceToGizmoView("Bottom")).toBe("z");
    expect(shouldShowViewCubeFaceLabel(new THREE.Vector3(0, 0, 1), new THREE.Vector3(10, 0, 0.1))).toBe(true);
    expect(shouldShowViewCubeFaceLabel(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, -1))).toBe(false);
  });
});
