# Fallbacks and honest limitations

## Open3D

Open3D was not introduced because the verified Python 3.12 geometry environment already provides
CadQuery/OCP, trimesh, NumPy, and SciPy, and deterministic custom fitting covers the current bounded
scope. Mesh2Param therefore uses:

- trimesh adjacency, topology, parsing, and deterministic sampling;
- NumPy total-least-squares plane fitting and normal covariance;
- SciPy bounded least-squares circle/cylinder refinement;
- deterministic seeded surface comparison with exact point-to-triangle queries.

This fallback is not presented as equivalent to a general point-cloud or organic-surface pipeline.
Full cylinders require at least 300 degrees of angular evidence, plane/cylinder fits must satisfy
explicit residual thresholds, and unsupported remainder stays freeform. A future Open3D integration
may add scale-aware robust estimation only if it installs cleanly and preserves deterministic seeds,
license compatibility, evidence links, and the same failure semantics.

## Geometry kernel and reconstruction reference

CadQuery 2.8.0 and the `cadquery-ocp` 7.9.3.1.1 bindings install and execute in the locked Python
3.12 environment, so no approximate kernel substitute is used. The production image build also
requires an OCCT STEP export/reimport and `BRepCheck` smoke test. If that gate fails, the image is
rejected; Mesh2Param does not relabel a mesh-only export as an exact B-Rep.

The OpenCAE reference implementation was available for architectural comparison at the pinned
commit recorded in `NOTICE`. Mesh2Param is a clean implementation and does not require OpenCAE at
runtime. Where a feature is outside the bounded automatic inference scope, the supported fallback is
explicit diagnostics, manual CADGraph editing, or an identified faceted representation—not an
unattributed copy or an invented source history.

## Damaged and coarse meshes

The engine never silently fills large holes or smooths detail. Missing patch boundaries are retained
as open loops and stop automatic L-profile inference. Cylinder facets that exceed the 12 degree
smooth-region threshold may still be recovered when they form a sufficiently dense closed,
common-radius ring within the configured chordal-sagitta limit. Sparse polygons, open rings,
irregular radii, excessive sagitta, or inconsistent axes still fail instead of being rounded by
guesswork. Small-hole filling exists only as an explicit repair operation with a configured
edge-count and planarity limit.

## Prismatic analytic path and faceted distinction

Sewing STL triangles can close a shell, but it cannot recover the mathematical plane, circle, or
cylinder that existed before tessellation. Every sewn triangle remains a planar B-Rep face. For a
validated linear extrusion, Mesh2Param instead reconstructs the cap's ordered 2-D boundary as lines
and circular arcs and extrudes one analytic face. This supports one exterior loop plus contained
holes on an arbitrary sketch plane; line/arc profiles may include tangent transitions even when the
side wall was segmented as one smooth `freeform` region.

The path currently rejects tapered or twisted sweeps, inconsistent caps, branching/open boundaries,
splines, arbitrary freeform surfaces, multiple disjoint exterior profiles, and geometry outside its
residual and scale limits. Rejection does not relabel the hypothesis as analytic and does not block
other supported inference paths. If no analytic path succeeds, the explicit source-bound faceted
operation below remains available; it is never presented as recovered parametric history.

## Explicit faceted STEP fallback

Freeform STL geometry can be converted without inventing analytic history through the Features
panel's **Faceted STEP fallback**. This is an explicit operation, never an automatic recovery from a
failed parametric search. The user-selected sewing tolerance is stored on the `importedFaceted`
feature as `sewingTolerance`; the original source bytes and SHA-256 remain authoritative and
unchanged. The value is in project units and is capped at the equivalent of 10 mm regardless of the
project's unit system.

The worker builds one planar OCCT face per preserved triangle, sews coincident/open boundaries only
within that tolerance, rejects any remaining free or multiply-connected edge, and requires exactly
one closed positive-volume `BRepCheck`-valid solid. STEP is then exported, independently reimported,
and checked for solid validity, volume stability, and matching face/edge counts. Large faceted
B-Reps deliberately skip OCCT re-tessellation during those two validation passes because it is
pathologically expensive; the already-validated preserved source facets are reused for the browser
layer and are explicitly labeled as a proxy, not as an OCCT tessellation. This does not weaken the
B-Rep or STEP reimport checks, and the UI labels the model non-parametric throughout. Because the
fallback does not run a source-to-result distance comparison, `toleranceSatisfied` remains unknown
and the overall validation state is partial even when both kernel gates pass.

