# `@mesh2param/contracts`

Shared CADGraph compatibility boundary for the Python engine/API and the TypeScript web app.

- `schema/cadgraph.schema.json` is the single compatibility source of truth.
- `python/mesh2param_contracts` provides strict Pydantic v2 models, reference-integrity checks,
  deterministic serialization, and explicit migrations.
- `src/types.generated.ts` and `src/validator.generated.ts` are generated from the schema.
- `src/validation.ts` adds graph invariants that portable JSON Schema cannot express cleanly.

After changing the schema, run `pnpm generate`. `pnpm verify` rejects stale generated files and
runs generation checks, strict TypeScript compilation, tests, and the production build. Python can
be verified independently with:

```sh
UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra test pytest
```

Current schema version: `1.0.0`. Migration from the initial `0.1.0` development shape is supported;
unknown versions fail closed. Migration fills deterministic metadata defaults but never fabricates
missing feature geometry.

The `bspline` sketch entity is deliberately bounded: degree 1–3, four to eight
control points, deterministic open-uniform clamped knots derived by the
compiler, and required `rational: false` / `periodic: false` declarations.
Composite profile entities must share their end/start coordinates; the
authoritative compiler rejects a disconnected B-spline loop before building or
scoring a solid.
