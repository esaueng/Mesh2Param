# Freeform STL to curved STEP reconstruction

## Decision

Mesh2Param should add a **hybrid analytic plus B-spline surface-network
reconstructor**. Analytic recognition remains the first choice for planes,
cylinders, cones, spheres, tori, and feature-derived faces. Every remaining
smooth region is partitioned into disk-like patches, parameterized in 2-D, fitted
to low-degree B-spline surfaces, and assembled into a watertight B-Rep with
shared edges and explicit pcurves.

This produces real curved STEP faces (`b_spline_surface_with_knots` or
`rational_b_spline_surface`) rather than one planar STEP face per STL triangle.
It does **not** recover the exact original CAD surface or design history. STL
contains only triangular facets, so the curved result is a tolerance-controlled
approximation inferred from incomplete data. The distinction must remain
visible in validation and UI language.

The current CadQuery 2.8.0 and OCP 7.9.3.1.1 stack is sufficient for a first
production implementation. NumPy, SciPy, and trimesh can supply the mesh,
parameterization, and sparse fitting algorithms; OCCT can build, heal, validate,
and export the final B-Rep. A new large geometry dependency is not required for
the recommended first implementation.

## What the current pipeline does

The current behavior is internally consistent but cannot generate freeform
curvature:

- `segmentation.py` recognizes only `plane` and `cylinder`. A region that fails
  both fits becomes `freeform`.
- Smooth regions are created by joining adjacent triangles whose normals differ
  by less than a fixed angle. This can turn an entire organic or blended area
  into one topologically complex freeform region, but no later stage constructs
  a surface for it.
- `reconstruction.py` rejects freeform remainder from automatic reconstruction.
- `faceted.py` intentionally builds one planar OCCT face per preserved triangle,
  sews the faces, and exports a kernel-valid faceted STEP. This is why an STL
  with a non-circular curved surface still has many small flat faces.
- `validation.py` already recognizes OCCT B-spline faces and performs the core
  solid, STEP reimport, topology, and volume checks needed by the new path.

`BRepBuilderAPI_NurbsConvert` is not a solution. OCCT documents it as converting
the geometry already supporting each face to NURBS. Applying it to a faceted
shell converts or preserves individual triangle supports; it does not infer one
smooth surface or merge triangles into a fitted patch.

## Meaning of “true curved STEP”

Three output levels should not be conflated:

1. **Faceted B-Rep**: a valid STEP solid with one planar face per source
   triangle. This is the current fallback.
2. **Approximate curved B-Rep**: analytic and B-spline surfaces bounded by B-Rep
   topology and proven within a requested tolerance of the STL. This is the
   proposed target.
3. **Recovered feature-parametric CAD**: editable sketches, dimensions, feature
   order, and exact original surfaces. This can be recovered for recognized
   mechanical cases, but cannot be guaranteed from an arbitrary STL.

The new path should be named **curved surface reconstruction** or **approximate
curved B-Rep**, not “exact conversion.” The STEP file is a true surface B-Rep;
the inferred geometry is approximate.

## Research conclusions

### Arbitrary topology requires a patch network

One tensor-product B-spline surface has a rectangular parameter domain. An
arbitrary solid, a region with handles, or a region with excessive distortion
cannot be represented robustly by one patch. Eck and Hoppe's canonical
reconstruction method therefore creates a network of quadrilateral B-spline
patches, fits the network with a sparse least-squares solve, enforces tangent
plane continuity, and refines the network until an error tolerance is met.

That is the right architectural model for Mesh2Param. Trying to fit one enormous
surface over a whole STL will fail on topology, fold its UV map, smear sharp
edges, or create an unstable high-degree surface.

### Parameterization is as important as fitting

OCCT's `GeomAPI_PointsToBSplineSurface` approximates or interpolates an ordered
2-D array of points. STL vertices are an unordered triangular graph, not a
rectangular grid. A mesh region must first be cut to a disk-like chart and mapped
to UV coordinates, or resampled into an ordered grid.

For the first implementation, use a convex-boundary harmonic/Tutte map as the
safe baseline. With positive weights and a convex boundary it provides the
useful injectivity guarantee that LSCM and ARAP do not generally provide. LSCM
or ARAP can be evaluated later as lower-distortion candidates, but their output
must be rejected when any UV triangle flips or charts overlap.

