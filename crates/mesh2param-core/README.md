# mesh2param-core

The Phase 1 reconstruction core: **mesh bytes in, STEP bytes out**, on a B-Rep
kernel pinned by revision.

The crate is deliberately pure — no filesystem, no threads, no globals — so the
same code runs in a native test, in a worker process, and in the browser on
`wasm32-unknown-unknown` with nothing stubbed out. Callers own the bytes.

## The ladder

A part is reconstructed at the best tier that holds, falling back region by
region:

| tier | meaning | status |
| --- | --- | --- |
| `Analytic` | every face is a recognised surface (plane, cylinder, cone, sphere, torus) | `build_solid` |
| `Mixed` | analytic where recognition succeeded, faceted where it declined | `build_solid` |
| `Faceted` | planar facets throughout | `faceted_step` |

`reconstruct` runs the whole ladder — `segment` → `recover` → `build_solid` —
and falls to the rung below whenever one declines.

The faceted tier is the floor: it is what every higher tier has to beat, and the
fallback whenever a higher tier declines a region.

### What the faceted tier does, and does not, do

`import_mesh` → validate → `unify_faces` → validate → `write_step`.

`heal_solid` is **not** in the chain. On faceted input it opens or splits closed
shells: 69 of the 111 corpus solids that import as valid come out of healing
invalid (38 with boundary edges, 31 failing Euler). Filed upstream as
esaueng/remus#244. Re-measure with the scoreboard before putting it back.

A solid that is produced but invalid is not an error — it comes back with
`valid: false` and its issues. The scoreboard needs to tell "the kernel refused"
apart from "the kernel produced something questionable".

## Segmentation

`segment` is *recognition*, not reconstruction: a mesh in, a set of patches out,
each named as a plane, cylinder, cone, torus, sphere, or `Unknown`. It builds
nothing. The analytic and mixed rungs are what will consume it.

`MeshData::welded` → dihedral over-segmentation → fit → merge → boundary
refinement. The fits run on each patch's **vertices**, weighted by incident
area: a tessellation samples the analytic surface at its vertices, so a coarse
cylinder's radius is only recoverable there — a centroid fit under-reports it by
`cos(facet / 2)`, 3.4% on a 12-facet cylinder. The circle fit behind the
cylinder and the torus is Kåsa refined by Gauss-Newton on the true
point-to-circle distance, because the algebraic fit is biased on exactly the
short arcs that partial cylinders and fillet bands produce.

Primitives are tried simplest first — plane, cylinder, cone, sphere, torus — and
the **first** one inside tolerance wins. Smallest residual is the wrong rule: a
sphere has one more free parameter than a cylinder and a torus two more, so they
never fit worse, and a short cylindrical band would always be reported as a
large sphere.

### Options and defaults

| option | default | what it is for |
| --- | ---: | --- |
| `angleDeg` | 12 | dihedral threshold for the first over-segmentation |
| `tolChordFactor` | 0.35 | tolerance as a multiple of **each patch's own** median edge length |
| `tolMinFrac` / `tolMaxFrac` | 1e-4 / 0.05 | clamps on that tolerance, as fractions of the bbox diagonal |
| `minSpreadDeg` | 8 | a flat patch must never become a huge-radius cylinder |
| `maxFacetDeg` | 40 | a hex prism puts its vertices on a circle too; only the step size separates it from a coarse cylinder |
| `maxNormalDevDeg` | 12 | a cone or torus band sits inside some sphere's distance budget; only its normals give it away |
| `radiusTolFrac` | 0.002 | residual budget relative to a curved fit's own radius |
| `minMinorSweepDeg` | 20 | a torus must sweep a real arc of its tube, or a cylinder fits as a huge-major-radius torus |
| `mergeAngleDeg` / `mergeHalfAngleDeg` | 1 / 1 | when two fitted primitives are declared the same |
| `mergeRadiusFrac` / `mergeTorusRadiusFrac` | 0.01 / 0.02 | radius slack for the same |
| `maxMergeRounds` / `refineRounds` / `splitLevels` | 12 / 2 / 3 | stage caps |
| `minPatchFaces` / `shardFactor` | 6 / 5 | promotion floor for a patch carved out of an unfittable region: face count, and span in units of its own tolerance |
| `minPatchAreaFraction` | 0 | optional extra promotion floor, as a share of the whole part; off by default |
| `fitOnCentroids` | false | reproduce the old centroid-fit behaviour |

