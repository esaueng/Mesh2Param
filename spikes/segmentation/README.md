# segmentation

A throwaway measurement spike for **Phase 0, item 3** of the reconstruction
plan: can region growing with primitive refit, in Rust, recover the analytic
surface inventory of a real part from its triangle mesh — including partial
cylinders and coarse tessellations, which the current Python segmenter cannot?

It reads an STL, segments it into patches, fits a plane / cylinder / sphere to
each, and writes the inventory as JSON plus a per-patch-coloured PLY. Nothing
is reconstructed: this measures *recognition* only.

Only `remus-io` is used, and only to parse the STL
(`remus_io::stl::reader::read_stl_with_limits`). Every fit, solver and file
writer is local, so the numbers are not confounded by kernel behaviour.

## Algorithm

**0. Weld and adjacency.** Vertices are welded on a uniform hash grid with
tolerance `1e-6 x bbox diagonal`. Degenerate triangles are dropped. An
edge → faces map gives per-face neighbours; edges with more than two owners are
counted (`nonManifoldEdges`) but still linked pairwise.

**1. Smooth over-segmentation.** Union-find over face pairs whose normals
differ by less than `--angle-deg` (default 12°).

**2. Fit.** Each patch gets a plane, a cylinder and a sphere; the **first** one
inside tolerance wins, in that order. Picking the smallest RMS instead lets a
short cylindrical band win as a large sphere — a sphere has one more free
parameter and so never fits worse — so the simplest model that is inside
tolerance is the right rule.

* plane — area-weighted PCA, normal = smallest eigenvector of the covariance
  (local cyclic Jacobi solver).
* cylinder — axis = smallest eigenvector of the area-weighted covariance of the
  face normals; points projected onto the plane ⊥ axis and fitted by a weighted
  Kåsa circle, then refined by Gauss-Newton on the true point-to-circle
  distance (the algebraic fit is biased on short arcs, i.e. exactly the partial
  cylinder case). Residual = `|distance to axis − r|`.
* sphere — algebraic least squares. Residual = `|‖p − c‖ − r|`.

Fits are computed on the patch's **vertices**, weighted by the incident patch
area, not on its face centroids. A tessellation samples the analytic surface
*at its vertices*, so a coarse cylinder's radius is only recoverable there: a
centroid fit under-reports the radius by `cos(facet/2)`, which is 3.4 % on a
12-facet cylinder and instantly fails a 2 % radius comparison.
`--fit-on centroids` restores the centroid behaviour for comparison.

Acceptance guards, all of which had to be added to stop a specific real
misfire seen on the corpus:

| guard | flag | why |
| --- | --- | --- |
| RMS ≤ `tol_frac x bboxDiag` | `--tol-frac` (0.002) | basic budget |
| RMS ≤ `radius_tol_frac x r` (curved only) | `--radius-tol-frac` (0.002) | on a 930 mm part the absolute budget is 1.9 mm — enough for two tangent 50 mm bosses to fit one 125 mm cylinder |
| normal spread > 8° (curved only) | `--min-spread-deg` | a flat patch must never become a huge-radius cylinder |
| facet step ≤ 40° around the axis | `--max-facet-deg` | a hex prism puts its vertices exactly on a circle too; only the step size separates it from a coarse cylinder |
| RMS face-normal deviation ≤ 12° | `--max-normal-dev-deg` | a cone or torus band sits inside the distance budget of some sphere; only its normals give it away |

**2b. Split what fitted nothing.** A vertical fillet is *tangent* to the planes
it joins, so a pure dihedral threshold leaks plane → fillet → plane into one
blob that fits no primitive. Any patch that fitted nothing is re-cut at
`angle/3`, then `angle/9`, down to 0.5° (`--split-levels`, default 3). Stage 3
then re-joins the pieces that really do share a surface. Without this,
`motor-mount-nema17` reports 47 % unknown area and `nist-ctc-01` 76 %.

**3. Merge.** Repeat until nothing changes (`--merge-rounds`, default 12):

* patches whose fitted primitives *agree* (planes: normals within 1° and offsets
  within tol; cylinders: axes within 1°, axis lines within tol, radii within
  1 %; spheres: centres within tol, radii within 1 %) are merged first;
* otherwise adjacent patches are **trial-merged**: fit the union and keep the
  merge if the union is a primitive inside tolerance. This is what turns a
  coarse cylinder's planar strips into one cylinder.

Two restrictions keep greedy merging honest. Only patches of the *same* fitted
type (or one that fitted nothing) may be trial-merged — a small plane tangent to
a large cylinder genuinely sits inside that cylinder's residual budget, and
allowing cross-type merges silently eats real planar faces. And a merge must fit
*everywhere*: the union's `maxResidual` must stay under `2 x tol`, not just its
area-weighted RMS, which a large well-fitting patch can otherwise hide behind.
Each accepted merge is re-fitted on the actual union before it is committed, so
a chain of merges cannot drift.

**4. Boundary refinement.** Two rounds (`--refine-rounds`): every face on a
patch boundary is re-scored against its own primitive and each neighbouring
patch's, and moves to the best one if that score is also inside tolerance. The
score is the mean surface distance at the triangle's three vertices plus its
normal deviation scaled to a length (`angle x sqrt(area)`). Patches are refitted
after each round. Finally, patches that still fitted nothing are absorbed by an
adjacent primitive whenever the union fits (two passes).

Patch ids are assigned largest-area first, so they are stable across runs.

## Build

