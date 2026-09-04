# Phase 0 decision: go on the Remus route

Date 2026-09-03. Closes Phase 0 of the reconstruction overhaul plan ("Mesh2Param on Remus").
Evidence: the real corpus (`samples/real`, 72 parts), the Remus floor spike
(`remus-floor-spike-2026-09-03.md`), and the segmentation spike
(`segmentation-spike-2026-09-03.md`).

## Decision

**Go.** Build `mesh2param-core` as a Rust crate on the Remus kernel, targeting `wasm32` from
the first commit, and retire the Python engine once it reaches the corpus targets.

The no-go alternative (keep OCCT and CadQuery, rewrite only segmentation in Python) is
rejected because the floor spike showed the kernel half is already there, the segmentation
spike showed the recognition half is tractable in Rust in under two seconds per 100k
triangles, and the Python path keeps the 45 second worker boot and the server-only shape.

## Why the evidence supports it

| question the plan asked | answer |
| --- | --- |
| Does Remus produce a valid faceted STEP from real meshes? | 111 of 120 corpus meshes, 29 of 29 owner STL exports, once `heal_solid` is skipped |
| Do real meshes need repair first? | Author exports: no, every one is manifold. Kernel tessellations of imported STEP: yes, 4 of 8 import failures are cracked OCCT meshes |
| Can Rust region growing recover the analytic inventory? | Exact on the coarse dovetail block, all 11 cylinders on the coarse flange; misses are confined to cones, tori, freeform policy, and tolerance scaling |
| Does the current Python engine do this? | 2 of 28 owner parts convert; the segmenter turns a coarse flange into 84 planes and 56 spheres |

## Dependency shape

- **Crate lives in this repository** as `crates/mesh2param-core` (workspace at the repo root,
  the two spikes stay standalone). Product and kernel move at different speeds, and a change
  needed in Remus is a deliberate pin bump with the scoreboard rerun, not an implicit drift.
- **Remus is a Cargo git dependency, pinned by revision.** Remus is public at
  `https://github.com/esaueng/remus`, so CI needs no credentials. Initial pin:
  `cbd1382f8ee3113ce1c42415308ab3488e641625` (2026-08-31), the revision both spikes ran on.
  Crates used: `remus-io`, `remus-topology`, `remus-math`, `remus-operations`; `remus-check`
  is reached through `remus_operations::validate`.
- **Toolchain** follows Remus: `rust-toolchain.toml` with channel `1.96.0`, edition 2024,
  target `wasm32-unknown-unknown`, components rustfmt, clippy, rust-src. CI adds a Rust job
  with a cargo cache; the existing Python and web jobs are untouched until Phase 4.
- **Lint policy** copied from Remus: deny `unsafe`, `unwrap`, `expect`, `panic`; typed errors.

## Remus items Phase 1 depends on

To be filed upstream in esaueng/remus with corpus meshes as reproducers, in priority order:

1. **`heal_solid` opens or splits closed shells on faceted input.** 69 of 111 valid solids
   become invalid (38 with boundary edges, 31 Euler failures). Reproducers: any
   `samples/real/*/mesh-coarse.stl`; `cable-saddle-clamp/mesh-default.stl` is small and
   deterministic. Until fixed, `heal_solid` stays off the product path.
2. **STEP reader input limit of 128 MiB** rejects files the writer produces (156k-triangle
   `thru-hull-hex-nut/mesh-export.stl` writes 154 MB). Either raise the limit or expose it in
   `ImportLimits`; the product also needs a triangle budget regardless.
3. **`unify_same_domain` Euler bookkeeping** on faces with many inner loops:
   `nist-ftc-07/mesh-coarse.stl` is valid at import, invalid after unify (44 inner loops).
4. **Round-trip rejections `ADVANCED_FACE ... leaves its plane`** on 3 of 120 written files,
   Remus's own writer output. Needs a tolerance-aware planarity check in the reader or a
   writer fix.
5. **Stability matrix item "inner-shell export and broader round-trip evidence pending"**:
   parts with voids need it; none of the corpus parts have voids yet, so add one.

## Phase 1 first work items, ordered by evidence

1. Faceted tier first: `import_mesh` + `unify_faces` + `validate` + `write_step`, no heal, with
   a triangle budget. Ships a valid STEP for every author-exported mesh on day one.
2. Cracked-mesh repair aimed at kernel tessellations of imported STEP: pair near-duplicate
   edges, weld with scale-relative tolerance, fill small holes. Owner exports do not need it.
3. Segmentation from the spike with three changes: minimum-area promotion so unfittable
   regions stay `unknown`, feature-relative tolerance instead of bbox-relative, and cone and
   torus fits. Keep vertex-based fitting and the Gauss-Newton circle refinement.
4. Corpus scoreboard as a cargo test before any face construction: per part, tier, matched
   surfaces against `part.json`, deviation, time.

## Targets carried forward unchanged

Phase 1 exit: 100% of corpus parts produce a valid STEP solid, at least 80% at analytic tier,
face count within 10% of ground truth on at least 90% of those, deviation p95 within
1.5 × chord tolerance, every STEP reopened by OCCT in CI.
