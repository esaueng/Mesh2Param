# Procedural samples

`samples/generated/<slug>/` is produced by the trusted CADGraph compiler, not by handwritten CAD
scripts. Each of the ten samples includes its validated CADGraph, normalized and reimported STEP,
safe generated CadQuery replay source, deterministic GLB, high/low/random binary STL meshes, a
geometry-derived SVG thumbnail, fixed expected metrics, and a SHA-256 manifest.

Run `pnpm samples:generate` from the repository root. Generation is byte-stable for the same engine
and dependency lock; tests generate the corpus into independent temporary directories and compare
every artifact byte.
