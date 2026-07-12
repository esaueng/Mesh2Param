import type { CADGraph } from "@mesh2param/contracts";

import type { JsonObject, SampleDescriptor } from "../state/types";

const ASSET_URLS = import.meta.glob("../../../../samples/generated/*/*", {
  eager: true,
  import: "default",
  query: "?url",
}) as Record<string, string>;

const SAMPLE_PATH = /\/samples\/generated\/([^/]+)\/([^/]+)$/;
const urlsBySample = new Map<string, Map<string, string>>();

for (const [path, url] of Object.entries(ASSET_URLS)) {
  const match = SAMPLE_PATH.exec(path);
  if (match === null) continue;
  const [, slug, name] = match;
  if (slug === undefined || name === undefined) continue;
  const files = urlsBySample.get(slug) ?? new Map<string, string>();
  files.set(name, url);
  urlsBySample.set(slug, files);
}

export interface BrowserSample {
  descriptor: SampleDescriptor;
  graph: CADGraph;
  metadata: JsonObject;
}

function assetUrl(slug: string, name: string): string {
  const value = urlsBySample.get(slug)?.get(name);
  if (value === undefined) throw new Error(`Bundled sample ${slug}/${name} is unavailable`);
  return value;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Bundled sample request failed (${response.status})`);
  return response.json() as Promise<T>;
}

function operationLabel(value: string): string {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (character) => character.toUpperCase());
}

export async function loadBrowserSample(slug: string): Promise<BrowserSample> {
  if (!urlsBySample.has(slug)) throw new Error(`No bundled sample has the identifier ${slug}`);
  const [metadata, graph] = await Promise.all([
    fetchJson<JsonObject>(assetUrl(slug, "metadata.json")),
    fetchJson<CADGraph>(assetUrl(slug, "model.cadgraph.json")),
  ]);
  const actual = metadata.actual as JsonObject | undefined;
  const expected = metadata.expected as JsonObject | undefined;
  const meshes = metadata.meshes as JsonObject | undefined;
  const high = meshes?.high as JsonObject | undefined;
  const operations = [...new Set(graph.features.map((feature) => feature.operation))];
  return {
    descriptor: {
      id: slug,
      name: typeof metadata.name === "string" ? metadata.name : graph.name,
      seed: typeof metadata.seed === "number" ? metadata.seed : graph.deterministicSeed,
      expectedBoundingBox: Array.isArray(expected?.bbox) ? expected.bbox.filter((item): item is number => typeof item === "number") : [],
      expectedVolume: typeof expected?.volume === "number" ? expected.volume : 0,
      expectedPlanarFaces: typeof expected?.planarFaceCount === "number" ? expected.planarFaceCount : 0,
      expectedCylindricalFaces: typeof expected?.cylindricalFaceCount === "number" ? expected.cylindricalFaceCount : 0,
      automaticReconstructionSupported: slug === "l-bracket-with-holes",
      triangleCount: typeof high?.triangleCount === "number" ? high.triangleCount : 0,
      intendedOperations: operations.map(operationLabel),
      toleranceMm: graph.projectTolerance.surfaceDeviation,
      thumbnailUrl: assetUrl(slug, "thumbnail.svg"),
    },
    graph,
    metadata: {
      ...metadata,
      ...(actual === undefined ? {} : { actual }),
    },
  };
}

export async function listBrowserSamples(): Promise<BrowserSample[]> {
  return Promise.all([...urlsBySample.keys()].sort().map(loadBrowserSample));
}

export function browserSampleAssetUrl(slug: string, name: string): string {
  return assetUrl(slug, name);
}

export function browserSampleAssetNames(slug: string): string[] {
  return [...(urlsBySample.get(slug)?.keys() ?? [])].sort();
}
