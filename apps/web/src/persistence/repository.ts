import { contentSha256 } from "@mesh2param/contracts";

import type {
  HistoryState,
  Mesh2ParamProjectFile,
  PersistedProjectUI,
  ProjectSummary,
  ProjectVersionSnapshot,
  ProjectWorkingDocument,
  SyncStateName,
} from "../state/types";
import {
  Mesh2ParamWorkspaceDB,
  blobKey,
  workspaceDb,
  type BlobRecord,
  type DocumentRecord,
  type OutboxRecord,
  type ProjectRecord,
  type UIRecord,
  type VersionRecord,
} from "./db";
import {
  createProjectFile,
  openProjectFile,
  parseProjectFile,
  projectFileSourceFromBlob,
  readBlobBytes,
  serializeProjectFile,
  sha256Hex,
  type ParsedProjectFile,
} from "./projectFile";

export const AUTOSAVE_DELAY_MS = 300;

export interface WorkspaceSnapshot {
  project: ProjectSummary;
  working: ProjectWorkingDocument;
  localRevision: number;
  serverRevision: number | string | null;
  lastAckedLocalRevision: number;
  baseVersionId: string | null;
  syncState: SyncStateName;
  ui: PersistedProjectUI;
  history: HistoryState;
  queueOutbox?: boolean;
}

export interface StoredWorkspace {
  project: ProjectRecord;
  document: DocumentRecord;
  versions: ProjectVersionSnapshot[];
  ui: UIRecord | null;
  history: HistoryState;
  outbox: OutboxRecord | null;
}

export interface ExportProjectFileOptions {
  maximumEmbeddedBytes?: number;
}

interface PendingAutosave {
  snapshot: WorkspaceSnapshot;
  resolve: () => void;
  reject: (error: unknown) => void;
}

function projectSummary(record: ProjectRecord): ProjectSummary {
  return {
    id: record.id,
    name: record.name,
    units: record.units,
    schemaVersion: record.schemaVersion,
    revision: record.revision,
    basedOnVersionId: record.basedOnVersionId,
    createdAt: record.createdAt,
    updatedAt: record.updatedAt,
  };
}

export class WorkspaceRepository {
  private pendingAutosaves: PendingAutosave[] = [];
  private autosaveTimer: ReturnType<typeof setTimeout> | null = null;
  private flushing: Promise<void> | null = null;
  private visibilityDocument: Document | null = null;

  constructor(readonly db: Mesh2ParamWorkspaceDB = workspaceDb) {}

  async saveWorkspace(snapshot: WorkspaceSnapshot): Promise<void> {
    const now = new Date().toISOString();
    const contentHash = await contentSha256(snapshot.working);
    const project: ProjectRecord = {
      ...snapshot.project,
      lastOpenedAt: now,
      activeVersionId: snapshot.working.currentVersionId,
      syncState: snapshot.syncState,
    };
    const document: DocumentRecord = {
      projectId: snapshot.project.id,
      document: structuredClone(snapshot.working),
      updatedAt: now,
      baseVersionId: snapshot.baseVersionId,
      localRevision: snapshot.localRevision,
      serverRevision: snapshot.serverRevision,
      lastAckedLocalRevision: snapshot.lastAckedLocalRevision,
      contentHash,
    };
    const ui: UIRecord = {
      projectId: snapshot.project.id,
      updatedAt: now,
      state: structuredClone(snapshot.ui),
      cameraPose: snapshot.ui.cameraPose,
    };
    await this.db.transaction(
      "rw",
      [this.db.projects, this.db.documents, this.db.ui, this.db.history, this.db.outbox],
      async () => {
        await Promise.all([
          this.db.projects.put(project),
          this.db.documents.put(document),
          this.db.ui.put(ui),
          this.db.history.put({ projectId: project.id, updatedAt: now, state: structuredClone(snapshot.history) }),
        ]);
        if (snapshot.queueOutbox !== false && snapshot.localRevision > snapshot.lastAckedLocalRevision) {
          await this.db.outbox.where("projectId").equals(project.id).delete();
          await this.db.outbox.add({
            projectId: project.id,
            createdAt: now,
            localRevision: snapshot.localRevision,
            expectedServerRevision: snapshot.serverRevision,
            contentHash,
            document: structuredClone(snapshot.working),
          });
        } else if (snapshot.localRevision <= snapshot.lastAckedLocalRevision) {
          await this.db.outbox.where("projectId").equals(project.id).delete();
        }
      },
    );
  }

  scheduleAutosave(snapshot: WorkspaceSnapshot): Promise<void> {
    const promise = new Promise<void>((resolve, reject) => {
      this.pendingAutosaves.push({ snapshot, resolve, reject });
    });
    if (this.autosaveTimer !== null) clearTimeout(this.autosaveTimer);
    this.autosaveTimer = setTimeout(() => void this.flushAutosave(), AUTOSAVE_DELAY_MS);
    return promise;
  }

