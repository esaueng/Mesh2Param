import { useGLTF } from "@react-three/drei";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactDescriptor } from "../state/types";
import {
  geometryArtifactUrls,
  releaseProjectGltfCache,
  retainedGltfUrls,
  syncProjectGltfCache,
} from "./gltfCache";

vi.mock("@react-three/drei", () => ({ useGLTF: { clear: vi.fn() } }));

const clear = vi.mocked(useGLTF.clear);

function artifact(name: string, sha256: string): ArtifactDescriptor {
  return {
    id: `artifact-${name}-${sha256}`,
    name,
    kind: "geometry",
    sha256,
    byteSize: 1_024,
    mediaType: "model/gltf-binary",
    createdAt: "2026-07-25T00:00:00.000Z",
  };
}

// Retention is module-global, so each test uses its own project id.
let projectCounter = 0;
function nextProject(): string {
  projectCounter += 1;
  return `project-${projectCounter}`;
}

beforeEach(() => { clear.mockClear(); });

describe("geometryArtifactUrls", () => {
  it("maps only the GLB artifacts to content-addressed URLs", () => {
    const urls = geometryArtifactUrls(
      [artifact("source.glb", "aaa"), artifact("model.step", "bbb"), artifact("reconstructed.GLB", "ccc")],
      (name, sha256) => `/artifacts/${name}?sha256=${sha256}`,
    );

    expect(urls).toEqual(["/artifacts/source.glb?sha256=aaa", "/artifacts/reconstructed.GLB?sha256=ccc"]);
  });
});

describe("syncProjectGltfCache", () => {
  it("retains the project's geometry without clearing anything", () => {
    const project = nextProject();

    syncProjectGltfCache(project, ["/a.glb", "/b.glb"]);

    expect(retainedGltfUrls(project)).toEqual(["/a.glb", "/b.glb"]);
    expect(clear).not.toHaveBeenCalled();
  });

  it("keeps entries across repeated syncs of the same artifacts", () => {
    const project = nextProject();
    syncProjectGltfCache(project, ["/a.glb", "/b.glb"]);

    syncProjectGltfCache(project, ["/a.glb", "/b.glb"]);

    expect(clear).not.toHaveBeenCalled();
  });

  it("clears geometry that a replaced artifact superseded", () => {
    const project = nextProject();
    syncProjectGltfCache(project, ["/source.glb?sha256=old", "/reconstructed.glb?sha256=keep"]);

    syncProjectGltfCache(project, ["/source.glb?sha256=new", "/reconstructed.glb?sha256=keep"]);

    expect(clear).toHaveBeenCalledExactlyOnceWith("/source.glb?sha256=old");
    expect(retainedGltfUrls(project)).toEqual(["/source.glb?sha256=new", "/reconstructed.glb?sha256=keep"]);
  });

  it("leaves another project's geometry alone", () => {
    const first = nextProject();
    const second = nextProject();
    syncProjectGltfCache(first, ["/first.glb"]);

    syncProjectGltfCache(second, ["/second.glb"]);

    expect(clear).not.toHaveBeenCalled();
    expect(retainedGltfUrls(first)).toEqual(["/first.glb"]);
  });
});

describe("releaseProjectGltfCache", () => {
  it("clears everything the project retained", () => {
    const project = nextProject();
    syncProjectGltfCache(project, ["/a.glb", "/b.glb"]);

    releaseProjectGltfCache(project);

    expect(clear.mock.calls).toEqual([["/a.glb"], ["/b.glb"]]);
    expect(retainedGltfUrls(project)).toEqual([]);
  });

  it("leaves other projects untouched and is safe to repeat", () => {
    const kept = nextProject();
    const closed = nextProject();
    syncProjectGltfCache(kept, ["/kept.glb"]);
    syncProjectGltfCache(closed, ["/closed.glb"]);

    releaseProjectGltfCache(closed);
    releaseProjectGltfCache(closed);

    expect(clear.mock.calls).toEqual([["/closed.glb"]]);
    expect(retainedGltfUrls(kept)).toEqual(["/kept.glb"]);
  });
});
