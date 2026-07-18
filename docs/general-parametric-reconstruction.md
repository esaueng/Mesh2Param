# General parametric reconstruction: filleted prismatic parts

This document is the grounded implementation plan for reconstructing the G-series
general-parametric fixtures (the spanner family) into compact, editable CADGraphs
with analytic OCCT B-Reps. It continues the milestone sequence that already landed:

- **G0 (merged):** exact feature-built spanner fixtures —
  `engine/mesh2param/general_fixtures.py`, `samples/general-parametric-benchmark/`.
- **G1 (merged):** curvature-space sub-segmentation with a `fillet-band` evidence
  class — `engine/mesh2param/segmentation.py`, opt-in via
  `SegmentationSettings.enable_curvature_subsegmentation`, analysis-only.
- **G2–G4 (this plan):** route that evidence into reconstruction: sharp
  spline-profile prismatic bodies, then constant-radius fillet recovery, then
  shallow-detail policy.

It supersedes an external draft plan ("intelligent STL-to-STEP reconstruction")
that was written without repository access. Section 2 records the material
corrections this plan makes to that draft so reviewers can see the deltas
explicitly.

## 1. Measured baseline (2026-07-18)

Environment: macOS arm64, locked Python 3.12 environment, CadQuery 2.8.0,
OCP 7.9.3.1.1. Commands run from the repository root:

```sh
pnpm mesh2param -- reconstruct samples/general-parametric-benchmark/spanner-filleted/source.stl --units mm --output <dir>
```

| Fixture | Source triangles | Volume (mm³) | Current parametric outcome |
| --- | ---: | ---: | --- |
| `spanner-sharp` | 508 | 11 999.41 | rejected: stage `segmentation`, code `unsupported-freeform-remainder` — "automatic L-bracket inference requires only plane and full-cylinder patches" |
| `spanner-filleted` | 5 858 | 11 821.21 | same rejection, same code |
| `spanner-filleted-embossed` | 5 874 | 11 864.41 | same rejection, same code |

PR-G2a recorded the explicit non-parametric faceted fallback with
`pnpm general:baseline` at 1,000 deterministic samples in each direction. The
one-face-per-source-triangle inventory is evidence that this path is not a
parametric answer:

| Fixture | Faceted faces / source triangles | STEP bytes | STEP SHA-256 | P99 distance (mm) | Runtime (s) |
| --- | ---: | ---: | --- | ---: | ---: |
| `spanner-sharp` | 508 / 508 | 1 178 053 | `0446c3dfe6e3beda097ee69c8c243e3f0848b2da9103bc8893db497d802b42f3` | 3.0995e-7 | 0.605 |
| `spanner-filleted` | 5 858 / 5 858 | 14 726 732 | `1bc9f0e553d2bd16f10d567da47d56b055249bc89dca0e7b4d30d37ab7853673` | 3.3098e-7 | 5.361 |
| `spanner-filleted-embossed` | 5 874 / 5 874 | 14 763 993 | `9eea3aaebb85f9aa48792c0c9b79595e34fab7acf509c2e20ece247fa55f972f` | 3.8147e-7 | 5.208 |

The normalized STEP hashes are deterministic; runtime is measured wall-clock
evidence and is not part of the determinism claim.

The native curved path was also exercised on `spanner-filleted` through
`create_curved_conversion` and fails qualification with "expected exactly one
planar region not adjacent to the freeform patch (the bottom), found 0". The
faceted fallback remains available only as an explicit, labeled, non-parametric
operation; it is never an acceptable answer for these fixtures.

Root causes, in order of the pipeline:

1. The spanner jaw is a genuine B-spline curve (`bsplineInterpolation` through
   six points in the fixture feature tree). Its extruded side wall is one smooth
   freeform region, so the segmentation gate that admits only plane and
   full-cylinder patches rejects all three fixtures — even `spanner-sharp`.
2. On the filleted variants, the 1.5 mm top/bottom edge fillets additionally
   fragment into hundreds of per-triangle "plane" patches; there is no clean
   antipodal cap pair for the existing extrusion test.
3. Even past the segmentation gate, the prismatic profile fitter admits only
   `line` and `circularArc` segments (RMS 0.025 mm, max residual 0.075 mm) and
   cannot represent the jaw.
4. The CADGraph schema has no B-spline sketch entity (`entityBase` variants are
   point, line, polyline, rectangle, circle, circularArc, closedProfile,
   constructionAxis). A contracts change is required and is called out in G2.
5. The 0.4 mm emboss boss on the third fixture has no representation in any
   current inference path.

What already works and must not regress: the sharp line/arc prismatic path with
matched caps (L-bracket acceptance, `pnpm test:geometry`), the bounded candidate
mechanism with `candidates.json`, the validation chain (schema → OCCT build →
BRepCheck → STEP export → independent reimport → bidirectional comparison),
G1 curvature evidence, and the deterministic fixture generators.

## 2. Corrections to the external draft

The draft's instincts are mostly right — infer construction, keep candidates,
validate hard, abstain honestly, evaluator before geometry. These are also
standing Mesh2Param principles. The material corrections are:

| Draft position | Correction in this plan |
| --- | --- |
| Greenfield C++20 core with CGAL, Ceres, Eigen, pybind11/WASM boundary | Extend the existing Python engine (trimesh, NumPy, SciPy, shapely, CadQuery/OCP). The locked dependency set, the GPL license gate, the documented no-Open3D decision, spawn-isolated worker boundaries, and the linux/amd64 wheel constraint all argue against a native core. No new heavyweight dependency is introduced anywhere in this plan. |
| Epic 0: "audit the repository, capture the baseline" | The audit and baseline are already done and recorded in Section 1. The plan starts from measured behavior, not from an audit task. |
| Epics 1–9 build an evaluator, extrusion detection, plane/cylinder fitting, profile DP segmentation, candidate scoring, STEP round-trip validation | All exist. Section 3 maps each capability to exists / extend / new. The plan only funds the gaps. |
| Wrench profile = lines + circular arcs; "B-spline as a last fallback" | The actual spanner profile contains a designed B-spline jaw. A bounded B-spline profile entity is a **required** G2 deliverable with a contracts change, not a fallback. Without it even `spanner-sharp` cannot pass. |
| Mid-thickness single-slice profile extraction | Generalized to a **section stack** (Section 5.2): one pass that yields the sharp profile, the fillet radius, the emboss/blind classification, and the draft-angle rejection signal. |
| Fillet radius via offset-surface spine intersection | For prismatic V1, radius comes from a loop-global circle model fitted to section offsets vs. height, with G1 curvature bands providing grouping. The general spine method is deferred with the revolution/sweep families. |
| Fillet application "through the CAD kernel" with generic edge search | The CADGraph `filletFeature` already exists and compiles through CadQuery/OCCT with semantic `targetEdges` resolved by the compiler registry. G3 emits that feature; kernel indices are never used. |
| Evaluator gate calibrated against "18.29 % volume change" from a screenshot | Not reproducible in this repository: both current paths reject the spanner with structured errors, so there is no bad STEP to measure. Calibration instead asserts today's structured rejections, then the per-fixture numeric gates in Section 8 derived from recorded ground truth. |
| New C++ repository tree | File-level implementation map against the real tree (Section 7). |
| 12 generic PRs | 8 PRs inside G2–G4, each with an allow-list, contracts-first ordering, tests, and docs, matching CONTRIBUTING change discipline. |
| Hex "socket" as six intentional edges | The fixture is a hexagonal **through-cut** recorded as `regularPolygon` (12 mm, at (25, 0)). Recovery needs no schema addition: emit a closed profile of six constraint-snapped line entities. |
| Confidence scores everywhere | Keep the repository's evidence style: residuals, measured values, and structured rejection reasons. Confidence is reported only where it is derived from measured residuals, never as a free-floating score. |

## 3. Capability map

| Capability (draft epic) | Status | Where |
| --- | --- | --- |
| Mesh ingestion, repair, adjacency, units discipline | exists | `ingest.py`, `repair.py`, `units.py` |
| Bidirectional comparison: RMS/median/P95/P99/max, normals, volume/area, unmatched/excess, heatmap GLB | exists — add P99 regression coverage and extend with suppression masks | `comparison.py` |
| B-Rep validity, STEP export + independent reimport, structural Part 21 audit | exists | `validation.py`, `step_audit.py` |
| Extrusion detection (antipodal caps, side-normal covariance) | exists — extend for filleted caps | `prismatic.py` |
| 2-D profile DP segmentation (line, circularArc) | exists — extend with bounded B-spline segments | `prismatic.py`, new `profile_fitting.py` |
| Fillet-band triangle evidence | exists (G1, opt-in, analysis-only) — route into reconstruction | `segmentation.py` |
| Fillet radius estimation, grouping, kernel application | new | `fillets.py`, `inference.py`, `compiler.py` |
| Bounded candidates with `candidates.json`, kernel-invalid rejected before scoring | exists — new candidate builders | `inference.py`, `reconstruction.py` |
| B-spline sketch entity in CADGraph | new contracts addition | `packages/contracts`, `compiler.py` |
| Detail (emboss) suppression with masked validation | new | `details.py`, `comparison.py` |
| Deterministic ground-truth fixtures | exists (G0) — add negative family fixtures | `general_fixtures.py` |

## 4. Scope

### Supported after G2–G4

- Single watertight (or explicitly repaired) CAD-derived STL; one primary solid;
  explicit or user-confirmed units.
- Linear extrusions of a 2-D profile composed of lines, circular arcs, circles,
  and one class of bounded, low-degree B-spline segments.
- Internal profile loops, including regular-polygon through-cuts.
- Constant-radius fillets on the top and bottom outer edge loops of the
  extrusion, one radius per loop group.
- Shallow embossed/engraved details on the primary caps, in two modes:
  functional (default; suppressed with declared masked regions) and full
  (recovered as shallow additive features).
- Structured, honest rejection for everything else, with measured values.

### Deferred (unchanged from current boundaries, plus explicit items)

- Revolution, sweep, loft, and general freeform families (the existing curved
  path keeps its own qualification and scope).
- Variable-radius fillets, fillets on vertical (profile) edges, multi-edge
  corner blends, chamfers (detected and reported by the section stack;
  reconstruction lands only if a milestone is scheduled).
