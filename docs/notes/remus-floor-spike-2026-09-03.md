# Remus floor spike, 2026-09-03

Phase 0, item 2 of the reconstruction overhaul plan: how far does the Remus kernel get on
STL to STEP with no Mesh2Param logic in the loop? The harness lives in
`spikes/remus-floor/` (standalone Cargo package, path dependencies on a local Remus checkout,
not part of any workspace or CI). It runs the same chain the Remus WASM bindings expose:

```
read_stl -> import_mesh -> validate -> unify_faces -> [heal_solid] -> validate -> write_step -> read_step
```

Input: every committed mesh in `samples/real/` (120 meshes over 72 parts: coarse and default
OCCT tessellations of every STEP part, plus owner and public STL/3MF exports). Remus at
commit `cbd1382f` (2026-08-31). One process per mesh, 120 s watchdog, peak RSS from
`/usr/bin/time -l`. Raw results are `results-heal.jsonl` and `results-skip-heal.jsonl` in the
session scratchpad; the tables below are computed from them.

## Headline

| chain | valid solid at the end | Remus round-trip OK | median / p90 / max ms | peak RSS |
| --- | ---: | ---: | ---: | ---: |
| with `heal_solid` | 42 / 120 | 108 / 120 | 145 / 15 980 / 71 579 | 580 MB |
| without `heal_solid` | **111 / 120** | 109 / 120 | 89 / 7 317 / 61 697 | 901 MB |

`import_mesh` alone yields a valid solid for 112 of 120 meshes. `unify_faces` keeps 111 of
those valid. `heal_solid` then breaks 69 of them: 38 by tearing closed shells open
("N boundary edges found"), 31 by leaving faces whose inner-loop count fails the Euler check.
The floor is therefore **import plus unify, no heal**: 92.5% of the corpus becomes a valid,
round-trippable faceted STEP.

By tessellation tier, without heal: coarse 40/45, default 41/45, owner STL exports 29/29,
the one 3MF export 1/1.

## What fails without heal

- 4 import rejections, all `non-manifold mesh edge between welded vertices`: the coarse and
  default OCCT tessellations of `mailbox-tray` and `nist-ctc-02`. Both are cracked kernel
  tessellations of imported STEP, the same failure the corpus audit already flags. Every
  author-exported STL imports.
- 1 mesh valid at import but not after unify: `nist-ftc-07` coarse, Euler check on a merged
  face with 44 inner loops. A face-bookkeeping bug in `unify_same_domain`, not an open shell.
- 4 other meshes invalid at import (Euler characteristic errors on shells).
- 3 STEP files Remus's own reader rejects with `ADVANCED_FACE ... leaves its plane`, and
  1 file over the reader's 128 MiB input limit (`thru-hull-hex-nut` export, 154 MB).

## Independent cross-check with OCCT

Every written STEP under 60 MB was reimported with OCCT through the corpus audit code and
checked with `BRepCheck_Analyzer`. For the heal chain, OCCT agreed with Remus's own verdict
on 104 of 106 files; the files Remus called invalid appear in OCCT as multiple solids, so
`heal_solid` is splitting shells rather than merely leaving gaps. Face counts matched
Remus's exactly for all 106.

For the no-heal chain, 106 files were checked (14 skipped: no STEP or over 60 MB). OCCT read
every one, face counts matched Remus's for all 106, and the two kernels agreed on validity
for 100 of them. Solid volume against the source mesh has a median relative error of 1e-8,
and only 1 of the 100 agreed-valid files exceeds 0.1%. The six disagreements: Remus rejects
four coarse or default NIST tessellations on its Euler check that OCCT's `BRepCheck` accepts
(`nist-ctc-04`, `nist-ctc-05` twice, `nist-ftc-07`), and OCCT reads the `bag-clip-150` and
`conduit-fitting` exports back as two solids where Remus reports one.

## What the floor means for the plan

- **Faceted STEP is solved by Remus today** for author-exported meshes, at roughly 850 bytes
  of STEP per input triangle. That is the fallback tier of the ladder, and it needs no new
  code beyond skipping `heal_solid`.
- **Face count stays proportional to triangle count.** `unify_faces` removes only 28% of
  faces corpus-wide because it merges coplanar neighbours and nothing else; a cylinder stays
  a fan of facets. Finer tessellation is strictly worse. Everything above the faceted tier
  is Phase 1 work: segmentation, primitive fitting, and face construction.
- **`heal_solid` is not usable on faceted input** in its current form. Report upstream with
  the corpus meshes as reproducers; do not put it on the product path until it stops opening
  closed shells.
- **Size and time are the browser risk, not validity.** 116k triangles took 580 MB and
  24 s natively; the 156k-triangle hex nut wrote a 154 MB STEP that the reader cannot read
  back. The Phase 2 size-based handoff to a server path, or a triangle budget, is needed.
- **Kernel-tessellated STEP is a poor mesh source.** Four of the eight import-level failures
  are OCCT tessellations of STEP, and the corpus audit shows most of those are non-watertight
  to begin with. Author exports are clean. Phase 1 mesh repair should target cracked
  tessellations specifically.

## Reproduce

```sh
cd spikes/remus-floor
MODE=skip-heal ./run_corpus.sh
```

`run_corpus.sh` finds the rustup toolchain itself; see the spike README for the exact Remus
API calls and flags.