### Fitting must be sparse, robust, and adaptive

Do not interpolate every STL vertex. Interpolation reproduces tessellation
noise, creates excessive knots and control points, and defeats the purpose of
surface recovery. Fit a cubic tensor-product B-spline to area-weighted source
samples with fairness and boundary terms:

```text
min P  sum_i w_i rho(||S(u_i,v_i; P) - x_i|| / sigma)^2
       + lambda_fair ||D2 P||^2
       + lambda_boundary E_boundary
       + lambda_smooth E_G1
```

Where:

- `P` is the control net;
- `rho` is a robust loss used through iteratively reweighted least squares;
- `D2` penalizes control-net bending without flattening legitimate shape;
- boundary terms force neighboring patches to use the same topology curves;
- `E_G1` is enabled only across boundaries classified as smooth.

Start with degree 3 in U and V and a small control net. Reproject samples to the
current surface, refit, and insert knots only where distance or normal residuals
remain too high. Cap degree, spans, iterations, and control points. If the cap is
reached, split the patch instead of constructing an ill-conditioned surface.

SciPy's sparse solvers are sufficient because, for fixed UV parameters and
knots, the control points enter the B-spline equation linearly. Solve X, Y, and Z
against the same sparse basis matrix. Keep coordinates in project units, scale
the linear system for conditioning, and convert results back without silently
changing units.

### Shared topology is mandatory

Independent surfaces that merely end near one another are not a reliable
solid. Build each patch-network boundary once as a shared 3-D edge curve and
shared vertices. Project that curve onto both supporting surfaces to obtain the
two pcurves, synchronize their parameter ranges, and use the same topological
edge in both faces.

This matters in OCCT specifically:

- `BRepBuilderAPI_MakeFace` requires pcurves for wires on non-planar surfaces;
- `BRepCheck_Analyzer` checks that the 3-D curve and surface pcurve agree within
  edge tolerance and that `SameParameter`/`SameRange` are valid;
- `BRepBuilderAPI_Sewing` can assemble contiguous faces, but sewing should be a
  final bounded operation, not a substitute for common boundary construction.

G0 positional continuity is required for every joined edge. G1 tangent-plane
continuity is required across artificial chart boundaries on a visually smooth
surface. True creases remain C0 and retain a sharp semantic edge.

### OCCT plate surfaces are a fallback, not the main fitter

`GeomPlate_BuildPlateSurface` can deform a surface to meet point and curve
constraints and minimize an energy; `GeomPlate_MakeApprox` converts the result
to a bounded-degree B-spline. This is useful for holes, three- or five-sided
transition patches, and boundary-driven repair. It is less suitable as the main
large scattered-data fitter because control over sampling, robust loss, global
patch continuity, and adaptive refinement is weaker than in a dedicated sparse
fit.

## Recommended pipeline

### 1. Preserve and qualify the source

Keep the original bytes, source hash, declared units, and scale factor exactly
as the current source-bound pipeline does. Reject non-finite coordinates,
unbounded resource use, ambiguous unit changes, and degenerate topology.

Classify each connected component as:

- closed orientable manifold;
- open orientable surface;
- non-manifold or self-intersecting;
- repairable only within an explicit tolerance.

Closed manifold components may become solids. Open components may become STEP
surface models, but must not be labeled solids. Non-manifold inputs should fail
closed or use an explicit repair operation; smoothing cannot make ambiguous
topology trustworthy.

### 2. Estimate scale-aware evidence

Compute area-weighted vertex normals, principal curvature estimates, dihedral
angles, local edge length, sampling density, and suspected tessellation chordal
error. These are evidence values, not permission to change project tolerance.

Sample triangle interiors as well as vertices. Vertex-only fitting is biased by
irregular tessellation density. Use mixed-area or per-triangle area weights so a
dense local tessellation does not dominate the surface.

### 3. Recognize analytic regions first

Extend surface fitting from plane/cylinder to:

- cone;
- sphere;
- torus;
- complete and partial cylinders;
- extrusion and revolution surfaces where profile evidence supports them.

Use deterministic seeded RANSAC or region growing for hypotheses, then robust
nonlinear least squares over all inliers. Score Euclidean residual, normal
agreement, connected support, boundary consistency, and complexity. Prefer an
analytic surface only when it passes the same source-deviation gates as a
B-spline candidate.

