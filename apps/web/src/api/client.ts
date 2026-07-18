import type { CADGraph, Units } from "@mesh2param/contracts";

import type {
  ArtifactPage,
  Job,
  JsonObject,
  PatchClassification,
  PatchPage,
  ProjectDetail,
  ProjectList,
  ProjectVersionSnapshot,
  Readiness,
  SamplePage,
  SourceAssetDescriptor,
  SuccessEnvelope,
  SurfacePatch,
  VersionPage,
} from "../state/types";
import { BrowserApiClient } from "../local/client";
import { apiErrorFromResponse, normalizeApiError } from "./errors";

export interface ApiResult<T> {
  data: T;
  requestId: string;
  revision: number | null;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
}

type ApiRequestInit = Omit<RequestInit, "signal"> & {
  signal?: AbortSignal | undefined;
};

export interface OperationOptions {
  settings?: JsonObject;
  timeoutSeconds?: number;
}

export interface UploadOptions {
  filename: string;
  units: Units;
  unitsConfirmed: true;
  scaleFactor?: number;
}

export interface UploadAccepted {
  source: SourceAssetDescriptor;
  job: Job;
  revision: number;
}

export interface SampleOpenAccepted {
  project: ProjectDetail;
  job: Job;
}

export interface RestoreAccepted {
  revision: number;
  state: ProjectDetail["state"];
  restoredVersionId: string;
}

export interface ProjectRequestToken {
  projectId: string;
  generation: number;
  expectedJobId: string | null;
  signal: AbortSignal;
}

interface ActiveProjectRequest {
  generation: number;
  expectedJobId: string | null;
  controller: AbortController;
}

/**
 * Keeps request lifetimes outside Zustand. Callers must check `isCurrent`
 * before applying a response to the workspace store.
 */
export class ProjectRequestCoordinator {
  private readonly generations = new Map<string, number>();
  private readonly active = new Map<string, ActiveProjectRequest>();

  begin(projectId: string, expectedJobId: string | null = null): ProjectRequestToken {
    this.active.get(projectId)?.controller.abort();
    const generation = (this.generations.get(projectId) ?? 0) + 1;
    this.generations.set(projectId, generation);
    const controller = new AbortController();
    this.active.set(projectId, { generation, expectedJobId, controller });
    return { projectId, generation, expectedJobId, signal: controller.signal };
  }

  isCurrent(
    token: ProjectRequestToken,
    currentProjectId: string | null,
    currentJobId: string | null = null,
  ): boolean {
    const active = this.active.get(token.projectId);
    return (
      currentProjectId === token.projectId &&
      active?.generation === token.generation &&
      !token.signal.aborted &&
      (token.expectedJobId === null || token.expectedJobId === currentJobId)
    );
  }

  finish(token: ProjectRequestToken): void {
    if (this.active.get(token.projectId)?.generation === token.generation) {
      this.active.delete(token.projectId);
    }
  }

  cancel(projectId: string): void {
    this.active.get(projectId)?.controller.abort();
    this.active.delete(projectId);
  }

  cancelAll(): void {
    for (const active of this.active.values()) active.controller.abort();
    this.active.clear();
  }
}

export const projectRequests = new ProjectRequestCoordinator();

function revisionEtag(revision: number | string): string {
  if (typeof revision === "string" && /^(?:W\/)?"rev-\d+"$/.test(revision)) return revision;
  const value = typeof revision === "number" ? revision : Number(revision);
  if (!Number.isSafeInteger(value) || value < 0) throw new TypeError("revision must be a non-negative integer");
  return `"rev-${value}"`;
}

function responseRevision(response: Response): number | null {
  const match = /^(?:W\/)?"rev-(\d+)"$/.exec(response.headers.get("ETag") ?? "");
  if (match === null) return null;
  const revision = Number(match[1]);
  return Number.isSafeInteger(revision) ? revision : null;
}