- Blind pockets and recesses (detected and classified; reconstructed later).
- Recovery of the exact original feature order. As now, the engine may produce
  an equivalent editable construction; the claim boundary in
  [`validation.md`](validation.md) continues to apply.

## 5. Core technical approach

### 5.1 Tolerance policy

Let `c` be the measured input tessellation chord error (estimated from curved
regions; the G-series fixtures record linear tolerance 0.005 mm / angular 0.18)
and `u` the user project tolerance. The working reconstruction tolerance is
`t = max(u, 3c)`. If the caller forces `u < 3c` on a curved source, reject with
`tolerance-below-chord-error` and measured values rather than overfitting
tessellation artifacts. Fitting residuals are always area-weighted.

Nominal-value snapping: after fitting, a dimension may snap to a simple value
(8.0 mm, 1.5 mm, 12.0 mm) when the relative deviation is below the configured
snapping tolerance (default 0.5 %). Every snap is recorded on the candidate
with its pre-snap measurement, and all validation gates are re-evaluated on the
snapped model. A snap that worsens any gate is reverted.

### 5.2 Section-stack analysis (new shared evidence engine)

For any accepted extrusion-axis hypothesis, slice the working mesh with planes
perpendicular to the axis at a deterministic set of heights: several inside each
cap/fillet zone, several across the middle, with exact positions derived from
the measured axial extent (not magic constants). Assemble each section into
ordered loops with gap bridging bounded by `t`.

Classify every boundary point by its behavior across the stack:

- **Stationary across all heights** → vertical (profile) edge. The sharp 2-D
  profile is taken from mid-thickness sections, which sit outside the fillet
  bands, and cross-checked for congruence across sections.
- **Moving outward as height approaches a cap** → top/bottom edge treatment.
  Fit the inset `i(z)` against two models: circle
  `i(z) = r − sqrt(r² − (z − (T−r))²)` (fillet, estimates radius `r` and the
  tangent-point height `T−r`) and line (chamfer, estimates angle/leg). The fit
  uses the whole loop at every band height, so it is far more robust than local
  spine methods, and it verifies radius constancy along the entire loop in one
  step. Systematic residual variation rejects the constant-radius hypothesis
  with code `variable-fillet-radius`.
- **Loop present only near a cap** → shallow detail (emboss/engrave) or blind
  feature. Record the axial span. Through-features must appear in every
  section; a loop that vanishes mid-body is classified blind and rejected for
  reconstruction in this milestone with `unsupported-blind-feature` (it is
  evidence, not noise).
- **Steady drift of the whole profile with height** → drafted walls: not a pure
  extrusion; reject with `unsupported-tapered-extrusion`.

All section evidence is exportable as debug GLB layers and is linked to source
triangle IDs, matching the existing evidence conventions.

### 5.3 Profile fitting v2

Reuse the cached dynamic program in `prismatic.py` for line/circularArc
intervals and add a third segment class:

- **Bounded B-spline segment.** Fitted over a maximal point range between two
  detected tangent/break points, clamped, non-rational, degree ≤ 3, control
  points ≤ 8, fitted by constrained least squares with a fairness
  regularization, then refined against geometric residuals. Admitted only when
  its max residual ≤ `t`, its endpoints share exact coordinates with
  neighbors, and its tangent gap at joints is within the existing joint
  tolerance. Every spline segment records an explicit uncertainty note: a
  spline is the weakest claim the profile fitter may make.
- **Regular-polygon hypothesis** for inner loops: for an all-line loop of
  `n ∈ 3..12` edges, test equal-side/equal-angle within `t`; on success snap to
  the canonical polygon and emit six (or `n`) line entities with shared exact
  coordinates. The spanner hex cut is recovered this way — no schema addition.
- Existing constraints stay: tangent line–arc transitions, collinearity,
  minimum primitive length, minimum arc sweep/sagitta, primitive and
  breakpoint penalties. Splines carry the highest penalty so lines/arcs always
  win when evidence is ambiguous.

### 5.4 Fillet recovery (G3)

1. Route G1 curvature evidence: with the fillet-band class enabled for the
   general-parametric family, band triangles provide grouping, loop
   assignment, and convexity; the section stack provides parameters.
2. Group bands by fitted radius (cluster within `t`), separately for the top
   and bottom outer loops. The spanner yields one group, radius ≈ 1.5 mm,
   covering both loops (matching the ground-truth single feature with
   `edgeSelection` on `>Z or <Z`).
3. Build the sharp body first (G2 output), then emit one CADGraph
   `filletFeature` per radius group. Edge targets are resolved to semantic
   edge identifiers through the compiler's semantic-topology registry — never
   kernel indices, never tessellation order. If the registry cannot express a
   needed selection, extend the contracts with a geometric selector rather
   than guessing identifiers.
4. Compile through the existing CadQuery/OCCT fillet path. Kernel failure
   (including fillet-order fragility) marks the candidate failed; a bounded
   alternative order (top group before bottom group, or split features) may be
   tried as separate candidates and scored normally.
