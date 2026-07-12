import { webcrypto } from "node:crypto";

import { afterEach, beforeAll, describe, expect, it } from "vitest";

import type {
  Mesh2ParamProjectFile,
  PersistedProjectUI,
  ProjectSummary,
  ProjectWorkingDocument,
} from "../state/types";
import { Mesh2ParamWorkspaceDB } from "./db";
import {
  ProjectFileError,
  createProjectFile,
  openProjectFile,
  parseProjectFile,
  projectFileSourceFromBlob,
  readBlobBytes,
  serializeProjectFile,
  sha256Hex,
} from "./projectFile";
import { WorkspaceRepository } from "./repository";

beforeAll(() => {
  if (globalThis.crypto?.subtle === undefined) {
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: webcrypto });
  }
});

function project(_sha256: string, _byteSize: number): ProjectSummary {
  return {
    id: "project-file-test",
    name: "Project file test",
    units: "mm",
    schemaVersion: "1.0.0",
    revision: 3,
    basedOnVersionId: null,
    createdAt: "2026-07-11T12:00:00Z",
    updatedAt: "2026-07-11T12:00:00Z",
  };
}

function working(sha256: string, byteSize: number): ProjectWorkingDocument {
  return {
    schemaVersion: "1.0.0",
    projectId: "project-file-test",
    name: "Project file test",
    units: "mm",
    source: {
      id: "source-1",
      originalFileName: "part.stl",
      format: "stl",
      encoding: "binary",
      sha256,
      byteSize,
      declaredUnits: "mm",
      unitsConfirmed: true,
      scaleFactor: 1,
      state: "valid",
    },
    diagnostics: null,
    repair: null,
    analysis: null,
    patches: [],
    cadgraph: null,
    validation: null,
    metrics: null,
    artifactSetId: null,
    artifacts: [],
    currentVersionId: null,
    settings: {},
  };
}

function persistedUi(): PersistedProjectUI {
  return {
    activeStep: "refine",
    selection: {
      patchId: "patch.cylinder.1",
      featureId: "feature.hole.1",
      sketchEntityId: null,
      hoverId: null,
    },
    viewer: {
      mode: "reconstructed",
      visible: {
        source: false,
        repaired: false,
        analysis: false,
        patches: false,
        reconstructed: true,
        residual: false,
      },
      sourceOpacity: 0.5,
      resultOpacity: 1,
      projection: "orthographic",
      shading: "shaded",
      edges: true,
    },
    shell: {
      theme: "light",
      railCollapsed: true,
      inspectorExpanded: true,
      bottomDrawerExpanded: true,
      bottomDrawerHeight: 260,
      singleKeyShortcuts: false,
    },
    cameraPose: null,
  };
}

function projectFileFixture(): Mesh2ParamProjectFile {
  const sha256 = "0".repeat(64);
  return createProjectFile({
    project: project(sha256, 0),
    working: working(sha256, 0),
    ui: persistedUi(),
    versions: [],
    source: null,
    artifactManifest: [],
    savedAt: "2026-07-11T12:30:00Z",
  });
}

function rawProjectFileFixture(): Record<string, unknown> {
  return JSON.parse(serializeProjectFile(projectFileFixture())) as Record<string, unknown>;
}

const databases: Mesh2ParamWorkspaceDB[] = [];

afterEach(async () => {
  await Promise.all(databases.splice(0).map(async (db) => {
    db.close();
    await db.delete();
  }));
});

