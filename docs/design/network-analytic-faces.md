# Surface-network analytic faces and shared trim curves

Status: proposed for review. This document is design only; it does not authorize
implementation until this PR is reviewed and merged.

## Goal

Add `mesh2param/surface-network/2`, a versioned surface-network artifact that can
describe analytic plane, cylinder, cone, and sphere faces beside tensor-product
B-spline patches. A face may carry explicit interior trim loops. The first
consumer is a recognized spherical cap whose rim is one canonical 3-D curve
referenced by both the freeform patch trim and the sphere trim. The fitter pins
the patch to that curve, and OCCT builds both faces on the same `TopoDS_Edge`.
No cap boolean is involved, so a steep-site cap has no near-tangency band to
discover or fragment.

The result remains an approximate curved B-Rep inferred from STL, not recovered
design history. No units, tolerances, source bytes, or existing artifact
semantics change implicitly.

## Non-goals

- Do not change code in the design PR.
- Do not reinterpret or rewrite `mesh2param/surface-network/1` or
  `mesh2param/curved-plate/1`.
- Do not make arbitrary topology, extraordinary chart vertices, or torus faces
  prerequisites for the first cap migration.
- Do not use sewing, healing, tolerance growth, `clean()`, or a boolean result
  to manufacture a cap join.
- Do not remove the current cylinder-hole path until the equivalent explicit
  analytic-face path passes all single- and multi-region hole gates.

## Constraints inherited from the current implementation

The Milestone 2 network has three properties worth preserving:

1. A shared tensor/tensor boundary is fitted once. Its boundary pole slots are
   aliased in `solve_patch_network`, so G0 is exactly zero rather than accepted
   after a proximity check.
2. `build_network_faces` creates one `TopoDS_Edge` for that curve, attaches an
   exact iso-line pcurve to each tensor surface, and reuses the edge in both
   face wires.
3. `surface-network/1` and `curved-plate/1` are canonical JSON identified by
   SHA-256, and driver, fit-cache, and compiler rebuilds produce byte-identical
   normalized STEP.

Schema 1 is intentionally narrower than the proposed topology. It contains
only tensor patches, only natural rectangular outer boundaries, and only
shared iso boundaries. Every `NetworkCurve` is assumed to join exactly two
tensor patches. `shared_edge_evidence` and `_plate_solid_from_network` embed
that assumption; the latter also treats the only network curve as the crease
whose endpoints split the two plate walls. A cap rim is different: it is an
interior loop of one tensor face and the outer loop of one analytic face. It
must not be counted as a wall-splitting crease.

The existing cap path records a `CapFuser` and asks OCCT to intersect a ball
with an already-fitted patch. That path established three constraints which
remain binding:

- the sphere parametric axis stays vertical and its seam placement is recorded;
- `clean()` is never run after sphere/freeform assembly;
- the freeform fit needs controlled support inside the removed loop, but
  synthetic support is not source evidence and is excluded from residual gates.

Multi-region holes add two more binding constraints. For each region, the
largest-perimeter loop remains the outer boundary. Interior hole loops are
filled only for harmonic parameterization by a virtual centroid fan whose
vertices are discarded afterward. Weak synthetic fit samples span a hole and
are excluded from convergence evidence. A schema change must not parameterize
the unfilled multiply-connected region, promote those synthetic samples to
source samples, or assume denser tessellation fixes the collapsing rim.

## Design invariants

The following are hard invariants, not scoring preferences:

- A topology curve has one canonical 3-D pole vector in memory and one curve
  record in the artifact. Attachments never duplicate those poles.
- Both trim uses reference the same curve id, and both OCCT wires contain the
  same underlying `TopoDS_Edge`; only the oriented edge wrapper differs.
- A pcurve is surface-specific. Its 2-D poles cannot be numerically identical
  across a tensor patch and a sphere because the UV coordinate systems differ.
  “Identical rim poles” therefore means the single canonical 3-D curve pole
  vector is shared by identity; each surface has its own pcurve constrained to
  that curve over the same parameter range.
- Every 3-D curve and every pcurve use the same normalized parameter range
  `[0, 1]`. Periodic analytic UVs are stored on an explicit unwrapped branch.
- The freeform patch is constrained to the rim during fitting. Trimming an
  unconstrained patch after the fit is rejected even if OCCT can sew it.
- Curve/surface agreement is adaptively measured and must be within the
  existing declared linear tolerance. The implementation may refine the curve,
  pcurve, or patch, but may not widen the tolerance.
