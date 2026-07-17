import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import {
  CADGRAPH_SCHEMA_SHA256,
  CADGraphValidationError,
  assertCADGraph,
  canonicalJson,
  contentSha256,
  migrateCADGraph,
  validateCADGraph,
} from "../../src/index.js";

const fixtureUrl = new URL("../fixtures/base.cadgraph.json", import.meta.url);
const schemaUrl = new URL("../../schema/cadgraph.schema.json", import.meta.url);
const generatedBracketUrl = new URL(
  "../../../../samples/generated/l-bracket-with-holes/model.cadgraph.json",
  import.meta.url,
);

async function fixture(): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(fixtureUrl, "utf8")) as Record<string, unknown>;
}

const common = {
  id: "feature.test",
  name: "Test feature",
  order: 1,
  dependencies: ["feature.base"],
  suppressed: false,
  sourceEvidence: ["evidence.source"],
  confidence: 1,
  userLocks: [],
  overrides: [],
  semanticOutputs: [],
};

const v3 = { x: 0, y: 0, z: 1 };
const axis = { origin: { x: 0, y: 0, z: 0 }, direction: v3 };
const plane = { origin: { x: 0, y: 0, z: 0 }, normal: v3, xAxis: { x: 1, y: 0, z: 0 } };

const supportedFeatures: Record<string, unknown>[] = [
  { ...common, operation: "extrusion", booleanMode: "additive", sketchId: "sketch.base", profileIds: ["profile.base"], direction: v3, extent: "blind", distance: 2 },
  { ...common, operation: "extrusion", booleanMode: "subtractive", sketchId: "sketch.base", profileIds: ["profile.base"], direction: v3, extent: "throughAll" },
  { ...common, operation: "pocket", booleanMode: "subtractive", sketchId: "sketch.base", profileIds: ["profile.base"], direction: v3, extent: "blind", depth: 2 },
  { ...common, operation: "hole", booleanMode: "subtractive", holeType: "through", position: v3, axis: v3, diameter: 5 },
  { ...common, operation: "hole", booleanMode: "subtractive", holeType: "blind", position: v3, axis: v3, diameter: 5, depth: 4 },
  { ...common, operation: "counterbore", booleanMode: "subtractive", holeType: "through", position: v3, axis: v3, diameter: 5, boreDiameter: 8, boreDepth: 2 },
  { ...common, operation: "countersink", booleanMode: "subtractive", holeType: "blind", position: v3, axis: v3, diameter: 5, depth: 8, sinkDiameter: 9, sinkAngleDeg: 90 },
  { ...common, operation: "revolution", booleanMode: "base", sketchId: "sketch.base", profileIds: ["profile.base"], axis, angleDeg: 360 },
  { ...common, operation: "revolution", booleanMode: "additive", sketchId: "sketch.base", profileIds: ["profile.base"], axis, angleDeg: 180 },
  { ...common, operation: "revolution", booleanMode: "subtractive", sketchId: "sketch.base", profileIds: ["profile.base"], axis, angleDeg: 90 },
  { ...common, operation: "linearPattern", sourceFeatureIds: ["feature.base"], direction: { x: 1, y: 0, z: 0 }, count: 3, spacing: 10 },
  { ...common, operation: "circularPattern", sourceFeatureIds: ["feature.base"], axis, count: 4, totalAngleDeg: 360 },
  { ...common, operation: "mirror", sourceFeatureIds: ["feature.base"], plane, keepOriginals: true },
  { ...common, operation: "chamfer", targetEdges: ["feature.base.edge.1"], width: 1 },
  { ...common, operation: "fillet", targetEdges: ["feature.base.edge.1"], radius: 1 },
  { ...common, operation: "importedFaceted", booleanMode: "additive", sourceArtifactId: "artifact.mesh", meshSha256: "0".repeat(64), intent: "fallback" },
  { ...common, operation: "reconstructedSurfaceNetwork", sourceArtifactId: "artifact.network", artifactSha256: "0".repeat(64) },
];

describe("CADGraph contracts", () => {
  it("validates the fixture and all sketch entity kinds", async () => {
    const document = await fixture();
    assertCADGraph(document);
    const kinds = new Set(document.sketches[0]?.entities.map((entity) => entity.kind));
    expect(kinds).toEqual(new Set(["point", "constructionPoint", "line", "constructionLine", "polyline", "rectangle", "circle", "circularArc", "closedProfile", "constructionAxis"]));
  });

  it("validates the generated bracket's explicit nullable fields", async () => {
    const document = JSON.parse(
      await readFile(generatedBracketUrl, "utf8"),
    ) as Record<string, unknown>;
    expect(validateCADGraph(document)).toEqual({ valid: true, issues: [] });
  });

  it.each(supportedFeatures)("validates supported operation $operation", async (feature) => {
    const document = await fixture();
    (document.features as unknown[]).push(feature);
    expect(validateCADGraph(document)).toEqual({ valid: true, issues: [] });
  });

  it("rejects unknown fields and invalid references", async () => {
    const document = await fixture();
    document.unexpected = true;
    expect(() => assertCADGraph(document)).toThrow(CADGraphValidationError);
  });

  it("serializes and hashes deterministically", async () => {
    const document = await fixture();
    expect(canonicalJson(document)).toBe(canonicalJson(JSON.parse(JSON.stringify(document))));
    expect(await contentSha256(document)).toMatch(/^[a-f0-9]{64}$/);
  });

  it("migrates 0.1.0 without mutating its input", () => {
    const legacy = { schemaVersion: "0.1.0", id: "project.legacy", name: "Legacy", units: "mm", operations: [], tolerance: 0.05, randomSeed: 7 };
    const snapshot = structuredClone(legacy);
    expect(migrateCADGraph(legacy).schemaVersion).toBe("1.0.0");
    expect(legacy).toEqual(snapshot);
  });

  it("pins generated output to the schema bytes", async () => {
    const schemaText = await readFile(schemaUrl, "utf8");
    expect(createHash("sha256").update(schemaText).digest("hex")).toBe(CADGRAPH_SCHEMA_SHA256);
  });
});