Three of these carry the fixes the Phase 0 spike
(`docs/notes/segmentation-spike-2026-09-03.md`) asked for.

**The tolerance follows feature size, not part size — and feature size varies
within one part.** A fraction of the bbox diagonal is 1.9 mm on the 930 mm NIST
part, enough to merge two tangent 50 mm bosses, and far too tight on a part
measured in centimetres; a mesh-wide median edge is 3.7 mm there and merges the
same bosses. So the tolerance is derived **per patch**, from that patch's own
median edge length, and a decision spanning two patches (a merge, a boundary
face moving) uses the looser of the two. A patch with fewer than two triangles
falls back to the mesh-wide value.

It is capped at the mesh-wide value, never above it. A patch's chords are long
either because the surface is finely modelled and gently curved, or because it
is flat and the tessellator spent two triangles on it — and the second case is
the common one, where slack buys nothing. Uncapped, a coarse flat claims a
proportionally huge budget and boundary refinement pulls half the part into it:
on the NIST plate that is a single `Unknown` blob over 53% of the area. The
useful signal is downward, where a finely tessellated boss gets the tight budget
that keeps it off its neighbour.

**A shard carved out of an unfittable region has to earn its promotion.**
Splitting such a region far enough eventually makes every triangle pair look
planar, which is how a freeform part shatters into hundreds of tiny "planes". A
patch that descends only from such splits is promoted only when it clears all of

* `minPatchFaces` triangles,
* an area of at least `(shardFactor * tol)²` — span measured in its own chords,
  because a real planar face on a CAD export is tessellated with many triangles
  across it while a shard carved from a curved region spans only the few chords
  it took to bend past the split angle,
* `minPatchAreaFraction` of the part, off by default, and
* a fit residual below a quarter of its tolerance, since a shard of a smooth
  surface fits a plane "well" only because it is small: over a short span the
  sagitta is far under the budget whatever the curvature.

Anything else stays `Unknown`, which is the honest answer; it may still be
absorbed later by an adjacent patch of the same primitive. A patch that merges
with a normally fitted neighbour loses the carved provenance entirely.

**Cones and tori are fitted, not left to reappear as spurious spheres.** Both
take their axis from the covariance of the face normals *about their mean*,
where a cone's `n . axis` is exactly constant. A cone then fits apex and half
angle by least squares on the `(axial position, radial distance)` pairs, which
are collinear for a true cone; a torus fits its tube by the same circle fit the
cylinder uses, in the `(radial distance, axial offset)` half-plane. A torus
swept more than about 140 degrees around its tube defeats the axis estimator —
fillets and rounds, which is what tori are on real parts, stay well inside that.

### Known limits

* A **coarse** cone or torus whose facet step exceeds `angleDeg` is not
  recovered: the merge stage grows patches pairwise, and two facets do not
  determine a cone axis the way they determine a cylinder axis.
* The span gate (`shardFactor`) does not separate shards from real faces as
  cleanly as intended, and its default is set by that. On `hammer-holder`'s
  freeform the surviving shards have a median area of about 100 of their own
  chords squared — they are large pieces, not slivers — so cutting them needs
  `shardFactor` near 30, while on a coarse mesh such as `cable-saddle-clamp`
  anything above 5 starts demoting genuine faces, whose whole area is only a few
  hundred chords squared. 5 is the largest value that costs nothing on the
  coarse corpus meshes. The residual gate is what actually does the work.
* Freeform stays the largest single error. Refusing to invent planes on
  `hammer-holder` cuts its inventory error from 273 to 205, but the area those
  planes used to cover becomes `Unknown` (2.6% -> 32%), because the part's 42
  b-spline faces have no primitive to be recognised as. Only cone/torus/general
  freeform handling moves that number, not promotion policy.
* `nist-ctc-01` reports roughly 41 planes against 80 in the ground truth. This
  was put down to STEP splitting coplanar adjacent faces, but the merged
  inventory measures that claim and refutes it: the part has no adjacent
  coincident face pair at all, so its 80 planes are 80 distinct surfaces and the
  gap is under-segmentation, not exporter bookkeeping.