- Face and wire orientation are explicit artifact data and are validated in UV
  and in the final shell.
- Schema 1 parsing, serialization, hashing, rebuilding, and cache replay stay on
  their historical code paths.
- A successful fixture remains below 30 seconds; budget failure is fail-closed
  and never selects a lower-quality geometry silently.

## `mesh2param/surface-network/2`

Schema 2 replaces the schema-1 `patches` array with a `faces` array. Each face
owns a supporting surface and its trim topology. Tensor faces retain their
implicit rectangular outer boundary so the existing straight plate closure
does not need to become explicit topology in the same change. Analytic faces
use explicit trim loops.

The following is a complete, valid schema-2 object. It describes a planar
cubic tensor patch trimmed by an exact rational quadratic circle and a
spherical cap using the same 3-D rim. It contains no comments or ellipses.
The pretty printing is for review; canonical serialization is defined below.

```json
{
  "schema": "mesh2param/surface-network/2",
  "units": "mm",
  "linearTolerance": 0.000001,
  "producer": {
    "algorithm": "mesh2param/curved-fit/5",
    "seed": 0
  },
  "vertices": [
    {"id": "corner-0", "point": [-2.0, -2.0, 0.0]},
    {"id": "corner-1", "point": [2.0, -2.0, 0.0]},
    {"id": "corner-2", "point": [2.0, 2.0, 0.0]},
    {"id": "corner-3", "point": [-2.0, 2.0, 0.0]},
    {"id": "rim-0-seam", "point": [1.0, 0.0, 0.0]}
  ],
  "curves": [
    {
      "id": "rim-0",
      "role": "interiorTrim",
      "kind": "rationalBSpline",
      "degree": 2,
      "knots": [0.0, 0.0, 0.0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1.0, 1.0, 1.0],
      "poles": [
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [-1.0, 1.0, 0.0],
        [-1.0, 0.0, 0.0],
        [-1.0, -1.0, 0.0],
        [0.0, -1.0, 0.0],
        [1.0, -1.0, 0.0],
        [1.0, 0.0, 0.0]
      ],
      "weights": [1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0],
      "periodic": false,
      "startVertexId": "rim-0-seam",
      "endVertexId": "rim-0-seam",
      "continuity": "crease"
    }
  ],
  "faces": [
    {
      "id": "patch-0",
      "orientation": "forward",
      "surface": {
        "kind": "tensorPatch",
        "degreeU": 3,
        "degreeV": 3,
        "knotsU": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0],
        "knotsV": [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0],
        "poles": [
          [[-2.0, -2.0, 0.0], [-2.0, -0.6666666666666666, 0.0], [-2.0, 0.6666666666666666, 0.0], [-2.0, 2.0, 0.0]],
          [[-0.6666666666666666, -2.0, 0.0], [-0.6666666666666666, -0.6666666666666666, 0.0], [-0.6666666666666666, 0.6666666666666666, 0.0], [-0.6666666666666666, 2.0, 0.0]],
          [[0.6666666666666666, -2.0, 0.0], [0.6666666666666666, -0.6666666666666666, 0.0], [0.6666666666666666, 0.6666666666666666, 0.0], [0.6666666666666666, 2.0, 0.0]],
          [[2.0, -2.0, 0.0], [2.0, -0.6666666666666666, 0.0], [2.0, 0.6666666666666666, 0.0], [2.0, 2.0, 0.0]]
        ]
      },
      "outerBoundary": {
        "kind": "tensorDomain",
        "cornerVertexIds": ["corner-0", "corner-1", "corner-2", "corner-3"],
        "sharedBoundaries": {}
      },
      "interiorTrimLoops": [
        {
          "id": "patch-0-rim-0",
          "orientation": "clockwise",
          "edges": [
            {
              "curveId": "rim-0",
              "orientation": "reversed",
              "parameterRange": [0.0, 1.0],
              "pcurve": {
                "kind": "rationalBSpline",
                "degree": 2,
                "knots": [0.0, 0.0, 0.0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1.0, 1.0, 1.0],
                "poles": [[0.75, 0.5], [0.75, 0.75], [0.5, 0.75], [0.25, 0.75], [0.25, 0.5], [0.25, 0.25], [0.5, 0.25], [0.75, 0.25], [0.75, 0.5]],
                "weights": [1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0, 0.7071067811865476, 1.0],
                "periodic": false
              }
            }
          ]
        }
      ]
    },
    {
      "id": "sphere-0",
      "orientation": "forward",
      "surface": {
        "kind": "sphere",
        "position": {
          "origin": [0.0, 0.0, -1.7320508075688772],
          "axis": [0.0, 0.0, 1.0],
          "xDirection": [1.0, 0.0, 0.0]
        },
        "radius": 2.0
      },
      "outerBoundary": {
        "kind": "trimLoop",
        "loop": {
          "id": "sphere-0-rim-0",
          "orientation": "counterClockwise",
          "edges": [
            {
              "curveId": "rim-0",
              "orientation": "forward",
              "parameterRange": [0.0, 1.0],
              "pcurve": {
                "kind": "bspline",
                "degree": 1,
                "knots": [0.0, 0.0, 1.0, 1.0],
                "poles": [[0.0, 1.0471975511965976], [6.283185307179586, 1.0471975511965976]],
                "periodic": false
              }
            }
          ]
        }
      },
      "interiorTrimLoops": []
    }
  ]
}
```

