# Mesh2Param

Mesh2Param converts supported mechanical triangle meshes into a versioned, editable CADGraph, exact
Open CASCADE B-Rep, reimport-validated STEP, deterministic tessellated artifacts, source/result
metrics, and safe generated CadQuery source. M1 provides the exact compiler and procedural corpus.
M2 adds a deliberately bounded, transform-blind reconstruction path for a sharp-edged,
plane/full-cylinder L-bracket with four through holes. M3 adds the local-first FastAPI service,
authoritative SQLite project/job/version state, immutable filesystem content-addressed storage,
spawn-isolated geometry jobs, durable SSE progress, cancellation, recovery, and export bundles.

## Development

Requirements: Python 3.12, Node.js 20 or newer, pnpm, and uv.

```sh
pnpm install
uv sync --extra dev
pnpm verify
pnpm mesh2param -- --help
pnpm db:migrate
pnpm dev
```

Generate the ten deterministic procedural samples with `pnpm samples:generate`.

The API listens on `http://127.0.0.1:8000` by default. Health, readiness, the self-hosted endpoint
index, and OpenAPI are available at `/health`, `/ready`, `/docs`, and `/openapi.json`. Create a
project, preserve a raw STL/OBJ/PLY upload, enqueue geometry work, replay progress from the durable
SSE event stream, and download content-addressed artifacts through the routes documented in
[`docs/api.md`](docs/api.md). The default local profile has no login and binds to loopback.

## Service architecture

```text
FastAPI request handlers
  ├─ SQLite/WAL: projects, revisions, jobs, attempts, events, versions, audit records
  ├─ SHA-256 CAS: immutable source and generated artifact bytes
  └─ spawn supervisor: one isolated temp directory and process per geometry job
       └─ trusted static operation map → mesh2param engine → validated artifacts
```

Project mutations require an `If-Match: "rev-N"` precondition. Only one mutating job may be active
per project. Successful artifact snapshots inherit prior immutable outputs, and export produces a
ZIP containing the complete conversion artifact set plus a hash manifest. See
[`docs/security.md`](docs/security.md) for the trust boundaries and production requirements.

## Reconstruction CLI

```sh
pnpm mesh2param -- analyze source.stl --units mm --output artifacts/
pnpm mesh2param -- repair source.stl --units mm --output artifacts/
pnpm mesh2param -- segment source.stl --units mm --output artifacts/
pnpm mesh2param -- reconstruct source.stl --units mm --output artifacts/
pnpm mesh2param -- rebuild model.cadgraph.json --output artifacts/
pnpm mesh2param -- compare source.stl model.step --units mm --output artifacts/
pnpm mesh2param -- validate model.step --units mm --output artifacts/
pnpm mesh2param -- samples generate --sample l-bracket-with-holes
```

STL, OBJ, and PLY ingestion is extension- and content-validated with configurable byte, triangle,
vertex, and coordinate limits. The original bytes and SHA-256 are preserved. Repair runs on a copy
and records every enabled operation, parameters, before/after metrics, warnings, and version IDs.

Successful L-bracket reconstruction writes diagnostics, repair records, analytic patches, inferred
frame and sketch evidence, candidate scores, a schema-valid editable CADGraph, validated STEP,
CadQuery export source, bidirectional distance/normal/area/volume metrics, a residual heatmap GLB,
truthful source/repair/analysis GLBs, and a GLB-hash-bound patch triangle selection map.

The automatic claim is intentionally narrow. Equal-axis extents, coarse cylinder facets, partial
cylinders, open/damaged loops, freeform remainder, fillets, chamfers, patterns, other hole counts,
and general prismatic or organic parts return explicit partial/unsupported results instead of a
fabricated parametric history. Open3D is not required; see `docs/fallbacks.md`.

Mesh2Param reconstructs an editable, geometrically equivalent CAD model. It does not guarantee
recovery of the source designer's exact original feature history.