5. Feature-order evidence is read from the mesh: the spanner's hex rim is
   sharp, so the cut follows the fillet (as in the ground-truth tree); a
   filleted rim would imply the opposite order and a different candidate.

### 5.5 Detail policy (G4)

The embossed fixture's boss is 18 × 6 × 0.4 mm = 43.2 mm³ ≈ 0.36 % of part
volume — large enough that silently absorbing it into a volume gate would be
dishonest, small enough that functional reconstruction should not fail.

- **Functional mode (default):** residual loops on a fitted cap are suppressed.
  The candidate records `suppressedRegions` (boundary loops, support plane,
  measured volume/area) as a reconstruction artifact. Comparison masks those
  source triangles and reports both masked and unmasked metrics; the UI labels
  the suppression explicitly. A suppressed region may not exceed a configured
  area/volume fraction, and every suppressed triangle must be inside a
  recorded region — no silent discards.
- **Full mode (opt-in):** qualifying detail loops are extruded or cut
  shallowly as additional features on the fitted cap plane and validated
  separately, exactly like the ground-truth `bossExtrude`.

### 5.6 Candidates and scoring

Keep the existing bounded-candidate machinery. Expected G3 candidate set on
`spanner-filleted`: sharp spline-profile extrusion (G2 candidate, expected to
fail distance gates on the band), one-radius filleted extrusion, split-radius
alternatives, and — only if analytic candidates fail — explicit rejection.
Scoring adds complexity penalties on top of the existing comparison score:
face count, spline segment count, control-point count, tiny edges/faces, and
unsupported operations. Kernel-invalid candidates are rejected before scoring,
per CONTRIBUTING. `candidates.json` continues to carry full snapshots and
rejection reasons for every bounded candidate.

### 5.7 Validation upgrades

- Preserve P99 in the comparison record alongside RMS/median/P95/max and add
  deterministic regression coverage for its calculation and serialization.
- Add a surface-type distribution gate to the parametric path. Classify OCCT
  `GeomAbs_SurfaceOfExtrusion` explicitly instead of folding it into `other`.
  The sharp family may contain plane, cylinder/cone, and the declared linear
  extrusion of a B-spline profile edge. A declared fillet candidate may add
  torus and B-spline surfaces produced by the kernel fillet operation. Any
  unclassified surface, any surface not justified by the candidate's declared
  operations, and one-planar-face-per-triangle output are hard failures for a
  candidate labeled parametric (the explicit faceted fallback is unaffected
  and stays labeled non-parametric).
- Add suppression-mask handling to comparison (Section 5.5).
- Keep the entire existing chain unchanged: schema → OCCT build → BRepCheck →
  normalized STEP → independent reimport → re-check → comparison → persisted
  hashes and versions.

## 6. Milestones and pull requests

Each PR states an allow-list of files, follows the contracts-first procedure
for any schema change, adds unit + integration coverage, runs the spanner
fixtures and the full Python suite, and updates docs. The standing rule from
the G0 review record applies: no work outside a PR's stated scope.

### G2 — Sharp spline-profile prismatic reconstruction

**PR-G2a — Evaluation hardening and recorded baseline.**
Allow-list: `engine/mesh2param/comparison.py`, `engine/mesh2param/validation.py`,
`scripts/run_general_baseline.py` (new), `package.json`, `tests/`, this
document, `licenses/overrides.toml`, `licenses/README.md`, and
`THIRD_PARTY_NOTICES.md` for the measured pre-existing gate reconciliation.

- Deterministic P99 regression coverage; surface-type distribution gate;
  calibration tests that assert the Section-1 structured rejections on all
  three fixtures.
- `pnpm general:baseline` records the faceted-baseline face counts/STEP sizes
  for the spanner corpus, mirroring the curved baseline table.
- Preserve the committed sample corpus without rewriting it: retain the
  historical one-part-per-million STEP volume tolerance for analytic models
  and use five parts per million only when the source or reimport contains a
  freeform surface that requires the wider OCCT p-curve allowance.
- Review the existing platform-constrained libvips package pulled by the
  Wrangler development toolchain through the repository's explicit copyleft
  policy and notices mechanism; do not add or conceal a dependency.

Gate: tests fail if the current rejection codes change silently; baseline
table committed to this document.

**PR-G2b — Section-stack extraction.**
Allow-list: `engine/mesh2param/sections.py` (new), `prismatic.py`,
`reconstruction.py` (wiring), `tests/test_sections.py` (new),
`tests/test_general_baseline.py` (calibrated filleted rejection expectations
only), debug GLB writer.

- Deterministic section stack, loop assembly with bounded gap bridging,
  stationary/moving classification, debug geometry artifacts.
- Fillet-band-aware rejection codes replace the generic
  `unsupported-freeform-remainder` for filleted prismatic sources:
  `fillet-band-detected` (routes to G3 candidates), `unsupported-tapered-extrusion`,
  `unsupported-blind-feature`.

Gate: on `spanner-sharp`, mid-thickness sections yield one closed outer loop +
one closed hexagonal inner loop, closure error < `t`, section-to-section
deviation reported; on the filleted fixtures the band inset-vs-height series
fits the circle model with radius within 0.1 mm of 1.5 (evidence only, not yet
reconstruction).