The example deliberately uses a closed, clamped rational curve rather than a
periodic curve. Its one seam vertex appears as both `startVertexId` and
`endVertexId`. The sphere pcurve is unwrapped from `u = 0` to `u = 2*pi`; its
endpoints are different in UV but map to the same 3-D vertex. This avoids an
implicit branch cut and keeps the edge and both pcurves on `[0, 1]`.

Under the canonical serializer below, this exact example is 2,709 bytes and
has SHA-256
`f3dd4086cbef986130f58d79add63eabda41257a125e36771fbd0079656e02c9`.

### Top-level fields

| Field | Contract |
| --- | --- |
| `schema` | Exactly `mesh2param/surface-network/2`. |
| `units` | Project length unit; no coordinate or tolerance conversion occurs while parsing. |
| `linearTolerance` | Positive finite length in `units`; upper-bounded by the existing physical tolerance policy. This is the maximum allowed 3-D curve/pcurve disagreement, not a healing budget. |
| `producer` | Exact fitting algorithm id and deterministic integer seed. These participate in the content hash. |
| `vertices` | Ordered, unique-id 3-D vertices. Closed edges may name the same start and end vertex. |
| `curves` | Ordered, unique-id canonical 3-D B-spline curves. |
| `faces` | Ordered, unique-id tensor or analytic face entries with explicit orientation and trim topology. |

Writers sort `vertices`, `curves`, and `faces` by id before serialization.
Loop edge order is topological and is never sorted. Pole, knot, weight, and
corner arrays are geometric data and retain their declared order.

### Curve records

`kind` is `bspline` or `rationalBSpline`. Knots are the full nondecreasing
knot vector, as in schema 1; this avoids a simultaneous knot-format migration.
`len(poles) == len(knots) - degree - 1`. A rational curve has exactly one
strictly positive finite weight per pole; a non-rational curve omits `weights`.
`periodic` is explicit. Schema 2 initially writes `false`; periodic input is
reserved until the builder and STEP round trip have dedicated coverage.

`role` is `patchJoin` or `interiorTrim`:

- `patchJoin` is referenced from two tensor-domain `sharedBoundaries` and may
  contribute endpoints to plate wall-chain derivation.
- `interiorTrim` is referenced from trim loops. It never changes wall chains.
  A manifold internal curve must have exactly two face uses, normally a tensor
  interior loop and an analytic outer loop.

`continuity` remains `crease` or `smooth`. A cap rim is normally a true crease.
If source evidence supports a tangent join, `smooth` activates the existing G1
gate generalized to arbitrary pcurves.

### Surface records

`surface.kind` is a closed union:

| Kind | Required fields | OCCT interpretation |
| --- | --- | --- |
| `tensorPatch` | `degreeU`, `degreeV`, `knotsU`, `knotsV`, `poles`; optional positive `weights` with the same U/V shape | `Geom_BSplineSurface` |
| `plane` | `position` | `Geom_Plane(gp_Ax3)` |
| `cylinder` | `position`, positive `radius` | `Geom_CylindricalSurface(gp_Ax3, radius)` |
| `cone` | `position`, nonnegative `referenceRadius`, `semiAngleRadians` strictly between 0 and pi/2 | `Geom_ConicalSurface(gp_Ax3, semiAngleRadians, referenceRadius)` |
| `sphere` | `position`, positive `radius` | `Geom_SphericalSurface(gp_Ax3, radius)` |

