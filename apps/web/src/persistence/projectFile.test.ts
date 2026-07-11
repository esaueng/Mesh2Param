import { webcrypto } from "node:crypto";

import { afterEach, beforeAll, describe, expect, it } from "vitest";

import type { Mesh2ParamProjectFile, ProjectSummary, ProjectWorkingDocument } from "../state/types";
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
      versions: [],
      source,
      artifactManifest: [],
    });
    const db = new Mesh2ParamWorkspaceDB(`mesh2param-test-${crypto.randomUUID()}`);
    databases.push(db);
    const repository = new WorkspaceRepository(db);

    await repository.importProjectFile(serializeProjectFile(file));

    const stored = await db.blobs.get(`source:${sha256}`);
    expect(stored?.projectId).toBe(file.project.id);
    expect(stored?.byteSize).toBe(bytes.byteLength);
    expect(stored?.blob).toBeDefined();
  });
});