CGAL documents Efficient RANSAC for plane, cylinder, sphere, cone, and torus,
which validates this primitive set, but its GPL/commercial dual licensing makes
direct integration unsuitable for this Apache-licensed repository without a
separate license decision. The algorithms can be implemented with the current
NumPy/SciPy stack or isolated behind a separately licensed service later.

### 4. Build a freeform patch atlas

For every remaining connected smooth region:

1. Mark source boundaries, non-manifold edges, sharp dihedral edges, persistent
   curvature ridges, and analytic/freeform interfaces.
2. Cut non-disk topology along deterministic shortest paths.
3. Seed charts by geodesic farthest-point sampling and grow them with a cost
   combining geodesic distance, normal change, and curvature variation.
4. Prefer four-sided charts; split charts with multiple boundary loops, high UV
   distortion, or poor rectangularity.
5. Merge neighboring charts only when the merged chart remains a disk and a
   small B-spline fit meets tolerance.

Variational Shape Approximation is a useful error-driven model for the
partition/merge loop: alternate between assigning triangles to proxies and
refitting proxies. Here the proxy is a low-complexity surface fit rather than
only a plane.

### 5. Parameterize and validate each chart

Map four boundary chains to a convex unit square by normalized boundary arc
length. Solve interior UV coordinates using positive harmonic weights. Record:

- signed UV triangle areas;
- minimum and maximum stretch;
- conformal and area distortion;
- boundary crowding;
- chart seam and corner identities.

Reject any fold, overlap, or near-zero UV triangle. High-distortion charts are
split and reparameterized rather than pushed into the fitter.

### 6. Fit surfaces and boundary curves

Fit shared boundary curves first using chord-length parameters, a robust cubic
B-spline approximation, preserved corners, and the project tolerance. Then fit
patch interiors with those boundary curves constrained.

Use alternating iterations:

1. solve the sparse control-net fit;
2. closest-point project samples to update UV parameters;
3. recompute distance and normal residuals;
4. update robust weights;
5. refine knots or split the chart where residual structure persists.

Use a non-rational B-spline for generic freeform patches. Preserve exact conics
as OCCT analytic surfaces rather than approximating them with rational control
nets. Rational B-splines remain available when a justified mixed representation
requires them.

### 7. Assemble and heal the B-Rep

Construct OCCT `Geom_BSplineSurface` objects from explicit poles, degrees,
knots, multiplicities, and optional weights. Build shared 3-D edges, project
pcurves, build trimmed faces, set `SameParameter`, orient shells, and sew only
within the declared linear resolution.

If sewing changes topology or requires tolerance above the project limit, reject
the candidate and return it for patch refinement. Do not raise tolerances until
the model happens to close.

### 8. Validate adaptively

Retain the existing schema, B-Rep, STEP export, independent STEP reimport,
closure, topology, volume, and tessellation gates. Add:

- exact surface-type counts before and after STEP reimport;
- symmetric source-to-result and result-to-source distances;
- per-patch RMS, P95, and maximum distance;
- per-patch normal-angle RMS, P95, and maximum;
- maximum shared-edge 3-D/pcurve deviation;
- G1 tangent mismatch on smooth patch boundaries;
- UV distortion and flipped-triangle count;
- control-point, span, and patch counts;
- comparison of source and reimport surface types, not only face/edge counts.

The global maximum-distance gate should use adaptive tessellation and targeted
resampling near high residuals. A finite random sample alone cannot prove a
maximum bound.

## CADGraph and artifact design

Do not embed a large control net directly in the main CADGraph. Add a base
feature such as `reconstructedSurfaceNetwork` that references a content-addressed
surface-network artifact and its SHA-256. The artifact should contain:

- patch IDs and source triangle evidence;
- analytic or B-spline surface definitions;
- degrees, knots, multiplicities, poles, and weights;
- shared vertices, 3-D edge curves, and per-face pcurves;
- trimming loops, orientations, and adjacency;
- intended continuity for every joined edge;
- local fit, parameterization, and confidence evidence;
- algorithm version, deterministic seed, units, and tolerances.

The compiler must resolve the artifact by hash and reconstruct the same OCCT
shape deterministically. Subsequent normal CADGraph features may then operate on
that base body. The UI should label it approximate curved B-Rep, not recovered
feature history.

