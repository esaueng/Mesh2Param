# Mesh2Param project-file format

The default filename is `project.mesh2param.json`; accepted files end in `.mesh2param.json`. The
format is a self-contained working-project envelope when its source is embedded and a local recovery
file when it contains a local blob reference.

## Envelope

```json
{
  "format": "mesh2param-project",
  "fileVersion": 1,
  "savedAt": "2026-07-11T12:30:00Z",
  "project": {},
  "working": {},
  "ui": {},
  "versions": [],
  "source": null,
  "artifactManifest": []
}
```

| Field | Meaning |
| --- | --- |
| `format` | Constant discriminator `mesh2param-project` |
| `fileVersion` | Envelope version; current value `1` |
| `savedAt` | ISO timestamp for this save operation |
| `project` | Project identity, name, units, schema, revision, base version, timestamps |
| `working` | Current working document: source metadata, diagnostics, repair, analysis, patches, CADGraph, validation, metrics, settings, artifacts |
| `ui` | Active workflow step, selection, viewer layers/opacity/projection, shell/theme state, and optional camera pose |
| `versions` | Immutable named version snapshots and their engine/dependency identity |
| `source` | `embedded`, `local-reference`, or `null` |
| `artifactManifest` | Name/media type/size/SHA-256 descriptors, never raw artifact bytes |

The working document and validated `ui` record include restore-relevant project state but do not
duplicate large GLB/STEP arrays in React state. Artifact descriptors refer to authoritative
service/CAS outputs. On import they remain in `artifactManifest` for verification, but are removed
from the active working document: a project file cannot establish that the corresponding service
blobs still exist, so the viewer must not try to render them.

## Source representations

An embedded source contains `kind: "embedded"`, lowercase SHA-256, byte size, media type, original
filename, and base64 bytes. The browser currently embeds sources up to 16 MiB. A local reference
contains `kind: "local-reference"`, the same integrity metadata, and an IndexedDB `blobKey`. A local
reference is not portable to another browser profile or device.

Saving never changes the source bytes. On import, embedded data is size-checked before decoding,
decoded under a configured bound, checked against the declared byte count and SHA-256, and only then
stored in IndexedDB. A missing local blob remains an explicit unavailable reference; no substitute
content is fetched or guessed.

## Limits and validation

Current browser limits are defined in `apps/web/src/persistence/projectFile.ts`:

- project JSON: 64 MiB;
- embedded source: 16 MiB;
- versions: 1,000;
- artifact descriptors: 512;
- units: mm, cm, m, in, ft;
- every hash: 64 lowercase hexadecimal SHA-256 characters;
- byte counts: non-negative safe integers;
- scale: finite and positive.

The parser accepts only JSON objects and detaches them from prototypes. It validates the envelope,
project, working state, UI state, versions, source, and artifact manifest. CADGraph is migrated and
validated through the shared contracts before hydration. Unsupported extensions, format discriminators,
future envelope versions, malformed values, oversized content, and hash mismatches fail with stable
project-file error codes.

## Migration

Envelope version `0`/missing is migrated to version `1` by filling explicit nullable/empty working
fields, artifact manifest defaults, and safe UI defaults. Early version-1 files without the additive
`ui` record receive the same safe defaults. CADGraph migration is independent because its schema has
its own version. Unknown future project-file or CADGraph versions fail closed; save a copy before
using a newer client against older data.

## Browser persistence

IndexedDB database `mesh2param-workspace` stores projects, documents, versions, verified blobs, UI
state/camera pose, unified history, settings, and an outbox. Autosave is local recovery. The backend
revision remains authoritative, and a local-only divergence blocks server geometry operations until
resolved. Opening a project file creates/imports the local records without silently replacing an
unrelated server project.

## Portability and backup

For a portable backup, confirm that `source.kind` is `embedded` and separately retain downloaded
STEP/CADGraph/export bundles. A project file does not promise that service artifact URLs or local CAS
content exist forever. Verify artifact hashes against `artifactManifest` or the export
`manifest.json` after transfer.
