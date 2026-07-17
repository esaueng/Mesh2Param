# Extraordinary network vertices

Status: design only. No behavior, artifact, fixture, or tolerance changes are
part of this PR.

## Decision

Support an extraordinary network vertex as a topology-first fan of
four-sided tensor-product patches. A supported fan has one interior source-mesh
vertex where `k >= 3` freeform regions and `k` pairwise shared crease curves
meet. A vertex is extraordinary when `k != 4`; the same fan representation
also accepts the regular valence-four case so it does not need a second
artifact form. Every incident region remains its own disk-like square chart;
the junction is one corner of each chart. The fitter solves all patches
jointly, aliases every copy of the junction pole into one equivalence class,
and builds each crease as one curve shared by exactly two patches.

The first fixture is a Y-ridge plate: three bicubic roof regions meet at one
interior valence-three vertex and three sharp ridges run from that vertex to
the sides of a triangular footprint. This exercises the extraordinary vertex
without introducing triangular surface patches, approximate edge sewing, or
an extraordinary smoothness construction.

This is not a relaxation of the current two-region path. The existing
single-region and two-region layouts, their tolerances, and their v1 artifact
bytes remain unchanged. Analytic-face-only v2 artifact bytes remain unchanged
as well. Unsupported fan topology fails closed before fitting.

## Existing constraints that must remain true

The current implementation has several useful invariants:

- `detect_rectangle_corners` accepts exactly four geometric boundary turns.
  It is correct for the legacy single-region and two-region plate layouts, but
  it cannot discover a junction that is a chart corner for topological rather
  than geometric reasons.
- `harmonic_square_parameterization` already accepts explicit corner-loop
  positions. The extraordinary path should use that input instead of changing
  its square-map or distortion gates.
- `solve_patch_network` already uses union-find so two pole slots can be one
  solve unknown. Its current callers only describe one shared row between two
  patches.
- `NetworkPatch.cornerVertexIds` can reference the same `NetworkVertex` from
  several patches. A curve still has exactly two incident patches even when
  three or more curves share an endpoint.
- `build_network_faces` constructs exact iso-line pcurves and one common OCCT
  edge per shared curve. This remains the assembly rule; sewing is not a
  substitute for common topology.
- `mesh2param/surface-network/1` and `mesh2param/curved-plate/1` must continue
  to rebuild byte-identically. The merged analytic-faces design owns
  `mesh2param/surface-network/2` and `mesh2param/curved-plate/2`, including
  analytic surfaces, trim loops, curve records, wall-chain closure, and the
  unsuffixed `sewingTolerance` field. Extraordinary plates extend those
  contracts as version 3; they do not reinterpret either earlier version.
- The multi-region-hole path fills each interior rim for the harmonic solve,
  drops the synthetic vertices afterward, and records exact boolean cutters.
  The extraordinary corner detector must never mistake an interior rim for an
  outer chart corner.
- Analytic caps keep their vertical parametric axis, fuse without `clean()`,
  and use strong ball-following fill samples. This design does not alter that
  path or extend caps to extraordinary networks.

All comparisons introduced by the implementation use an explicit absolute
epsilon in project units with zero relative tolerance. No unit conversion,
fit tolerance, sewing tolerance, UV distortion limit, continuity angle, or
source-deviation threshold changes as part of this feature.

## Supported topology

### Crease graph

Build an explicit crease graph from source-mesh topology after segmentation:

1. Label every triangle by its freeform region ID.
2. Select each manifold mesh edge whose two incident triangles have different
   freeform labels.
3. Group selected edges by the unordered pair of region IDs they separate.
4. Walk each group into deterministic simple chains. A chain interior has
   graph degree two; its endpoints have a different degree or lie on the
   freeform network's outer boundary.
5. Treat a source vertex as an extraordinary candidate when at least three
   pairwise chains end there.

Detection is by shared mesh vertex and edge IDs, not by welding nearby
coordinates. If nominally coincident ridge endpoints are distinct topological
vertices, the input is ambiguous and fails closed.

For a candidate with valence `k`, validate its source one-ring before any UV
solve:

- the junction is interior to the freeform top, not on its outer boundary;
- exactly `k` distinct freeform regions appear as connected wedges around the
  vertex;
