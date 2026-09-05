import { afterEach, expect, it, vi } from "vitest";
import { GLTFLoader } from "three-stdlib";
import { setApiToken } from "../api/auth";
import { authenticateGltfLoader } from "./gltfAuth";
import { prefetchGeometry } from "./geometryPrefetch";

afterEach(() => { setApiToken(null); vi.unstubAllGlobals(); });

it("authenticates both the real GLTF loader request and its prefetch", async () => {
  setApiToken("test-token");
  const fetcher = vi.fn().mockResolvedValue(new Response("missing", { status: 404 }));
  vi.stubGlobal("fetch", fetcher);
  const url = new URL("/api/projects/p/artifacts/source.glb", window.location.href).href;
  const loader = new GLTFLoader();
  authenticateGltfLoader(loader, url);
  await expect(loader.loadAsync(url)).rejects.toThrow();
  const request = fetcher.mock.calls[0]![0] as Request;
  expect(request.headers.get("Authorization")).toBe("Bearer test-token");
  prefetchGeometry([url]);
  expect(fetcher.mock.calls[1]![1]).toMatchObject({ headers: { Authorization: "Bearer test-token" } });
});

it("clears reused loader credentials for public, blob, and foreign URLs", () => {
  setApiToken("test-token");
  const loader = new GLTFLoader();
  for (const target of ["/samples/model.glb", "blob:http://localhost/model", "https://elsewhere.invalid/api/model.glb"]) {
    authenticateGltfLoader(loader, "/api/projects/p/artifacts/source.glb");
    expect(loader.requestHeader).toEqual({ Authorization: "Bearer test-token" });
    authenticateGltfLoader(loader, target);
    expect(loader.requestHeader).toEqual({});
  }
});
