import type { CADGraph } from "./types.generated.js";
import { assertCADGraph } from "./validation.js";

export const CURRENT_SCHEMA_VERSION = "1.0.0" as const;
export const LEGACY_SCHEMA_VERSION = "0.1.0" as const;

export class MigrationError extends TypeError {
  constructor(message: string) {
    super(message);
    this.name = "MigrationError";
  }
}

const DEFAULT_SCORE_WEIGHTS = {
  rmsDistance: 1,
  p95Distance: 1,
  maxDistance: 0.5,
  normalAgreement: 0.5,
  volumeDifference: 0.75,
  overlap: 0.75,
  sharpEdgeAlignment: 0.5,
  boundaryAlignment: 0.5,
  unmatchedSource: 1,
  excessResult: 1,
  complexity: 0.1,
  unsupportedOperation: 2,
  evidenceConfidence: 0.25,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function detachedObject(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new MigrationError("CADGraph must be a JSON object");
  }
  try {
    return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  } catch (error) {
    throw new MigrationError(`CADGraph must contain only JSON values: ${String(error)}`);
  }
}

function normalizeEntities(sketch: Record<string, unknown>): void {
  if (!Array.isArray(sketch.entities)) return;
  const constructionKinds = new Set(["constructionPoint", "constructionLine", "constructionAxis"]);
  for (const rawEntity of sketch.entities) {
    if (!isRecord(rawEntity)) continue;
    if (rawEntity.kind === undefined && typeof rawEntity.type === "string") {
      rawEntity.kind = rawEntity.type;
      delete rawEntity.type;
    }
    rawEntity.construction ??= constructionKinds.has(String(rawEntity.kind));
    rawEntity.sourceEvidence ??= [];
    rawEntity.confidence ??= 1;
    rawEntity.locked ??= false;
    rawEntity.suppressed ??= false;
  }
}

function normalizeFeature(feature: Record<string, unknown>, index: number): void {
  if (feature.operation === undefined && typeof feature.type === "string") {
    const legacyOperation = feature.type;
    delete feature.type;
    const operationMap: Record<string, [string, string?]> = {
      baseExtrusion: ["extrusion", "base"],
      additiveExtrusion: ["extrusion", "additive"],
      subtractiveExtrusion: ["extrusion", "subtractive"],
      throughHole: ["hole", "subtractive"],
      blindHole: ["hole", "subtractive"],
      baseRevolution: ["revolution", "base"],
      additiveRevolution: ["revolution", "additive"],
      subtractiveRevolution: ["revolution", "subtractive"],
    };
    const [operation, booleanMode] = operationMap[legacyOperation] ?? [legacyOperation];
    feature.operation = operation;
    if (booleanMode !== undefined) feature.booleanMode ??= booleanMode;
    if (legacyOperation === "throughHole") feature.holeType ??= "through";
    if (legacyOperation === "blindHole") feature.holeType ??= "blind";
  }
  if (feature.dependencies === undefined && Array.isArray(feature.dependsOn)) {
    feature.dependencies = feature.dependsOn;
    delete feature.dependsOn;
  }
  feature.order ??= index;
  feature.dependencies ??= [];
  feature.suppressed ??= false;
  feature.sourceEvidence ??= [];
  feature.confidence ??= 1;
  feature.userLocks ??= [];
  feature.overrides ??= [];
  feature.semanticOutputs ??= [];
}

function migrateLegacy(document: Record<string, unknown>): Record<string, unknown> {
  document.schemaVersion = CURRENT_SCHEMA_VERSION;
  if (document.features === undefined && Array.isArray(document.operations)) {
    document.features = document.operations;
    delete document.operations;
  }
  if (document.deterministicSeed === undefined && Number.isInteger(document.randomSeed)) {
    document.deterministicSeed = document.randomSeed;
    delete document.randomSeed;
  }

  document.sketches ??= [];
  if (Array.isArray(document.sketches)) {
    for (const rawSketch of document.sketches) {
      if (!isRecord(rawSketch)) continue;
      normalizeEntities(rawSketch);
      rawSketch.constraints ??= [];
      rawSketch.profiles ??= [];
      rawSketch.sourceEvidence ??= [];
      rawSketch.confidence ??= 1;
      rawSketch.userLocks ??= [];
      rawSketch.overrides ??= [];
      rawSketch.suppressed ??= false;
    }
  }
  document.features ??= [];
  if (Array.isArray(document.features)) {
    document.features.forEach((feature, index) => {
      if (isRecord(feature)) normalizeFeature(feature, index);
    });
  }

  const legacyTolerance = typeof document.tolerance === "number" ? document.tolerance : 0.1;
  delete document.tolerance;
  document.sourceCoordinateFrame ??= {
    origin: { x: 0, y: 0, z: 0 },
    xAxis: { x: 1, y: 0, z: 0 },
    yAxis: { x: 0, y: 1, z: 0 },
    zAxis: { x: 0, y: 0, z: 1 },
    locked: false,
    confidence: 0,
    evidenceIds: [],
  };
  document.projectTolerance ??= {
    surfaceDeviation: legacyTolerance,
    angularDeviationDeg: 1,
    linearResolution: Math.max(legacyTolerance / 10, 1e-9),
  };
  document.semanticTopology ??= [];
  document.sourceEvidence ??= [];
  document.userLocks ??= [];
  document.overrides ??= [];
  document.reconstructionSettings ??= {
    maxFeatures: 64,
    beamWidth: 3,
    candidatesPerResidual: 4,
    wallClockSeconds: 300,
    maxRebuilds: 200,
    minScoreImprovement: 0.001,
    nominalSnappingEnabled: true,
    nominalSnapTolerance: legacyTolerance,
    scoreWeights: { ...DEFAULT_SCORE_WEIGHTS },
  };
  document.engineVersions ??= {
    mesh2param: "unknown",
    contracts: CURRENT_SCHEMA_VERSION,
    cadBackend: "OCCT",
    cadQuery: "unknown",
    ocp: "unknown",
    dependencies: {},
  };
  document.deterministicSeed ??= 0;
  document.fitMetrics ??= {
    rmsSurfaceDistance: 0,
    p95SurfaceDistance: 0,
    maxSurfaceDistance: 0,
    normalAgreement: 0,
    volumeDifference: 0,
    overlap: 0,
    unmatchedSourceArea: 0,
    excessResultArea: 0,
    score: 0,
  };
  document.validation ??= {
    status: "notRun",
    brepValid: null,
    stepReimportValid: null,
    toleranceSatisfied: null,
    issues: [],
  };
  document.versionMetadata ??= {
    versionId: "version.migrated",
    createdAt: "1970-01-01T00:00:00Z",
    createdBy: "migration",
    message: "Migrated from CADGraph 0.1.0",
  };
  return document;
}

/** Return a detached current-version document without mutating the input. */
export function migrateDocument(value: unknown): Record<string, unknown> {
  const document = detachedObject(value);
  if (document.schemaVersion === CURRENT_SCHEMA_VERSION) return document;
  if (document.schemaVersion === LEGACY_SCHEMA_VERSION) return migrateLegacy(document);
  throw new MigrationError(`unsupported CADGraph schemaVersion: ${String(document.schemaVersion)}`);
}

/** Migrate and validate, returning a graph safe for engine or UI use. */
export function migrateCADGraph(value: unknown): CADGraph {
  const document = migrateDocument(value);
  assertCADGraph(document);
  return document;
}
