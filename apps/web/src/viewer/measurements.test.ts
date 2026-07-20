import { describe, expect, it } from "vitest";
import { angleDegrees, circumradius, measurementLabel, pointDistance } from "./measurements";

describe("CAD measurements", () => {
  it("measures three-dimensional point distance in project units", () => {
    expect(pointDistance([0, 0, 0], [2, 3, 6])).toBe(7);
    expect(measurementLabel("distance", [[0, 0, 0], [2, 3, 6]], "mm")).toBe("7.000 mm");
  });

  it("measures the angle at the middle picked point", () => {
    expect(angleDegrees([1, 0, 0], [0, 0, 0], [0, 1, 0])).toBeCloseTo(90, 12);
    expect(measurementLabel("angle", [[1, 0, 0], [0, 0, 0], [0, 1, 0]], "in"))
      .toBe("90.000°");
  });

  it("measures a three-point circle radius and rejects collinear points", () => {
    expect(circumradius([1, 0, 0], [0, 1, 0], [-1, 0, 0])).toBeCloseTo(1, 12);
    expect(circumradius([0, 0, 0], [1, 0, 0], [2, 0, 0])).toBeNull();
  });
});