`cargo` is not on the default PATH on this machine; the whole toolchain `bin/`
has to be on PATH, not just the `cargo` binary:

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
cargo build --release
```

`run_parts.sh` discovers a toolchain itself. This is a **standalone package**,
not a member of any workspace (note the empty `[workspace]` table in
`Cargo.toml`, which also stops Cargo from adopting a parent workspace). The
path dependency `../../../../../../remus/crates/io` resolves
`spikes/segmentation` → worktree root → `.claude/worktrees` → `.claude` →
`Mesh2Param` → `~/claude` → `remus`. `target/` is gitignored via
`spikes/*/target/`.

No `unsafe`. Bad input never panics: argument parsing, I/O and every stage run
under `catch_unwind`, and a failure is emitted as a JSON `error` field with a
non-zero exit status, so a corpus run always gets a record per part.

## Binary

```bash
segmentation --stl <path.stl> --out <dir> [--angle-deg 12] [--tol-frac 0.002]
```

Other flags: `--min-spread-deg`, `--max-facet-deg`, `--max-normal-dev-deg`,
`--radius-tol-frac`, `--merge-rounds`, `--refine-rounds`, `--split-levels`,
`--fit-on vertices|centroids`.

Writes `<out>/<stem>.segments.json` and `<out>/<stem>.segments.ply` (binary
little-endian, per-face `red green blue`, one hue per patch on a golden-angle
walk, unknown patches grey), and prints the JSON to stdout.

JSON keys: `stl`, `triangles`, `rawTriangles`, `weldedVertices`,
`nonManifoldEdges`, `bboxDiagonal`, `params`, `patches[]`
(`id`, `type`, `faces`, `area`, `rmsResidual`, `maxResidual`, and one of
`plane` / `cylinder` / `sphere`), `inventory`, `unknownAreaFraction`,
`plyPath`, `timings`.

`rmsResidual` is reported even for an `unknown` patch: it is the best candidate
fit's residual, i.e. how far off the nearest primitive was.

## Corpus runner

```bash
./run_parts.sh
```

Builds release and runs the eight probe meshes, one process each, under
`/usr/bin/time -l`, appending a JSON line per mesh (plus `slug`, `mesh`,
`wallSeconds`, `peakRssMb`, without the `patches` array) to
`$SCRATCH/segmentation/results.jsonl`. Per-part JSON and PLY land in
`$SCRATCH/segmentation/<slug>/`.

macOS has no `timeout(1)`, so the per-mesh watchdog is
`perl -e 'alarm shift; exec @ARGV' 300 ...` — `alarm` survives `exec`.

Env overrides: `SCRATCH`, `LIMIT_SEC` (default 300), `CARGO`, `ANGLE_DEG`,
`TOL_FRAC`.

## Scoring against STEP

```bash
XDG_CACHE_HOME=.cache uv run --frozen python spikes/segmentation/compare.py \
    <segments.json> samples/real/<slug>/model.step
```

Reuses `scripts/real_corpus/audit.py` (`load_step_shape`, `_sub_shapes`,
`_surface_name`). Every STEP face is reduced to its surface type and
parameters; cones, tori and b-splines are counted only. STEP faces on the same
analytic surface (a bore split into two half cylinders, a plane split by a
boolean) are then merged into one **ground-truth surface**, because the
segmenter has no reason to reproduce a kernel's face splitting.

Patches are matched greedily, largest area first, within 2° of angle, 1 % of
the bbox diagonal in distance and 2 % in radius. The table reports ground-truth
surfaces by type, recovered by type, matched / missed / spurious, and the
unknown area fraction; `<stem>.compare.json` carries the same numbers plus the
missed and spurious lists.

**Duplicates** are counted separately from spurious: two coplanar but
*disconnected* regions of a solid are two connected patches for the segmenter
and one ground-truth surface after coincident merging, so a second patch
landing on an already-matched surface is not an error.

## Known limits

* **Cones and tori are out of scope by design** — there is no cone or torus fit.
  A chamfer or a fillet ring therefore lands either in `unknown` or, worse, as a
  spurious sphere or cylinder that happens to sit inside the distance budget.
  On `flange-four-bolt` the two cones and two tori come back as four spurious
  spheres covering 17 % of the surface area.
* **Freeform parts fragment.** `hammer-holder` (Shapr3D, 42 b-spline and 14
  torus faces) shatters into hundreds of small planar patches, because splitting
  an unfittable region down to 0.5° eventually makes every triangle pair
  "planar". A minimum patch size, or refusing to promote a shard carved out of
  an unfittable region, is the obvious fix and is not implemented.
* **The absolute tolerance does not scale with feature size.** `tol_frac x
  bboxDiag` is 1.9 mm on `nist-ctc-01`; `--radius-tol-frac` compensates for
  curved fits but planes on a large part are still merged too eagerly. Running
  that part at `--tol-frac 0.0005` moves it from 48/98 to 79/98 matched.
* **Fragments of one hole in a hand-exported mesh do not always re-join.** On
  `hammer-holder` a single 3 mm bore comes back as three or four arcs of 44-90°
  whose radii agree to ~0.4 % but whose merged fit exceeds `0.002 x r`.
* Thread helices, as on `thru-hull-hex-nut`, are correctly left `unknown` (52 %
  of that part's area) — there is no primitive for them.
* Merging is greedy, and nothing is ever un-merged. Every accepted merge is
  re-validated on the real union, which bounds the damage but does not undo a
  merge that a later merge makes wrong.
* Patch adjacency is recomputed from scratch every merge round and each
  candidate pair costs a trial fit, so the cost is roughly
  `O(rounds x pairs x patch size)`. It is not a bottleneck at 156 k triangles
  (about 7 s) but it would be at 10^6.
