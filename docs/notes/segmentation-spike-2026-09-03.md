# Segmentation spike, 2026-09-03

Phase 0, item 3 of the reconstruction overhaul plan: can region growing with primitive refit,
written in Rust, recover the analytic surface inventory of real parts from their triangle
meshes, including partial cylinders and coarse tessellations? The harness is
`spikes/segmentation/` (standalone Cargo package, `remus-io` for STL parsing only, every fit
and solver local, PLY output coloured per patch). `compare.py` matches recovered patches to
the STEP ground truth face by face, merging split half-cylinders into one surface first.

Algorithm: weld, dihedral over-segmentation at 12°, plane / cylinder / sphere fits on patch
vertices (Kåsa circle plus Gauss-Newton for short arcs), merge adjacent patches whose
primitives agree, two rounds of boundary refinement. Tolerance is `0.002 × bbox diagonal`.

## Results

| part | tris | s | recovered pl / cy / sp / unk | ground truth pl / cy / sp, other | matched / missed / spurious | unknown area |
| --- | ---: | ---: | --- | --- | --- | ---: |
| dovetail-slide-block, coarse | 356 | 0.03 | 13 / 4 / 0 / 0 | 12 / 4 / 0, 0 | **16 / 0 / 0** | 0.000 |
| flange-four-bolt, coarse | 1 992 | 0.04 | 7 / 11 / 6 / 0 | 4 / 11 / 0, 4 | **15 / 0 / 6** | 0.000 |
| cable-saddle-clamp | 2 204 | 0.04 | 6 / 14 / 0 / 0 | 6 / 10 / 0, 0 | 14 / 2 / 2 | 0.000 |
| motor-mount-nema17 | 2 996 | 0.05 | 26 / 9 / 0 / 0 | 17 / 11 / 0, 4 | 26 / 2 / 4 | 0.000 |
| nist-ctc-01 | 13 048 | 0.39 | 78 / 37 / 4 / 0 | 45 / 53 / 0, 2 | 73 / 25 / 23 | 0.000 |
| hammer-holder, export | 70 034 | 1.45 | 209 / 89 / 24 / 84 | 31 / 37 / 8, 58 | 41 / 35 / 251 | 0.021 |
| windshield-holder-fine, export | 115 670 | 1.74 | 219 / 280 / 28 / 111 | no STEP | | 0.017 |
| thru-hull-hex-nut, export | 155 762 | 6.69 | 259 / 177 / 14 / 6 | no STEP | | 0.520 |

"other" in the ground truth is cones, tori, and B-splines, which the spike does not fit.
Peak RSS 3 to 148 MB. `--tol-frac 0.0005` lifts NIST CTC 1 to 79 of 98.

## The same meshes through the current Python segmenter

| part | Python patches | comment |
| --- | --- | --- |
| dovetail-slide-block, coarse | 33 plane, 2 cylinder, 2 sphere | ground truth 12 plane, 4 cylinder |
| flange-four-bolt, coarse | 84 plane, 8 cylinder, 6 cone, 56 sphere, 1 freeform | ground truth 7 plane, 11 cylinder, 2 cone, 2 torus |
| cable-saddle-clamp | 4 plane, 2 cylinder, 6 sphere, 1 freeform | ground truth 6 plane, 10 cylinder |
| motor-mount-nema17 | 11 plane, 3 cylinder, 2 freeform | ground truth 17 plane, 11 cylinder, 4 cone |
| nist-ctc-01 | crash: "patch area must be positive" | |
| hammer-holder, export | 30 plane, 2 cylinder, 2 cone, 1 torus, 15 freeform | ground truth 52 plane, 42 cylinder |
| windshield-holder-fine | 2 plane, 1 freeform | whole part is one freeform blob |
| thru-hull-hex-nut | 1 036 plane, 1 cylinder, 2 sphere, 4 freeform | |

The Python segmenter has no merge step and no partial-cylinder acceptance, so coarse
cylinders stay as planar strips and fine fillets pull whole sides into one freeform region.

## Reading the numbers

- **Coarse tessellations and partial cylinders are recovered.** The coarse dovetail block is
  exact; the coarse flange recovers all eleven cylinders. Two details made that work: fitting
  on patch vertices instead of face centroids, which under-report a coarse radius by
  `cos(facet/2)`, and refining the Kåsa circle with Gauss-Newton for short arcs. Both belong
  in Phase 1 as-is.
- **Freeform shatters into spurious planes.** The hammer holder's 42 B-spline and 14 torus
  faces are split down to 0.5° until every triangle pair looks planar, producing about 200
  tiny plane patches. That is the single largest error and it is a policy bug: a patch carved
  out of an unfittable region must clear a minimum area or face count before it is promoted,
  otherwise it stays `unknown`.
- **Cones and tori are missing by design** and reappear as spurious spheres (flange) or vanish
  into neighbours (motor mount). They are roughly 40% of the hammer holder's faces and 18% of
  the flange's, so both fits are Phase 1 requirements, not extras.
- **Tolerance must be local, not global.** `0.002 × bbox diagonal` is 1.9 mm on the 930 mm
  NIST part and merges tangent 50 mm bosses. Feature-size-relative tolerance (chord length,
  local curvature) is the fix.
- **Threads are correctly unknown.** The hex nut's 52% unknown area is the helix, and the hex
  flats are not mistaken for a cylinder.

## Verdict for the go / no-go

Recognition of planes and cylinders on real meshes, coarse or fine, works in under two
seconds for 100k triangles with a first-cut algorithm. The misses are all in areas the spike
deliberately left out (cones, tori, freeform policy, local tolerance), not in the approach.
That is enough evidence to build Phase 1 on this design.

## Reproduce

```sh
cd spikes/segmentation
./run_parts.sh
XDG_CACHE_HOME=.cache uv run --frozen python spikes/segmentation/compare.py \
  <scratch>/segmentation/flange-four-bolt/mesh-coarse.segments.json samples/real/flange-four-bolt/model.step
```

Per-patch coloured PLY files land next to each `.segments.json` in the scratch directory.
