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
import { readBlobBytes, sha256Hex } from "../persistence/projectBytes";
import type {
  ArtifactDescriptor,
  ArtifactPage,
  Job,
  JobEvent,
  JobPage,
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
import { deleteProjectBlobs } from "../persistence/blobs";
import { BROWSER_TRIANGLE_BUDGET, browserGeometry } from "./geometry/client";
import type { BrowserMeshFormat, BrowserReconstruction, BrowserReconstructionMode } from "./geometry/types";
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
    settings: { executionMode: "browser-local", geometryKernel: BROWSER_ENGINE },
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

/** What the browser path runs, as it is reported in project state. */
const BROWSER_ENGINE = "Mesh2Param core (WebAssembly)";

/** The core's default dihedral threshold for its initial over-segmentation. */
const BROWSER_SEGMENTATION_ANGLE_DEG = 12;

const MESH_FORMATS: readonly BrowserMeshFormat[] = ["stl", "3mf", "obj", "ply"];

function sourceFormat(detail: ProjectDetail): BrowserMeshFormat {
  const format = detail.state.source?.format?.toLowerCase();
  const match = MESH_FORMATS.find((candidate) => candidate === format);
  if (match === undefined) throw new Error(`Browser-local geometry cannot read ${format ?? "this"} sources; use the Mesh2Param service`);
  return match;
}

/**
 * The record the UI reads a run's tier and evidence from. Everything in it is
 * measured by the core; nothing is inferred here.
 */
function reconstructionEvidence(result: BrowserReconstruction, mode: BrowserReconstructionMode): JsonObject {
  return {
    engine: BROWSER_ENGINE,
    requestedMode: mode,
    tier: result.tier,
    valid: result.valid,
    stepReimportValid: result.roundTripOk,
    fallbackReason: result.fallbackReason,
    issues: result.issues,
    facesFinal: result.facesFinal,
    facesAnalytic: result.facesAnalytic,
    facesTriangle: result.facesTriangle,
    surfaceCounts: { ...result.inventory },
    unknownAreaFraction: result.unknownAreaFraction,
    volume: result.volume,
    sourceVolume: result.sourceVolume,
    stepBytes: result.stepBytes,
    ...(result.patches === null ? {} : { patches: result.patches }),
    ...(result.edges === null ? {} : { edges: result.edges }),
    ...(result.deviation === null ? {} : {
      deviationP95: result.deviation.p95,
      deviationMax: result.deviation.max,
      deviationSamples: result.deviation.samples,
    }),
    designHistoryRecovered: false,
  };
}

const TIER_ISSUES: Record<BrowserReconstruction["tier"], { code: string; message: string }> = {
  analytic: {
    code: "analytic-tier",
    message: "Every face was recognised as an analytic surface. This is a fit to the mesh, not recovered design history.",
  },
  mixed: {
    code: "mixed-tier",
    message: "Some faces are analytic surfaces and some remain triangulated. This is a fit to the mesh, not recovered design history.",
  },
  faceted: {
    code: "faceted-tier",
    message: "No analytic surfaces survived; the STEP preserves the source facets and is not a parametric model.",
  },
};

function reconstructionIssues(result: BrowserReconstruction): JsonObject[] {
  const tier = TIER_ISSUES[result.tier];
  return [
    { code: tier.code, severity: result.tier === "faceted" ? "warning" : "info", message: tier.message },
    ...(result.fallbackReason === null ? [] : [{ code: "tier-fallback", severity: "warning", message: result.fallbackReason }]),
    ...result.issues.map((message) => ({ code: "kernel-issue", severity: "warning", message })),
  ];
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
    return Promise.resolve(result({ status: "ready", database: true, storage: true, supervisor: true, executionMode: "browser-local" }));
  }

  async listProjects(_signal?: AbortSignal, page: { limit?: number; offset?: number } = {}): Promise<ApiResult<ProjectList>> {
    const records = await workspaceDb.projects.orderBy("updatedAt").reverse().toArray();
    const all = (await Promise.all(records.map((record) => this.detail(record.id)))).filter((item): item is ProjectDetail => item !== null);
    const limit = page.limit ?? 100;
    const offset = page.offset ?? 0;
    const items = all.slice(offset, offset + limit);
    return result({ items, total: all.length, limit, offset, hasMore: offset + items.length < all.length });
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
    // Blob URLs are process-local and intentionally are not persisted. Rebuild
    // the URL cache whenever a project is reopened.
    await this.cacheProjectArtifactUrls(projectId);
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
      await deleteProjectBlobs(workspaceDb, projectId);
      await Promise.all([
        workspaceDb.projects.delete(projectId), workspaceDb.documents.delete(projectId),
        workspaceDb.versions.where("projectId").equals(projectId).delete(),
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
    const job = this.queueJob(projectId, operation, detail.revision, async (report) => {
      if (operation === "repair") {
        const next = await this.requireProject(projectId);
        next.state.settings = { ...next.state.settings, [`${operation}Mode`]: "browser-local" };
        await this.save(next, true);
        return { operation, mode: "browser-local", changed: false };
      }
      if (operation === "analyze") {
        const next = await this.requireProject(projectId);
        const existingArtifacts = next.state.artifacts;
        const preserveGeneratedResult = next.state.cadgraph !== null
          || next.state.validation !== null
          || existingArtifacts.some((artifact) => artifact.name === "model.step");
        const source = await this.sourceBlob(next);
        const tolerance = Math.max(0.001, Number(options.settings?.tolerance ?? 0.1));
        const importedProjectPreview = options.settings?.importedProjectPreview === true;
        const analysis = await browserGeometry.analyze(source, sourceFormat(next));
        // The worker only builds a display mesh for STL. Another container is
        // analyzed and reconstructed without a source layer rather than being
        // given an empty GLB the viewer would fail to load.
        const preview = analysis.mesh.triangleCount > 0
          ? [await this.putArtifact(projectId, "source.glb", meshToGlb(analysis.mesh), "source")]
          : [];
        next.state.artifacts = preserveGeneratedResult
          ? [...existingArtifacts.filter((artifact) => artifact.name !== "source.glb"), ...preview]
          : preview;
        if (importedProjectPreview) {
          const saved = await this.save(next, true);
          return { operation, revision: saved.revision, mode: "browser-local-import-preview" };
        }
        next.state.patches = [{
          id: "patch.browser-local.source", type: "freeform", name: "Imported mesh surface",
          triangleCount: analysis.triangleCount, vertexCount: analysis.weldedVertexCount,
          areaMm2: analysis.surfaceArea, confidence: 1, locked: false,
        }];
        // The core segments and classifies surfaces inside `reconstruct`; its
        // `analyze` reports mesh statistics only. These settings are what the
        // reconstruction will actually replay, not a separate analysis model.
        next.state.analysis = {
          settings: {
            engine: BROWSER_ENGINE,
            angleDeg: BROWSER_SEGMENTATION_ANGLE_DEG,
            triangleBudget: BROWSER_TRIANGLE_BUDGET,
            tolerance,
          },
          patches: next.state.patches,
          meshHealth: {
            watertight: analysis.watertight,
            edgeManifold: analysis.edgeManifold,
            nonManifoldEdgeCount: analysis.nonManifoldEdgeCount,
            droppedTriangleCount: analysis.droppedTriangleCount,
          },
        } as unknown as JsonObject;
        const [lower, upper] = analysis.bounds;
        next.state.diagnostics = {
          format: next.state.source!.format as "stl" | "obj" | "ply",
          encoding: "binary-or-text", byteSize: source.size, sha256: next.state.source!.sha256,
          rawVertexCount: analysis.rawVertexCount,
          weldedVertexCount: analysis.weldedVertexCount,
          duplicateVertexCount: Math.max(0, analysis.rawVertexCount - analysis.weldedVertexCount),
          triangleCount: analysis.triangleCount,
          // The core measures edges, not bodies, boundary loops or winding, so
          // those stay null rather than being guessed at in JavaScript.
          connectedComponentCount: null,
          bounds: analysis.bounds,
          boundingDimensions: [upper[0] - lower[0], upper[1] - lower[1], upper[2] - lower[2]],
          coordinateRange: [Math.min(...lower), Math.max(...upper)],
          surfaceArea: analysis.surfaceArea,
          closedVolume: analysis.closedVolume,
          watertight: analysis.watertight,
          windingConsistent: null,
          degenerateTriangleCount: analysis.droppedTriangleCount,
          duplicateFaceCount: null,
          nonManifoldEdgeCount: analysis.nonManifoldEdgeCount,
          openBoundaryEdgeCount: null,
          openBoundaryCount: null,
          selfIntersectionStatus: "not-evaluated-in-browser",
          warnings: analysis.watertight ? [] : [{
            code: "not-watertight",
            message: "The mesh is not watertight; reconstruction may fall back to the faceted tier.",
            severity: "warning",
          }],
        };
        next.state.metrics = {
          volume: analysis.closedVolume, surfaceArea: analysis.surfaceArea, bounds: analysis.bounds,
          vertexCount: analysis.weldedVertexCount, triangleCount: analysis.triangleCount,
        };
        const saved = await this.save(next, true);
        return { operation, revision: saved.revision, mode: "browser-local-analyze" };
      }
      if (operation === "reconstruct") {
        const next = await this.requireProject(projectId);
        // A project that already carries a CADGraph would be rebuilt from that
        // history, which the browser core cannot do.
        if (next.state.cadgraph !== null) return await browserGeometry.compile(next.state.cadgraph);
        const source = await this.sourceBlob(next);
        const requested = Number(options.settings?.surfaceDeviationTolerance ?? options.settings?.tolerance ?? Number.NaN);
        const tolerance = Number.isFinite(requested) ? Math.min(10, Math.max(0.001, requested)) : null;
        const mode: BrowserReconstructionMode = options.settings?.mode === "faceted"
          ? "faceted"
          : options.settings?.mode === "curved" ? "curved" : "automatic";
        const result = await browserGeometry.reconstruct(source, sourceFormat(next), {
          mode,
          tolerance,
          triangleBudget: BROWSER_TRIANGLE_BUDGET,
          onProgress: ({ stage, fraction, message }) => { report(stage, Math.round(10 + fraction * 85), message); },
        });
        const evidence = reconstructionEvidence(result, mode);
        const artifacts = await Promise.all([
          this.putArtifact(projectId, "model.step", new Blob([result.step], { type: "model/step" }), `${result.tier}-step`),
          this.putArtifact(projectId, "reconstructed.glb", new Blob([result.glb], { type: "model/gltf-binary" }), `reconstructed-${result.tier}`),
          this.putArtifact(projectId, "reconstruction.json", new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" }), "reconstruction-evidence"),
        ]);
        next.state.artifactSetId = `artifact-set-${crypto.randomUUID()}`;
        next.state.artifacts = [...next.state.artifacts.filter((artifact) => artifact.name === "source.glb"), ...artifacts];
        next.state.validation = {
          status: result.valid && result.roundTripOk
            ? (result.tier === "faceted" ? "valid-with-warnings" : "valid")
            : "invalid-brep",
          brepValid: result.valid,
          stepReimportValid: result.roundTripOk,
          toleranceSatisfied: tolerance === null || result.deviation === null ? null : result.deviation.p95 <= tolerance,
          issues: reconstructionIssues(result),
          compilation: {
            kernel: BROWSER_ENGINE,
            mode: `browser-local-${result.tier}`,
            tier: result.tier,
            facesFinal: result.facesFinal,
            facesAnalytic: result.facesAnalytic,
            facesTriangle: result.facesTriangle,
            surfaceCounts: { ...result.inventory },
          },
          step: { exported: true, reimported: result.roundTripOk },
        };
        next.state.metrics = {
          volume: result.volume,
          sourceVolume: result.sourceVolume,
          bounds: next.state.diagnostics?.bounds ?? null,
          triangleCount: next.state.diagnostics?.triangleCount ?? null,
          faceCount: result.facesFinal,
          ...(result.deviation === null ? {} : { p95Distance: result.deviation.p95, maxDistance: result.deviation.max }),
        };
        next.state.settings = { ...next.state.settings, reconstruction: evidence };
        const saved = await this.save(next, true);
        return {
          operation,
          revision: saved.revision,
          mode: `browser-local-${result.tier}`,
          tier: result.tier,
          requestedMode: mode,
          brepValid: result.valid,
          stepReimportValid: result.roundTripOk,
        };
      }
      const next = await this.requireProject(projectId);
      if (next.state.cadgraph === null) throw new Error("This project does not have a CADGraph to compile");
      // `validate`, `export` and `rebuild` all mean "run the CADGraph through
      // the kernel again", which the browser core does not do.
      return await browserGeometry.compile(next.state.cadgraph);
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

  async listJobs(
    filters: { projectId?: string; status?: Job["status"]; limit?: number; offset?: number } = {},
    _signal?: AbortSignal,
  ): Promise<ApiResult<JobPage>> {
    const all = [...this.jobs.values()]
      .filter((job) => filters.projectId === undefined || job.projectId === filters.projectId)
      .filter((job) => filters.status === undefined || job.status === filters.status)
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt) || left.id.localeCompare(right.id));
    const limit = filters.limit ?? 100;
    const offset = filters.offset ?? 0;
    const items = all.slice(offset, offset + limit).map((job) => structuredClone(job));
    return result({ items, total: all.length, limit, offset, hasMore: offset + items.length < all.length });
  }

  async deleteJob(jobId: string, _signal?: AbortSignal): Promise<ApiResult<void>> {
    const job = this.jobs.get(jobId);
    if (job === undefined) throw missing("job", jobId);
    if (job.status === "queued" || job.status === "running") {
      throw new ApiError({
        status: 409,
        code: "active_job",
        summary: "Active job cannot be deleted",
        detail: "Cancel the job and wait for it to become terminal before deleting it.",
        phase: job.phase,
        projectId: job.projectId,
        jobId,
        recoverable: true,
        recommendedAction: "Cancel the job first.",
        requestId: crypto.randomUUID(),
      });
    }
    this.jobs.delete(jobId);
    this.lastEvents.delete(jobId);
    return result(undefined);
  }

  async cancelJob(jobId: string, _signal?: AbortSignal): Promise<ApiResult<Job>> {
    const job = this.jobs.get(jobId);
    if (job === undefined) throw missing("job", jobId);
    if (job.status === "queued" || job.status === "running") {
      if (job.status === "running") browserGeometry.cancelAll();
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

  async listVersions(projectId: string, _signal?: AbortSignal, page: { limit?: number; offset?: number } = {}): Promise<ApiResult<VersionPage>> {
    await this.requireProject(projectId);
    const all = (await workspaceDb.versions.where("projectId").equals(projectId).sortBy("createdAt")).map((record) => record.snapshot).reverse();
    const limit = page.limit ?? 100;
    const offset = page.offset ?? 0;
    const items = all.slice(offset, offset + limit);
    return result({ items, total: all.length, limit, offset, hasMore: offset + items.length < all.length });
  }

  async createVersion(projectId: string, revision: number | string, label: string, _signal?: AbortSignal): Promise<ApiResult<ProjectVersionSnapshot>> {
    const detail = await this.requireProject(projectId, revision);
    const snapshot: ProjectVersionSnapshot = {
      id: `version-${crypto.randomUUID()}`, projectId, parentId: detail.state.currentVersionId, label: label || "Snapshot",
      state: structuredClone(detail.state), sourceSha256: detail.state.source?.sha256 ?? null,
      validationStatus: detail.state.validation?.status ?? "not-run", metrics: detail.state.metrics,
      artifactSetId: detail.state.artifactSetId, engineVersion: "browser-local/1", dependencyVersions: { core: BROWSER_ENGINE },
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

  async listArtifacts(projectId: string, _signal?: AbortSignal, page: { limit?: number; offset?: number } = {}): Promise<ApiResult<ArtifactPage>> {
    const detail = await this.requireProject(projectId);
    await this.cacheProjectArtifactUrls(projectId);
    const limit = page.limit ?? 100;
    const offset = page.offset ?? 0;
    const items = detail.state.artifacts.slice(offset, offset + limit);
    return result({ items, total: detail.state.artifacts.length, limit, offset, hasMore: offset + items.length < detail.state.artifacts.length }, detail.revision);
  }

  artifactUrl(projectId: string, name: string, sha256?: string): string {
    const url = this.artifactUrls.get(this.artifactUrlKey(projectId, name, sha256));
    if (url === undefined) throw missing("artifact", `${name}${sha256 === undefined ? "" : ` (${sha256})`}`);
    return url;
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
      const [glb, stl, obj, step, source, previewSource] = await Promise.all([
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.glb"), "model/gltf-binary"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.stl"), "model/stl"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.obj"), "model/obj"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "model.step"), "model/step"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "source-random.stl"), "model/stl"),
        blobFromUrl(browserSampleAssetUrl(sampleId, "source-high.stl"), "model/stl"),
      ]);
      const sourceSha = await sha256Hex(await readBlobBytes(source));
      const sourcePreview = await browserGeometry.analyze(previewSource, "stl");
      next.state.source = {
        id: `source-${sourceSha.slice(0, 16)}`, originalFileName: `${sampleId}.stl`, format: "stl", encoding: "binary",
        sha256: sourceSha, byteSize: source.size, declaredUnits: sample.graph.units, unitsConfirmed: true, scaleFactor: 1, state: "bundled-local",
      };
      await workspaceDb.blobs.put({
        key: `source:${sourceSha}`, projectId: saved.id, kind: "source", sha256: sourceSha, byteSize: source.size,
        mediaType: source.type, originalFileName: `${sampleId}.stl`, blob: source, createdAt: new Date().toISOString(),
      });
      const artifacts = await Promise.all([
        this.putArtifact(saved.id, "source.glb", meshToGlb(sourcePreview.mesh), "source"),
        this.putArtifact(saved.id, "reconstructed.glb", glb, "reconstructed"),
        this.putArtifact(saved.id, "reconstructed.stl", stl, "reconstructed"),
        this.putArtifact(saved.id, "reconstructed.obj", obj, "reconstructed"),
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

  private async cacheProjectArtifactUrls(projectId: string): Promise<void> {
    const detail = await this.requireProject(projectId);
    await Promise.all(detail.state.artifacts.map(async (artifact) => {
      const record = await workspaceDb.blobs.get(`artifact:${projectId}:${artifact.name}:${artifact.sha256}`)
        ?? await workspaceDb.blobs.get(`artifact:${projectId}:${artifact.name}`);
      this.artifactUrls.delete(this.artifactUrlKey(projectId, artifact.name));
      if (record?.sha256 === artifact.sha256 && record.projectId === projectId) {
        this.cacheArtifactUrl(projectId, artifact.name, artifact.sha256, record.blob);
      }
    }));
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

  private queueJob(
    projectId: string,
    kind: Job["kind"],
    inputRevision: number,
    work: (report: (phase: string, progress: number, message: string) => void) => Promise<JsonObject>,
  ): Job {
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

  private async runJob(
    job: Job,
    work: (report: (phase: string, progress: number, message: string) => void) => Promise<JsonObject>,
  ): Promise<void> {
    if (job.status === "cancelled") return;
    job.status = "running"; job.progress = 10; job.phase = "browser-local"; job.startedAt = new Date().toISOString(); job.heartbeatAt = job.startedAt;
    this.emit(job, "progress", "Running locally in this browser.");
    try {
      const value = await work((phase, progress, message) => {
        if (this.jobs.get(job.id)?.status === "cancelled") return;
        job.phase = phase;
        job.progress = Math.max(job.progress, Math.min(99, Math.max(0, progress)));
        job.heartbeatAt = new Date().toISOString();
        this.emit(job, "progress", message);
      });
      if (this.jobs.get(job.id)?.status === "cancelled") return;
      job.status = "completed"; job.progress = 100; job.phase = "completed"; job.result = value; job.finishedAt = new Date().toISOString();
      this.emit(job, "completed", "Browser-local operation completed.");
    } catch (cause) {
      if (this.jobs.get(job.id)?.status === "cancelled") return;
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
      key: `artifact:${projectId}:${name}:${sha256}`, projectId, kind: `artifact:${kind}`, sha256, byteSize: blob.size,
      mediaType: blob.type || "application/octet-stream", originalFileName: name, blob, createdAt: new Date().toISOString(),
    });
    this.cacheArtifactUrl(projectId, name, sha256, blob);
    return { id: `artifact-${crypto.randomUUID()}`, name, kind, sha256, byteSize: blob.size, mediaType: blob.type || "application/octet-stream", createdAt: new Date().toISOString() };
  }

  private artifactUrlKey(projectId: string, name: string, sha256?: string): string {
    return `${projectId}\u0000${name}\u0000${sha256 ?? ""}`;
  }

  private cacheArtifactUrl(projectId: string, name: string, sha256: string, blob: Blob): void {
    const key = this.artifactUrlKey(projectId, name, sha256);
    const url = this.artifactUrls.get(key) ?? URL.createObjectURL(blob);
    this.artifactUrls.set(this.artifactUrlKey(projectId, name), url);
    this.artifactUrls.set(this.artifactUrlKey(projectId, name, sha256), url);
  }
}