`position` contains `origin`, `axis`, and `xDirection`. `axis` and
`xDirection` must be finite unit vectors, perpendicular within the existing
epsilon policy. `yDirection` is derived as `axis x xDirection`; it is not
stored. This records sphere/cylinder/cone seam placement and avoids an OCCT
default-axis choice changing a replay. For cones, the artifact stores OCCT's
native reference plane and radius; an apex is derived, never substituted for
the constructor contract during replay.

Analytic parameters use network length units and radians. Field names do not
carry an `Mm` suffix because `units` is authoritative. This differs from the
historical curved-plate assembly fields only in the new schema; old field names
are not changed.

### Boundary and trim records

A tensor face has `outerBoundary.kind == tensorDomain`, four corner vertex ids,
and the schema-1 iso-side map `sharedBoundaries`. Missing iso sides remain
natural patch edges. Its `interiorTrimLoops` may contain zero or more explicit
loops.

An analytic face has `outerBoundary.kind == trimLoop`. Plane and analytic side
faces may also have interior loops. Every trim edge use contains:

- the referenced canonical `curveId`;
- traversal `orientation` (`forward` or `reversed`);
- the canonical `[0, 1]` `parameterRange`;
- one 2-D `bspline` or `rationalBSpline` pcurve with the same parameter domain.

Loop orientation is `counterClockwise` or `clockwise` in the unwrapped UV
domain and is checked against face orientation. A forward tensor face has a
counter-clockwise outer loop and clockwise interior loops. Periodic analytic
surfaces use a stored unwrapped UV branch; the validator permits an endpoint
offset by exactly one declared analytic period but not an arbitrary seam jump.

## Canonical bytes and hashing

Schema 2 gets a separate codec. Its canonical bytes are:

```python
json.dumps(
    canonical_payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("utf-8")
```

There is no BOM, indentation, trailing whitespace, or final newline. Before
serialization the schema-2 canonicalizer:

1. converts NumPy scalars to Python `int` or `float`;
2. rejects NaN and infinity;
3. normalizes negative zero to positive `0.0`;
4. sorts id-addressed arrays by id while preserving topology and geometry
   array order;
5. rejects duplicate JSON object keys on read;
6. validates every reference and closed-union discriminator.

`SurfaceNetworkV2.artifact_sha256()` is SHA-256 of those bytes. A schema-2
artifact read from disk must equal its own canonical reserialization byte for
byte; otherwise it fails with `network_noncanonical_artifact`. This creates one
hash for one schema-2 semantic object. It does not apply a new canonicalizer to
schema 1.

The CADGraph feature continues to hash the complete `curved-plate.json` file,
not only the nested network. `mesh2param/curved-plate/2` has the same top-level
shape as version 1:

```text
schema = "mesh2param/curved-plate/2"
units = <project units>
network = <complete mesh2param/surface-network/2 object>
assembly.corners = <four 3-D plate corners>
assembly.prismVector = <3-D vector in project units>
assembly.sewingTolerance = <positive length in project units>
assembly.holes = [{radius, basePoint, direction, height}, ...] or []
```

The actual file contains the nested object directly; the notation above is not
serialized JSON. Version 2 changes `sewingToleranceMm` to
`sewingTolerance` because its `units` field is authoritative. It never has an
`assembly.caps` key: analytic caps are faces in the network. Recorded hole
cutters use unsuffixed `radius` and `height` lengths in the declared units;
`direction` is a finite unit vector. They are retained during the cap migration
so current single- and multi-region hole behavior composes without a
simultaneous hole-topology rewrite. A later step migrates each cylinder into
analytic network faces and then writes an empty `assembly.holes` list for new
artifacts.

The plate hash is SHA-256 of the schema-2 canonical bytes of the entire plate
object. The compiler still verifies the CADGraph hash against the raw file
bytes before parsing.

## Schema 1 compatibility

Compatibility is a dispatch, not an in-memory upgrade:

- `surface-network/1` continues through the existing `NetworkVertex`,
  `NetworkCurve`, `NetworkPatch`, `SurfaceNetwork.to_artifact`,
  `artifact_bytes`, and `_occt_bspline_curve` behavior.
- `curved-plate/1` continues to accept `sewingToleranceMm`, `holes`, and the
  optional `caps` key. Its cap boolean replay stays available for historical
  artifacts.
- Parsing a version-1 object does not add `faces`, `producer`,
  `linearTolerance`, curve `role`, weights, or trim-loop fields.