* Merging is greedy and nothing is ever un-merged. Every accepted merge is
  re-fitted on the real union, which bounds the damage but does not undo a merge
  a later one makes wrong.

## Topology recovery

`recover` is the rung above segmentation: patches in, a **vertex / edge / loop
skeleton** out. It still builds nothing — face construction is what consumes
it — but it is where the mesh stops being the answer and the fitted surfaces
start being it.

`MeshData::welded` → boundary chains per patch pair → vertices → edge curves →
loops.

**Chains.** A mesh edge whose triangles do not all belong to one patch is a
boundary edge. Boundary edges are grouped by the unordered patch pair they
separate and linked into ordered runs of mesh vertices; a run ends at a vertex
touching three or more patches, or where the pair's own edge graph branches,
and otherwise closes into a **ring**. An edge with three or more patches on it
is skipped rather than forced into a pair: its endpoints are corners anyway,
and inventing a chain there would claim two surfaces meet along something
neither of them bounds.

**Vertices.** Every chain endpoint becomes a vertex. When all its incident
patches are analytic the point is refined by Gauss-Newton on the sum of squared
signed distances to those surfaces — a fitted corner is more accurate than a
tessellated one — but only while the fits are right, so a refinement that moves
further than `vertexSnapFactor` tolerances is thrown away and the mesh vertex
kept. Whatever survives is then merged inside one tolerance.

**Edge curves.** Between two analytic patches the chain is replaced by the real
surface-surface intersection, trimmed to the chain's own span between its end
vertices (a ring becomes a full circle or a closed polyline). Three routes
reach the kernel, because its `AnalyticSurface` has no plane arm:

| pair | kernel entry point | best case |
| --- | --- | --- |
| plane / plane | `plane_plane_intersection` | `Line` |
| plane / analytic | `exact_plane_analytic_bounded` | `Circle`, else sampled |
| analytic / analytic | `exact_cylinder_cylinder`, `exact_cone_cylinder`, `exact_sphere_cylinder`, `exact_torus_cylinder`, `exact_torus_sphere`, `exact_cone_cone`, then `intersect_analytic_analytic_bounded` | `Circle` from the `exact_*` arm, else sampled |

The kernel is asked for every branch it can see and the branch **this** chain
lies on is picked by mean distance; anything further off than
`edgeFitFactor` tolerances is not this chain's curve and is rejected. The
marching route takes v-range hints derived from the chain's own extent on each
surface — only for the cylinder and the cone, whose default ranges are a couple
of units wide; the sphere and the torus are already angular in `v`.

Everything that is not a line or a circle — an ellipse, a marched quartic —
becomes a `Polyline` tagged `marching`. Nothing downstream consumes an ellipse
yet, and demoting it is honest about that.

**Tangent pairs never reach any of that.** Where the two surface normals along
the chain differ by less than `tangentAngleDeg` — a fillet running out into its
wall, a round meeting the cylinder it blends — the intersection exists but its
*position* is ill-conditioned in the fit error: it moves like the square root
of it. The mesh's own samples beat it, so the edge is marked `tangent` and
takes the fallback.

**The fallback** is the chain's mesh samples projected onto whichever side is
analytic and fits them better, with the refined end vertices substituted for
the first and last point so adjacent edges still share a corner. `rmsDeviation`
and `maxDeviation` are recorded against the emitted curve in every case,
including the fallback, so a polyline that hides a bad fit says so.

**Loops.** Each patch's incident edges are chained into oriented loops by
vertex connectivity, a ring edge being a closed loop on its own — which is how
a full cylinder or a bore keeps a valid boundary with no vertex anywhere on it.
Which loop is outer is deliberately **not** decided here: that needs the face's
surface parameterisation, which is the next rung's job.

### Options and defaults

| option | default | what it is for |
| --- | ---: | --- |
| `tolerance` | `null` | absolute; `null` takes the segmentation's own tolerance, so the two stages agree on what "the same point" means |
| `vertexSnapFactor` | 3 | how far, in tolerances, a refined vertex may move before the refinement is rejected |
| `tangentAngleDeg` | 5 | below this angle between the two surface normals, no intersection is attempted |
| `edgeFitFactor` | 2 | how far, in tolerances, the chain samples may sit off an intersection before it is rejected as the wrong branch |
| `gridRes` | 16 | seed-grid resolution for the kernel's marching intersection |
| `refineIterations` | 12 | cap on Gauss-Newton iterations per vertex |

