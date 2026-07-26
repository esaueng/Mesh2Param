/**
 * Times the scene build that ArtifactLayer performs for each display state:
 * cloning the parsed GLTF, recomputing creased normals, creating display
 * materials, and generating edge overlays.
 *
 * This is instrumented rather than assumed because the cost has been guessed at
 * wrongly more than once. It is the obvious suspect whenever the viewer stalls,
 * and it is not the cause: on the bundled sample the whole build runs in single
 * digit milliseconds, while the long tasks around it come from the WebGL path.
 * See docs/viewer-performance.md. The measurement gives the E2E suite something
 * GPU-independent to assert on, so a future change that does make this build
 * expensive fails loudly instead of hiding behind driver noise.
 */
export const SCENE_BUILD_MEASURE = "mesh2param:artifact-build";

export function profileSceneBuild<T>(build: () => T): T {
  const start = performance.now();
  try {
    return build();
  } finally {
    performance.measure(SCENE_BUILD_MEASURE, { start, end: performance.now() });
  }
}