- Serializing a parsed version-1 artifact must reproduce the exact original
  bytes and SHA-256. The version-1 writer is frozen; no negative-zero or
  `allow_nan` behavior is retrofitted.
- Rebuilding a version-1 curved plate must continue to produce the same
  normalized STEP bytes, including the historical sphere boolean when present.
- New reconstruction writes version 1 until a layout actually uses an analytic
  network face or explicit interior trim. This keeps unaffected fixtures and
  their hashes stable during the early migration steps.

Golden tests must cover a single patch, split smooth network, two-region
crease, single-region hole, multi-region hole, and historical sphere cap. Each
golden stores the original bytes and SHA-256, parses and reserializes them, and
rebuilds the normalized STEP byte-for-byte.

## Rim fitting and solver constraints

### Ownership and initialization

The segmentation boundary loop between the freeform region and recognized
analytic region supplies ordered source evidence. The implementation chooses a
deterministic seam vertex: the lexicographically smallest quantized 3-D rim
point after transforming to the recorded analytic frame, with the source
vertex id as a tie-breaker. Loop direction follows the owning freeform face.

The recognized analytic fit defines the sphere, cone, cylinder, or plane
support. Its `position.xDirection` is chosen deterministically. For a spherical
cap the axis remains vertical as required by the existing cap evidence; the
pcurve is unwrapped across one full U period instead of rotating the axis to
hide a seam.

The 3-D rim is initialized as a bounded-degree B-spline approximation of the
ordered source rim with its start and end pole coincident. Rational weights are
allowed when an exact conic is justified; generic rims start non-rational.
There is one rim pole vector `R`, not `R_patch` and `R_analytic`.

### Joint constraints

For fixed patch pcurve parameters `q(t) = (u(t), v(t))`, tensor control points
enter the following constraint linearly:

```text
S_patch(q(t_k); P) - C_rim(t_k; R) = 0
```

The solver adds exact sparse equality rows at endpoints, knot breaks, Greville
abscissae, and adaptively inserted worst-error parameters. These are hard KKT
constraints or eliminated degrees of freedom, not high-weight least-squares
penalties. Existing outer-boundary fixed poles and tensor/tensor aliases remain
in the same joint system. Fairness and source fitting stay in the objective.

The analytic attachment uses its stored pcurve `a(t)`:

```text
S_analytic(a(t_k)) - C_rim(t_k; R) = 0
```

Because analytic evaluation and pcurve coordinates make this nonlinear, the
fit alternates deterministically:

1. hold both pcurves fixed and solve the sparse patch/rim system;
2. closest-point project rim samples onto the analytic support on the current
   unwrapped UV branch;
3. refit the bounded analytic pcurve without changing parameter order;
4. update the patch pcurve by closest-point projection on the tensor surface;
5. insert the worst curve/surface parameter when either attachment exceeds
   tolerance;
6. stop only when both attachments and source-rim residuals pass, or fail the
   iteration/span/time budget.

Collocation alone is not claimed as an everywhere proof. The final attachment
gate samples all curve and pcurve knot spans adaptively, brackets local maxima,
and checks endpoints and the closed seam. If the maximum 3-D disagreement is
above `linearTolerance`, refinement continues or the reconstruction fails with
`curved_patch_rim_fit_failed`. No tolerance is increased.

The patch fit keeps the current virtual fill strategy inside an interior loop
so unsupported interior poles remain bounded. Those samples are excluded from
the source residual and cannot pull the rim off the actual segmented boundary.
Cap fill may initialize the interior, but the shared rim constraints, not an
overshoot clearance or a later boolean, define the join.

### Continuity evidence

G0 for a cap rim is topological identity plus the measured pcurve attachments.
For a `crease` rim, the generalized evidence records minimum, mean, P95, and
maximum dihedral angle using normals evaluated at the two pcurves. The existing
minimum-angle gate prevents a true crease from collapsing. For a `smooth` rim,
the existing interior G1 maximum-angle gate applies and the solver adds
tangent-plane constraints. End-span exclusions are allowed only for the same
documented forced-corner reason as tensor/tensor joins, never merely because a
cap is difficult.

## OCCT construction

`build_network_faces` becomes schema-dispatched. The version-1 implementation
is preserved. The version-2 path runs in deterministic phases:

1. Validate the complete network before constructing OCCT objects.
2. Build all `TopoDS_Vertex` objects once.
3. Build each canonical 3-D B-spline curve once and create exactly one
   `TopoDS_Edge` from it and its recorded vertices.
