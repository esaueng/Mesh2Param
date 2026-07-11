# Security model

Mesh files and generated geometry are untrusted. CADGraph is the only executable geometry model;
the service never runs uploaded scripts or generated CadQuery source. Worker dispatch uses a static,
trusted operation map and the generated `.cq.py` file is download-only.

Uploads are streamed to randomized private staging files under a byte cap, then structurally parsed
through an STL/OBJ/PLY allowlist. Extension/content mismatches, archives, executables, external OBJ
references, path traversal, symlinks, malformed counts, non-finite or excessive coordinates, and
configured byte/vertex/triangle limits are rejected before immutable publication. Original source
bytes are never repaired or rescaled in place.

Source and output bytes live in a SHA-256 filesystem CAS. Canonical paths are derived only from the
digest; publication is atomic and deduplicating; reads reject links and non-regular files. Artifact
downloads use safe attachment names and stream an already-open no-follow file handle. Project
deletion removes database references, and old unreferenced blobs are removed on startup after the
configured retention period.

Each geometry job uses Python `spawn`, a fresh private work directory, JSON-only bounded IPC, CPU,
file-size, descriptor and wall-clock limits, and a configurable Linux address-space limit. The
supervisor persists attempts and heartbeats, enforces cancellation/timeout precedence, terminates
unresponsive children, retries crashes in a fresh process only when safe, rejects unsafe output
paths, cleans work directories, and recovers abandoned database jobs after restart. In production,
the worker installs a Python audit policy that rejects socket connection/name-resolution attempts.
Deployment must additionally deny worker egress at the container or host network boundary; the
in-process audit hook is defense in depth, not an OS sandbox.

The default local profile deliberately has no login and binds to loopback. Host allowlisting,
origin checks for browser mutations, environment-scoped CORS, request IDs, structured audit rows,
strict error envelopes, and security response headers are enabled. Production configuration rejects
wildcard hosts/CORS and debug mode. Use a trusted single-origin reverse proxy and TLS for any remote
deployment; do not expose the no-login local profile directly to an untrusted network.