## Dependency choices

### Recommended: existing Python and OCCT stack

Use trimesh for adjacency and topology, NumPy/SciPy for deterministic graph and
sparse fitting work, and OCP for geometry and topology. This keeps one runtime,
preserves the existing license envelope, and exposes all required OCCT classes
in the locked environment.

A local probe using the repository's exact versions fitted a non-round 9 by 9
wavy point grid with `GeomAPI_PointsToBSplineSurface`, thickened it into one
solid, exported and reimported STEP, passed `BRepCheck_Analyzer`, and retained
B-spline face types. The reproducible probe is
[`scripts/probe_bspline_step.py`](../scripts/probe_bspline_step.py); run it with
`uv run python scripts/probe_bspline_step.py`.

### Optional reference: PCL on_nurbs

PCL's BSD-licensed `on_nurbs` module fits and iteratively refines a B-spline
surface from unordered points and fits a trimming curve. It is a useful
algorithmic reference and benchmark. It does not solve multi-patch atlas
generation, common OCCT topology, G1 joins, or STEP solid validation, and adding
PCL would introduce a substantial C++ dependency and binding boundary. Do not
make it the first implementation dependency.

### Not recommended as a shortcut

- OCCT NURBS conversion: changes representation of existing faces; it does not
  reconstruct surfaces from triangles.
- Rhino `MeshToNURB`: explicitly duplicates each mesh polygon as a NURBS face,
  which is the same face-explosion problem.
- Unbounded “organic smoothing”: may produce a visually smooth body but does not
  prove source tolerance or preserve engineering creases.
- CGAL direct linking: technically valuable for shape detection and
  parameterization, but requires a GPL or commercial licensing decision.

Autodesk Fusion's documented `Organic` mesh conversion is a useful product
benchmark: it separates faceted, prismatic, and organic conversion and exposes
an accuracy/face-count tradeoff. Its result should not be treated as evidence
that a universally exact inverse STL conversion exists.

## Implementation sequence

### Milestone 0: benchmark and baseline (implemented)

- Add procedural ground-truth B-Rep fixtures with non-round B-spline surfaces,
  varying tessellation density, noise, units, pose, holes, and sharp creases.
- Record current faceted face count, file size, runtime, and distance metrics.
- Add negative fixtures for open, non-manifold, self-intersecting, coarse, and
  multi-body STL.

The fixture corpus lives in [`samples/curved-benchmark/`](../samples/curved-benchmark/)
and is generated deterministically by
[`scripts/generate_curved_fixtures.py`](../scripts/generate_curved_fixtures.py)
from [`engine/mesh2param/curved_fixtures.py`](../engine/mesh2param/curved_fixtures.py).
Every positive fixture derives from an exact ground-truth solid whose top face
is a real `Geom_BSplineSurface` (6-7 B-Rep faces total), so curved
reconstruction can be scored against exact geometry.
[`scripts/run_curved_baseline.py`](../scripts/run_curved_baseline.py) records
the current faceted-fallback behavior; the baseline measured on the reference
machine (macOS arm64, CadQuery 2.8.0, OCP 7.9.3.1.1, 1000 comparison samples
each direction):

| Fixture | Source triangles | Faceted faces | STEP size | Runtime | Max distance (mm) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `bspline-bump-plate` | 492 | 492 | 1167 KiB | 0.47 s | 2.1e-07 |
| `wavy-slab` | 262 | 262 | 582 KiB | 0.31 s | 4.7e-07 |
| `wavy-slab-dense` | 2784 | 2784 | 6637 KiB | 2.36 s | 5.7e-07 |
| `wavy-slab-noisy` | 262 | 262 | 617 KiB | 0.32 s | 5.5e-07 |
| `wavy-slab-inch` | 728 | 728 | 1721 KiB | 0.73 s | 6.7e-08 |
| `wavy-slab-posed` | 270 | 270 | 633 KiB | 0.33 s | 6.4e-07 |
| `wavy-slab-hole` | 510 | 510 | 1176 KiB | 0.48 s | 5.9e-07 |
| `wavy-slab-coarse` | 168 | 168 | 374 KiB | 0.33 s | 5.1e-07 |
| `open-wavy-sheet` | 1058 | rejected: `faceted_sewing_incomplete` | — | — | — |
| `non-manifold-fin` | 14 | rejected: `faceted_sewing_incomplete` | — | — | — |
| `self-intersecting-boxes` | 24 | rejected: `faceted_brep_failed` | — | — | — |
| `multi-body-boxes` | 24 | rejected: `faceted_brep_failed` | — | — | — |

