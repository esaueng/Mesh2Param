# CADGraph

CADGraph is Mesh2Param's authoritative, versioned, typed, editable representation. It is data—not
Python source—and is the only input accepted by the exact feature compiler.

## Sources of truth

| Artifact | Path |
| --- | --- |
| JSON Schema | `packages/contracts/schema/cadgraph.schema.json` |
| Python models/invariants | `packages/contracts/python/mesh2param_contracts/models.py` |
| Generated TypeScript types | `packages/contracts/src/types.generated.ts` |
| Browser invariant validation | `packages/contracts/src/validation.ts` |
| Python/TypeScript migration | `packages/contracts/python/mesh2param_contracts/migrations.py`, `packages/contracts/src/migrations.ts` |
| Canonical serialization/hash | `packages/contracts/*/serialization.*` |
| Valid fixture | `packages/contracts/tests/fixtures/base.cadgraph.json` |

The current schema is `1.0.0`. Legacy `0.1.0` documents have explicit migrations. Unknown future
versions fail closed. Generated files are checked against the schema bytes so hand-edited generated
types cannot drift unnoticed.

## Document shape

A graph includes:

- identity, name, units, optional source descriptor, and source coordinate frame;
- project surface/angular tolerances;
- sketches with planes, construction and ordinary entities, constraints, and closed profiles;
- ordered typed features with dependencies, boolean mode, suppression, evidence, confidence,
  locks, overrides, and semantic outputs;
- provenance-based semantic topology references;
- reconstruction/search settings and deterministic random seed;
- engine/dependency versions, fit metrics, validation state, and version metadata;
- namespaced JSON-only extensions for data not understood by core behavior.

All core models reject unknown fields. IDs are unique, feature order is unique and ascending,
dependencies must reference earlier features, sketch/profile/evidence/topology references must exist,
vectors and planes satisfy geometric invariants, and non-finite JSON values are rejected.

## Supported sketch entities

Point, construction point, line, construction line, polyline, rectangle, circle, circular arc,
closed profile, and construction axis are represented explicitly. A profile refers to outer and
inner entity loops; features refer to profile IDs rather than embedding anonymous geometry.

## Supported feature operations

| Operation | Important parameters |
| --- | --- |
| Extrusion | sketch/profiles, direction, blind/symmetric/through/to-face extent, distance, base/additive/subtractive |
| Pocket | sketch/profiles, direction, depth/extent, subtractive boolean |
| Hole | position, axis, diameter, through/blind and optional depth |
| Counterbore/countersink | base hole plus bore/sink diameter and depth/angle |
| Revolution | sketch/profiles, axis, angle, boolean mode |
| Linear/circular pattern | source feature dependencies, direction/axis, count, spacing/angle |
| Mirror | source dependencies and semantic plane |
| Chamfer/fillet | semantic edge references and positive width/radius |
| Imported faceted | source artifact/hash and explicit fallback/reference intent |
| Reconstructed surface network | content-addressed curved-plate artifact id/hash; rebuilds an approximate curved B-Rep base body deterministically |

Automatic inference is narrower than compilation. A schema-supported operation may be manually
authored even when no inference rule currently proposes it.

## Compilation and rollback

The compiler processes features in deterministic order. Each step resolves dependencies and
semantic references, performs exact OCCT operations, validates the intermediate shape, and records
generated/modified topology. A feature failure reports its ID, operation, order, parameters,
dependencies, kernel error, and last valid feature. The invalid result does not replace the last
valid geometry.

After a successful build the engine can produce a B-Rep, normalized STEP, tessellated GLB, and
deterministic CadQuery source. The `.cq.py` source includes feature IDs and documented units, but it
is export-only and never becomes the authoritative state or an execution input.

## Semantic topology

Raw kernel labels such as `Face12` are unstable and are never the sole persisted identity.
References use provenance roles such as `feature.base.topFace`, `feature.hole.1.wall`, or
`feature.pocket.1.floor`. Rebuild maps generated/modified kernel topology back to these roles and
fails unresolved references instead of silently targeting a different face or edge.

The current browser has an authoritative source-patch selection map. Final reconstructed
face-to-feature highlighting remains limited until OCCT history proves the semantic mapping; the UI
must not present whole-body highlighting as feature-level evidence.

## Safe evolution

To change CADGraph, update the JSON Schema first, regenerate types/validator, implement both language
migrations, and add roundtrip/invariant/compiler tests. Preserve canonical key ordering, finite
numbers, deterministic IDs/seeds, and schema/version metadata. Never reinterpret an old field
silently.
