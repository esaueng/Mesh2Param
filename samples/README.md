# Procedural samples

`samples/generated/<slug>/` is produced by the trusted CADGraph compiler, not by handwritten CAD
scripts. Each of the ten samples includes its validated CADGraph, normalized and reimported STEP,
safe generated CadQuery replay source, deterministic GLB, high/low/random binary STL meshes, a
geometry-derived SVG thumbnail, fixed expected metrics, and a SHA-256 manifest.

Run `pnpm samples:generate` from the repository root. Generation is byte-stable for the same engine
and dependency lock; tests generate the corpus into independent temporary directories and compare
every artifact byte.

# Curved reconstruction benchmark

`samples/curved-benchmark/<slug>/` is the Milestone 0 corpus for
[curved STEP reconstruction](../docs/curved-step-reconstruction.md). Positive fixtures are
tessellated from exact ground-truth solids whose top face is a genuine non-round B-spline surface,
covering tessellation density, deterministic noise, inch units, pose, a through hole, and sharp
creases. Negative fixtures are hand-built STL meshes that are open, non-manifold,
self-intersecting, too coarse, or multi-body. Each fixture ships its binary STL, a `fixture.json`
manifest with SHA-256 and expected qualification, and (for positives) exact ground-truth metrics.

Run `pnpm curved:fixtures` to regenerate (byte-stable) and `pnpm curved:baseline` to record the
current faceted-fallback baseline to `artifacts/curved-baseline/baseline.json`.
