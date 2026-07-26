import { useGLTF } from "@react-three/drei";
import type { ArtifactDescriptor } from "../state/types";

/** Every artifact the viewer can hand to `useGLTF`, as its content-addressed URL. */
export function geometryArtifactUrls(
  artifacts: readonly ArtifactDescriptor[],
  toUrl: (name: string, sha256: string) => string,
): string[] {
  return artifacts
    .filter((artifact) => artifact.name.toLowerCase().endsWith(".glb"))
    .map((artifact) => toUrl(artifact.name, artifact.sha256));
}

/**
 * drei caches parsed GLTFs by URL, and Mesh2Param's artifact URLs are SHA-256
 * addressed: the bytes behind one can never change. An entry is therefore
 * valid for as long as the project owning it stays open, which is far longer
 * than the layer components that read it — those remount on every display
 * mode, opacity, shading, and theme change.
 *
 * Retention is tracked per project so that closing one project cannot evict
 * geometry another has already loaded, and so that superseded artifacts (a
 * replaced source mesh, a re-run reconstruction) are released as soon as they
 * leave the project's artifact list rather than at the end of the session.
 */
const retained = new Map<string, Set<string>>();

/**
 * Declares the full set of geometry URLs the project can display. URLs already
 * retained but absent from `urls` belong to superseded artifacts and are
 * dropped from the cache.
 */
export function syncProjectGltfCache(projectId: string, urls: Iterable<string>): void {
  const next = new Set(urls);
  for (const url of retained.get(projectId) ?? []) {
    if (!next.has(url)) useGLTF.clear(url);
  }
  retained.set(projectId, next);
}

/** Drops every entry the project retained. Call when its viewport goes away. */
export function releaseProjectGltfCache(projectId: string): void {
  const urls = retained.get(projectId);
  if (urls === undefined) return;
  retained.delete(projectId);
  for (const url of urls) useGLTF.clear(url);
}

export function retainedGltfUrls(projectId: string): string[] {
  return [...(retained.get(projectId) ?? [])];
}