- exactly `k` non-zero crease chains are incident;
- each chain separates exactly two consecutive region wedges;
- the region/curve link is one cycle, not a bow-tie, T-junction, duplicate
  wedge, or non-manifold star;
- every incident region contains the junction once on its outer loop and is
  bounded by the two crease chains adjacent to that region in the one-ring.

The graph and all emitted IDs are canonical. Region IDs use the segmentation's
stable IDs. Curves sort by their unordered region-ID pair and outer endpoint
source vertex ID. Junctions sort by source vertex ID. Patch IDs sort by region
ID. Every extraordinary crease is oriented from the junction toward the outer
boundary. These rules make the same source and settings produce the same pole
alias order and artifact bytes.

### Scope of the first implementation

The topology and data model are valence-agnostic for any `k >= 3`, subject to
the existing patch and solve-unknown budgets. The first positive fixture is
valence three. Initial implementation supports one extraordinary fan in one
connected, plate-like freeform top. Every incident edge is a real sharp crease.

Multiple extraordinary vertices, internal crease loops, junction-to-junction
branches, mixed analytic/freeform junctions, and smooth extraordinary joins
remain outside this step.

## Corner detection beyond the exactly-four rule

Do not loosen `detect_rectangle_corners` or lower its turn threshold. Add an
extraordinary-layout detector that combines mandatory topology corners with
geometric outer corners.

For each incident region:

1. Select its outer loop exactly as the current multi-region path does. Hole
   loops are separate and never participate in corner discovery.
2. Mark three mandatory corners: the extraordinary source vertex and the two
   outer endpoints of that region's incident crease chains. A crease endpoint
   is mandatory even when its boundary turn is below the geometric threshold.
3. On the outer-loop arc between the two crease endpoints that does not pass
   through the junction, run the existing turn-angle evidence and require
   exactly one additional outer corner.
4. Require the two outer chains from the crease endpoints to that corner to
   pass the existing straight-boundary deviation gate.
5. Normalize the loop to the chart corner cycle
   `(junction, branch-a endpoint, outer corner, branch-b endpoint)`, using the
   oriented source boundary walk rather than a coordinate-angle sort.

This produces exactly four explicit corner positions for every incident
region while allowing more than four regions and more than four corners in the
whole network. Missing mandatory vertices, another sharp turn on an outer
arc, a non-straight outer chain, or a non-cyclic order means the region is not
one supported quadrilateral chart; it is rejected instead of being forced
through the square map.

The existing `reindexed_chart_region` and
`harmonic_square_parameterization(..., corner_loop_positions=...)` then map
each chart independently. Existing flip, area, stretch, and distortion gates
apply unchanged. The source junction point is retained as a real chart vertex;
it is never duplicated per chart and then merged by coordinate tolerance.

## Joint fit and shared-curve aliasing

### Pole equivalence classes

Generalize the solver input from pairwise `shared_poles` to canonical alias
groups of `PoleSlot` values. Existing callers translate their pairs into
two-element groups without changing results.

For every shared curve:

- map its two incident patch iso rows into the curve's junction-to-boundary
  orientation;
- require equal degree, knot vector, and pole count on both sides;
- alias corresponding row poles into one unknown class.

For every shared network vertex:

- collect the endpoint pole slot from every incident curve and the matching
  corner slot from every incident patch;
- alias the complete set into one equivalence class.

At a valence-three Y junction, the three patch-corner slots and the junction
ends of all three crease rows therefore resolve to one pole class. They are not
three independently fitted coordinates that merely compare close later. Union
operations and free-column assignment sort by encoded pole slot so the sparse
system is deterministic.

The extraordinary junction class is pinned to the one canonical source-mesh
junction point. Ridge endpoints and outer corners remain pinned by the
boundary construction. Interior crease poles remain free and emerge from the
joint fit. Conflicting fixed values beyond the recorded assembly epsilon fail
with `curved_patch_junction_alias_conflict`; they are never averaged.

The first implementation uses one degree and one span schedule for all patches
in the fan, as the current joint solver does. Refinement advances the complete
fan so every shared row remains knot-compatible. A budget exhaustion fails
closed rather than permitting incompatible curves or silently elevating
degree.

### Constraints and residuals

All incident curves are declared `crease`; no C1 rows are added. Each curve
must retain the current minimum crease-angle evidence along its open interior.
The junction itself has no single tangent plane, so normal-angle evidence is
reported pairwise per incident curve and is not evaluated exactly at the
multi-face corner.

