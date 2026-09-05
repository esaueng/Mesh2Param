import { Blob as NodeBlob } from "node:buffer";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import graphFixture from "../../../../packages/contracts/tests/fixtures/base.cadgraph.json";
import { workspaceDb } from "../persistence/db";
import { readBlobBytes } from "../persistence/projectBytes";
import { WorkspaceRepository } from "../persistence/repository";
import { BrowserApiClient } from "./client";
import { browserGeometry } from "./geometry/client";
import type { BrowserCadResult } from "./geometry/types";

vi.mock("./geometry/client", () => ({ browserGeometry: { compile: vi.fn() } }));
const objects = new Map<string, Blob>();

beforeAll(() => { vi.stubGlobal("Blob", NodeBlob); });
afterAll(() => { vi.unstubAllGlobals(); });
beforeEach(async () => {
  await workspaceDb.open();
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
    if (!(blob instanceof Blob)) throw new TypeError("Expected a Blob");
    const url = `blob:test-${objects.size}`;
    objects.set(url, blob);
    return url;
  });
});
afterEach(async () => {
  await workspaceDb.delete();
  objects.clear();
  vi.restoreAllMocks();
});

async function waitJob(client: BrowserApiClient, id: string) {
  await vi.waitFor(async () => expect((await client.getJob(id)).data.status).toBe("completed"));
}

async function upload(client: BrowserApiClient, id: string, contents = "shared source") {
  const project = (await client.getProject(id)).data;
  const accepted = (await client.uploadSource(id, project.revision, new Blob([contents]), {
    filename: "part.stl", units: "mm", unitsConfirmed: true,
  })).data;
  await waitJob(client, accepted.job.id);
  return accepted;
}

function compiled(step: string): BrowserCadResult {
  return {
    step, valid: true, solid: true, stepReimportValid: true, volume: 1, surfaceArea: 1,
    bounds: [[0, 0, 0], [1, 1, 0]], featureCount: 1,
    mesh: { positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]),
      vertexCount: 3, triangleCount: 1 },
  };
}

async function rebuild(client: BrowserApiClient, id: string, step: string) {
  vi.mocked(browserGeometry.compile).mockResolvedValueOnce(compiled(step));
  const project = (await client.getProject(id)).data;
  const job = (await client.startOperation(id, "rebuild", project.revision)).data;
  await waitJob(client, job.id);
  return (await client.getProject(id)).data;
}

async function artifactText(url: string) {
  return new TextDecoder().decode(await readBlobBytes(objects.get(url)!));
}

describe("browser blob retention", () => {
  it.each(["client", "repository"])("keeps a shared source when deleting its latest owner through %s", async (path) => {
    const client = new BrowserApiClient();
    const a = (await client.createProject("A")).data;
    const b = (await client.createProject("B")).data;
    const source = (await upload(client, a.id)).source;
    await upload(client, b.id);
    if (path === "client") await client.deleteProject(b.id, (await client.getProject(b.id)).data.revision);
    else await new WorkspaceRepository(workspaceDb).deleteProject(b.id);
    expect((await workspaceDb.blobs.get(`source:${source.sha256}`))?.projectId).toBe(a.id);
    const exported = await new WorkspaceRepository(workspaceDb).exportProjectFile(a.id);
    expect(exported.source?.kind).toBe("embedded");
    await client.deleteProject(a.id, (await client.getProject(a.id)).data.revision);
    expect(await workspaceDb.blobs.get(`source:${source.sha256}`)).toBeUndefined();
  });

  it("keeps a shared source referenced only by another project's saved version", async () => {
    const client = new BrowserApiClient();
    const a = (await client.createProject("A")).data;
    const b = (await client.createProject("B")).data;
    const original = await upload(client, a.id);
    const version = (await client.createVersion(a.id, original.revision, "Original source")).data;
    await upload(client, a.id, "replacement source");
    const latest = await upload(client, b.id);
    await client.deleteProject(b.id, latest.revision);
    await client.restoreVersion(a.id, version.id, (await client.getProject(a.id)).data.revision);
    expect((await new WorkspaceRepository(workspaceDb).exportProjectFile(a.id)).source?.kind).toBe("embedded");
  });

  it("keeps a shared source referenced only by another project's undo history", async () => {
    const client = new BrowserApiClient();
    const a = (await client.createProject("A")).data;
    const b = (await client.createProject("B")).data;
    const original = await upload(client, a.id);
    const prior = (await client.getProject(a.id)).data.state;
    await upload(client, a.id, "replacement source");
    await workspaceDb.history.put({ projectId: a.id, updatedAt: a.updatedAt, state: {
      past: [{ id: "upload", label: "Upload", timestamp: a.updatedAt, forwardPatches: [],
        inversePatches: [{ op: "replace", path: [], value: prior }], scopes: ["project"],
        beforeLocalRevision: 0, afterLocalRevision: 1, requiresRebuild: false, serializedBytes: 100 }], future: [],
    } });
    const latest = await upload(client, b.id);
    await client.deleteProject(b.id, latest.revision);
    const source = await workspaceDb.blobs.get(`source:${original.source.sha256}`);
    expect(source?.projectId).toBe(a.id);
    expect(new TextDecoder().decode(await readBlobBytes(source!.blob))).toBe("shared source");
  });

  it.each([false, true])("restores immutable artifact bytes after reload (legacy key: %s)", async (legacy) => {
    const client = new BrowserApiClient();
    const project = (await client.createProject("Versions")).data;
    await client.updateCadgraph(project.id, project.revision, graphFixture as unknown as CADGraph);
    const first = await rebuild(client, project.id, "first STEP");
    const old = first.state.artifacts.find((artifact) => artifact.name === "model.step")!;
    if (legacy) {
      const key = `artifact:${project.id}:model.step:${old.sha256}`;
      const record = (await workspaceDb.blobs.get(key))!;
      await workspaceDb.blobs.put({ ...record, key: `artifact:${project.id}:model.step` });
      await workspaceDb.blobs.delete(key);
    }
    const version = (await client.createVersion(project.id, first.revision, "First")).data;
    const second = await rebuild(client, project.id, "second STEP");
    await client.restoreVersion(project.id, version.id, second.revision);
    const reopened = new BrowserApiClient();
    const restored = (await reopened.getProject(project.id)).data;
    expect(restored.state.artifacts.find((artifact) => artifact.name === "model.step")?.sha256).toBe(old.sha256);
    expect(await artifactText(reopened.artifactUrl(project.id, "model.step", old.sha256))).toBe("first STEP");
    expect(await artifactText(reopened.artifactUrl(project.id, "model.step"))).toBe("first STEP");
    expect(() => reopened.artifactUrl(project.id, "model.step", "0".repeat(64))).toThrow();
  });
});
