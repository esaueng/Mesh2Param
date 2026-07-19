# Browser-local parametric STEP reconstruction

Mesh2Param can reconstruct the proven general-parametric spanner family on a Cloudflare static
deployment without a Python service. Cloudflare serves the application; the user's browser performs
all geometry processing in a dedicated module Web Worker backed by OCCT-WASM. Source bytes and
generated artifacts are stored in that browser profile and are not posted to Cloudflare or another
geometry service.

## Supported feature funnel

The browser accepts a mesh only when measured evidence supports this ordered feature sequence:

1. one watertight, consistently wound STL in explicit project units;
2. one constant-axis prismatic member with a bounded outer profile;
3. two straight profile spans, one broad circular arc, and one cubic B-spline with four to eight
   control points;
4. one regular six-sided through-cut;
5. optionally, paired top/bottom outer-rim fillets with a measured radius;
6. optionally, one cap-attached shallow rectangular boss.

The sharp, filleted, and filleted-plus-embossed fixtures under
`samples/general-parametric-benchmark/` are executable acceptance fixtures. This is not a claim that
arbitrary STL design history can be recovered.

Functional mode suppresses a detected shallow boss, validates against the functional reference
volume, and emits `suppressed-regions.json` plus a `residual.glb` containing the omitted source
triangles. Full mode adds the boss as an editable sketch and additive extrusion.

## Worker pipeline

The input scale factor is applied exactly once while the STL is promoted to double-precision
coordinates. Area-weighted face normals determine the extrusion axis. Thirty-two deterministic
interior sections establish cap offsets, loop count, taper/blind-feature evidence, and an optional
fillet-radius model. The profile fitter uses SVD least squares and bounded parameter refinement for
the cubic B-spline; it refuses residuals outside the configured project tolerance.

The CADGraph compiler maps every supported entity to native OCCT curves and wires. It records
deterministically sorted semantic edge descriptors after each feature, resolves the extrusion rim
edge identifiers before applying the fillet, and validates one positive-volume solid after every
feature. No triangle-per-face fallback participates in this path.

Every accepted candidate is tessellated and compared in both directions with deterministic
area-weighted samples and BVH nearest-point queries. Acceptance requires p95 surface distance at or
below the requested tolerance, at least 95% sampled surface coverage within tolerance, and relative
volume difference no greater than 0.1%. The final B-Rep must export to STEP, reimport as one valid
solid, and retain analytic torus evidence whenever a fillet was accepted.

## Runtime and deployment

The current OCCT build is single-threaded. `Cross-Origin-Opener-Policy` and
`Cross-Origin-Embedder-Policy` are already emitted so a separately measured pthread build can be
evaluated later without changing the isolation contract. Geometry requests are serialized inside
one reusable worker; cancellation terminates that worker and creates a clean instance on the next
request.

Run the Cloudflare delivery gate with:

```sh
pnpm cf:check
```

This builds the frontend, enforces the 25 MiB static-asset ceiling, refreshes Wrangler types,
typechecks the Cloudflare entrypoint, and performs a dry-run deployment. `pnpm cf:test` exercises the
deployed static headers, worker-only Embind CSP exception, OCCT initialization, IndexedDB reload,
and artifact rendering.

After one online use, the production service worker caches the app shell and fetched hashed assets,
including the geometry worker and WASM, for later offline sessions. Clearing the origin's site data
removes cached runtime files, IndexedDB projects, source meshes, and generated artifacts.