**PR-G2c — Contracts: bounded B-spline sketch entity.**
Allow-list: `packages/contracts/schema/cadgraph.schema.json` + generated
artifacts + migrations, `engine/mesh2param/compiler.py`,
`tests/test_compiler_operations.py`, docs.

- `bsplineEntity`: clamped, non-rational, degree ≤ 3, ≤ 8 control points,
  endpoints shared with neighbors; compiled through OCCT to one
  `Geom_BSplineCurve` edge; STEP export/reimport and surface-type audit
  coverage; generated CadQuery source coverage. Follows the six-step contract
  procedure in CONTRIBUTING.

Gate: a hand-written CADGraph reproducing the recorded spanner profile
compiles to a valid solid and round-trips STEP with topology and volume
stable.

**PR-G2d — Spline-aware profile fitting and sharp-body candidate.**
Allow-list: `engine/mesh2param/profile_fitting.py` (new), `prismatic.py`,
`inference.py`, `reconstruction.py`, `tests/test_prismatic_reconstruction.py`,
`tests/test_general_fixtures.py`, `tests/test_general_baseline.py` (only to
replace the obsolete calibrated `spanner-sharp` rejection with G2d success
expectations; filleted rejection calibration remains unchanged).

- B-spline segment class with penalties and uncertainty records;
  regular-polygon inner-loop hypothesis; nominal snapping policy.
- New candidate builder `analytic-prismatic-spline` emitting sketch →
  extrusion → polygon cut, with the sharp body validated end to end.

Gate: `spanner-sharp` reconstructs successfully (Section 8 gates);
`spanner-filleted*` still reject, now with `fillet-band-detected` and measured
radius evidence; no change to any curved-corpus artifact
(`pnpm samples:check` byte-stable).

### G3 — Constant-radius top/bottom fillets

**PR-G3a — Fillet-band routing and radius estimation.**
Allow-list: `engine/mesh2param/fillets.py` (new), `segmentation.py`,
`sections.py`, `tests/test_curvature_segmentation.py`, new fillet tests.

- Enable/route the fillet-band class for the general-parametric family; band
  grouping and loop assignment from curvature evidence; loop-global radius
  estimation from the section stack; `variable-fillet-radius` rejection.

Gate: on `spanner-filleted`, one radius group covering both outer loops,
estimate within 0.02 mm of 1.5 and stable along the loop; on
`spanner-sharp`, no fillet group is reported.

**PR-G3b — Fillet feature emission and validation.**
Allow-list: `engine/mesh2param/inference.py`, `reconstruction.py`, `prismatic.py`
(only to route the same bounded G2d spline decomposition from a cyclic
mid-thickness section whose tessellation splits analytic line spans),
`compiler.py` (only if the semantic registry needs a selector extension),
`packages/contracts` (only if 3a proves the registry insufficient), tests,
`docs/fallbacks.md`, `docs/validation.md`.

- Sharp body → `filletFeature` with semantic edge targets → compile → full
  validation chain; bounded candidate set with scoring and rejection reasons.

Gate: `spanner-filleted` reconstructs successfully (Section 8 gates);
repeated runs produce identical artifact hashes; `candidates.json` lists the
sharp candidate with its measured failure on the band.

### G4 — Shallow details and program hardening

**PR-G4a — Detail suppression with masked validation (functional mode).**
Allow-list: `engine/mesh2param/details.py` (new), `comparison.py`,
`reconstruction.py`, artifact/manifest writers, tests, docs.

- `suppressedRegions` artifact with loops, support plane, measured volume;
  masked + unmasked metrics; configured fraction limits; UI/API labels.

Gate: `spanner-filleted-embossed` succeeds in functional mode with the boss
declared (43.2 mm³ recorded); masked metrics meet the `spanner-filleted`
gates; no triangle is discarded outside a declared region.

**PR-G4b — Full-mode boss recovery and UI surfacing.**
Allow-list: `engine/mesh2param/details.py`, `inference.py`,
`reconstruction.py` (bounded functional/full mode routing only),
`services/api` (bounded settings), `apps/web` (feature tree, suppressed-region
overlay, reusing existing patches/residual GLB layers), tests, docs.

- Opt-in recovery of qualifying detail loops as shallow additive features
  (target: the recorded 18 × 6 × 0.4 boss within gates).
- Feature tree and diagnostics surfaced in the workspace; README path table
  updated only when the gates actually pass.

Gate: full mode recovers the boss within Section 8 gates; functional mode
remains the default.

**G4b implementation evidence (2026-07-18):** passed. The opt-in graph is
`base extrusion → constant-radius fillet → hex through-cut → additive boss`.
The recovered boss footprint is 108.0000 mm² (18 × 6 mm), measured depth is
0.400073 mm, and measured volume is 43.2079 mm³. The independently reimported
STEP has 25 faces versus 5,874 source triangles. At 1,000 deterministic samples
per direction: median 0.000123 mm, P95 0.009352 mm, P99 0.040706 mm, maximum
0.096499 mm, P95 normal error 2.85038°, and relative volume delta 0.00439%.
All Section 8 gates passed; functional mode remains the default and retained
its masked/unmasked evidence. The complete backend suite passed 279 tests with
one expected missing-attachment skip in 968.17 seconds; strict typecheck, lint,
production build, 100-file sample determinism, sixteen-step geometry acceptance,
license audit, and the general faceted baseline also passed.

