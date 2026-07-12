import { contentSha256, type CADGraph, type Units } from "@mesh2param/contracts";

import type {
  ApiResult,
  OperationOptions,
  RestoreAccepted,
  SampleOpenAccepted,
  UploadAccepted,
  UploadOptions,
} from "../api/client";
import { ApiError } from "../api/errors";
import { workspaceDb, type DocumentRecord, type ProjectRecord } from "../persistence/db";
import { readBlobBytes, sha256Hex } from "../persistence/projectFile";
import type {
  ArtifactDescriptor,
  ArtifactPage,
  Job,
  JobEvent,
  JsonObject,
  PatchClassification,
  PatchPage,
  ProjectDetail,
  ProjectList,
  ProjectVersionSnapshot,
  Readiness,
  SamplePage,
  SourceAssetDescriptor,
  SurfacePatch,
  VersionPage,
} from "../state/types";
import { browserGeometry } from "./geometry/client";
import { inferBrowserPrismaticCadGraph } from "./geometry/prismatic";
import { meshToGlb } from "./glb";
import { browserSampleAssetUrl, listBrowserSamples, loadBrowserSample } from "./sampleAssets";

type Operation = "repair" | "analyze" | "reconstruct" | "rebuild" | "validate" | "export";
type JobListener = (event: JobEvent) => void;

function result<T>(data: T, revision: number | null = null): ApiResult<T> {
  return { data, revision, requestId: crypto.randomUUID() };
}

function emptyDocument(projectId: string, name: string, units: Units): ProjectDetail["state"] {
  return {
    schemaVersion: "1.0.0",
    projectId,
    name,
    units,
    source: null,
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
    settings: { executionMode: "browser-local", geometryKernel: "OCCT WebAssembly" },
  };
}

function conflict(projectId: string, expected: number | string, actual: number): ApiError {
  return new ApiError({
    status: 412,
    code: "revision_conflict",
    summary: "Project changed",
    detail: `Expected revision ${String(expected)}, but the browser workspace is at revision ${actual}.`,
    phase: null,
    projectId,
    jobId: null,
    recoverable: true,
    recommendedAction: "Refresh the project and retry.",
    requestId: crypto.randomUUID(),
  });
}

function missing(kind: string, id: string): ApiError {
  return new ApiError({
    status: 404,
    code: `${kind}_not_found`,
    summary: `${kind} not found`,
    detail: `The browser workspace does not contain ${kind} ${id}.`,
    phase: null,
    projectId: kind === "project" ? id : null,
    jobId: kind === "job" ? id : null,
    recoverable: false,
    recommendedAction: null,
    requestId: crypto.randomUUID(),
  });
}

function numericRevision(value: number | string): number {
  if (typeof value === "number") return value;
  const match = /(?:rev-)?(\d+)/.exec(value);
  return match === null ? Number.NaN : Number(match[1]);
}

