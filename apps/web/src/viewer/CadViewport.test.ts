import { describe, expect, test } from "vitest";
import { viewerDpr } from "./CadViewport";

describe("CAD viewport rendering resolution", () => {
  test("uses a full HiDPI backing buffer for normal geometry", () => {
    expect(viewerDpr(false)).toBe(2);
  });

  test("keeps dense geometry above 1x while retaining a performance cap", () => {
    expect(viewerDpr(true)).toBe(1.5);
  });
});
