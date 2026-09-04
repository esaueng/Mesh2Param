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
| `Analytic` | every face is a recognised surface (plane, cylinder, cone, sphere, torus) | not implemented |
| `Mixed` | analytic where recognition succeeded, faceted where it declined | not implemented |
| `Faceted` | planar facets throughout | `faceted_step` |

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

## Running the scoreboard

The scoreboard walks `samples/real/*/part.json`, runs `faceted_step`, `segment`
and `recover` on every mesh, writes `target/scoreboard.json`, prints a table,
and compares the outcome against the committed `scoreboard-baseline.json`.

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
# Subset mode: meshes up to 30,000 triangles. ~45 s. This is what CI runs.
cargo test -p mesh2param-core --test scoreboard -- --nocapture

# Everything, including the 150k-triangle exports. Minutes.
MESH2PARAM_SCOREBOARD=full cargo test -p mesh2param-core --test scoreboard -- --nocapture
```

Without `--nocapture` the table is only printed when the test fails;
`target/scoreboard.json` is written either way.

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