A `Curve::Circle` carries only centre, axis, radius and two angles. The angles
are measured in the frame the kernel derives from the axis alone — the frame
`Circle3D::new(center, axis, radius)` builds — so a consumer that rebuilds the
circle from those three numbers reproduces the parameterisation. `endAngle` is
always above `startAngle`; the arc runs counter-clockwise about `axis`.

### Known limits

* **The analytic fraction is capped by recognition, not by this stage.** On the
  fine exports most chains have an `Unknown` patch on one side and can only
  fall back: `hammer-holder/mesh-export` has 294 unknown patches out of 587 and
  576 chains with an analytic surface on *both* sides out of 3030.
  `windshield-holder-fine` is 514 of 1087, and 1255 of 5608. Freeform
  recognition is what moves those numbers.
* **About a fifth of the both-analytic chains are still rejected** — 134 of 576
  on `hammer-holder/mesh-export`, 9 of 191 on `nist-ctc-01/mesh-default` — the
  intersection of two fitted surfaces landing further than `edgeFitFactor`
  tolerances from the samples the fits came from. On a fine mesh the tolerance
  is small and a fit error of a few chords is enough.
* **No ellipse, hyperbola or parabola output.** An oblique plane through a
  cylinder or a cone has an exact conic in the kernel and this stage throws it
  away as a polyline. The kernel's topology builder takes `Ellipse` edges
  today, so this is a gap here, not upstream.
* **Marching is the slow arm.** A pair with no closed form — torus/torus,
  cone/sphere — costs tens of milliseconds per edge:
  `flange-four-bolt/mesh-coarse` spends ~700 ms on 26 edges,
  `nist-ftc-06/mesh-coarse` ~1.3 s on 497. Everything else is a few
  milliseconds per hundred edges.
* **Loop assembly is greedy.** At a vertex where four of a patch's edges meet —
  two loops touching at a point — the walk pairs them by discovery order, which
  can close the wrong two loops together. It never reports a false *open* loop,
  so the scoreboard's closure number is an upper bound.
* **`Unknown` patches are still given chains and loops**, with a polyline
  through the raw mesh vertices. They are boundaries the faceted fallback will
  need; they are just not analytic.

### Remus gaps this stage ran into

* `AnalyticSurface` has no `Plane` arm, so `intersect_analytic_analytic_bounded`
  can never be called for a pair involving a plane — the overwhelmingly common
  case on real parts. Every caller has to dispatch planes itself, to
  `exact_plane_analytic_bounded` and `plane_plane_intersection`.
* There is no plane/plane helper on the intersection module at all;
  `remus_math::plane::plane_plane_intersection` lives elsewhere and returns a
  point and a direction rather than an `ExactIntersectionCurve::Line`, so
  `ExactIntersectionCurve` has no `Line` variant to receive it.
* No exact torus/torus, torus/cone or cone/sphere arm: those fall to the
  general marcher, and its output is a fitted NURBS, never a circle, even for
  configurations (coaxial tori, a sphere centred on a cone axis) whose
  intersection is exactly a circle.

## Face construction

`build_solid` is the fourth rung and the first analytic STEP the core writes:
patches and their recovered boundaries in, a B-Rep solid and its STEP file out.
`reconstruct` is the whole ladder in one call.

### The algorithm

**Edges once, shared.** Every recovered edge becomes kernel topology exactly
once and both adjacent faces reference that same edge, so the shell is closed by
construction. `Curve::Line` becomes a line edge between the two refined corner
vertices; `Curve::Circle` becomes a `Circle3D` edge trimmed to the recovered
angles, or a closed full-turn edge with its own seam vertex when the edge is a
rim; `Curve::Polyline` becomes a chain of straight edges through the curve's own
points, or one interpolating degree-3 NURBS edge when `polylineNurbs` is on.

An edge with a **triangulated patch on either side** is always the mesh
polyline through its chain's own vertices. The triangles bound themselves with
the mesh polygon, so an analytic neighbour has to bound itself with the same
one or the shell has a slit down that boundary.

