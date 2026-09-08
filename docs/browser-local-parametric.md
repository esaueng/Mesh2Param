# Browser-local reconstruction

On a Cloudflare static deployment there is no Python service. Cloudflare serves the application;
the user's browser runs the whole conversion in a dedicated module Web Worker backed by
[`@mesh2param/core-wasm`](../packages/core-wasm/README.md) — the same Rust reconstruction core the
corpus scoreboard measures, compiled to WebAssembly. Source bytes and generated artifacts stay in
that browser profile; nothing is posted to Cloudflare or to a conversion service.

## What runs

The worker serves two operations. Both are synchronous inside the worker, which is why they run
there: a 70k-triangle part occupies the thread for the best part of a minute.

| Operation | What the core does | What the app gets |
| --- | --- | --- |
| `analyze` | Reads and welds the mesh, then reports statistics | Triangle and vertex counts, bounding box, watertight and edge-manifold flags, non-manifold edge count, dropped degenerate triangles |
| `reconstruct` | Segments the mesh, fits surfaces, builds and validates a solid, writes STEP | `model.step`, `reconstructed.glb`, and a measured evidence record |

`analyze` reports statistics, not geometry, so the worker also parses the STL itself to build the
viewer's source layer and to measure surface area and closed volume. Everything the core does not
measure — body count, winding consistency, boundary loops, duplicate faces — is recorded as `null`
and is not shown, rather than being re-derived in JavaScript.

## The tier ladder

The core runs one ladder and reports the tier it reached. It cannot be forced: the three
reconstruction modes the UI offers (automatic, curved, faceted) differ only in the tolerance and
triangle budget they request, and every one of them reports its measured tier back.

| Tier | Meaning |
| --- | --- |
| `analytic` | Every face is a recognised analytic surface — plane, cylinder, cone, torus or sphere |
| `mixed` | Some faces are analytic; the rest stay triangulated |
| `faceted` | No analytic surfaces survived; the STEP preserves the source facets |

The tier reaches the UI as the conversion status label and as the evidence line under the primary
command, together with the final face count, the surface inventory, the measured maximum deviation
from the source mesh, and the core's own reason for any fallback. None of it is a claim of recovered
design history: a reconstruction is a fit to the mesh that was opened.

A run also records whether the finished solid passed kernel validation (`brepValid`) and whether the
kernel's own reader read the STEP file back (`stepReimportValid`). The workspace shows a result as
validated only when both hold.

## What is not supported in the browser

- **Rebuilding a STEP file from a CADGraph.** The core converts mesh bytes; it does not replay a
  feature history. `validate`, `export` and `rebuild` on a project that carries a CADGraph fail with
  a structured `unsupported` error, surfaced as the normal error alert. The bundled sample projects
  are unaffected: their STEP, GLB and CADGraph artifacts are precomputed and shipped with the app.
- **Editing a recovered feature model.** Browser reconstructions produce a solid and a STEP file,
  not a CADGraph, so there is nothing to edit parametrically. Use the Mesh2Param service for that.
- **Meshes over the triangle budget** (200 000 by default). The core refuses them with a
  `BudgetError` rather than running for an unbounded time; the fix is a coarser export.

## Budgets and runtime

The WebAssembly module is 1.79 MB raw, 636 kB gzipped, and is fetched only when a browser-local
conversion starts — never on the first-paint path. The worker's own JavaScript is about 12 kB: the
message protocol plus `wasm-bindgen`'s glue. Both are gated by
[`scripts/check_bundle_budgets.mjs`](../scripts/check_bundle_budgets.mjs); the 25 MiB Cloudflare
per-asset ceiling is gated by [`scripts/check_cloudflare_assets.mjs`](../scripts/check_cloudflare_assets.mjs).

The build is single-threaded. `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` are
emitted so a separately measured threaded build can be evaluated later without changing the
isolation contract. `wasm-bindgen` needs only `'wasm-unsafe-eval'`, which the site-wide policy
already grants, so the worker no longer carries a `'unsafe-eval'` exception of its own. Geometry
requests are serialized inside one reusable worker; cancellation terminates it and the next request
creates a clean instance.

## Gates

```sh
pnpm cf:check   # build, 25 MiB asset ceiling, Wrangler types, entrypoint typecheck, dry-run deploy
pnpm cf:dev     # the same build, served by wrangler on 127.0.0.1:8787
pnpm cf:test    # Playwright against pnpm cf:dev
```

`pnpm cf:test` exercises the static headers, core initialization, an upload → analyze →
reconstruct → download STEP flow with its tier label, the CADGraph refusal, IndexedDB reload, and
artifact rendering.

After one online use the production service worker caches the app shell and fetched hashed assets,
including the geometry worker and the WebAssembly module, for later offline sessions. Clearing the
origin's site data removes cached runtime files, IndexedDB projects, source meshes, and generated
artifacts.