### G5 (deferred, recorded for completeness)

Revolution-family detection with a turned-shaft negative fixture, vertical-edge
fillets, chamfer reconstruction from the section-stack line model, blind
pockets. No work is scheduled; the rejection codes from G2 keep these honest.

## 7. File-level implementation map

- `engine/mesh2param/sections.py` (new): section stack, loop assembly,
  stationary/moving classification, inset-model fits, debug GLB.
- `engine/mesh2param/prismatic.py`: axis/cap reuse, profile hand-off from
  sections, fillet-band-aware diagnostics.
- `engine/mesh2param/profile_fitting.py` (new): bounded B-spline segments,
  regular-polygon hypotheses, nominal snapping.
- `engine/mesh2param/fillets.py` (new): band grouping, radius estimation,
  group construction.
- `engine/mesh2param/details.py` (new): residual detail regions, suppression
  masks, shallow feature recovery.
- `engine/mesh2param/segmentation.py`: route the G1 fillet-band class into
  reconstruction for this family (default policy decided in G3a, recorded in
  `docs/fallbacks.md`).
- `engine/mesh2param/inference.py`, `reconstruction.py`: new candidate
  builders, semantic edge resolution, scoring penalties.
- `engine/mesh2param/comparison.py`: P99 regression coverage, suppression masks.
- `engine/mesh2param/validation.py`: surface-type distribution gate for the
  parametric path.
- `engine/mesh2param/compiler.py`: `bsplineEntity` compilation; fillet selector
  extension only if required.
- `packages/contracts`: `bsplineEntity` (+ generated code, migrations) via the
  standard generator; no other schema change is anticipated (polygon cuts use
  line entities; suppression is reconstruction metadata, not CADGraph).
- `scripts/run_general_baseline.py` (new) + `pnpm general:baseline`.
- `tests/`: `test_sections.py`, `test_profile_fitting.py`,
  `test_fillet_reconstruction.py`, `test_detail_suppression.py`, plus updates to
  `test_general_fixtures.py`, `test_prismatic_reconstruction.py`,
  `test_m2_reconstruction.py`.
- `docs/`: this file, plus `validation.md`, `fallbacks.md`, and the README path
  table when each milestone's gates pass.

## 8. Acceptance gates

Program-wide, with `t` from Section 5.1 (fixtures: `c ≈ 0.005` mm, default
`u = 0.05` mm ⇒ `t = 0.05` mm):

| Gate | Requirement |
| --- | --- |
| Valid closed single solid, BRepCheck pre/post export | required |
| STEP export + independent reimport, topology/volume stable | required |
| P95 bidirectional distance | ≤ 1.5 t |
| P99 bidirectional distance | ≤ 3 t |
| Maximum distance | ≤ 6 t outside declared regions |
| P95 normal error | ≤ 3° |
| Relative volume error | ≤ 0.1 % (masked regions reported separately) |
| Surface-type audit on reimport | no unclassified or triangle-per-face surfaces; only surfaces justified by declared operations (`plane`, `cylinder`/`cone`, declared spline-profile `surfaceOfExtrusion`; fillet candidates may add kernel-generated `torus`/`bspline`) |
| Triangle-per-face STEP on a parametric candidate | prohibited (hard fail) |
| Missing through-features, extra components | zero |
| Determinism | identical artifact hashes on repeated runs |
| Regression | curved corpus, samples, and L-bracket acceptance byte-stable |

Per-fixture gates, scored against the recorded ground truth as well as the
mesh:

| Fixture | Gates |
| --- | --- |
| `spanner-sharp` | family = linear extrusion; thickness 8.00 ± 0.05 mm (snapped value recorded); outer profile = 2 lines + 1 arc (R ≈ 10) + 1 declared B-spline; hex cut = 6 edges, 12.0 ± 0.05 mm parameter; ≈ 12 B-Rep faces vs 508 triangles; all program gates |
| `spanner-filleted` | all sharp gates plus one fillet group, radius 1.5 ± 0.02 mm, top + bottom outer loops; ≈ 20 faces (2 caps, 4 profile sides, 6 hex walls, 8 fillet faces) vs 5 858 triangles; hex rim sharp (cut after fillet) |
| `spanner-filleted-embossed` | functional mode: `spanner-filleted` gates on masked metrics, boss declared at 43.2 mm³ with boundary loops; full mode: boss recovered 18 × 6 × 0.4 mm within profile/depth tolerances |
| Negative fixtures | turned shaft → `unsupported-model-family`; drafted walls → `unsupported-tapered-extrusion`; blind recess → `unsupported-blind-feature`; variable radius → `variable-fillet-radius`; all existing curved negatives keep their current codes |

Failure remains structured and honest, in the repository's existing error
shape. Example for a forced too-strict tolerance:

```json
{
  "stage": "profile_fitting",
  "code": "tolerance-below-chord-error",
  "message": "Requested tolerance 0.01 mm is below 3x the measured tessellation chord error (0.0052 mm) on curved regions; fitting would track tessellation artifacts.",
  "measured": {"chordErrorMm": 0.0052, "requestedMm": 0.01, "requiredMinimumMm": 0.0156}
}
```

## 9. Agent operating rules

1. Read `docs/architecture.md`, `docs/validation.md`, `docs/fallbacks.md`,
   CONTRIBUTING, and this document before touching code. Build and run the
   baseline commands in Section 1 first; keep unrelated working-tree changes
   intact.
2. Preserve the source mesh as immutable evidence; repairs only on a recorded
   working copy. Never smooth the evidence mesh.
3. Contracts changes start in `packages/contracts/schema/cadgraph.schema.json`
   and go through the generator, migrations, compiler semantics, STEP
   round-trip tests, generated-source coverage, and docs — in that order.
4. No new runtime dependency without a documented decision in
   `docs/fallbacks.md` and a passing license gate. GPL-bearing dependencies are
   prohibited. The C++ core, CGAL, Ceres, and Open3D are not part of this plan.
5. Keep search, memory, input, operation, and job bounds explicit and
   deterministic; all randomized sampling uses the recorded seed; repeated
   runs must reproduce artifact hashes.
6. Prefer the simplest analytic model within `t`; splines are admitted only
   with recorded uncertainty; kernel-invalid candidates are rejected before
   scoring; a visually plausible result is not sufficient.
7. Every rejected hypothesis emits a structured diagnostic with measured
   values. Never export a nominally successful STEP because the file wrote.
8. One architectural capability per PR, with its allow-list; no unrelated
   refactors; docs updated in the same PR (`validation.md`, `fallbacks.md`,
   README only when gates pass).
9. Verification per PR: `pnpm test:backend` (at minimum the affected suites),
   `pnpm typecheck`, `pnpm lint`, `pnpm samples:check` (byte-stable), the
   spanner fixtures through the CLI, and `pnpm test:geometry` for the
   L-bracket acceptance. Report the metrics template below with real numbers —
   never fabricate a metric, benchmark, or test result.
10. Do not mark a task complete until its acceptance gate passes. If a gate
    fails, report the failing numbers, keep the last valid state, and stop.

Per-task report template:

```text
Task / branch / commit:
Behavior changed:
Files changed (allow-list):
Tests added:
Commands run:
Fixture results (per fixture):
  status / rejection code:
  B-Rep valid / STEP round trip:
  median / P95 / P99 / max distance (mm):
  P95 normal error (deg):
  volume error (%):
  face count (vs source triangles):
  surface types on reimport:
  recovered parameters (thickness, radius, polygon, spline residuals):
  runtime:
New diagnostics / codes:
Docs updated:
Acceptance criteria: passed / failed (with numbers)
Known limitations / next blocking task:
```

## 10. Later-stage machine learning

Unchanged in spirit from the draft, deferred until G4 passes: ML may rank
hypotheses or propose segmentations, but parameter refinement, topology,
kernel operations, and acceptance stay deterministic. The deterministic
pipeline already produces training labels for free — the G-series fixture
feature trees and `candidates.json` rejection reasons are exactly the hard
cases a model would need.

## 11. Authoritative references

- Repository: [`architecture.md`](architecture.md),
  [`validation.md`](validation.md), [`fallbacks.md`](fallbacks.md),
  [`curved-step-reconstruction.md`](curved-step-reconstruction.md),
  [`cadgraph.md`](cadgraph.md), [`../samples/README.md`](../samples/README.md),
  [`notes/g0-pr37-proposal.md`](notes/g0-pr37-proposal.md).
- Ground truth: `engine/mesh2param/general_fixtures.py` and the per-fixture
  `fixture.json` manifests under `samples/general-parametric-benchmark/`.
- OCCT: `GeomAPI_PointsToBSpline`, `BRepCheck_Analyzer`, STEP translator
  surface mapping (as already used by `compiler.py` / `validation.py`);
  CadQuery `Workplane.fillet` (existing compiler path, `compiler.py`).

## Appendix A — master prompt for the coding agent

