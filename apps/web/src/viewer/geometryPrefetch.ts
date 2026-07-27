import type { ViewerMode } from "../state/types";

/**
 * The `.glb` artifact each single-layer display mode draws. Kept here — free of
 * three.js and drei — so the restore path can decide what geometry to warm
 * without pulling in the viewer chunk, and so `CadViewport` and the prefetch
 * cannot drift apart on which artifact a mode reads.
 */
export const MODE_GEOMETRY: Partial<Record<ViewerMode, string>> = {
  source: "source.glb",
  repaired: "repaired.glb",
  patches: "patches.glb",
  reconstructed: "reconstructed.glb",
  residual: "residual.glb",
  analysis: "analysis-proxy.glb",
};

/** Overlay is the one mode that draws two layers at once. */
export const OVERLAY_GEOMETRY = ["source.glb", "reconstructed.glb"] as const;

export function geometryNamesForMode(mode: ViewerMode): readonly string[] {
  return mode === "overlay" ? OVERLAY_GEOMETRY : [MODE_GEOMETRY[mode] ?? ""].filter((name) => name !== "");
}

/**
 * The order the viewer falls back through when the preferred mode has no
 * artifact to draw. Shared so a prefetch cannot warm geometry for a mode the
 * viewer is about to move off.
 */
export const VIEWER_MODE_FALLBACK_ORDER: readonly ViewerMode[] = [
  "source",
  "reconstructed",
  "patches",
  "repaired",
  "analysis",
  "residual",
];

/**
 * The geometry the viewer will actually draw for `mode`, given what exists —
 * following the same fallback the viewport applies when the preferred mode has
 * nothing to show.
 */
export function geometryToWarm(mode: ViewerMode, available: ReadonlySet<string>): string[] {
  const preferred = geometryNamesForMode(mode).filter((name) => available.has(name));
  if (mode === "overlay" ? preferred.length === OVERLAY_GEOMETRY.length : preferred.length > 0) {
    return [...preferred];
  }
  const fallback = VIEWER_MODE_FALLBACK_ORDER
    .find((candidate) => geometryNamesForMode(candidate).every((name) => available.has(name)));
  return fallback === undefined ? [] : [...geometryNamesForMode(fallback)];
}

/**
 * Warms the browser's HTTP cache with geometry the viewer is about to draw.
 *
 * Nothing requests a `.glb` until `ArtifactLayer` renders inside the r3f canvas,
 * which cannot happen until the viewer chunk — over a megabyte of three.js — has
 * been downloaded and parsed and React has mounted. That leaves the network idle
 * during the exact stretch where the geometry could have been arriving, so the
 * download only starts once everything else is done.
 *
 * Artifact URLs are SHA-256 addressed and served `immutable` for a year, so a
 * plain GET here is reused by the loader rather than repeated. The request is
 * deliberately header-free: `useGLTF` fetches without the API authorization
 * header, and a prefetch that did not match it would not be reused.
 */
export function prefetchGeometry(urls: Iterable<string>): void {
  for (const url of urls) {
    // Failures are not worth reporting: this is an optimisation, and the loader
    // will make the same request again (and surface any real error) shortly.
    void fetch(url, { credentials: "same-origin" }).catch(() => undefined);
  }
}