function jsonBody(value: unknown): { body: string; headers: Record<string, string> } {
  return {
    body: JSON.stringify(value),
    headers: { "Content-Type": "application/json" },
  };
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof globalThis.fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(
    path: string,
    init: ApiRequestInit = {},
    acceptedStatuses: readonly number[] = [],
  ): Promise<ApiResult<T>> {
    try {
      const { signal, ...requestOptions } = init;
      const requestInit: RequestInit = {
        ...requestOptions,
        headers: { Accept: "application/json", ...init.headers },
      };
      if (signal !== undefined) requestInit.signal = signal;
      const response = await this.fetcher(`${this.baseUrl}${path}`, requestInit);
      if (!response.ok && !acceptedStatuses.includes(response.status)) throw await apiErrorFromResponse(response);
      if (response.status === 204) {
        return { data: undefined as T, requestId: response.headers.get("X-Request-ID") ?? "", revision: null };
      }
      const envelope = (await response.json()) as Partial<SuccessEnvelope<T>>;
      if (!("data" in envelope) || typeof envelope.meta?.requestId !== "string") {
        throw new TypeError("API response is not a Mesh2Param success envelope");
      }
      return {
        data: envelope.data as T,
        requestId: envelope.meta.requestId,
        revision: responseRevision(response),
      };
    } catch (error) {
      throw normalizeApiError(error);
    }
  }

  health(signal?: AbortSignal): Promise<ApiResult<{ status: "ok" }>> {
    return this.request("/health", { signal });
  }

  ready(signal?: AbortSignal): Promise<ApiResult<Readiness>> {
    return this.request("/ready", { signal }, [503]);
  }

  listProjects(signal?: AbortSignal): Promise<ApiResult<ProjectList>> {
    return this.request("/api/projects", { signal });
  }

  createProject(name = "Untitled project", units: Units = "mm", signal?: AbortSignal): Promise<ApiResult<ProjectDetail>> {
    return this.request("/api/projects", { method: "POST", signal, ...jsonBody({ name, units }) });
  }

  getProject(projectId: string, signal?: AbortSignal): Promise<ApiResult<ProjectDetail>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}`, { signal });
  }

  updateProject(
    projectId: string,
    revision: number | string,
    patch: { name?: string; units?: Units },
    signal?: AbortSignal,
  ): Promise<ApiResult<ProjectDetail>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      signal,
      ...jsonBody(patch),
      headers: { ...jsonBody(patch).headers, "If-Match": revisionEtag(revision) },
    });
  }

  deleteProject(projectId: string, revision: number | string, signal?: AbortSignal): Promise<ApiResult<void>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
      signal,
      headers: { "If-Match": revisionEtag(revision) },
    });
  }

  uploadSource(
    projectId: string,
    revision: number | string,
    content: Blob,
    options: UploadOptions,
    signal?: AbortSignal,
  ): Promise<ApiResult<UploadAccepted>> {
    const query = new URLSearchParams({
      filename: options.filename,
      units: options.units,
      unitsConfirmed: "true",
      scaleFactor: String(options.scaleFactor ?? 1),
    });
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/upload?${query}`, {
      method: "POST",
      signal,
      body: content,
      headers: {
        "Content-Type": "application/octet-stream",
        "If-Match": revisionEtag(revision),
        "X-Mesh2Param-Filename": options.filename,
      },
    });
  }

  startOperation(
    projectId: string,
    operation: "repair" | "analyze" | "reconstruct" | "rebuild" | "validate" | "export",
    revision: number | string,
    options: OperationOptions = {},
    signal?: AbortSignal,
  ): Promise<ApiResult<Job>> {
    const body: { settings: JsonObject; timeoutSeconds?: number } = { settings: options.settings ?? {} };
    if (options.timeoutSeconds !== undefined) body.timeoutSeconds = options.timeoutSeconds;
    const json = jsonBody(body);
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/${operation}`, {
      method: "POST",
      signal,
      ...json,
      headers: { ...json.headers, "If-Match": revisionEtag(revision) },
    });
  }

  getCadgraph(projectId: string, signal?: AbortSignal): Promise<ApiResult<CADGraph>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/cadgraph`, { signal });
  }

  updateCadgraph(
    projectId: string,
    revision: number | string,
    cadgraph: CADGraph,
    signal?: AbortSignal,
  ): Promise<ApiResult<CADGraph>> {
    const json = jsonBody({ cadgraph });
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/cadgraph`, {
      method: "PATCH",
      signal,
      ...json,
      headers: { ...json.headers, "If-Match": revisionEtag(revision) },
    });
  }

  listPatches(projectId: string, signal?: AbortSignal): Promise<ApiResult<PatchPage>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/patches`, { signal });
  }

  updatePatch(
    projectId: string,
    patchId: string,
    revision: number | string,
    patch: {
      name?: string;
      hidden?: boolean;
      locked?: boolean;
      classification?: PatchClassification;
      parameters?: JsonObject;
      smoothBoundaryIds?: string[];
    },
    signal?: AbortSignal,
  ): Promise<ApiResult<SurfacePatch>> {
    const json = jsonBody(patch);
    return this.request(
      `/api/projects/${encodeURIComponent(projectId)}/patches/${encodeURIComponent(patchId)}`,
      { method: "PATCH", signal, ...json, headers: { ...json.headers, "If-Match": revisionEtag(revision) } },
    );
  }

  mergePatches(
    projectId: string,
    patchIds: [string, string],
    revision: number | string,
    signal?: AbortSignal,
  ): Promise<ApiResult<SurfacePatch>> {
    const json = jsonBody({ patchIds });
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/patches/merge`, {
      method: "POST",
      signal,
      ...json,
      headers: { ...json.headers, "If-Match": revisionEtag(revision) },
    });
  }

  splitPatch(
    projectId: string,
    patchId: string,
    triangleIds: number[],
    revision: number | string,
    signal?: AbortSignal,
  ): Promise<ApiResult<SurfacePatch>> {
    const json = jsonBody({ patchId, triangleIds });
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/patches/split`, {
      method: "POST",
      signal,
      ...json,
      headers: { ...json.headers, "If-Match": revisionEtag(revision) },
    });
  }

  getJob(jobId: string, signal?: AbortSignal): Promise<ApiResult<Job>> {
    return this.request(`/api/jobs/${encodeURIComponent(jobId)}`, { signal });
  }

  cancelJob(jobId: string, signal?: AbortSignal): Promise<ApiResult<Job>> {
    return this.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", signal });
  }

  listVersions(projectId: string, signal?: AbortSignal): Promise<ApiResult<VersionPage>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/versions`, { signal });
  }

  createVersion(
    projectId: string,
    revision: number | string,
    label: string,
    signal?: AbortSignal,
  ): Promise<ApiResult<ProjectVersionSnapshot>> {
    const json = jsonBody({ label });
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/versions`, {
      method: "POST",
      signal,
      ...json,
      headers: { ...json.headers, "If-Match": revisionEtag(revision) },
    });
  }

  getVersion(projectId: string, versionId: string, signal?: AbortSignal): Promise<ApiResult<ProjectVersionSnapshot>> {
    return this.request(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`,
      { signal },
    );
  }

  restoreVersion(
    projectId: string,
    versionId: string,
    revision: number | string,
    signal?: AbortSignal,
  ): Promise<ApiResult<RestoreAccepted>> {
    return this.request(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/restore`,
      { method: "POST", signal, headers: { "If-Match": revisionEtag(revision) } },
    );
  }

  deleteVersion(projectId: string, versionId: string, signal?: AbortSignal): Promise<ApiResult<void>> {
    return this.request(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`,
      { method: "DELETE", signal },
    );
  }

  listArtifacts(projectId: string, signal?: AbortSignal): Promise<ApiResult<ArtifactPage>> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}/artifacts`, { signal });
  }

  artifactUrl(projectId: string, name: string, sha256?: string): string {
    const path = `${this.baseUrl}/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(name)}`;
    return sha256 === undefined ? path : `${path}?sha256=${encodeURIComponent(sha256)}`;
  }

  listSamples(signal?: AbortSignal): Promise<ApiResult<SamplePage>> {
    return this.request("/api/samples", { signal });
  }

  openSample(sampleId: string, signal?: AbortSignal): Promise<ApiResult<SampleOpenAccepted>> {
    return this.request(`/api/samples/${encodeURIComponent(sampleId)}/open`, { method: "POST", signal });
  }
}