  async flushAutosave(): Promise<void> {
    if (this.autosaveTimer !== null) {
      clearTimeout(this.autosaveTimer);
      this.autosaveTimer = null;
    }
    if (this.flushing !== null) {
      await this.flushing;
      if (this.pendingAutosaves.length > 0) await this.flushAutosave();
      return;
    }
    if (this.pendingAutosaves.length === 0) return;
    const pending = this.pendingAutosaves.splice(0);
    const newestByProject = new Map<string, PendingAutosave>();
    for (const item of pending) newestByProject.set(item.snapshot.project.id, item);
    this.flushing = (async () => {
      try {
        await Promise.all([...newestByProject.values()].map((item) => this.saveWorkspace(item.snapshot)));
        for (const item of pending) item.resolve();
      } catch (error) {
        for (const item of pending) item.reject(error);
        throw error;
      } finally {
        this.flushing = null;
      }
    })();
    await this.flushing;
  }

  attachVisibilityFlush(documentRef: Document = document): () => void {
    this.detachVisibilityFlush();
    this.visibilityDocument = documentRef;
    documentRef.addEventListener("visibilitychange", this.onVisibilityChange);
    return () => this.detachVisibilityFlush();
  }

  private readonly onVisibilityChange = (): void => {
    if (this.visibilityDocument?.visibilityState === "hidden") void this.flushAutosave();
  };

  detachVisibilityFlush(): void {
    this.visibilityDocument?.removeEventListener("visibilitychange", this.onVisibilityChange);
    this.visibilityDocument = null;
  }

  async getWorkspace(projectId: string): Promise<StoredWorkspace | null> {
    const [project, document, versions, ui, history, outbox] = await Promise.all([
      this.db.projects.get(projectId),
      this.db.documents.get(projectId),
      this.db.versions.where("projectId").equals(projectId).sortBy("createdAt"),
      this.db.ui.get(projectId),
      this.db.history.get(projectId),
      this.db.outbox.where("projectId").equals(projectId).last(),
    ]);
    if (project === undefined || document === undefined) return null;
    return {
      project,
      document,
      versions: versions.map((item) => item.snapshot),
      ui: ui ?? null,
      history: history?.state ?? { past: [], future: [] },
      outbox: outbox ?? null,
    };
  }

  async listRecentProjects(limit = 10): Promise<ProjectRecord[]> {
    if (!Number.isSafeInteger(limit) || limit < 1) throw new TypeError("recent project limit must be positive");
    return this.db.projects.orderBy("lastOpenedAt").reverse().limit(limit).toArray();
  }

  async touchProject(projectId: string): Promise<void> {
    await this.db.projects.update(projectId, { lastOpenedAt: new Date().toISOString() });
  }

  async putBlob(record: Omit<BlobRecord, "key" | "createdAt"> & { key?: string }): Promise<string> {
    const key = record.key ?? blobKey(record.kind, record.sha256);
    if (record.blob.size !== record.byteSize) throw new TypeError("Blob size does not match descriptor");
    if (await sha256Hex(await readBlobBytes(record.blob)) !== record.sha256) {
      throw new TypeError("Blob content does not match its SHA-256 descriptor");
    }
    await this.db.blobs.put({ ...record, key, createdAt: new Date().toISOString() });
    return key;
  }

  getBlob(key: string): Promise<BlobRecord | undefined> {
    return this.db.blobs.get(key);
  }

  async putVersions(versions: ProjectVersionSnapshot[]): Promise<void> {
    const records: VersionRecord[] = versions.map((snapshot) => ({
      projectId: snapshot.projectId,
      versionId: snapshot.id,
      parentVersionId: snapshot.parentId,
      createdAt: snapshot.createdAt,
      snapshot: structuredClone(snapshot),
    }));
    if (records.length > 0) await this.db.versions.bulkPut(records);
  }

  async deleteProject(projectId: string): Promise<void> {
    await this.db.transaction(
      "rw",
      [
        this.db.projects,
        this.db.documents,
        this.db.versions,
        this.db.blobs,
        this.db.ui,
        this.db.history,
        this.db.outbox,
      ],
      async () => {
        await Promise.all([
          this.db.projects.delete(projectId),
          this.db.documents.delete(projectId),
          this.db.versions.where("projectId").equals(projectId).delete(),
          this.db.blobs.where("projectId").equals(projectId).delete(),
          this.db.ui.delete(projectId),
          this.db.history.delete(projectId),
          this.db.outbox.where("projectId").equals(projectId).delete(),
        ]);
      },
    );
  }

  async importProjectFile(text: string): Promise<ParsedProjectFile> {
    return this.importParsedProjectFile(await parseProjectFile(text));
  }

  async importProjectFileBlob(file: Blob & { name?: string }): Promise<ParsedProjectFile> {
    return this.importParsedProjectFile(await openProjectFile(file));
  }

