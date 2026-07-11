# Mesh2Param

Mesh2Param converts supported mechanical triangle meshes into a versioned, editable CADGraph, exact
Open CASCADE B-Rep, reimport-validated STEP, deterministic tessellated artifacts, source/result
metrics, and safe generated CadQuery source. M1 provides the exact compiler and procedural corpus.
M2 adds a deliberately bounded, transform-blind reconstruction path for a sharp-edged,
plane/full-cylinder L-bracket with four through holes.

## Development

Requirements: Python 3.12, Node.js 20 or newer, pnpm, and uv.

```sh
pnpm install
uv sync --extra dev
pnpm verify
pnpm mesh2param -- --help
```

Generate the ten deterministic procedural samples with `pnpm samples:generate`.

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
and a GLB-hash-bound patch triangle selection map.

The automatic claim is intentionally narrow. Equal-axis extents, coarse cylinder facets, partial
cylinders, open/damaged loops, freeform remainder, fillets, chamfers, patterns, other hole counts,
and general prismatic or organic parts return explicit partial/unsupported results instead of a
fabricated parametric history. Open3D is not required; see `docs/fallbacks.md`.

Mesh2Param reconstructs an editable, geometrically equivalent CAD model. It does not guarantee
recovery of the source designer's exact original feature history.
