import Dexie, { type Table } from "dexie";

import type {
  CameraPose,
  HistoryState,
  PersistedProjectUI,
  ProjectSummary,
  ProjectVersionSnapshot,
  ProjectWorkingDocument,
  SyncStateName,
} from "../state/types";

export const WORKSPACE_DB_NAME = "mesh2param-workspace";

export interface ProjectRecord extends ProjectSummary {
  lastOpenedAt: string;
  activeVersionId: string | null;
  syncState: SyncStateName;
}

export interface DocumentRecord {
  projectId: string;
  document: ProjectWorkingDocument;
  updatedAt: string;
  baseVersionId: string | null;
  localRevision: number;
  serverRevision: number | string | null;
  lastAckedLocalRevision: number;
  contentHash: string;
}

export interface VersionRecord {
  projectId: string;
  versionId: string;
  parentVersionId: string | null;
  createdAt: string;
  snapshot: ProjectVersionSnapshot;
}

export interface BlobRecord {
  key: string;
  projectId: string;
  kind: string;
  sha256: string;
  byteSize: number;
  mediaType: string;
  originalFileName: string | null;
  blob: Blob;
  createdAt: string;
}

export interface UIRecord {
  projectId: string;
  updatedAt: string;
  state: PersistedProjectUI;
  cameraPose: CameraPose | null;
}

export interface HistoryRecord {
  projectId: string;
  updatedAt: string;
  state: HistoryState;
}

export interface SettingRecord<T = unknown> {
  key: string;
  value: T;
  updatedAt: string;
}

export interface OutboxRecord {
  id?: number;
  projectId: string;
  createdAt: string;
  localRevision: number;
  expectedServerRevision: number | string | null;
  contentHash: string;
  document: ProjectWorkingDocument;
}

export class Mesh2ParamWorkspaceDB extends Dexie {
  projects!: Table<ProjectRecord, string>;
  documents!: Table<DocumentRecord, string>;
  versions!: Table<VersionRecord, [string, string]>;
  blobs!: Table<BlobRecord, string>;
  ui!: Table<UIRecord, string>;
  history!: Table<HistoryRecord, string>;
  settings!: Table<SettingRecord, string>;
  outbox!: Table<OutboxRecord, number>;

  constructor(name = WORKSPACE_DB_NAME) {
    super(name);
    this.version(1).stores({
      projects: "&id, updatedAt, lastOpenedAt, activeVersionId, syncState",
      documents: "&projectId, updatedAt, baseVersionId, localRevision, serverRevision",
      versions: "&[projectId+versionId], projectId, createdAt, parentVersionId",
      blobs: "&key, projectId, kind, sha256",
      ui: "&projectId, updatedAt",
      history: "&projectId, updatedAt",
      settings: "&key",
      outbox: "++id, projectId, createdAt, localRevision",
    });
  }
}

export const workspaceDb = new Mesh2ParamWorkspaceDB();

export function blobKey(kind: string, sha256: string): string {
  return `${kind}:${sha256}`;
}