Fit convergence records both:

- assigned-region residuals, where each region's real samples must be
  explained by its own patch; and
- the existing closest-network residual used near shared boundaries.

Both must pass the existing fit tolerance. Adding the assigned-region gate
prevents one roof patch from hiding a poor neighboring fit near the junction.
Synthetic samples, if supported in a later extraordinary-hole step, remain
excluded from convergence exactly as in the current hole path.

Reprojection seeds each adjacent patch through the relevant iso curve and its
canonical curve parameter. It must not use the current two-patch assumption
that the other patch is `1 - side` or that every shared edge has the same iso
orientation.

## Surface-network and plate artifacts

### `mesh2param/surface-network/3`

Schema 3 is exactly the merged `mesh2param/surface-network/2` contract -- its
analytic and tensor `faces`, explicit trim loops, and canonical 3-D curve and
pcurve records -- plus one id-addressed top-level `junctions` array. It does
not restore the schema-1 `patches` array or define alternate face, trim, or
curve records.

This excerpt shows the only new record shape; the surrounding `vertices`,
`curves`, and `faces` are the complete schema-2 records with the top-level
schema string changed to `mesh2param/surface-network/3`:

```json
{
  "junctions": [
    {
      "id": "junction-0",
      "vertexId": "vertex-junction-0",
      "sourceVertexId": 123,
      "incidentCurveIds": ["crease-0", "crease-1", "crease-2"],
      "incidentPatchIds": ["patch-0", "patch-1", "patch-2"],
      "valence": 3
    }
  ]
}
```

Every incident tensor face refers to `vertex-junction-0` in its
`outerBoundary.cornerVertexIds`. Do not write three equal-coordinate junction
vertices. Every crease remains one canonical curve with role `patchJoin`, is
referenced by exactly two tensor-domain shared boundaries, and names the
shared junction vertex as its start vertex. Analytic faces may coexist in a
schema-3 network but cannot participate in the first extraordinary fan.

Schema-3 validation derives incidence from faces, shared-boundary curve uses,
and curve endpoints and requires it to match the recorded junction arrays and
valence. `incidentPatchIds` names tensor faces whose `surface.kind` is
`tensorPatch`; both incidence arrays are unique and sorted by id. Validation
also checks with an explicit absolute epsilon that:

- every curve endpoint pole agrees with its referenced vertex;
- every tensor-face corner pole agrees with its referenced vertex;
- every shared row agrees with its canonical curve poles with zero relative
  tolerance;
- every shared curve has exactly two incident tensor faces;
- every extraordinary vertex link is one manifold region/curve cycle; and
- every incident tensor face has two junction curves meeting at the one
  recorded corner, not at two merely coincident corners.