async function blobFromUrl(url: string, mediaType?: string): Promise<Blob> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Bundled asset request failed (${response.status})`);
  const blob = await response.blob();
  return mediaType === undefined || blob.type === mediaType ? blob : new Blob([await blob.arrayBuffer()], { type: mediaType });
}

export class BrowserApiClient {
  private readonly jobs = new Map<string, Job>();
  private readonly listeners = new Map<string, Set<JobListener>>();
  private readonly lastEvents = new Map<string, JobEvent>();
  private readonly artifactUrls = new Map<string, string>();

  health(_signal?: AbortSignal): Promise<ApiResult<{ status: "ok" }>> {
    return Promise.resolve(result({ status: "ok" }));
  }

  ready(_signal?: AbortSignal): Promise<ApiResult<Readiness>> {
    return Promise.resolve(result({ status: "ready", database: true, storage: true, supervisor: true }));
  }

  async listProjects(_signal?: AbortSignal): Promise<ApiResult<ProjectList>> {
    const records = await workspaceDb.projects.orderBy("updatedAt").reverse().toArray();
    const items = (await Promise.all(records.map((record) => this.detail(record.id)))).filter((item): item is ProjectDetail => item !== null);
    return result({ items, total: items.length });
  }

  async createProject(name = "Untitled project", units: Units = "mm", _signal?: AbortSignal): Promise<ApiResult<ProjectDetail>> {
    const now = new Date().toISOString();
    const id = `project-${crypto.randomUUID()}`;
    const state = emptyDocument(id, name, units);
    const project: ProjectRecord = {
      id, name, units, schemaVersion: "1.0.0", revision: 0, basedOnVersionId: null,
      createdAt: now, updatedAt: now, lastOpenedAt: now, activeVersionId: null, syncState: "clean",
    };
    const document: DocumentRecord = {
      projectId: id, document: state, updatedAt: now, baseVersionId: null,
      localRevision: 0, serverRevision: 0, lastAckedLocalRevision: 0,
      contentHash: await contentSha256(state),
    };
    await workspaceDb.transaction("rw", [workspaceDb.projects, workspaceDb.documents], async () => {
      await workspaceDb.projects.put(project);
      await workspaceDb.documents.put(document);
    });
    return result({ ...project, state }, 0);
  }

  async getProject(projectId: string, _signal?: AbortSignal): Promise<ApiResult<ProjectDetail>> {
    const detail = await this.detail(projectId);
    if (detail === null) throw missing("project", projectId);
    return result(detail, detail.revision);
  }

  async updateProject(
    projectId: string,
    revision: number | string,
    patch: { name?: string; units?: Units },
    _signal?: AbortSignal,
  ): Promise<ApiResult<ProjectDetail>> {
    const detail = await this.requireProject(projectId, revision);
    if (patch.name !== undefined) { detail.name = patch.name; detail.state.name = patch.name; }
    if (patch.units !== undefined) { detail.units = patch.units; detail.state.units = patch.units; }
    const saved = await this.save(detail, true);
    return result(saved, saved.revision);
  }

  async deleteProject(projectId: string, revision: number | string, _signal?: AbortSignal): Promise<ApiResult<void>> {
    await this.requireProject(projectId, revision);
    await workspaceDb.transaction("rw", [workspaceDb.projects, workspaceDb.documents, workspaceDb.versions, workspaceDb.blobs, workspaceDb.ui, workspaceDb.history, workspaceDb.outbox], async () => {
      await Promise.all([
        workspaceDb.projects.delete(projectId), workspaceDb.documents.delete(projectId),
        workspaceDb.versions.where("projectId").equals(projectId).delete(), workspaceDb.blobs.where("projectId").equals(projectId).delete(),
        workspaceDb.ui.delete(projectId), workspaceDb.history.delete(projectId), workspaceDb.outbox.where("projectId").equals(projectId).delete(),
      ]);
    });
    return result(undefined);
  }

  async uploadSource(
    projectId: string,
    revision: number | string,
    content: Blob,
    options: UploadOptions,
    _signal?: AbortSignal,
  ): Promise<ApiResult<UploadAccepted>> {
    const detail = await this.requireProject(projectId, revision);
    const bytes = await readBlobBytes(content);
    const sha256 = await sha256Hex(bytes);
    const format = options.filename.split(".").at(-1)?.toLowerCase() || "stl";
    const source: SourceAssetDescriptor = {
      id: `source-${sha256.slice(0, 16)}`, originalFileName: options.filename, format, encoding: "binary-or-text",
      sha256, byteSize: content.size, declaredUnits: options.units, unitsConfirmed: true,
      scaleFactor: options.scaleFactor ?? 1, state: "stored-locally",
    };
    detail.state.source = source;
    detail.state.diagnostics = null;
    detail.state.cadgraph = null;
    detail.state.validation = null;
    detail.state.artifacts = [];
    await workspaceDb.blobs.put({
      key: `source:${sha256}`, projectId, kind: "source", sha256, byteSize: content.size,
      mediaType: content.type || `model/${format}`, originalFileName: options.filename, blob: content, createdAt: new Date().toISOString(),
    });
    const saved = await this.save(detail, true);
    const job = this.queueJob(projectId, "upload", saved.revision, async () => ({ sourceSha256: sha256 }));
    return result({ source, job, revision: saved.revision }, saved.revision);
  }

  async startOperation(
    projectId: string,
    operation: Operation,
    revision: number | string,
    options: OperationOptions = {},
    _signal?: AbortSignal,
  ): Promise<ApiResult<Job>> {
    const detail = await this.requireProject(projectId, revision);
    const job = this.queueJob(projectId, operation, detail.revision, async () => {
      if (operation === "repair") {
        const next = await this.requireProject(projectId);
        next.state.settings = { ...next.state.settings, [`${operation}Mode`]: "browser-local" };
        await this.save(next, true);
        return { operation, mode: "browser-local", changed: false };
      }
      if (operation === "analyze") {
        const next = await this.requireProject(projectId);
        const source = await this.sourceBlob(next);
        const tolerance = Math.max(0.01, Number(options.settings?.tolerance ?? 0.1));
        const importedProjectPreview = options.settings?.importedProjectPreview === true;
        const compiled = await browserGeometry.compileStl(source, tolerance, {
          solidify: !importedProjectPreview,
          validateStep: false,
        });
        const diagnostics = compiled.diagnostics;
        const preview = await this.putArtifact(projectId, "source.glb", meshToGlb(compiled.mesh), "source");
        next.state.artifacts = [preview];
        if (importedProjectPreview) {
          const saved = await this.save(next, true);
          return { operation, revision: saved.revision, mode: "browser-local-import-preview" };
        }
        next.state.patches = [{
          id: "patch.browser-local.source", type: "freeform", name: "Imported STL surface",
          triangleCount: compiled.mesh.triangleCount, vertexCount: diagnostics?.weldedVertexCount ?? compiled.mesh.vertexCount,
          areaMm2: compiled.surfaceArea, confidence: 1, locked: false,
        }];
        const prismatic = inferBrowserPrismaticCadGraph(compiled.mesh.positions, next.state.source!, next.units);
        next.state.analysis = {
          settings: {
            smoothAngleDeg: 12,
            planarFitToleranceMm: 0.005,
            cylinderFitToleranceMm: 0.01,
            minimumCylinderCoverageDeg: 300,
            maximumCylinderAxisNormalComponent: 0.05,
            minimumPatchAreaMm2: 1e-8,
            stableIdResolutionMm: 1e-5,
          },
          patches: next.state.patches,
          prismaticCandidate: prismatic?.analysis ?? {
            accepted: false,
            profiles: [],
            diagnostics: [{ code: "browser-prismatic-unsupported", message: "No bounded orthogonal line/arc extrusion was detected." }],
          },
        } as unknown as JsonObject;
        next.state.diagnostics = {
          format: "stl", encoding: "binary-or-text", byteSize: source.size, sha256: next.state.source!.sha256,
          rawVertexCount: diagnostics?.rawVertexCount ?? compiled.mesh.vertexCount,
          weldedVertexCount: diagnostics?.weldedVertexCount ?? compiled.mesh.vertexCount,
          duplicateVertexCount: diagnostics?.duplicateVertexCount ?? 0,
          triangleCount: compiled.mesh.triangleCount,
          connectedComponentCount: diagnostics?.connectedComponentCount ?? 1,
          bounds: compiled.bounds, boundingDimensions: [
            compiled.bounds[1][0] - compiled.bounds[0][0],
            compiled.bounds[1][1] - compiled.bounds[0][1],
            compiled.bounds[1][2] - compiled.bounds[0][2],
          ],
          coordinateRange: [Math.min(...compiled.bounds[0]), Math.max(...compiled.bounds[1])],
          surfaceArea: compiled.surfaceArea, closedVolume: compiled.solid ? compiled.volume : null,
          watertight: diagnostics?.watertight ?? compiled.solid,
          windingConsistent: diagnostics?.windingConsistent ?? compiled.valid,
          degenerateTriangleCount: diagnostics?.degenerateTriangleCount ?? 0,
          duplicateFaceCount: diagnostics?.duplicateFaceCount ?? 0,
          nonManifoldEdgeCount: diagnostics?.nonManifoldEdgeCount ?? 0,
          openBoundaryEdgeCount: diagnostics?.openBoundaryEdgeCount ?? (compiled.solid ? 0 : 1),
          openBoundaryCount: diagnostics?.openBoundaryCount ?? (compiled.solid ? 0 : 1),
          selfIntersectionStatus: "not-evaluated-in-browser",
          warnings: compiled.solid ? [] : [{ code: "not-solid", message: "OCCT could not solidify the imported STL.", severity: "warning" }],
        };
        next.state.metrics = {
          volume: compiled.volume, surfaceArea: compiled.surfaceArea, bounds: compiled.bounds,
          vertexCount: compiled.mesh.vertexCount, triangleCount: compiled.mesh.triangleCount,
        };
        const saved = await this.save(next, true);
        return { operation, revision: saved.revision, mode: "browser-local-stl" };
      }
      if (operation === "reconstruct" && options.settings?.mode === "faceted") {
        const next = await this.requireProject(projectId);
        const source = await this.sourceBlob(next);
        const compiled = await browserGeometry.compileStl(source, 0.1);
        if (!compiled.valid || !compiled.solid || !compiled.stepReimportValid) {
          throw new Error("OCCT could not create and reimport a valid solid from this STL");
        }
        const artifacts = await Promise.all([
          this.putArtifact(projectId, "model.step", new Blob([compiled.step], { type: "model/step" }), "faceted-step"),
          this.putArtifact(projectId, "reconstructed.glb", meshToGlb(compiled.mesh), "preserved-source-proxy"),
        ]);
        next.state.artifactSetId = `artifact-set-${crypto.randomUUID()}`;
        next.state.artifacts = [...next.state.artifacts.filter((artifact) => artifact.name === "source.glb"), ...artifacts];
        next.state.validation = {
          status: "valid-with-warnings", brepValid: true, stepReimportValid: true, toleranceSatisfied: null,
          issues: [{ code: "faceted-source", message: "STEP preserves source facets; it is not a recovered parametric history." }],
          compilation: { kernel: "OCCT WebAssembly", mode: "preserved-source-faceted" },
        };
        const saved = await this.save(next, true);
        return { operation, revision: saved.revision, mode: "preserved-source-faceted", exactParametric: false };
      }
      const next = await this.requireProject(projectId);
      if (next.state.cadgraph === null && operation === "reconstruct") {
        const source = await this.sourceBlob(next);
        const analyzed = await browserGeometry.compileStl(source, 0.1, { solidify: false, validateStep: false });
        const prismatic = inferBrowserPrismaticCadGraph(analyzed.mesh.positions, next.state.source!, next.units);
        if (prismatic === null) {
          throw new Error("Smooth browser-local reconstruction is unavailable for this mesh. The faceted fallback remains available explicitly.");
        }
        next.state.cadgraph = prismatic.graph;
        next.state.analysis = {
          ...(next.state.analysis ?? {}),
          prismaticCandidate: prismatic.analysis,
        } as JsonObject;
      }
      if (next.state.cadgraph === null) throw new Error("This project does not have a CADGraph to compile");
      const compiled = await browserGeometry.compile(next.state.cadgraph);
      const step = new Blob([compiled.step], { type: "model/step" });
      const glb = meshToGlb(compiled.mesh);
      const artifacts = await Promise.all([
        this.putArtifact(projectId, "model.step", step, "step"),
        this.putArtifact(projectId, "reconstructed.glb", glb, "reconstructed"),
        this.putArtifact(projectId, "model.cadgraph.json", new Blob([JSON.stringify(next.state.cadgraph, null, 2)], { type: "application/json" }), "cadgraph"),
      ]);
      next.state.artifactSetId = `artifact-set-${crypto.randomUUID()}`;
      next.state.artifacts = [
        ...next.state.artifacts.filter((artifact) => artifact.name === "source.glb"),
        ...artifacts,
      ];
      next.state.validation = {
        status: compiled.valid && compiled.solid && compiled.stepReimportValid ? "valid" : "invalid-brep",
        brepValid: compiled.valid && compiled.solid,
        stepReimportValid: compiled.stepReimportValid,
        toleranceSatisfied: null,
        compilation: { kernel: "OCCT WebAssembly", featureCount: compiled.featureCount },
        step: { exported: true, reimported: compiled.stepReimportValid },
      };
      next.state.metrics = {
        volume: compiled.volume, surfaceArea: compiled.surfaceArea, bounds: compiled.bounds,
        vertexCount: compiled.mesh.vertexCount, triangleCount: compiled.mesh.triangleCount,
      };
      next.state.cadgraph = {
        ...next.state.cadgraph,
        engineVersions: {
          ...next.state.cadgraph.engineVersions,
          dependencies: { ...next.state.cadgraph.engineVersions.dependencies, "occt-wasm": "3.6.1" },
        },
        validation: {
          ...next.state.cadgraph.validation,
          status: compiled.valid && compiled.stepReimportValid ? "valid" : "invalid",
          brepValid: compiled.valid,
          stepReimportValid: compiled.stepReimportValid,
          checkedAt: new Date().toISOString(),
          issues: [],
        },
      };
      const saved = await this.save(next, true);
      return { operation, revision: saved.revision, exactBrep: compiled.valid, stepReimportValid: compiled.stepReimportValid };
    });
    return result(job, detail.revision);
  }

  async getCadgraph(projectId: string, _signal?: AbortSignal): Promise<ApiResult<CADGraph>> {
    const detail = await this.requireProject(projectId);
    if (detail.state.cadgraph === null) throw missing("cadgraph", projectId);
    return result(structuredClone(detail.state.cadgraph), detail.revision);
  }

  async updateCadgraph(projectId: string, revision: number | string, cadgraph: CADGraph, _signal?: AbortSignal): Promise<ApiResult<CADGraph>> {
    const detail = await this.requireProject(projectId, revision);
    detail.state.cadgraph = structuredClone(cadgraph);
    detail.state.validation = null;
    const saved = await this.save(detail, true);
    return result(structuredClone(cadgraph), saved.revision);
  }

  async listPatches(projectId: string, _signal?: AbortSignal): Promise<ApiResult<PatchPage>> {
    const detail = await this.requireProject(projectId);
    return result({ items: detail.state.patches, total: detail.state.patches.length }, detail.revision);
  }

  async updatePatch(projectId: string, patchId: string, revision: number | string, patch: {
    name?: string; hidden?: boolean; locked?: boolean; classification?: PatchClassification; parameters?: JsonObject;
  }, _signal?: AbortSignal): Promise<ApiResult<SurfacePatch>> {
    const detail = await this.requireProject(projectId, revision);
    const index = detail.state.patches.findIndex((item) => item.id === patchId);
    if (index < 0) throw missing("patch", patchId);
    const current = detail.state.patches[index]!;
    const updated: SurfacePatch = {
      ...current,
      ...(patch.name === undefined ? {} : { name: patch.name }),
      ...(patch.hidden === undefined ? {} : { hidden: patch.hidden }),
      ...(patch.locked === undefined ? {} : { locked: patch.locked }),
      ...(patch.classification === undefined ? {} : { type: patch.classification, userOverriddenClassification: true }),
      ...(patch.parameters === undefined ? {} : { fit: patch.parameters }),
    };
    detail.state.patches[index] = updated;
    const saved = await this.save(detail, true);
    return result(updated, saved.revision);
  }

  async mergePatches(projectId: string, patchIds: [string, string], revision: number | string, _signal?: AbortSignal): Promise<ApiResult<SurfacePatch>> {
    const detail = await this.requireProject(projectId, revision);
    const sources = patchIds.map((id) => detail.state.patches.find((patch) => patch.id === id));
    if (sources.some((patch) => patch === undefined)) throw missing("patch", patchIds.join(","));
    const [first, second] = sources as [SurfacePatch, SurfacePatch];
    const merged: SurfacePatch = {
      ...first, id: `patch-${crypto.randomUUID()}`, name: `${first.name ?? first.id} + ${second.name ?? second.id}`,
      triangleCount: (first.triangleCount ?? 0) + (second.triangleCount ?? 0),
      triangleIds: [...(first.triangleIds ?? []), ...(second.triangleIds ?? [])], mergedFrom: patchIds,
    };
    detail.state.patches = detail.state.patches.filter((patch) => !patchIds.includes(patch.id)).concat(merged);
    const saved = await this.save(detail, true);
    return result(merged, saved.revision);
  }

  async splitPatch(projectId: string, patchId: string, triangleIds: number[], revision: number | string, _signal?: AbortSignal): Promise<ApiResult<SurfacePatch>> {
    const detail = await this.requireProject(projectId, revision);
    const source = detail.state.patches.find((patch) => patch.id === patchId);
    if (source === undefined) throw missing("patch", patchId);
    const split: SurfacePatch = { ...source, id: `patch-${crypto.randomUUID()}`, triangleIds, triangleCount: triangleIds.length, name: `${source.name ?? source.id} split` };
    detail.state.patches.push(split);
    const saved = await this.save(detail, true);
    return result(split, saved.revision);
  }

  getJob(jobId: string, _signal?: AbortSignal): Promise<ApiResult<Job>> {
    const job = this.jobs.get(jobId);
    if (job === undefined) return Promise.reject(missing("job", jobId));
    return Promise.resolve(result(structuredClone(job)));
  }

  async cancelJob(jobId: string, _signal?: AbortSignal): Promise<ApiResult<Job>> {
    const job = this.jobs.get(jobId);
    if (job === undefined) throw missing("job", jobId);
    if (job.status === "queued" || job.status === "running") {
      job.status = "cancelled"; job.phase = "cancelled"; job.finishedAt = new Date().toISOString(); job.cancelRequestedAt = job.finishedAt;
      this.emit(job, "cancelled", "Browser-local operation cancelled.");
    }
    return result(structuredClone(job));
  }

  subscribeJob(jobId: string, listener: JobListener): () => void {
    const set = this.listeners.get(jobId) ?? new Set<JobListener>();
    set.add(listener); this.listeners.set(jobId, set);
    const last = this.lastEvents.get(jobId);
    if (last !== undefined) queueMicrotask(() => listener(structuredClone(last)));
    return () => { set.delete(listener); if (set.size === 0) this.listeners.delete(jobId); };
  }

  async listVersions(projectId: string, _signal?: AbortSignal): Promise<ApiResult<VersionPage>> {
    await this.requireProject(projectId);
    const items = (await workspaceDb.versions.where("projectId").equals(projectId).sortBy("createdAt")).map((record) => record.snapshot);
    return result({ items, total: items.length });
  }

  async createVersion(projectId: string, revision: number | string, label: string, _signal?: AbortSignal): Promise<ApiResult<ProjectVersionSnapshot>> {
    const detail = await this.requireProject(projectId, revision);
    const snapshot: ProjectVersionSnapshot = {
      id: `version-${crypto.randomUUID()}`, projectId, parentId: detail.state.currentVersionId, label: label || "Snapshot",
      state: structuredClone(detail.state), sourceSha256: detail.state.source?.sha256 ?? null,
      validationStatus: detail.state.validation?.status ?? "not-run", metrics: detail.state.metrics,
      artifactSetId: detail.state.artifactSetId, engineVersion: "browser-local/1", dependencyVersions: { occtWasm: "3.6.1" },
      createdAt: new Date().toISOString(),
    };
    await workspaceDb.versions.put({ projectId, versionId: snapshot.id, parentVersionId: snapshot.parentId, createdAt: snapshot.createdAt, snapshot });
    detail.state.currentVersionId = snapshot.id;
    await this.save(detail, true);
    return result(snapshot, detail.revision + 1);
  }

  async getVersion(projectId: string, versionId: string, _signal?: AbortSignal): Promise<ApiResult<ProjectVersionSnapshot>> {
    const record = await workspaceDb.versions.get([projectId, versionId]);
    if (record === undefined) throw missing("version", versionId);
    return result(record.snapshot);
  }

  async restoreVersion(projectId: string, versionId: string, revision: number | string, _signal?: AbortSignal): Promise<ApiResult<RestoreAccepted>> {
    const detail = await this.requireProject(projectId, revision);
    const record = await workspaceDb.versions.get([projectId, versionId]);
    if (record === undefined) throw missing("version", versionId);
    detail.state = structuredClone(record.snapshot.state);
    detail.basedOnVersionId = versionId;
    const saved = await this.save(detail, true);
    return result({ revision: saved.revision, state: saved.state, restoredVersionId: versionId }, saved.revision);
  }

  async deleteVersion(projectId: string, versionId: string, _signal?: AbortSignal): Promise<ApiResult<void>> {
    await workspaceDb.versions.delete([projectId, versionId]);
    return result(undefined);
  }

  async listArtifacts(projectId: string, _signal?: AbortSignal): Promise<ApiResult<ArtifactPage>> {
    const detail = await this.requireProject(projectId);
    const records = await workspaceDb.blobs.where("projectId").equals(projectId).filter((record) => record.kind.startsWith("artifact:")).toArray();
    for (const record of records) this.cacheArtifactUrl(projectId, record.originalFileName ?? record.kind.slice(9), record.sha256, record.blob);
    return result({ items: detail.state.artifacts, total: detail.state.artifacts.length }, detail.revision);
  }

  artifactUrl(projectId: string, name: string, sha256?: string): string {
    return this.artifactUrls.get(this.artifactUrlKey(projectId, name, sha256))
      ?? this.artifactUrls.get(this.artifactUrlKey(projectId, name))
      ?? "data:text/plain;charset=utf-8,Artifact%20is%20not%20available%20in%20this%20browser";
  }

  async listSamples(_signal?: AbortSignal): Promise<ApiResult<SamplePage>> {
    const samples = await listBrowserSamples();
    return result({ items: samples.map((sample) => sample.descriptor), total: samples.length });
  }

  async openSample(sampleId: string, _signal?: AbortSignal): Promise<ApiResult<SampleOpenAccepted>> {
    const sample = await loadBrowserSample(sampleId);
    const created = await this.createProject(sample.descriptor.name, sample.graph.units);
    const detail = created.data;
    detail.state.cadgraph = structuredClone(sample.graph);
    detail.state.analysis = { bundledSample: sampleId, exactReferenceGeometry: true };
    detail.state.settings = { ...detail.state.settings, automaticReconstruction: true, sampleId };
    const saved = await this.save(detail, true);
    const job = this.queueJob(saved.id, "sample_open", saved.revision, async () => {
      const next = await this.requireProject(saved.id);
      const [glb, step, source] = await Promise.all([
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.glb"), "model/gltf-binary"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.step"), "model/step"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "source-random.stl"), "model/stl"),
      ]);
      const sourceSha = await sha256Hex(await readBlobBytes(source));
      next.state.source = {
        id: `source-${sourceSha.slice(0, 16)}`, originalFileName: `${sampleId}.stl`, format: "stl", encoding: "binary",
        sha256: sourceSha, byteSize: source.size, declaredUnits: sample.graph.units, unitsConfirmed: true, scaleFactor: 1, state: "bundled-local",
      };
      await workspaceDb.blobs.put({
        key: `source:${sourceSha}`, projectId: saved.id, kind: "source", sha256: sourceSha, byteSize: source.size,
        mediaType: source.type, originalFileName: `${sampleId}.stl`, blob: source, createdAt: new Date().toISOString(),
      });
      const artifacts = await Promise.all([
        this.putArtifact(saved.id, "reconstructed.glb", glb, "reconstructed"),
        this.putArtifact(saved.id, "model.step", step, "step"),
        this.putArtifact(saved.id, "model.cadgraph.json", new Blob([JSON.stringify(sample.graph, null, 2)], { type: "application/json" }), "cadgraph"),
      ]);
      const actual = sample.metadata.actual as JsonObject | undefined;
      next.state.artifactSetId = `artifact-set-${crypto.randomUUID()}`;
      next.state.artifacts = artifacts;
      next.state.validation = { status: "valid", brepValid: true, stepReimportValid: true, toleranceSatisfied: true, step: { bundledReference: true } };
      next.state.metrics = actual ?? {};
      const final = await this.save(next, true);
      return { revision: final.revision, sampleId, exactReferenceGeometry: true };
    });
    return result({ project: saved, job }, saved.revision);
  }

  private async detail(projectId: string): Promise<ProjectDetail | null> {
    const [project, document] = await Promise.all([workspaceDb.projects.get(projectId), workspaceDb.documents.get(projectId)]);
    if (project === undefined || document === undefined) return null;
    return {
      id: project.id, name: project.name, units: project.units, schemaVersion: project.schemaVersion,
      revision: project.revision, basedOnVersionId: project.basedOnVersionId,
      createdAt: project.createdAt, updatedAt: project.updatedAt, state: structuredClone(document.document),
    };
  }

  private async sourceBlob(detail: ProjectDetail): Promise<Blob> {
    const source = detail.state.source;
    if (source === null) throw new Error("This project does not have a source mesh");
    if (source.format !== "stl") throw new Error("Browser-local geometry currently supports STL sources; use the native service for OBJ or PLY");
    const record = await workspaceDb.blobs.get(`source:${source.sha256}`);
    if (record === undefined) throw new Error("The source mesh is no longer available in this browser profile");
    return record.blob;
  }

  private async requireProject(projectId: string, revision?: number | string): Promise<ProjectDetail> {
    const detail = await this.detail(projectId);
    if (detail === null) throw missing("project", projectId);
    if (revision !== undefined && numericRevision(revision) !== detail.revision) throw conflict(projectId, revision, detail.revision);
    return detail;
  }

  private async save(detail: ProjectDetail, advance: boolean): Promise<ProjectDetail> {
    const now = new Date().toISOString();
    const revision = advance ? detail.revision + 1 : detail.revision;
    const saved: ProjectDetail = { ...detail, revision, updatedAt: now, state: structuredClone(detail.state) };
    const existing = await workspaceDb.documents.get(detail.id);
    const project: ProjectRecord = {
      id: saved.id, name: saved.name, units: saved.units, schemaVersion: saved.schemaVersion,
      revision, basedOnVersionId: saved.basedOnVersionId, createdAt: saved.createdAt, updatedAt: now,
      lastOpenedAt: now, activeVersionId: saved.state.currentVersionId, syncState: "clean",
    };
    const document: DocumentRecord = {
      projectId: saved.id, document: saved.state, updatedAt: now, baseVersionId: saved.basedOnVersionId,
      localRevision: existing?.localRevision ?? 0, serverRevision: revision,
      lastAckedLocalRevision: existing?.lastAckedLocalRevision ?? 0, contentHash: await contentSha256(saved.state),
    };
    await workspaceDb.transaction("rw", [workspaceDb.projects, workspaceDb.documents], async () => {
      await workspaceDb.projects.put(project); await workspaceDb.documents.put(document);
    });
    return saved;
  }

  private queueJob(projectId: string, kind: Job["kind"], inputRevision: number, work: () => Promise<JsonObject>): Job {
    const now = new Date().toISOString();
    const job: Job = {
      id: `job-${crypto.randomUUID()}`, projectId, kind, status: "queued", progress: 0, phase: "queued",
      inputRevision, attempt: 1, maxAttempts: 1, createdAt: now, startedAt: null, heartbeatAt: null, finishedAt: null,
      cancelRequestedAt: null, error: null, result: null, eventsUrl: `local-job:${projectId}`,
    };
    this.jobs.set(job.id, job);
    window.setTimeout(() => void this.runJob(job, work), 0);
    return structuredClone(job);
  }

  private async runJob(job: Job, work: () => Promise<JsonObject>): Promise<void> {
    if (job.status === "cancelled") return;
    job.status = "running"; job.progress = 10; job.phase = "browser-local"; job.startedAt = new Date().toISOString(); job.heartbeatAt = job.startedAt;
    this.emit(job, "progress", "Running locally in this browser.");
    try {
      const value = await work();
      if (this.jobs.get(job.id)?.status === "cancelled") return;
      job.status = "completed"; job.progress = 100; job.phase = "completed"; job.result = value; job.finishedAt = new Date().toISOString();
      this.emit(job, "completed", "Browser-local operation completed.");
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : String(cause);
      job.status = "failed"; job.phase = "failed"; job.finishedAt = new Date().toISOString();
      job.error = {
        code: "browser_local_operation_failed", summary: "Browser-local operation failed", detail,
        phase: job.phase, projectId: job.projectId, jobId: job.id, recoverable: true,
        recommendedAction: "Review the CADGraph and retry.",
      };
      this.emit(job, "failed", detail);
    }
  }

  private emit(job: Job, type: JobEvent["type"], message: string): void {
    const event: JobEvent = {
      jobId: job.id, type, phase: job.phase, progress: job.progress, level: type === "failed" ? "error" : "info",
      message, code: job.error?.code ?? null, timestamp: new Date().toISOString(), status: job.status,
      ...(job.result === null ? {} : { result: job.result }),
      ...(job.error === null ? {} : { detail: job.error.detail, recoverable: job.error.recoverable, recommendedAction: job.error.recommendedAction }),
    };
    this.lastEvents.set(job.id, event);
    for (const listener of this.listeners.get(job.id) ?? []) listener(structuredClone(event));
  }

  private async putArtifact(projectId: string, name: string, blob: Blob, kind: string): Promise<ArtifactDescriptor> {
    const sha256 = await sha256Hex(await readBlobBytes(blob));
    await workspaceDb.blobs.put({
      key: `artifact:${projectId}:${name}`, projectId, kind: `artifact:${kind}`, sha256, byteSize: blob.size,
      mediaType: blob.type || "application/octet-stream", originalFileName: name, blob, createdAt: new Date().toISOString(),
    });
    this.cacheArtifactUrl(projectId, name, sha256, blob);
    return { id: `artifact-${crypto.randomUUID()}`, name, kind, sha256, byteSize: blob.size, mediaType: blob.type || "application/octet-stream", createdAt: new Date().toISOString() };
  }

  private artifactUrlKey(projectId: string, name: string, sha256?: string): string {
    return `${projectId}\u0000${name}\u0000${sha256 ?? ""}`;
  }

  private cacheArtifactUrl(projectId: string, name: string, sha256: string, blob: Blob): void {
    const url = URL.createObjectURL(blob);
    this.artifactUrls.set(this.artifactUrlKey(projectId, name), url);
    this.artifactUrls.set(this.artifactUrlKey(projectId, name, sha256), url);
  }
}