**Faces from patches.** A patch with a recognised primitive, closed loops, a
boundary the chain builder fully covered, and an orientation the mesh can give
becomes one trimmed face. The surface comes from the fitted primitive (the
cone's half angle complemented on the way across, as in topology recovery); the
face is oriented so its normal agrees with the patch's own mesh triangles.
**A plane carries the sign in its own normal and is never a reversed face; a
quadric keeps the outward normal its parameterisation defines and takes the
sign on the face's `reversed` flag.** Getting that wrong flips a face's
effective normal twice and the shell reads as inside out.

Each edge's traversal direction is decided **independently of the loop**, from
which of its two patches walks the boundary chain counter-clockwise — the mesh
half-edge answers that exactly. Two faces on one edge therefore traverse it in
opposite senses by construction, which is what the kernel's shell-orientation
check demands. The loop walk only has to put the edges in an order that joins
head to tail.

On a plane the loops are classified by **winding**, not by size: one loop winds
with the outward normal and every hole against it. Two loops winding with it is
not a face with a hole — it is a patch the segmenter merged out of two disjoint
regions of the same plane, and one face cannot bound both, so the patch is
demoted.

**Periodic faces are seamed, not holed.** A face on a cylinder, a cone, a torus
or a sphere is never an outer rim with the other rim as a hole: every structured
tessellation path in `remus_operations::tessellate` declines a curved face that
has inner wires at all, so the outer-plus-inner form validates clean and
tessellates to about a third of its volume. The conventions are the kernel's
own, read off its builders and its tessellator:

* **The wire is `rim, seam, rim⁻¹, seam⁻¹`**, both rims still whole. That is
  `extrude`'s side face over a full-circle profile
  (`crates/operations/src/extrude.rs:1198-1214`) and `revolve`'s analytic wall
  (`revolve.rs:1002-1009`). A rim is not halved to give the seam somewhere to
  land: what the band mesher reads is a cycle that winds a full turn, either one
  closed circle or a chain of arcs summing to one
  (`tessellate/nonplanar.rs:292-299`).
* **A rim is what winds, not what is round.** Which of a face's loops are rims
  is decided by net winding about the surface's own axis, measured on the loop's
  mesh polygon — the same question the kernel asks of its tessellation
  candidates. A rim arrives as one closed circle when nothing lands on it and as
  a chain of arcs when something does; a bore through the wall is closed and
  winds nothing, so it stays an inner wire.
* **Both rims seam on one meridian.** Each rim's circle comes from its own
  intersection and its normal can point either way along the shared axis, and
  `Frame3::from_normal` builds `x` as `z x candidate`, which flips with `z`: a
  rim anchored at its own `evaluate(0)` can sit half a turn from its neighbour
  and the seam between them then cuts across the body instead of running along
  it. The anchor is taken from the axis **line**, sign canonicalised.
* **The seam is a straight edge**, created once and used twice. `revolve` seams
  its walls with the original profile — an arc on a torus or a sphere — but the
  tessellator does not require that: its two-rim torus band takes "the one OPEN
  edge used exactly twice" of any curve type and reads only its ends and its
  midpoint (`nonplanar.rs:683-702`). Drawing the meridian arc instead was
  measured and is worse, because two rims recovered as arc chains meet at
  corners the mesh put wherever it liked and the meridian through one is not the
  meridian through the other.
* **A wall that runs out to a point** is `rim, seam, seam⁻¹`, the seam doubled
  between the rim and a cone's apex — the only wire
  `tessellate_cone_apex_fan_shared` accepts (`nonplanar.rs:507`).
* **A surface closed in both directions** — a whole doughnut — has no rim at all
  and is bounded by the fundamental polygon `a b a⁻¹ b⁻¹` on two degenerate seam
  edges at one vertex, as `revolve` builds one (`revolve.rs:1181-1199`).

**A marched rim is read back as the circle it is.** Topology recovery hands a
rim over as a `Curve::Circle` when the kernel had a closed form for it and as a
sampled `Curve::Polyline` when only the marcher did — a cone against a coaxial
cylinder is exactly a circle and still comes back as a thousand points. Built
literally that rim is a thousand `EdgeCurve::Line` edges, and the band mesher
counts only circles and NURBS as rim candidates and reads every line as a seam:
the band declines and the CDT fallback meshes the wrong region.
`stepped-shaft-spacer/mesh-default` is 14.5% off its own volume that way and
0.5% off with the rim read back. Three gates keep the fit honest — every sample
within a quarter tolerance of the circle and of its plane, a radius no more than
four times the ring's own extent, and a full turn of winding — and it is only
attempted where **the marcher was the only route**: both sides quadrics, and the
circle coaxial with one of them. A plane against a quadric has a closed-form arm
that returns the circle directly, so a plane-bounded ring that came back marched
is one where that arm was tried and rejected, and the samples are then the
better answer than any circle drawn through them.

Measured: the capped cylinder, the cone frustum, the pointed cone and the whole
torus each tessellate to within 0.5% of their closed-form volume, and the corpus
histogram moves from 9 analytic / 24 mixed / 66 faceted to 13 / 25 / 61.
esaueng/remus#264 stays **open**: the workaround is here, not upstream, and
`validate_solid` still accepts the inner-wire form without a word.

**Unknown and open patches become triangles**, one planar face per mesh
triangle, on the same shared vertices and edges, so the shell still closes.

**Assembly.** Shell, solid, `unify_faces`, `validate_solid`. `sew_faces` is
**not** used and neither is `make_solid_from_faces`, which is `sew_faces` under
another name: sewing rebuilds every edge as `EdgeCurve::Line` and drops each
face's inner wires, so it would delete exactly the arcs and holes this stage
exists to produce. Edges are already shared, so there is nothing for it to do.
`heal_solid` stays off for the same reason as at the faceted tier
(esaueng/remus#244).

An invalid solid is retried once with the analytic faces the validator named
demoted to triangles — the report is prose, so when no edge can be localised
every curved face is demoted, a plane bounded by the mesh polygon being the one
analytic face that cannot be in the wrong place. Still invalid, and the run
falls back to `faceted_step` with `fallbackReason` set.

**Verification is part of the tier claim.** The result is tessellated and
measured against the source mesh in both directions — source centroids and
vertices against the result, result vertices against the source — with a
uniform-grid point-to-triangle query, and its volume compared. A solid whose
volume is more than `maxVolumeError` off, or whose deviation p95 is more than
`maxDeviationFraction` of the bounding box, does not keep a tier above
`Faceted`. A hex prism recognised as a cylinder is closed, manifold, orientable
and half again too big; topology cannot see that and a caller acting on the
tier would.

### Options and defaults

| option | default | what it is for |
| --- | ---: | --- |
| `tolerance` | `null` | absolute; `null` takes the segmentation's own tolerance |
| `deflection` | `null` | verification tessellation chord; `null` takes `min(tolerance, 1e-3 x diagonal)` |
| `verify` | `true` | measure the result against the mesh; off makes `deviation` null and disables the tier gate |
| `unify` | `true` | merge same-surface adjacent faces before validating |
| `polylineNurbs` | `false` | interpolate a polyline edge instead of chaining straight edges |
| `triangleBudget` | 200000 | refuse larger meshes |
| `maxRounds` | 3 | demote-and-rebuild rounds before the faceted fallback |
| `maxVolumeError` | 0.05 | volume error, relative, above which the tier drops to `Faceted` |
| `maxDeviationFraction` | 0.02 | deviation p95, as a fraction of the diagonal, above which the same |

`polylineNurbs` is **off on measurement, not on principle**. The interpolating
curve itself is checked against its own samples before it is kept, and passes;
what fails is what the kernel does with it. A NURBS boundary edge on a
cylindrical face is collected as a rim candidate by
`tessellate_revolution_band_shared`, and the filleted block then tessellates
0.5 mm off a 4 mm part where the same points as straight edges are 0.03 mm off.
The cost of the straight edges is file size: 27 kB against 16 kB on that part.

### Known limits

* **Recognition, not assembly, is what caps the tier.** Of 99 corpus meshes
  that reach this stage, 13 come back `Analytic`, 25 `Mixed` and 61 `Faceted`.
  Most of the 61 are solids that built and validated and then failed
  verification — the shape is wrong, not the topology — and the biggest of
  those are gross: `cable-saddle-clamp/mesh-default` builds a valid 16-face
  analytic solid whose volume is 960x the mesh's, and `hex-standoff-spacer`
  reports 8 planes and 2 spheres against a ground truth of 20 planes and no
  sphere. Those are recognition failures with nothing periodic about them: the
  seam work above moved five meshes and none of the hex-prism-as-cylinder
  class.
* **A spherical face wider than about 80 degrees has no structured
  tessellation path.** `fill_sphere_cap_web` declines it outright
  (`tessellate/nonplanar.rs:2604`) and the latitude-cap path needs a second
  trimmed face on the same sphere, which a lone ball has not got — so the ball
  stud shape (a sphere with one flat cut off it) builds a valid solid that
  tessellates 59% under its volume and drops to `Faceted`. Seaming it out to
  its pole the way a cone's wall is seamed to its apex measures **worse**, 82%,
  so it is not done; a spherical dome inside the 80 degrees meshes fine.
* **A whole doughnut cannot be reached through `reconstruct`.** The face is
  built and measured (`build_solid` on a hand-written single-torus
  segmentation), but a torus swept a full turn around its tube defeats the
  segmenter's axis estimator, which breaks the mesh into eight patches instead
  of one.
* **The retry is all-or-nothing.** A solid that fails verification falls
  straight to the faceted tier rather than demoting the faces responsible and
  rebuilding, because the deviation is measured per part and not per face. A
  per-face deviation would keep the good half of those 21.
* **Euler failures are the largest topological class**, 20 of the 66. They are
  concentrated in the triangulated regions, where a patch pinched by the
  topology stage's vertex merge leaves a mesh edge whose two ends resolve to
  one kernel vertex.
* **Two mesh edges can collapse onto one kernel edge.** Topology recovery
  merges corners inside one tolerance, so two distinct mesh edges can end up
  between the same pair of kernel vertices. They are deliberately shared rather
  than kept apart: kept apart, eight more corpus parts lose their shell to
  boundary edges; shared, the edge carries four face uses and the validator
  says so. 14 of the 66 fall over on that.
* **The kernel panics on four corpus meshes** —
  `camera-support-arm/mesh-export`, `conduit-fitting/mesh-export`,
  `hinge-half-knuckle/mesh-coarse`, `motor-mount-nema17/mesh-default`:
  `index out of bounds` in the non-planar CDT at
  `crates/operations/src/tessellate/nonplanar.rs:2187`, reached from
  `tessellate_solid` on a face this stage builds. The scoreboard catches it so
  one mesh does not take the corpus with it; a product caller cannot.
* **No ellipse, hyperbola or parabola faces or edges**, because topology
  recovery does not produce them.
* **A patch merged out of two disjoint regions of one plane is demoted**
  rather than split into one face per connected component, which is what it
  should become.

### Remus gaps this stage ran into

* `sew_faces` (and `make_solid_from_faces`, its alias) rebuilds every edge as
  `EdgeCurve::Line` and drops each face's inner wires. There is no assembly
  entry point that preserves analytic edge geometry or holes, so a caller with
  correctly shared edges has to build the `Shell` and `Solid` itself.
* `tessellate_solid` panics with an out-of-bounds index in the non-planar CDT
  (`nonplanar.rs:2187`) on faces this stage produces. A tessellator should
  decline a face, not abort the process.
* Every structured tessellation path declines a curved face with inner wires,
  so a periodic band has to be expressed with a doubled seam edge. That is a
  reasonable convention, but `validate_solid` accepts the inner-wire form
  without a word and only the geometry gives it away. Filed as
  **esaueng/remus#264**, and left open: the seam is built here now (see
  "Periodic faces are seamed, not holed" above), but nothing upstream yet
  either accepts the two-rim form or rejects it with a message, so the next
  caller will find it the same way this one did.
* A spherical face wider than about 80 degrees has no structured tessellation
  path, and the CDT fallback meshes the wrong side of the rim. The latitude-cap
  path could take it, but is gated on a second trimmed face existing on the
  same sphere.
* The general marcher's output is a fitted NURBS, never a circle, even where
  the intersection is exactly one. Every caller that needs a rim has to
  recognise the circle back out of the samples itself.
* A NURBS boundary edge on a cylindrical face is treated as a rim candidate by
  the band tessellator, which then sweeps a band that is not there.

## Running the scoreboard

The scoreboard walks `samples/real/*/part.json`, runs `faceted_step`, `segment`,
`recover` and `build_solid` on every mesh, writes `target/scoreboard.json`,
prints two tables, and compares the outcome against the committed
`scoreboard-baseline.json`.

Each row carries the recognised inventory, the unknown area fraction, the STEP
ground truth from `part.json` and `inventoryError`: the total absolute miscount
over plane, cylinder, cone, torus and sphere. Parts with no STEP have no ground
truth and no error.

The ground truth is `groundTruth.surfaceInventoryMerged`, which counts analytic
surfaces rather than STEP faces: adjacent faces sharing one carrier surface (a
bore exported as two half cylinders) are one surface, which is what the
segmenter grows. `groundTruth.surfaceInventory`, the raw per-face count, is used
only for a `part.json` written before the audit grew the merged key;
`groundTruthSource` on each row records which was used. B-splines and anything
else with no primitive are ignored either way.

```bash
# Subset mode: meshes up to 30,000 triangles. ~100 s. This is what CI runs.
cargo test -p mesh2param-core --test scoreboard -- --nocapture

# Everything, including the 150k-triangle exports. Minutes.
MESH2PARAM_SCOREBOARD=full cargo test -p mesh2param-core --test scoreboard -- --nocapture

# One mesh, for looking at a single part. The baseline is not compared.
MESH2PARAM_SCOREBOARD_ONLY=hammer-holder/mesh-export \
  cargo test -p mesh2param-core --test scoreboard -- --nocapture
```

Without `--nocapture` the table is only printed when the test fails;
`target/scoreboard.json` is written either way.

Each row also carries the reconstruct block — `tier`, `facesAnalytic`,
`facesTriangle`, `facesFinal`, `valid`, `deviationP95`, `volumeRelErr`,
`stepBytes`, `ms` and `fallbackReason` — printed as its own table with a tier
histogram under it. Two things are scored: a mesh's tier may never regress
(`analytic` > `mixed` > `faceted`) and a valid reconstruction may never become
invalid. Everything else on the block is measurement, not a contract.

Each row also carries the topology block: `edges`, `analyticFraction` (the
share of edges whose curve came from a real intersection, closed-form or
marched), `tangentEdges`, `closedPatchFraction` (the share of patches all of
whose loops closed) and `maxEdgeDeviation`.

The comparison fails when a mesh that was `valid` in the baseline is not valid
now, when a mesh that did not error now errors, when a mesh's `inventoryError`
grows by more than 20% against the baseline, when its `closedPatchFraction`
falls more than 0.05 below the baseline, when topology recovery starts erroring
on a mesh it used to handle, or when a baseline mesh is missing from the run. Meshes not in the baseline are reported, not failed, so adding a
corpus part does not break the build. Recognition and topology are scored separately from the
faceted tier, and from each other, on purpose: a mesh can still build a valid
solid while the segmenter reports the wrong surfaces, and it can keep its
recognition while its patch boundaries stop closing. Loop closure is the one
topology number a face builder cannot work around — a patch whose boundary does
not close has no face — which is why it is the one with a budget.

### Re-blessing the baseline

Only after reading the diff and deciding the new numbers are the ones you want:

```bash
MESH2PARAM_SCOREBOARD_WRITE_BASELINE=1 cargo test -p mesh2param-core --test scoreboard
```

The baseline is generated in subset mode and carries no timings, so it does not
change when the machine running it does.

## Bumping the kernel pin

The kernel is a git dependency pinned by revision, never by branch: picking up a
kernel change is a deliberate act with evidence attached, not implicit drift.

1. Record the current scoreboard: `cargo test -p mesh2param-core --test scoreboard -- --nocapture > before.txt`.
2. Edit `Cargo.toml` and replace `rev = "..."` on **all four** kernel
   dependencies with the new revision. They must stay identical — a mismatch
   pulls two copies of the kernel into one build.
3. `cargo update -p remus-io -p remus-math -p remus-operations -p remus-topology`
   (or just `cargo build`, which relocks), then commit `Cargo.lock`.
4. Re-run the scoreboard. Any regression is a reason not to bump; any
   improvement is the justification for bumping.
5. If the numbers moved, re-bless the baseline in the same commit as the pin, so
   the pin and the evidence for it land together.
6. Check `[workspace.lints]` in the root `Cargo.toml` against the kernel's lint
   policy and re-sync if it moved.