Version 3 adopts the version-2 canonical byte and hashing contract in
[`network-analytic-faces.md`](network-analytic-faces.md#canonical-bytes-and-hashing)
verbatim; it does not define another serializer. That inherited contract is
the authority for negative-zero normalization, rejection of an artifact whose
raw bytes differ from its canonical reserialization, and id sorting for every
id-addressed array. `junctions` is such an array. Its two incidence arrays are
sets encoded in id order; topology and geometry arrays retain their declared
order exactly as in version 2. A noncanonical schema-3 network fails with the
same `network_noncanonical_artifact` code.

Readers permanently dispatch and rebuild `surface-network/1`,
`surface-network/2`, and `surface-network/3` on their own code paths. They do
not upgrade v1 or v2 objects in memory. New reconstruction continues to emit
v1 or v2 unless explicit extraordinary-junction incidence requires v3, so
historical and analytic-face-only hashes and rebuild bytes do not change.

### `mesh2param/curved-plate/3`

Schema 3 is exactly the merged `mesh2param/curved-plate/2` contract --
including `assembly.wallChains`, `assembly.baseCornerVertexIds`, and the
unit-aware `assembly.sewingTolerance` field -- with a complete
`surface-network/3` object. It never writes `sewingToleranceMm`, and it does
not introduce a second wall-closure representation.

The Y-ridge uses the version-2 fields with three ordered
`baseCornerVertexIds` and three ordered `wallChains`, one per triangular base
edge. A wall chain may contain the two consecutive unshared tensor-face sides
which meet at the elevated ridge endpoint on that wall. Across all wall
chains, the referenced sides form the complete top outer boundary exactly
once. The first and last side endpoints equal the chain's named base vertices;
every intermediate vertex lies in that wall's plane within the existing
boundary tolerance. The lower wire is the ordered triangular base polygon
translated by the unchanged `prismVector`.

No additional plate field is needed for the Y-ridge. Version 3 changes only
the schema signal and permits the nested surface-network/3 junction incidence,
but does not change the assembly record. Version 2 already permits a base
polygon of at least three unique vertices and more than one top side in a wall
chain, so its existing validation accepts the Y-ridge's three non-collinear
base corners and split wall tops. The version-2 constraints on ordered closure,
bounded sewing, holes, units, and solid validation apply unchanged.

`build_network_faces` continues the version-2 contract of returning an edge by
`(patchId, iso)` for unshared tensor boundaries as well as the curve-ID map for
shared boundaries. The version-3 assembly builder uses those exact top edges,
creates the recorded planar wall wires, and applies the same bounded sewing
and solid validation. It does not infer walls by vertex names or
nearest-segment tests.

The CADGraph `reconstructedSurfaceNetwork` feature needs no public contract
change: it already resolves a content-addressed curved-plate artifact. The
compiler verifies the SHA-256 first, dispatches curved-plate v1, v2, or v3,
and rebuilds through the same assembly function as the driver and fit cache.
Version-3 plate bytes use the version-2 canonicalizer verbatim, including its
negative-zero, noncanonical-input, and id-sorting rules.

The fit-cache key adds the surface-network schema, sorted junction evidence,
region-to-chart corner cycles, curve orientations, and algorithm version. A
cache hit still reruns assembly, shared-edge and junction evidence, kernel and
STEP validation, and source comparison. Curved-plate v1 and v2 remain readable
and rebuildable indefinitely without reserialization through the v3 writer.

## B-Rep and validation evidence

OCCT receives three distinct shared edges at the Y junction. Each edge is used
by exactly two faces and all three reuse one `TopoDS_Vertex`. No topological
edge is shared by three faces. Exact iso-line pcurves, `SameParameter`, and
`SameRange` remain required for both incident faces of every curve.

Add junction evidence alongside the existing per-curve evidence:

- junction ID and valence;
- incident patch and curve IDs;
- maximum patch-corner-to-vertex distance;
- maximum curve-endpoint-to-vertex distance;
- source junction distance;
- one-ring manifold/cycle result; and
- count of incident OCCT edges and faces before and after STEP reimport.

All distance evidence must be within the existing linear/sewing tolerance;
per-curve G0 and crease-angle gates remain unchanged. STEP reimport must
preserve the B-spline face count, the extraordinary vertex incidence, one
closed positive-volume solid, and the expected Euler topology. Repeated driver
runs, artifact rebuild, cache hit, and normalized STEP export remain
byte-identical.

## Minimal deterministic fixture

Add `bspline-y-ridge-plate` only through
`scripts/generate_curved_fixtures.py` in the first implementation PR that
needs it.

Ground truth:

- an equilateral or deliberately scalene triangular base with one planar
  bottom and three planar side walls;
- three exact bicubic tensor-product roof patches;
- one interior junction shared by all three patch corner IDs;
- three exact cubic crease curves running from the junction to one point on
  each side wall, shared pole-for-pole by the adjacent roofs;
- straight outer patch sides and ridge endpoints lying in their side-wall
  planes, so each wall is one planar pentagon; and
- interior roof perturbations that vanish on every boundary pole row.

Choose ridge heights and perturbations so each complete ridge stays above the
existing segmentation threshold and the existing five-degree
`crease_minimum_angle_deg` gate, including near the junction. Do not widen
either angle. Tessellate densely enough for stable segmentation and harmonic
charts while keeping a successful full reconstruction below 30 seconds.

The fixture acceptance test requires:

- exactly three adjacent freeform regions and four planar regions;
- one valence-three interior junction and three simple crease branches;
- one valid, non-overlapping square chart per roof with the explicit corner
  cycle described above;
- three B-spline faces, three plane walls, and one plane bottom after STEP
  reimport;
- one shared network vertex, three pairwise shared curves, and exact artifact
  incidence;
- G0 gaps within the unchanged sewing tolerance and every crease above the
  unchanged sharpness gate;
- assigned-region and closest-network residuals within the existing fit
  tolerance, source deviation within the existing comparison tolerance, and
  volume within the existing curved-fixture relative-volume gate;
- byte-identical surface-network and curved-plate artifacts on repeat runs;
- byte-identical normalized STEP for repeat, artifact rebuild, and cache-hit
  paths; and
- successful runtime below 30 seconds.

When the fixture is added, regenerate the entire corpus through the canonical
script and assert that every pre-existing manifest entry and STL SHA-256 is
unchanged. The new entry is appended in the canonical spec order.

## Fail-closed behavior retained

The first implementation must reject these cases with stable codes and the
faceted-fallback recommendation:

| Condition | Proposed code |
| --- | --- |
| No unique source vertex represents the nominal junction | `curved_patch_junction_ambiguous` |
| The junction one-ring is non-manifold, a bow-tie, T-junction, or not one fan cycle | `curved_patch_junction_nonfan` |
| More than one extraordinary vertex or a junction-to-junction/internal-loop crease graph | `curved_patch_junction_count` |
| An incident region is not one four-sided disk after topology corners are assigned | `curved_patch_extraordinary_chart` |
| Fixed corner or endpoint aliases disagree beyond the recorded epsilon | `curved_patch_junction_alias_conflict` |
| A smooth override touches an extraordinary junction | `curved_patch_extraordinary_smooth` |
| A hole or analytic cap belongs to an extraordinary fan | `curved_patch_extraordinary_opening` |
| A cone, sphere, torus, cylinder, or other analytic region participates in the junction | `curved_patch_extraordinary_analytic` |
| Curve degree, knots, pole count, or orientation cannot be made identical within the existing budget | `curved_patch_extraordinary_curve_mismatch` |
| The outer wall-chain/base-polygon closure is ambiguous or non-planar | `curved_patch_extraordinary_assembly` |

The following existing failures also remain active: open or non-manifold
source meshes, non-finite coordinates, flipped/overlapping/high-distortion UVs,
fit or source-deviation failure, lost crease evidence, B-Rep or STEP reimport
failure, cancellation, time/patch/control-point/unknown budgets, and
`forceSplit` on an already multi-region network.

In particular, the implementation does not average close vertices, increase
sewing tolerance, downgrade a crease to smooth, let one patch explain another
region's samples, use `clean()` after analytic fusion, or accept a cache hit
without rerunning downstream gates.

## Implementation sequence after the version-2 foundation

No extraordinary-vertex implementation starts until the prerequisite parts
of the analytic-faces plan have landed: the frozen v1 compatibility tests, the
v2 codec and canonicalizer, tensor faces in the v2 `faces` representation,
canonical curve/shared-boundary records, and curved-plate/2 wall-chain,
compiler, and cache dispatch. Schema 3 extends those implementations; it does
not develop a parallel artifact stack while version 2 is still in flight.

After those dependencies and this design are merged, each item below is one
implementation PR and stops at its stated boundary:

1. **Topology and charts.** Add crease-graph/junction extraction, the
   topology-plus-geometry corner layout, valence-agnostic fan records, negative
   stable-code tests, and the generator-owned Y-ridge ground truth. Keep
   reconstruction fail-closed after chart validation.
2. **Joint fit and surface-network v3.** Add canonical pole alias groups,
   N-patch residual/reprojection logic, v3 junction serialization and
   validation, and deterministic fit/rebuild unit tests. Do not yet expose a
   successful plate conversion through services.
3. **Plate v3 and end-to-end reconstruction.** Reuse the v2 wall-chain
   assembly for the triangular Y-ridge footprint, add v3 nested-network
   validation and compiler/cache dispatch, OCCT/STEP incidence evidence,
   service integration, and all repeat/rebuild/cache determinism tests for the
   Y-ridge fixture.
4. **Optional follow-ups, separately reviewed.** Extraordinary networks with
   recognized holes, multiple junctions, mixed analytic boundaries, or
   unbiased G1 constructions around a smooth extraordinary vertex each need
   their own design and PR. They are not implied by the crease-fan support.

Every implementation PR runs the repository's unchanged ruff and strict mypy
gates, the full frozen dev pytest suite with zero failures, canonical fixture
regeneration with pre-existing hashes unchanged, and the per-fixture runtime
budget. No step proceeds by widening a tolerance or loosening an assertion.