type ApiClientSurface = Pick<ApiClient, keyof ApiClient> & {
  subscribeJob?: BrowserApiClient["subscribeJob"];
};

const BACKEND_PROBE_TIMEOUT_MS = 2_000;

/**
 * Prefer the full FastAPI/OCCT service whenever the same-origin `/ready` route is
 * reachable. Cloudflare proxies that route when MESH2PARAM_API_ORIGIN is set;
 * UI-only deployments return 503 and retain the browser-local workspace.
 */
export async function backendAvailable(
  client: Pick<ApiClientSurface, "ready">,
  timeoutMs = BACKEND_PROBE_TIMEOUT_MS,
): Promise<boolean> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await client.ready(controller.signal);
    return response.data.status === "ready";
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function createAdaptiveApiClient(
  remote: ApiClientSurface = new ApiClient(),
  local: ApiClientSurface = new BrowserApiClient(),
): ApiClientSurface {
  let selected: ApiClientSurface | null = null;
  let selection: Promise<ApiClientSurface> | null = null;

  const resolveClient = (): Promise<ApiClientSurface> => {
    if (selected !== null) return Promise.resolve(selected);
    selection ??= backendAvailable(remote).then((available) => {
      selected = available ? remote : local;
      return selected;
    });
    return selection;
  };

  return new Proxy({} as ApiClientSurface, {
    get(_target, property) {
      if (property === "subscribeJob") {
        if (selected === null || selected.subscribeJob === undefined) return undefined;
        return selected.subscribeJob.bind(selected);
      }
      if (property === "artifactUrl") {
        return (...args: unknown[]) => {
          if (selected === null) {
            throw new Error("The geometry execution mode has not been selected yet");
          }
          return Reflect.apply(selected.artifactUrl, selected, args);
        };
      }
      return (...args: unknown[]) => resolveClient().then((client) => {
        const member = Reflect.get(client, property);
        if (typeof member !== "function") return member;
        return Reflect.apply(member, client, args);
      });
    },
  });
}

export const apiClient = createAdaptiveApiClient();