The pattern to beat is explicit: the faceted fallback always produces exactly
one planar face per source triangle (the ground truth needs 6-7 curved faces)
and STEP size grows linearly with tessellation density. Distance metrics are
already excellent because planar facets reproduce the mesh exactly; the curved
path must stay within tolerance while collapsing the face count and file size
by orders of magnitude. All four invalid meshes are correctly rejected today
with structured error codes, which curved qualification must preserve.

### Milestone 1: one freeform disk patch (implemented)

- Add harmonic square parameterization with flip/distortion checks.
- Fit one cubic B-spline patch using sparse least squares and fairness.
- Combine it with analytic faces into a closed solid.
- Export/reimport STEP and require at least one actual B-spline face.
- Adaptively refine until source tolerance is met or a hard budget is reached.

This milestone proves the full vertical path without pretending to support
arbitrary topology. Implementation:

- [`engine/mesh2param/parameterization.py`](../engine/mesh2param/parameterization.py):
  square boundary mapping by arc length, positive Floater mean-value harmonic
  interior solve (geometry-aware while keeping the convex-boundary injectivity
  guarantee; uniform Tutte weights proved unusable on boundary fan
  triangulations, reaching stretch 413 on the reference fixture versus 81 with
  mean-value weights), and fold/stretch/area-distortion evidence that fails
  closed.
- [`engine/mesh2param/surface_fit.py`](../engine/mesh2param/surface_fit.py):
  clamped open-uniform cubic tensor basis, sparse area-weighted least squares
  with second-difference fairness, boundary poles pinned exactly to the crease
  rectangle (collinear poles make the natural boundary geometrically straight
  and shareable), Huber IRLS reweighting, vectorized Gauss-Newton UV
  reprojection, and span doubling capped both by budget and by sample count so
  the normal equations stay overdetermined.
- [`engine/mesh2param/curved_patch.py`](../engine/mesh2param/curved_patch.py):
  the vertical driver. Segments with the existing plane/cylinder segmentation,
  requires exactly one disk-like freeform region, fits its straight crease
  boundary and bottom plane, samples triangle interiors on an area-scaled
  barycentric lattice (straight crease edges never subdivide, so boundary fan
  triangles would otherwise leave knot spans empty), fits the patch, sews it
  with the analytic walls and bottom into one closed solid, and gates on
  B-Rep validity, surviving B-spline face type, and symmetric source
  deviation.

Measured on `bspline-bump-plate` (492 source triangles): the curved result is
a 6-face solid (5 planes + 1 B-spline, 7x7 control net) in a 20 KiB STEP versus
492 planar faces in 1167 KiB from the faceted baseline; maximum source
deviation 0.095 mm, RMS 0.014 mm, volume within 0.05 % of the exact ground
truth; the STEP reimport preserves surface types and byte-identical repeat
runs. Covered by `tests/test_curved_patch.py`.

### Milestone 2: surface-network topology

- Add deterministic chart cutting, shared boundary curves, pcurves, and common
  OCCT edges.
- Add G0 and smooth-boundary G1 evidence.
- Support multiple B-spline patches, holes, and extraordinary chart vertices.
- Add the content-addressed surface-network artifact and CADGraph base feature.

### Milestone 3: hybrid analytic/freeform reconstruction

- Expand analytic primitive recognition.
- Allow analytic and B-spline patches in one shell.
- Score alternate patch layouts and retain rejected candidates/evidence.
- Add user controls for split/merge, crease classification, and patch locking.

### Milestone 4: production hardening

- Add time, memory, patch, span, and control-point budgets.
- Parallelize independent patch fits while keeping deterministic reduction.
- Cache fits by source hash, settings, and patch evidence hash.
- Add cancellation/progress at segmentation, parameterization, fitting,
  assembly, and validation stages.
- Verify STEP import in at least OCCT plus one independent CAD application.

## Acceptance gates

A curved reconstruction is successful only when all applicable gates pass:

- source units and transforms are explicit and unchanged;
- every input triangle is accounted for or explicitly excluded with evidence;
- every chart has valid non-overlapping UVs;
- per-patch and global distance plus normal tolerances pass;
- smooth joins pass their G1 angular tolerance and crease joins remain sharp;
- all shared edge/pcurve deviations are within linear resolution;
- one expected closed positive-volume solid exists for a closed single-body
  source;
- OCCT and CadQuery validity checks pass before and after STEP export;
- STEP reimport preserves topology, volume, and surface-type classification;
- repeated runs with the same source and settings produce the same geometry
  artifact hashes;
- face count and STEP size are materially below the faceted baseline on smooth
  fixtures, without using a universal face-count target that would underfit
  complex geometry.

If geometric tolerance passes but inferred design intent is unknown, validation
may be `valid` for geometry while reconstruction metadata remains
`approximate-curved` and non-parametric. If the source is too coarse to justify
a unique surface, report the uncertainty rather than overfit it.

## File-level implementation map

- `engine/mesh2param/segmentation.py`: analytic kinds, curvature evidence,
  crease graph, and atlas seeds.
- New `engine/mesh2param/parameterization.py`: chart topology, cuts, harmonic
  UV solve, distortion checks.
- New `engine/mesh2param/surface_fit.py`: basis construction, robust sparse fit,
  reprojection, refinement, and boundary constraints.
- New `engine/mesh2param/surface_network.py`: shared curves, pcurves, OCCT face
  construction, shell assembly, and artifact serialization.
- `engine/mesh2param/reconstruction.py`: hybrid candidate orchestration and
  partial-result semantics.
- `engine/mesh2param/compiler.py`: hashed reconstructed-surface-network base
  feature.
- `engine/mesh2param/validation.py`: surface-type roundtrip, edge/pcurve,
  continuity, UV, and adaptive maximum-distance evidence.
- `packages/contracts`: new base feature and versioned artifact contract.
- `services/api`: bounded settings, job progress, cancellation, and artifact
  resolution.
- `apps/web`: curved reconstruction mode, tolerance/complexity controls,
  patch diagnostics, and explicit approximate-versus-faceted labeling.

## Authoritative references

- [STL is a triangular surface mesh](https://www.loc.gov/preservation/digital/formats/fdd/fdd000504.shtml)
- [Eck and Hoppe: automatic B-spline reconstruction of arbitrary topology](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bspline.pdf)
- [Variational Shape Approximation](https://geometry-1.cms.caltech.edu/pubs/CAD04.pdf)
- [OCCT `GeomAPI_PointsToBSplineSurface`](https://dev.opencascade.org/doc/refman/html/class_geom_a_p_i___points_to_b_spline_surface.html)
- [OCCT `GeomPlate_BuildPlateSurface`](https://dev.opencascade.org/doc/refman/html/class_geom_plate___build_plate_surface.html)
- [OCCT `GeomPlate_MakeApprox`](https://dev.opencascade.org/doc/refman/html/class_geom_plate___make_approx.html)
- [OCCT `BRepBuilderAPI_MakeFace`](https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___make_face.html)
- [OCCT `BRepBuilderAPI_Sewing`](https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___sewing.html)
- [OCCT `BRepCheck_Analyzer`](https://dev.opencascade.org/doc/refman/html/class_b_rep_check___analyzer.html)
- [OCCT STEP translator surface mapping](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html)
- [OCCT `BRepBuilderAPI_NurbsConvert`](https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___nurbs_convert.html)
- [CGAL surface parameterization methods and guarantees](https://doc.cgal.org/latest/Surface_mesh_parameterization/index.html)
- [CGAL analytic shape detection](https://doc.cgal.org/latest/Shape_detection/index.html)
- [CGAL dual licensing](https://doc.cgal.org/latest/Manual/license.html)
- [PCL trimmed B-spline fitting](https://pointclouds.org/documentation/tutorials/bspline_fitting.html)
- [PCL repository and BSD license statement](https://github.com/PointCloudLibrary/pcl)
- [Rhino `MeshToNURB` behavior](https://docs.mcneel.com/rhino/9/help/en-us/commands/meshtonurb.htm)
- [Autodesk Fusion faceted, prismatic, and organic mesh conversion](https://help.autodesk.com/view/fusion360/ENU/?guid=MESH-CONVERT-TO-SOLID)