```text
You are implementing the general-parametric reconstruction milestones for the
Mesh2Param repository.

SOURCE OF TRUTH
- Plan: docs/general-parametric-reconstruction.md (G0/G1 are already merged;
  you implement G2 → G4).
- Before writing any code, read: the plan, docs/architecture.md,
  docs/validation.md, docs/fallbacks.md, docs/cadgraph.md, CONTRIBUTING.md,
  engine/mesh2param/general_fixtures.py, and the fixture.json manifests under
  samples/general-parametric-benchmark/.
- The plan contains the measured baseline (Section 1), the per-PR allow-lists
  (Section 6), and the acceptance gates (Section 8). Follow it. If reality
  disagrees with the plan, stop and report the discrepancy with measured
  numbers instead of improvising.

ENVIRONMENT
- Python 3.12 via uv, Node 20+, pnpm 11.7.0. Setup:
    pnpm install --frozen-lockfile
    XDG_CACHE_HOME=.cache uv sync --extra dev
- Verify the baseline before changing anything. For each of spanner-sharp,
  spanner-filleted, spanner-filleted-embossed:
    pnpm mesh2param -- reconstruct samples/general-parametric-benchmark/<slug>/source.stl --units mm --output <tmpdir>
  All three must currently reject with stage "segmentation", code
  "unsupported-freeform-remainder". If they do not, stop and report.

MISSION
Implement the plan's pull requests strictly in order: PR-G2a, PR-G2b, PR-G2c,
PR-G2d, PR-G3a, PR-G3b, PR-G4a, PR-G4b. One PR = one architectural capability,
one branch (codex/g2a-…, codex/g2b-…, …), independently reviewable and
mergeable. Do not start a milestone until the previous milestone's acceptance
gates pass. Do not reorder: the contracts change (PR-G2c) lands before the
code that depends on it.

HARD RULES — violating any of these fails the task
1. Evidence: never modify the source mesh; repairs only on a recorded working
   copy; never smooth the evidence mesh.
2. Honesty: never fabricate a metric, benchmark, test, kernel-valid status, or
   STEP file. A plausible render is not evidence. Every rejected hypothesis
   produces a structured diagnostic with measured values.
3. No new runtime dependencies. No CGAL, Ceres, Open3D, Eigen, or C++ core.
   GPL-bearing dependencies are prohibited; pnpm licenses:check must pass.
4. Contracts-first: CADGraph schema changes start in
   packages/contracts/schema/cadgraph.schema.json and go through the
   generator, migrations, compiler semantics, STEP round-trip tests,
   generated-source coverage, and docs — in that order. Never hand-edit
   generated contract code.
5. Determinism: explicit bounds everywhere; recorded seeds; repeated runs
   produce identical artifact hashes. pnpm samples:check stays byte-stable;
   never change an existing fixture, sample, or curved-corpus artifact.
6. Kernel-invalid candidates are rejected before scoring. Never export a STEP
   just because the file wrote. Triangle-per-face output on a parametric
   candidate is a hard failure.
7. Scope: touch only the PR's allow-list files; no unrelated refactors; if
   scope must change, add a proposal note under docs/notes/ and stop that PR.
8. Docs land with code in the same PR (validation.md, fallbacks.md; README
   only when the gates actually pass).

PER-PR WORKFLOW
1. Declare the PR: goal, allow-list, gate(s) from the plan.
2. Reproduce and record the current behavior first.
3. Implement minimally, following existing module conventions (frozen
   dataclasses with slots, settings classes with validate(), structured
   stage/code/message errors, evidence links to source triangle IDs).
4. Add unit tests plus integration tests on the deterministic fixtures;
   existing negative cases keep their rejection codes.
5. Verify from the repo root and report real output:
     pnpm typecheck
     pnpm lint
     pnpm test:backend
     pnpm samples:check
     pnpm test:geometry
     pnpm licenses:check
     pnpm mesh2param -- reconstruct <each spanner fixture> --units mm --output <tmpdir>
     pnpm general:baseline        (after PR-G2a adds it)
6. Evaluate the PR's acceptance gate with numbers. If any gate fails: report
   the failing numbers, keep the last valid state, and stop. Do not weaken
   tolerances, patch around the gate, or relabel failure as success.
7. Report using the per-task template in plan Section 9: median/P95/P99/max
   distance, P95 normal error, volume error, face count vs source triangles,
   reimport surface types, recovered parameters, runtime, new diagnostics,
   explicit passed/failed criteria.

DEFINITION OF DONE
- spanner-sharp: validated STEP; family = linear extrusion; thickness
  8.00 ± 0.05 mm with the snapped value recorded; profile = 2 lines + 1 arc +
  1 declared B-spline; hex through-cut recovered as 6 edges, 12.0 ± 0.05 mm;
  ≈12 B-Rep faces vs 508 triangles; reimport surface audit contains only
  plane, cylinder/cone, and the declared B-spline profile's linear-extrusion
  surface.
- spanner-filleted: all sharp gates plus one fillet group, radius
  1.5 ± 0.02 mm, top+bottom outer loops, kernel-generated fillet faces;
  ≈20 faces vs 5 858 triangles.
- spanner-filleted-embossed: succeeds in functional mode with the 43.2 mm³
  boss declared in suppressedRegions; masked metrics meet the filleted gates;
  opt-in full mode recovers the 18 × 6 × 0.4 mm additive boss within gates.
- Program gates (plan Section 8): P95 ≤ 1.5t, P99 ≤ 3t, max ≤ 6t outside
  declared regions, volume error ≤ 0.1 %, zero missing through-features,
  deterministic hashes, and the full pre-existing suite (curved corpus,
  L-bracket acceptance, samples) green and byte-stable.
- Out-of-scope geometry rejects with a structured code
  (unsupported-model-family, unsupported-tapered-extrusion,
  unsupported-blind-feature, variable-fillet-radius,
  tolerance-below-chord-error) — never a guess.

FIRST ACTIONS
1. Read the documents listed above.
2. Run the setup and the three baseline commands; confirm they match plan
   Section 1. If not, stop and report.
3. Open branch codex/g2a-evaluation-baseline and begin PR-G2a.

Report after each PR with the template. Stop at the first failed gate.
```