4. Build every supporting surface from its explicit artifact parameters:
   `Geom_BSplineSurface`, `Geom_Plane`, `Geom_CylindricalSurface`,
   `Geom_ConicalSurface`, or `Geom_SphericalSurface`.
5. For every edge use, construct the stored `Geom2d_BSplineCurve`, attach it to
   the already-created edge on that supporting surface with
   `BRep_Builder.UpdateEdge`, and preserve the `[0, 1]` range.
6. Assemble each outer wire in declared order using oriented views of the
   common edges. For tensor-domain outer boundaries, retain the current exact
   iso-line construction and implicit natural edges.
7. Assemble every interior wire from its declared oriented edge uses and add it
   to the same `BRepBuilderAPI_MakeFace` before extracting the face.
8. Run the edge/curve/pcurve consistency checks. Set `SameRange` and
   `SameParameter` only after they are proven or after OCCT's bounded
   same-parameter operation succeeds without exceeding `linearTolerance`.
9. Apply the recorded face orientation, then pass the prepared faces and plate
   closure faces to the existing bounded sewing/solidification stage.

The patch interior wire and sphere outer wire both receive the same edge object.
The patch use is reversed while the sphere use is forward in the example. No
two coincident edges are made, and sewing is not asked to discover their
equivalence.

The sphere's stored frame and unwrapped pcurve handle the meridian seam. The
implementation does not rotate the sphere to a horizontal parametric axis, and
it does not call `clean()` on the assembled result.

`_plate_solid_from_network` must stop using `len(network.curves)` to infer plate
layout. Wall chains derive only from `patchJoin` curves referenced by tensor
outer `sharedBoundaries`. `interiorTrim` curves never contribute wall vertices.
This is necessary for one crease plus one or more cap/hole rims.

## Multi-region and hole composition

Schema 2 supports a trim loop on any tensor face, including either side of a
two-region crease network. The ownership of each segmented interior loop is
retained explicitly when building the corresponding face entry.

The current multi-region hole algorithm remains unchanged during initial cap
migration:

- largest perimeter selects the outer loop per region;
- virtual centroid fans exist only during harmonic parameterization and are
  discarded;
- weak hole-fill samples exist only during fitting and are excluded from
  convergence evidence;
- recorded cylinder cutters replay after network face assembly;
- smooth-join overrides continue to compose with holes.

Multi-region caps continue to fail closed with
`curved_patch_multiregion_caps` until the dedicated migration step owns a cap
loop on one region, emits a tensor/analytic rim, and proves crease plus cap plus
hole composition. Merely making the parser accept the topology is not enough to
remove that error.

When cylinder holes migrate into the network, the cylinder support uses a
recorded analytic frame and explicit pcurves for its upper and lower rims and
seam. The upper rim edge is shared with the owning tensor interior loop; the
lower rim is shared with the bottom plane. This migration must preserve the
filled-chart parameterization and cannot infer a cylindrical face by
subtracting a cutter and inspecting the result. Until those explicit faces are
validated, the version-2 plate envelope may retain recorded cutters.

## Evidence and gates

Every new writer and rebuild path is fail-closed. The following gates are
required in addition to the existing curved reconstruction gates.

### Artifact gates

- exact schema discriminator and closed unions;
- finite values, positive radii and weights, valid degrees and knot vectors;
- unit and orthogonal analytic frames within the existing epsilon policy;
- unique ids and complete references;
- one canonical parameter range per edge and pcurve;
- closed-loop vertex continuity and declared UV orientation;
- `patchJoin` adjacency of exactly two tensor outer boundaries;
- manifold `interiorTrim` adjacency of exactly two face uses;
- canonical bytes and SHA-256 reproducibility;
- schema-1 golden bytes and hashes unchanged.

### Geometric gates

- maximum canonical-curve to tensor-pcurve 3-D deviation;
- maximum canonical-curve to analytic-pcurve 3-D deviation;
- closed-seam position and tangent mismatch;
- no pcurve self-intersection, fold, or unintended periodic seam jump;
- interior loop strictly inside the tensor UV outer domain and not intersecting
  another loop;
- exact common-edge identity in the two face wires;
- expected continuity or crease evidence along every shared curve;
- zero unexpected free or multiply-connected sewing edges;
- valid, closed, positive-volume single solid before STEP export;
- B-Rep validity, face inventory, topology, and volume preserved after STEP
  reimport;
