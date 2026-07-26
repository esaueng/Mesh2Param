# Viewer performance: what the long tasks during a reveal actually are

An end-to-end testing report (2026-07-25) recorded two main-thread long tasks of
523 ms and 549 ms during the first browser-local sample load, and suggested they
came from "lazy workspace/Three.js parsing, GLB materialization, or initial WebGL
setup". Two follow-up changes independently guessed at `ArtifactLayer`'s scene
build as the cause. This note records what the measurements show, so the same
ground is not re-covered a fourth time.

## The scene build is not the cause

`ArtifactLayer` rebuilds a display scene for each display state: it clones the
parsed GLTF, optionally recomputes creased normals, creates display materials,
and generates fat-line edge overlays. Instrumented on the bundled L-bracket
sample (1,044 triangles):

| phase | duration |
| --- | ---: |
| `gltf.scene.clone(true)` | <1 ms |
| triangle count | <1 ms |
| traverse: creased normals + materials | 2 ms |
| edge overlays (creases) | 3–4 ms |
| bounds `Box3.setFromObject` | <1 ms |

Around 5 ms in total, against long tasks of 400–1,000 ms. Three orders of
magnitude apart. Lazy chunk loading is not the cause either: the workspace chunk
parses in about 50 ms and finishes several hundred milliseconds before the long
tasks begin.

Dense meshes are already handled separately — `MAX_TRIANGLE_EDGE_OVERLAY` skips
the overlay above 20,000 triangles, which is the part that would otherwise scale
badly.

## The long tasks are the WebGL path, and mostly the software rasterizer

Same page, same flow, only the GL backend changed:

| backend | long tasks ≥500 ms, 3 cold passes |
| --- | --- |
| SwiftShader (headless default) | 840 ms; 694 ms; 603–1,037 ms — every pass |
| Apple M5 Pro via ANGLE/Metal | none; none; 503 ms once |

Headless Chromium renders through SwiftShader, a CPU rasterizer, so shader
compilation and the first frames are charged to the main thread. On real
hardware the same work is mostly absent. The report's Chromium session, and the
project's Playwright suite, both run on SwiftShader by default — which is why
this looks worse under test than it is in a browser with a GPU.

To reproduce the hardware measurement locally:

```bash
pnpm --filter @mesh2param/web exec playwright test --config playwright.cloudflare.config.ts
```

with `launchOptions.args` set to `["--enable-gpu", "--use-angle=metal", "--ignore-gpu-blocklist"]`.

## Why there is no shader-precompilation fix

The usual mitigation for a blocking first-frame compile is
`WebGLRenderer.compileAsync`, which relies on `KHR_parallel_shader_compile` to
compile off the main thread. SwiftShader does not expose that extension, so
under headless test the call degrades to the same synchronous compile and only
delays the reveal. On hardware, where the extension exists, there is little left
to recover. Gating the reveal on a compile that cannot run in parallel would
make the tested configuration slower, not faster.

## What the reveal does about it

The compile cost cannot be removed, but the viewer no longer presents an empty
canvas while it happens. `CadViewport` holds the reveal behind a stated
"Preparing the 3D preview…" state until react-three-fiber has actually drawn a
frame containing the artifact — the second `useFrame` callback, since callbacks
run before the frame they belong to is rendered.

Two details matter:

- Only the **first** paint of a project is held. A display-mode or shading
  change leaves the previous frame on the canvas, and covering that with a
  placeholder would replace useful context with less.
- The overlay is committed immediately but fades in on a 140 ms CSS animation
  delay. A cheap redraw removes it before it is ever visible, and because the
  fade is a compositor animation it still plays while the main thread is blocked
  compiling — which is precisely when it needs to appear.

A failsafe timer clears the hold regardless after 6 s, so a paused or dropped
render loop cannot strand the viewport behind the overlay.

## What is guarded

`tests/browser/viewer-scene-build.spec.ts` asserts the scene build stays under
100 ms across display states and for an analyzed source mesh, reading the
`mesh2param:artifact-build` measure emitted by `viewer/buildProfile.ts`. That
number is pure CPU work and therefore GPU-independent, which makes it a stable
thing to assert on — unlike long tasks, which mostly measure the driver.

`tests/browser/viewer-reveal.spec.ts` asserts the hold happens on a first reveal
and never on a later redraw, reading `data-viewer-preparing` through a
MutationObserver. Polling would not survive the stall; the observer's records
are queued and delivered once the main thread frees.
