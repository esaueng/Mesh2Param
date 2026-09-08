import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { defaultViewerPreferences } from "../state/store";
import type { ArtifactDescriptor } from "../state/types";
import { CadViewport } from "./CadViewport";

vi.mock("../api/client", () => ({ apiClient: { artifactUrl: vi.fn() } }));

vi.mock("@react-three/fiber", async (original) => ({
  ...await original<typeof import("@react-three/fiber")>(),
  Canvas: () => <div data-testid="canvas" />,
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("contains unavailable saved geometry and recovers when artifacts change", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.spyOn(apiClient, "artifactUrl").mockImplementation(() => {
    throw new Error("Saved artifact bytes are unavailable");
  });
  const artifact: ArtifactDescriptor = {
    name: "reconstructed.glb", sha256: "a".repeat(64), byteSize: 10,
    mediaType: "model/gltf-binary", kind: "reconstructed",
  };
  const props = {
    projectId: "project-test", units: "mm" as const, artifacts: [artifact],
    preferences: defaultViewerPreferences, theme: "dark" as const,
    selectedPatchId: null, onPreferences: vi.fn(), onSelectPatch: vi.fn(),
  };
  const view = render(<CadViewport {...props} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Saved artifact bytes are unavailable");
  view.rerender(<CadViewport {...props} artifacts={[]} />);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getAllByTestId("canvas").length).toBeGreaterThan(0);
});

it("keeps geometry usable when an optional selection map is unavailable", async () => {
  vi.mocked(apiClient.artifactUrl).mockImplementation(() => {
    throw new Error("Selection map bytes are unavailable");
  });
  render(<CadViewport
    projectId="project-test" units="mm" theme="dark"
    artifacts={[{ name: "selection-map.json", sha256: "b".repeat(64), byteSize: 10, mediaType: "application/json" }]}
    preferences={defaultViewerPreferences} selectedPatchId={null}
    onPreferences={vi.fn()} onSelectPatch={vi.fn()}
  />);
  await waitFor(() => expect(apiClient.artifactUrl).toHaveBeenCalled());
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getAllByTestId("canvas").length).toBeGreaterThan(0);
});