describe("Mesh2Param project files", () => {
  it("round-trips and verifies an embedded source before exposing it", async () => {
    const bytes = new TextEncoder().encode("mesh");
    const sha256 = await sha256Hex(bytes);
    const source = await projectFileSourceFromBlob({
      sha256,
      byteSize: bytes.byteLength,
      mediaType: "model/stl",
      originalFileName: "part.stl",
      blob: new Blob([bytes.buffer], { type: "model/stl" }),
    });
    const file = createProjectFile({
      project: project(sha256, bytes.byteLength),
      working: working(sha256, bytes.byteLength),
      ui: persistedUi(),
      versions: [],
      source,
      artifactManifest: [],
      savedAt: "2026-07-11T12:30:00Z",
    });

    const parsed = await parseProjectFile(serializeProjectFile(file));

    expect(parsed.file).toEqual(file);
    expect(parsed.embeddedSource?.sha256).toBe(sha256);
    expect(new TextDecoder().decode(await readBlobBytes(parsed.embeddedSource?.blob as Blob))).toBe("mesh");
  });

  it("rejects a declared oversized source before base64 decoding", async () => {
    const sha256 = "0".repeat(64);
    const file = createProjectFile({
      project: project(sha256, 17),
      working: working(sha256, 17),
      ui: persistedUi(),
      versions: [],
      source: {
        kind: "embedded",
        sha256,
        byteSize: 17,
        mediaType: "model/stl",
        originalFileName: "part.stl",
        dataBase64: "AA==",
      },
      artifactManifest: [],
    });

    await expect(parseProjectFile(serializeProjectFile(file), { maxEmbeddedSourceBytes: 16 })).rejects.toMatchObject({
      code: "embedded_source_too_large",
    });
  });

  it("rejects files outside the .mesh2param.json open contract", async () => {
    const file = new File(["{}"], "project.json", { type: "application/json" });
    await expect(openProjectFile(file)).rejects.toMatchObject({ code: "unsupported_extension" });
  });

  it("fills safe UI defaults for an older version-1 envelope without UI state", async () => {
    const sha256 = "0".repeat(64);
    const file = createProjectFile({
      project: project(sha256, 0),
      working: working(sha256, 0),
      ui: persistedUi(),
      versions: [],
      source: null,
      artifactManifest: [],
    });
    const legacy = JSON.parse(serializeProjectFile(file)) as Record<string, unknown>;
    delete legacy.ui;

    const parsed = await parseProjectFile(JSON.stringify(legacy));

    expect(parsed.file.ui.activeStep).toBe("import");
    expect(parsed.file.ui.selection.featureId).toBeNull();
    expect(parsed.file.ui.shell.theme).toBe("dark");
  });

  it("migrates signed browser OCCT volume magnitudes in saved projects", async () => {
    const raw = rawProjectFileFixture();
    const state = raw.working as Record<string, unknown>;
    state.diagnostics = {
      format: "stl",
      encoding: "binary-or-text",
      byteSize: 0,
      sha256: "0".repeat(64),
      rawVertexCount: 3,
      weldedVertexCount: 3,
      duplicateVertexCount: 0,
      triangleCount: 1,
      connectedComponentCount: 1,
      bounds: [[0, 0, 0], [1, 1, 1]],
      boundingDimensions: [1, 1, 1],
      coordinateRange: [0, 1],
      surfaceArea: 2,
      closedVolume: -12.5,
      watertight: true,
      windingConsistent: true,
      degenerateTriangleCount: 0,
      duplicateFaceCount: 0,
      nonManifoldEdgeCount: 0,
      openBoundaryEdgeCount: 0,
      openBoundaryCount: 0,
      selfIntersectionStatus: "not-evaluated-in-browser",
      warnings: [],
    };
    state.metrics = { volume: -12.5 };

    const parsed = await parseProjectFile(JSON.stringify(raw));

    expect(parsed.file.working.diagnostics?.closedVolume).toBe(12.5);
    expect(parsed.file.working.metrics?.volume).toBe(12.5);
  });

  it.each([
    ["diagnostics strings", (state: Record<string, unknown>) => { state.diagnostics = "truthy"; }],
    ["empty repair objects", (state: Record<string, unknown>) => { state.repair = {}; }],
    ["null patch entries", (state: Record<string, unknown>) => { state.patches = [null]; }],
    [
      "truthy non-boolean validation claims",
      (state: Record<string, unknown>) => {
        state.validation = {
          status: "valid",
          brepValid: "yes",
          stepReimportValid: [],
          toleranceSatisfied: {},
        };
      },
    ],
    ["array analysis payloads", (state: Record<string, unknown>) => { state.analysis = []; }],
    ["string metrics payloads", (state: Record<string, unknown>) => { state.metrics = "oops"; }],
    [
      "non-boolean source confirmation",
      (state: Record<string, unknown>) => {
        (state.source as Record<string, unknown>).unitsConfirmed = "yes";
      },
    ],
  ])("rejects malformed working state: %s", async (_label, mutate) => {
    const raw = rawProjectFileFixture();
    const state = raw.working as Record<string, unknown>;
    mutate(state);

    await expect(parseProjectFile(JSON.stringify(raw))).rejects.toBeInstanceOf(ProjectFileError);
  });

  it.each([
    ["savedAt", (raw: Record<string, unknown>) => { raw.savedAt = "not-a-date"; }],
    [
      "project.createdAt",
      (raw: Record<string, unknown>) => {
        (raw.project as Record<string, unknown>).createdAt = "not-a-date";
      },
    ],
  ])("rejects malformed timestamps in %s", async (_label, mutate) => {
    const raw = rawProjectFileFixture();
    mutate(raw);

    await expect(parseProjectFile(JSON.stringify(raw))).rejects.toMatchObject({
      code: "invalid_timestamp",
    });
  });

  it.each([
    ["metrics", []],
    ["dependencyVersions", []],
  ])("rejects invalid version %s", async (field, malformed) => {
    const raw = rawProjectFileFixture();
    raw.versions = [{
      id: "version-1",
      projectId: "project-file-test",
      parentId: null,
      label: "Version 1",
      state: raw.working,
      sourceSha256: "0".repeat(64),
      validationStatus: "not-run",
      metrics: null,
      artifactSetId: null,
      engineVersion: "test",
      dependencyVersions: {},
      createdAt: "2026-07-11T12:00:00Z",
      [field]: malformed,
    }];

    await expect(parseProjectFile(JSON.stringify(raw))).rejects.toMatchObject({
      code: "invalid_version",
    });
  });

  it("keeps additive defaults for version metadata omitted by early files", async () => {
    const raw = rawProjectFileFixture();
    raw.versions = [{
      id: "version-1",
      projectId: "project-file-test",
      parentId: null,
      label: "Version 1",
      state: raw.working,
      sourceSha256: "0".repeat(64),
      validationStatus: "not-run",
      artifactSetId: null,
      engineVersion: "test",
      createdAt: "2026-07-11T12:00:00Z",
    }];

    const parsed = await parseProjectFile(JSON.stringify(raw));

    expect(parsed.file.versions[0]?.metrics).toBeNull();
    expect(parsed.file.versions[0]?.dependencyVersions).toEqual({});
  });

  it("rejects source content whose SHA-256 does not match", async () => {
    const bytes = new TextEncoder().encode("mesh");
    const sha256 = await sha256Hex(bytes);
    const source = await projectFileSourceFromBlob({
      sha256,
      byteSize: bytes.byteLength,
      mediaType: "model/stl",
      originalFileName: "part.stl",
      blob: new Blob([bytes.buffer], { type: "model/stl" }),
    });
    const file = createProjectFile({
      project: project(sha256, bytes.byteLength),
      working: working(sha256, bytes.byteLength),
      ui: persistedUi(),
      versions: [],
      source,
      artifactManifest: [],
    });
    if (file.source?.kind !== "embedded") throw new ProjectFileError("test", "expected embedded source");
    file.source.dataBase64 = "bmVzaA==";

    await expect(parseProjectFile(serializeProjectFile(file))).rejects.toMatchObject({
      code: "source_hash_mismatch",
    });
  });

  it("writes a verified embedded source directly to Dexie during import", async () => {
    const bytes = new TextEncoder().encode("mesh");
    const sha256 = await sha256Hex(bytes);
    const source = await projectFileSourceFromBlob({
      sha256,
      byteSize: bytes.byteLength,
      mediaType: "model/stl",
      originalFileName: "part.stl",
      blob: new Blob([bytes.buffer], { type: "model/stl" }),
    });
    const file: Mesh2ParamProjectFile = createProjectFile({
      project: project(sha256, bytes.byteLength),
      working: working(sha256, bytes.byteLength),
      ui: persistedUi(),
      versions: [],
      source,
      artifactManifest: [],
    });
    const db = new Mesh2ParamWorkspaceDB(`mesh2param-test-${crypto.randomUUID()}`);
    databases.push(db);
    const repository = new WorkspaceRepository(db);

    await repository.importProjectFile(serializeProjectFile(file));

    const stored = await db.blobs.get(`source:${sha256}`);
    const storedUi = await db.ui.get(file.project.id);
    expect(stored?.projectId).toBe(file.project.id);
    expect(stored?.byteSize).toBe(bytes.byteLength);
    expect(stored?.blob).toBeDefined();
    expect(storedUi?.state).toEqual(file.ui);
  });

  it("drops unavailable artifact descriptors from the active imported workspace", async () => {
    const file = projectFileFixture();
    file.working.artifactSetId = "artifact-set-1";
    file.working.artifacts = [{
      id: "artifact-1",
      name: "reconstructed.glb",
      kind: "reconstructed",
      sha256: "1".repeat(64),
      byteSize: 128,
      mediaType: "model/gltf-binary",
    }];
    file.artifactManifest = structuredClone(file.working.artifacts);
    const db = new Mesh2ParamWorkspaceDB(`mesh2param-test-${crypto.randomUUID()}`);
    databases.push(db);
    const repository = new WorkspaceRepository(db);

    const imported = await repository.importProjectFile(serializeProjectFile(file));
    const stored = await db.documents.get(file.project.id);

    expect(imported.file.artifactManifest).toHaveLength(1);
    expect(imported.file.working.artifacts).toEqual([]);
    expect(imported.file.working.artifactSetId).toBeNull();
    expect(stored?.document.artifacts).toEqual([]);
  });
});