The current fallback accepts STL only. Increasing sewing tolerance can merge unintended nearby
boundaries, so the control is bounded, visible, recorded, and rerunnable rather than silently tuned.
This path currently requires the source's declared units to match the project units and its scale
factor to equal 1. Unit conversion or manual scaling must first be applied to an explicit working
copy; Mesh2Param rejects the fallback instead of producing a dimensionally mislabeled STEP.

## Self-intersection

The deterministic fallback has no robust self-intersection backend installed. Diagnostics therefore
emit an `unverified` warning. They never label the source clean on that dimension.

## Reconstructed feature selection

Patch selection is deterministic through `patches.glb` and `selection-map.json`, with the map bound
to the GLB SHA-256 and triangle ranges carrying `patchId`. Final reconstructed face-to-feature
selection is deferred until OCCT semantic topology can prove a final-face mapping without guessing;
the UI must not imply that whole-body highlighting identifies an individual feature.

## Browser acceptance in the managed desktop sandbox

The primary workflow suite is authored in `tests/browser`. For this managed Codex run, the Chromium
build was installed under a writable temporary browser cache. In this Codex desktop sandbox,
Chromium launch reaches the executable but macOS denies its Mach-port rendezvous registration
(`bootstrap_check_in ... Permission denied`). The same restriction affects the system Chrome channel.
The in-app Browser is therefore used for responsive visual and interaction QA in-session; the
portable `pnpm test:e2e` suite remains the required automated gate when run from a normal host shell
or CI runner with Playwright browsers installed.
This is an environment limitation, not a passing Playwright result.
A later successful run of the same portable suite from the final host or acceptance environment
supersedes this session-specific observation; its result must be reported separately rather than
retroactively describing the managed-sandbox attempt as successful.

## License-safe JSON Schema format validation

The broad `jsonschema[format]` extra was not retained because its dependency set includes
`rfc3987`, whose upstream metadata declares GPL-3.0-or-later. Both Python projects instead use the
official `jsonschema[format-nongpl]` extra, which resolves to `rfc3986-validator` and
`rfc3987-syntax` for the relevant URI/IRI checks. Both lockfiles are audited, and the license gate
fails if the GPL-bearing distribution returns. This substitution preserves the format-validation
path required by Mesh2Param without treating a license exception as a technical fallback.

## Production backends and isolation

SQLite plus the filesystem content-addressed store is the only implemented persistent deployment
in this release. PostgreSQL, S3, and Redis-compatible queue settings fail at startup instead of
silently falling back to local state. External SQLite mode is limited to one geometry worker.

The Compose worker has no network and uses a read-only root filesystem, dropped capabilities,
`no-new-privileges`, a non-root UID, and resource limits. On deployments that do not reproduce those
OS/container controls, the Python audit hook is only defense in depth and must not be described as
equivalent isolation. See [deployment](deployment.md) for the supported topology.

## Container architecture

The production API and worker run as `linux/amd64` containers. The locked `nlopt` package does not
publish a CPython 3.12 Linux ARM wheel, while CadQuery/OCP and CasADi do. A native `linux/arm64`
backend build therefore fails closed during frozen dependency installation; ARM hosts use container
emulation until the complete locked dependency set has native wheels. The nginx/web image remains
native-platform.

## Alternative reconstruction histories

`candidates.json` contains scores, validity evidence, feature counts, rejection reasons, and a complete
schema-valid CADGraph snapshot for every bounded candidate. Reconstruction also persists the histories
and selected label in project state so artifact-set replacement and reload do not erase them. The web
application permits only kernel-valid snapshots to be selected, updates the authoritative editable
CADGraph, and rebuilds it through the worker. Candidate generation remains intentionally bounded by
the reconstruction settings and the engine's current supported feature-inference scope.