- independent STEP audit surface inventory includes the analytic face;
- symmetric source deviation and normal gates still pass;
- no extra trim islands or analytic face fragments.

### Determinism and performance gates

- repeated fresh fits produce identical network bytes, plate bytes, normalized
  STEP bytes, and evidence;
- artifact rebuild and compiler rebuild match the driver STEP byte-for-byte;
- cache hit matches a fresh fit byte-for-byte and reruns every assembly,
  pcurve, topology, source-deviation, STEP, and audit gate;
- serial and fixture-worker execution produce identical artifacts;
- each successful benchmark fixture remains under approximately 30 seconds;
- cancellation and all existing budget error codes remain stable.

A new steep-site spherical-cap fixture is required because the current gentle
dome does not exercise the failure this design targets. It must be procedural,
generated only through `scripts/generate_curved_fixtures.py`, and demonstrate a
single shared rim without a boolean tangency band. Fixture regeneration must
also prove every pre-existing manifest SHA-256 is unchanged.

## Compiler impact

The CADGraph operation remains `reconstructedSurfaceNetwork`; no public feature
union change is needed. Its `sourceArtifactId` and `artifactSha256` continue to
refer to the complete curved-plate artifact.

`_surface_network_tool` keeps its current order:

1. resolve the artifact;
2. hash the raw bytes and compare with CADGraph;
3. parse strict JSON;
4. dispatch `curved-plate/1` or `curved-plate/2`;
5. rebuild through the corresponding versioned assembly path;
6. let normal downstream CADGraph features operate on the resulting body.

Version-2 parsing additionally verifies canonical raw bytes. Unsupported
network or plate versions continue to fail closed. Stable errors distinguish
`invalid_network_artifact`, `network_noncanonical_artifact`,
`network_rebuild_failed`, and `artifact_hash_mismatch`; no parser fallback
tries to reinterpret an unknown version.

The compiler does not regenerate, refit, project, or heal geometry. All surface,
curve, pcurve, frame, orientation, and tolerance data required for replay are in
the artifact.

## Fit-cache impact

The active schema-2 fitting path uses
`FIT_CACHE_ALGORITHM = "mesh2param/curved-fit/5"`. The cache key includes:

- source mesh content SHA-256;
- complete reconstruction and network settings;
- exact chart vertex/triangle evidence;
- region-to-interior-loop ownership;
- recognized analytic kind and canonical parameters;
- deterministic analytic frame and seam vertex;
- smooth-boundary overrides;
- the target surface-network schema.

Version-1 key generation remains available as `/4` for historical replay tests;
existing cache files are neither rewritten nor interpreted as schema 2. A v5
cache payload embeds the canonical schema-2 network plus iteration and candidate
evidence. A load validates the embedded schema and cache-key inputs before
skipping only the fit. It then rebuilds the common-edge faces and reruns every
downstream gate. A stale, corrupt, or schema-mismatched cache entry is a miss or
a stable fail-closed cache error, never permission to use its geometry.

## Incremental implementation plan

Each step below is one C2+ draft PR after this design is reviewed and merged.
Every step must leave the full suite at zero failures and preserve all schema-1
goldens.

### Step 1: freeze schema 1 and add schema-2 codecs

- Add byte/hash golden fixtures for all existing schema-1 layouts, including
  caps and multi-region holes.
- Add version-dispatched data classes and strict schema-2 validation.
- Add the schema-2 canonicalizer and the complete JSON example above as a
  round-trip/hash test.
- Do not change reconstruction output or OCCT construction.

Verification: schema tests, schema-1 exact bytes/hashes, ruff, strict mypy,
full pytest, fixture regeneration with unchanged hashes.

### Step 2: tensor-only schema-2 faces

- Represent existing tensor patches as schema-2 face entries with tensor-domain
  outer boundaries and no interior loops.
- Rebuild synthetic tensor-only schema-2 networks through a separate
  `build_network_faces_v2` path.
- Prove normalized STEP equality with the equivalent schema-1 network.
- Keep production reconstruction writing schema 1.

Verification: single, split, crease, and multi-region-hole synthetic rebuilds;
schema-1 bytes unchanged; all global gates.

### Step 3: explicit trim loops on tensor faces

- Add rational/non-rational 2-D B-spline pcurves, oriented trim uses, and
  interior wires on a tensor face.
- Build one exact planar patch/circular-hole synthetic case matching the JSON
  example.
- Prove one edge object, valid wires, no extra islands, and STEP round-trip
  identity across repeat runs.
