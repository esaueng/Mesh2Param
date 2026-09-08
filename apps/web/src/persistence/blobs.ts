import type { Mesh2ParamWorkspaceDB } from "./db";

/** Run inside the project-deletion transaction, before removing its documents. */
export async function deleteProjectBlobs(db: Mesh2ParamWorkspaceDB, projectId: string): Promise<void> {
  const [blobs, documents, versions, outbox, histories] = await Promise.all([
    db.blobs.where("projectId").equals(projectId).toArray(),
    db.documents.toArray(),
    db.versions.toArray(),
    db.outbox.toArray(),
    db.history.toArray(),
  ]);
  const owners = new Map<string, string>();
  for (const record of [...documents, ...outbox]) {
    const digest = record.document.source?.sha256;
    if (record.projectId !== projectId && digest !== undefined) owners.set(digest, record.projectId);
  }
  for (const record of versions) {
    const digest = record.snapshot.state.source?.sha256;
    if (record.projectId !== projectId && digest !== undefined) owners.set(digest, record.projectId);
  }
  for (const record of histories) {
    if (record.projectId === projectId) continue;
    for (const entry of [...record.state.past, ...record.state.future]) {
      for (const patch of [...entry.forwardPatches, ...entry.inversePatches]) {
        const value: unknown = patch.value;
        let digest: string | null = null;
        if (patch.path.length === 0 && typeof value === "object" && value !== null && "source" in value) {
          digest = sourceHash(value.source);
        } else if (patch.path.length === 1 && patch.path[0] === "source") {
          digest = sourceHash(value);
        } else if (patch.path.length === 2 && patch.path[0] === "source" && patch.path[1] === "sha256") {
          digest = typeof value === "string" ? value : null;
        }
        if (digest !== null) owners.set(digest, record.projectId);
      }
    }
  }
  for (const blob of blobs) {
    // Legacy and current source keys are shared across projects and saved files.
    const owner = blob.kind === "source" ? owners.get(blob.sha256) : undefined;
    if (owner === undefined) await db.blobs.delete(blob.key);
    else await db.blobs.put({ ...blob, projectId: owner });
  }
}

function sourceHash(value: unknown): string | null {
  return typeof value === "object" && value !== null && "sha256" in value && typeof value.sha256 === "string"
    ? value.sha256 : null;
}
