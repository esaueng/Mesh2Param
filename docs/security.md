# Security model

Mesh2Param treats uploaded meshes, project documents, CADGraph documents, generated geometry, and
artifact metadata as untrusted. Its default local profile has no authentication. It binds the API to
loopback and is suitable only for a trusted single-user workstation. A remote deployment requires a
separate TLS and authentication boundary; the application must not be exposed directly to an
untrusted network.

Report suspected vulnerabilities privately as described in the root [security policy](../SECURITY.md).

## Trust boundaries

| Boundary | Principal risk | Required control |
| --- | --- | --- |
| Browser to API | Cross-origin mutation, stale overwrite, malformed JSON | Exact origin/host allowlists, schema and size bounds, `If-Match` revisions |
| Mesh/project upload | Parser abuse, path traversal, allocation exhaustion | Streaming byte cap, structural allowlist, bounded counts/coordinates, randomized staging |
| API to geometry worker | Native-kernel crash, runaway CPU/memory, unsafe output path | Static operation dispatch, spawned process, bounded JSON IPC, resource/time limits |
| Worker to network | Exfiltration or unexpected dependency traffic | No worker container network plus Python audit-hook defense in depth |
| Worker to persistent data | Corruption, symlink escape, concurrent ownership | Shared absolute data root, singleton lock, no-follow CAS, atomic publication |
| Artifact download | Header/path injection, content confusion | Server-owned descriptors, safe attachment names, opened no-follow file handles |

Generated `model.cq.py` is a download artifact only. The service never imports or executes uploaded
scripts, project-file code, or generated CadQuery source. CADGraph is the only executable geometry
model, and workers dispatch its operations through a static trusted map.

## Upload and storage controls

Uploads are streamed to private randomized staging files under `MESH2PARAM_MAX_UPLOAD_MB`; the API
does not buffer an unbounded request in memory. It accepts only the supported STL, OBJ, and PLY
structures. It rejects extension/content mismatches, archives and executables, external OBJ
references, traversal names, symlinks, malformed element counts, non-finite coordinates, excessive
absolute coordinates, and configured vertex/triangle limits before publication.

Original bytes are immutable: repair and unit conversion create derived artifacts instead of
rewriting the source. Persistent source/output bytes use a SHA-256 filesystem content-addressed
store. Canonical paths derive from validated digests, publication is atomic, and reads reject links
and non-regular files. Database records bind blobs to projects, jobs, versions, and immutable
artifact sets.

Project deletion removes its database references. Blobs are deleted only after they become
unreferenced and are older than `MESH2PARAM_RETENTION_DAYS`; cleanup occurs at service startup.
Deletion is therefore not an immediate secure-erasure guarantee. Backups, filesystem snapshots,
browser downloads, and IndexedDB copies have their own retention policies.

## Geometry-job isolation

Each geometry attempt uses Python's `spawn` start method, a fresh private work directory, bounded
JSON-only IPC, and limits for wall time, address space on supported Linux hosts, CPU, file size, and
file descriptors. The supervisor persists attempts and heartbeats, enforces cancellation and timeout
precedence, terminates unresponsive children, retries only safe crash cases in a fresh process,
rejects output paths outside the attempt directory, and recovers abandoned database jobs after
restart.

In production the worker's Python audit policy rejects socket connection and name-resolution
attempts. This is defense in depth, not an OS sandbox: native code may not trigger every Python audit
event. The Compose deployment additionally gives the worker `network_mode: none`, drops every
capability, enables `no-new-privileges`, uses a read-only root filesystem, runs as UID/GID 10001,
and applies PID/CPU/memory bounds. Equivalent host-level egress and resource controls are mandatory
outside Compose.

## HTTP and configuration controls

Mutation routes apply origin checks, host allowlisting, request IDs, strict error envelopes, and
optimistic concurrency. The same-origin web container adds a restrictive Content Security Policy,
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` headers. It
proxies `/api`, `/health`, `/ready`, and `/openapi.json` to the private API network.

Production configuration fails closed. It rejects:

- unknown `MESH2PARAM_*` variables, wildcard or empty host policies, wildcard CORS, debug mode, and
  `DEBUG` logging;
- relative or symlink-containing data, storage, and SQLite paths;
- malformed public/API URLs and URLs containing credentials, queries, or fragments;
- unimplemented S3, Redis-compatible queue, or non-SQLite database settings;
- external runner mode with any worker count other than one; and
- a worker-heartbeat stale threshold less than twice the heartbeat interval.

For a proxied browser deployment, `MESH2PARAM_PUBLIC_URL` and `MESH2PARAM_CORS_ORIGINS` must include
the exact public origin and `MESH2PARAM_ALLOWED_HOSTS` must include its hostname. The internal
`MESH2PARAM_API_URL` remains the Compose service URL (`http://api:8000`). Never put secrets in any
`PUBLIC_*` build variable, project file, CADGraph metadata, artifact manifest, or committed `.env`.

## Authentication and tenancy limitations

Mesh2Param supports an optional shared `MESH2PARAM_API_TOKEN` bearer token for all `/api` routes,
including artifact downloads and SSE job streams. This is a coarse deployment boundary, not user
authentication: Mesh2Param does not implement users, sessions, roles, quotas, per-project
authorization, tenant separation, or a secrets store. A reverse proxy or identity-aware gateway
should still authenticate every remote request before it reaches the web service. Because the
backend has no user identity, a shared
instance grants every authenticated upstream principal the same application-level access; use a
separate deployment/data volume per trust domain unless an external policy can enforce isolation.

The default API and worker use one SQLite database and filesystem store. S3, PostgreSQL, and a Redis
queue are future interfaces, not failover backends. Do not weaken validation to make unsupported
configuration appear operational.

## Operator checklist

- Keep the web port loopback-only and terminate TLS/authentication at a trusted gateway.
- Configure exact public URL, origin, and host values; test both an allowed and a rejected Origin.
- Preserve `MESH2PARAM_JOB_RUNNER_MODE=external` and `MESH2PARAM_WORKER_COUNT=1` for SQLite Compose.
- Keep the worker without network access and keep API/storage networks private.
- Back up and protect the complete data volume; test restore with a matching application version.
- Monitor `/ready`, not only `/health`, plus container restarts, job failures, disk usage, and audit
  records. A `200 /health` response proves only that the API process is alive.
- Rebuild from pinned lockfiles/base-image digests and run the license, test, sample, and container
  security gates before release.
- Apply OS/container-runtime updates and review dependency advisories independently of this codebase.

## Residual risks

CadQuery, OCCT, CasADi, mesh parsers, and image/geometry dependencies include native code. Process
and container limits reduce blast radius but do not prove absence of memory-safety defects. Complex
yet valid geometry can still consume the configured timeout or memory budget. The deterministic mesh
diagnostic path also has no robust self-intersection backend installed and reports that dimension as
`unverified`, never as clean. See [fallbacks](fallbacks.md) for the complete bounded-scope record.