- Do not alter the current cylinder boolean path.

### Step 4: analytic face constructors

- Add plane, cylinder, cone, and sphere surface records and constructors.
- Add bounded synthetic trim tests for each analytic kind, including periodic U
  unwrapping and recorded seam frames.
- Generalize edge evidence from tensor iso sides to arbitrary face pcurves.
- Keep production cap and hole booleans unchanged.

### Step 5: jointly constrained spherical rim

- Add the shared rim unknowns, hard patch/rim constraints, analytic pcurve
  alternation, adaptive attachment gate, and stable failure codes.
- Add the steep-site fixture through the fixture generator.
- Construct the tensor and sphere faces on one common rim edge and eliminate the
  cap boolean for the new schema-2 candidate.
- Keep multi-region caps fail-closed.

Verification includes the current dome, the new steep cap, deliberate
non-convergence, seam placement, repeated fits, runtime, and absence of calls to
the cap boolean or `clean()` on the schema-2 path.

### Step 6: curved-plate/2, compiler, and cache

- Emit the version-2 plate envelope for successful explicit-cap networks.
- Dispatch compiler rebuilds without changing the CADGraph feature contract.
- Introduce the v5 cache key/payload and rerun all gates on hits.
- Prove fresh, cache-hit, artifact-rebuild, compiler-rebuild, and service-job
  STEP bytes are identical.

### Step 7: multi-region cap and hole composition

- Permit a cap trim loop to belong to either tensor face of a crease or smooth
  two-region network.
- Derive wall chains only from `patchJoin` curves.
- Preserve virtual fan parameterization and excluded weak samples for every
  hole-bearing region.
- Add cap-only, hole-only, and cap-plus-hole multi-region fixtures and prove the
  smooth override still composes.
- Remove `curved_patch_multiregion_caps` only for the proven topology; all other
  unsupported cases keep failing closed.

### Step 8: migrate remaining analytic faces

- Replace recorded cylinder cutters with explicit cylinder faces and shared
  upper/lower rim edges after single- and multi-region parity is proven.
- Migrate recognized cones and explicit plate planes through the same face
  union in separate small commits/PRs if needed.
- Keep the version-1 boolean replay forever; remove only new-output dependence
  on those booleans.

Torus support requires a later schema-2 union addition and its own reviewed
design because it introduces two periodic parameters; it is intentionally not
smuggled into these steps.

## File-level impact

- `engine/mesh2param/surface_network.py`: versioned models/codecs, analytic
  constructors, pcurves, trim wires, common-edge adjacency, generalized
  evidence.
- `engine/mesh2param/surface_fit.py`: shared rim unknowns, hard equality rows,
  pcurve alternation, adaptive curve/surface checks.
- `engine/mesh2param/curved_patch.py`: cap candidate construction, role-based
  wall derivation, versioned plate assembly, removal of booleans only on the
  proven version-2 path.
- `engine/mesh2param/fit_cache.py`: versioned algorithm/key/payload.
- `engine/mesh2param/compiler.py`: strict curved-plate version dispatch.
- `engine/mesh2param/validation.py` and `step_audit.py`: analytic shared-edge,
  trim-loop, surface inventory, and round-trip evidence.
- `engine/mesh2param/curved_fixtures.py` and
  `scripts/generate_curved_fixtures.py`: generator-only steep and composition
  fixtures.
- `tests/`: schema goldens, solver constraints, OCCT topology, determinism,
  compiler, cache, services, multi-region holes, and runtime gates.

The CADGraph schema, generated TypeScript types, web request contract, units,
defaults, and tolerance values do not change in the initial implementation.

## Acceptance criteria

The design is fully implemented only when:

- new explicit-cap artifacts use `surface-network/2` inside `curved-plate/2`;
- the patch and analytic face reference one rim curve record and one
  `TopoDS_Edge`;
- the patch is constrained to that rim during fitting;
- both pcurve attachments pass adaptive maximum-deviation gates without a
  tolerance change;
- steep-site caps no longer use a boolean and complete under the fixture budget;
- single- and multi-region holes retain their current parameterization,
  evidence, determinism, and performance;
- schema-1 artifact bytes, hashes, rebuilds, compiler behavior, and historical
  cap replay remain unchanged;
- fresh fit, repeated fit, artifact rebuild, compiler rebuild, and cache hit are
  byte-identical;
- ruff, strict mypy, and the complete frozen pytest suite pass with zero
  failures at every step.