  async importParsedProjectFile(parsed: ParsedProjectFile): Promise<ParsedProjectFile> {
    const now = new Date().toISOString();
    // Project files carry an artifact manifest, not the artifact bytes. Do not
    // hydrate stale descriptors into the active viewer; the browser client can
    // deterministically regenerate a preview from the embedded source/CADGraph.
    const working = structuredClone(parsed.file.working);
    working.artifacts = [];
    working.artifactSetId = null;
    const contentHash = await contentSha256(working);
    const project: ProjectRecord = {
      ...parsed.file.project,
      lastOpenedAt: now,
      activeVersionId: working.currentVersionId,
      syncState: "clean",
    };
    const document: DocumentRecord = {
      projectId: project.id,
      document: working,
      updatedAt: now,
      baseVersionId: project.basedOnVersionId,
      localRevision: 0,
      serverRevision: project.revision,
      lastAckedLocalRevision: 0,
      contentHash,
    };
    const versions: VersionRecord[] = parsed.file.versions.map((snapshot) => ({
      projectId: snapshot.projectId,
      versionId: snapshot.id,
      parentVersionId: snapshot.parentId,
      createdAt: snapshot.createdAt,
      snapshot: structuredClone(snapshot),
    }));
    const ui: UIRecord = {
      projectId: project.id,
      updatedAt: now,
      state: structuredClone(parsed.file.ui),
      cameraPose: parsed.file.ui.cameraPose,
    };
    await this.db.transaction(
      "rw",
      [
        this.db.projects,
        this.db.documents,
        this.db.versions,
        this.db.blobs,
        this.db.ui,
        this.db.history,
        this.db.outbox,
      ],
      async () => {
        await this.db.projects.put(project);
        await this.db.documents.put(document);
        await this.db.ui.put(ui);
        await this.db.versions.where("projectId").equals(project.id).delete();
        if (versions.length > 0) await this.db.versions.bulkPut(versions);
        if (parsed.embeddedSource !== null) {
          await this.db.blobs.put({
            ...parsed.embeddedSource,
            projectId: project.id,
            kind: "source",
            createdAt: now,
          });
        }
        await this.db.history.put({ projectId: project.id, updatedAt: now, state: { past: [], future: [] } });
        await this.db.outbox.where("projectId").equals(project.id).delete();
      },
    );
    return { ...parsed, file: { ...parsed.file, working } };
  }

  async exportProjectFile(
    projectId: string,
    options: ExportProjectFileOptions = {},
  ): Promise<Mesh2ParamProjectFile> {
    const stored = await this.getWorkspace(projectId);
    if (stored === null) throw new Error(`Local project ${projectId} was not found`);
    const sourceDescriptor = stored.document.document.source;
    let source: Mesh2ParamProjectFile["source"] = null;
    if (sourceDescriptor !== null) {
      const key = blobKey("source", sourceDescriptor.sha256);
      const sourceBlob = await this.db.blobs.get(key);
      source = sourceBlob === undefined
        ? {
            kind: "local-reference",
            blobKey: key,
            sha256: sourceDescriptor.sha256,
            byteSize: sourceDescriptor.byteSize,
            mediaType: `model/${sourceDescriptor.format}`,
            originalFileName: sourceDescriptor.originalFileName,
          }
        : await projectFileSourceFromBlob(
            {
              sha256: sourceBlob.sha256,
              byteSize: sourceBlob.byteSize,
              mediaType: sourceBlob.mediaType,
              originalFileName: sourceBlob.originalFileName ?? sourceDescriptor.originalFileName,
              blob: sourceBlob.blob,
            },
            options.maximumEmbeddedBytes,
          );
    }
    return createProjectFile({
      project: projectSummary(stored.project),
      working: structuredClone(stored.document.document),
      ui: structuredClone(stored.ui?.state ?? defaultPersistedProjectUI()),
      versions: stored.versions.map((version) => structuredClone(version)),
      source,
      artifactManifest: structuredClone(stored.document.document.artifacts),
    });
  }

  async serializeProject(projectId: string, options: ExportProjectFileOptions = {}): Promise<string> {
    return serializeProjectFile(await this.exportProjectFile(projectId, options));
  }

  async close(): Promise<void> {
    this.detachVisibilityFlush();
    await this.flushAutosave();
    this.db.close();
  }
}

function defaultPersistedProjectUI(): PersistedProjectUI {
  return {
    activeStep: "import",
    selection: {
      patchId: null,
      featureId: null,
      sketchEntityId: null,
      hoverId: null,
    },
    viewer: {
      mode: "source",
      visible: {
        source: true,
        repaired: false,
        analysis: false,
        patches: false,
        reconstructed: false,
        residual: false,
      },
      sourceOpacity: 1,
      resultOpacity: 1,
      projection: "perspective",
      shading: "shaded",
      edges: true,
    },
    shell: {
      theme: "dark",
      railCollapsed: false,
      inspectorExpanded: true,
      bottomDrawerExpanded: false,
      bottomDrawerHeight: 220,
      singleKeyShortcuts: true,
    },
    cameraPose: null,
  };
}

export const workspaceRepository = new WorkspaceRepository();
