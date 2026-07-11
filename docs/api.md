# API service

Run the authoritative local service from the repository root:

```sh
pnpm db:migrate
pnpm dev
```

The defaults are API `http://127.0.0.1:8000`, endpoint index
`http://127.0.0.1:8000/docs`, OpenAPI `http://127.0.0.1:8000/openapi.json`, health
`/health`, and dependency readiness `/ready`. The docs page is self-hosted and has no runtime CDN
dependency.

## Protocol

JSON successes use `{ "data": ..., "meta": { "requestId": ... } }`. Failures use a stable error
code, summary, technical detail, phase, project/job IDs when applicable, recoverability, and a
recommended action. Raw tracebacks are logged server-side only.

Project representations carry an `ETag: "rev-N"`. Every project mutation requires that value in
`If-Match`; stale edits return `412` with the current ETag. Upload is a raw
`application/octet-stream` request with `filename`, explicitly confirmed `unitsConfirmed`, units,
and optional scale query parameters. The service preserves the original bytes and hash unchanged.

Geometry routes return `202` and a durable job. Poll `GET /api/jobs/{jobId}`, replay
`GET /api/jobs/{jobId}/events` as Server-Sent Events, and send `Last-Event-ID` to resume. Cancellation
uses `POST /api/jobs/{jobId}/cancel`. Progress is emitted only at real operation boundaries.

## Routes

```text
POST /api/projects                         GET /api/projects
GET|PATCH|DELETE /api/projects/{id}
POST /api/projects/{id}/upload|repair|analyze|reconstruct|rebuild|validate|export
GET /api/projects/{id}/patches
PATCH /api/projects/{id}/patches/{patchId}
POST /api/projects/{id}/patches/merge|split
GET|PATCH /api/projects/{id}/cadgraph
GET|POST /api/projects/{id}/versions
GET /api/projects/{id}/versions/{versionId}
POST /api/projects/{id}/versions/{versionId}/restore
DELETE /api/projects/{id}/versions/{versionId}
GET /api/projects/{id}/artifacts
GET /api/projects/{id}/artifacts/{name}
GET /api/jobs/{jobId}
GET /api/jobs/{jobId}/events
POST /api/jobs/{jobId}/cancel
GET /api/samples
POST /api/samples/{sampleId}/open
GET /health                              GET /ready
```

`POST /api/projects/{id}/reconstruct` accepts the ordinary bounded parametric request with empty
settings. An explicit faceted fallback uses:

```json
{"settings":{"mode":"faceted","sewingTolerance":0.05}}
```

This mode is source-hash-bound, STL-only, non-parametric, and fails unless OCCT sewing produces one
closed solid whose STEP export passes independent kernel reimport validation. `sewingTolerance` is
expressed in the project's units (`0.05` above assumes a millimeter project) and is capped at the
equivalent of 10 mm. Successful fallback validation is `partial`: B-Rep and STEP reimport validity
are proven, while geometric deviation from the input mesh remains unmeasured. Until explicit mesh
normalization is implemented for this path, the source units must match project units and the
source scale factor must be `1`; other combinations fail before geometry is claimed.

## Configuration

Settings use the `MESH2PARAM_` prefix. Supported local settings include `DATABASE_URL` (SQLite),
`STORAGE_PATH`, `PUBLIC_URL`, `API_URL`, `MAX_UPLOAD_MB`, `MAX_TRIANGLES`, `MAX_VERTICES`,
`MAX_ABS_COORDINATE`, `JOB_TIMEOUT_SECONDS`, `WORKER_COUNT`, `WORKER_MEMORY_MB`, `RETENTION_DAYS`,
`CORS_ORIGINS`, `ALLOWED_HOSTS`, and `LOG_LEVEL`. `S3_ENDPOINT`, `S3_BUCKET`, and `QUEUE_URL` are
reserved configuration interfaces; M3 intentionally continues to use local filesystem CAS and its
SQLite-backed queue rather than claiming those future backends are active.

## Artifacts

Artifact sets are immutable snapshots and carry forward unchanged prior outputs by content hash.
The completed conversion/export contains `model.step`, `model.cadgraph.json`, `model.cq.py`,
`source.glb`, `repaired.glb`, `analysis-proxy.glb`, `patches.glb`, `reconstructed.glb`,
`residual.glb`, `analysis.json`, `metrics.json`, `manifest.json`, `project.mesh2param.json`, and
`mesh2param-export.zip`. The manifest records artifact sizes and SHA-256 values, project/source and
version identity, units, engine/schema/dependency versions, settings, validation, and timestamp.
