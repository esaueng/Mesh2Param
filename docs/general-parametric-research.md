# General parametric reconstruction of filleted mechanical parts: state of the art and recommended pipeline

Research report for the G2 ("general parametric") path: spanner-class parts — an
extruded 2-D profile (lines + arcs + freeform segments), constant-radius edge
fillets joining the caps to the walls tangentially, through-pockets, and shallow
embossed features. Commissioned against the G0 spanner fixtures
(`samples/general-parametric-benchmark/`) and the G1 curvature sub-segmentation
stage.

Every external claim below was verified during the research pass (July 2026) by
fetching the DOI/arXiv record, official documentation page, or repository.
Entries that could not be verified are explicitly flagged; see the verification
ledger at the end.

---

## (a) Ranked recommendation

### The doctrine the literature converges on

For conventional engineering objects, four independent canonical lines of work —
Várady/Martin/Cox's reverse-engineering methodology (1997, *CAD*), Attene et
al.'s primitive-fitting clustering (2006, *The Visual Computer*), Cohen-Steiner
et al.'s variational shape approximation (2004, *SIGGRAPH*), and Eck & Hoppe's
automatic B-spline reconstruction (1996, *SIGGRAPH*) — converge on the same
structural answer: **decompose first, fit per-region, never fit one smooth
surface to the whole part.** For filleted parts specifically, the Várady school
prescribes the full feature-tree recipe (Várady & Martin 2002, *Handbook of
CAGD*, ch. 21):

1. Segment into **primary surfaces** (functional: planes, cylinders, …) and
   **auxiliary surfaces** (blends/fillets) — two different classes, segmented
   with different indicators (Benkő & Várady 2004, *CAD*).
2. Fit primaries **simultaneously under geometric constraints** (parallelism,
   perpendicularity, coaxiality, tangency, equal radii) (Benkő et al. 2002,
   *CAGD*).
3. Recognize each blend as a constant-radius rolling-ball fillet: estimate
   spine, radius, and springlines (Kós, Martin & Várady 2000, *CAGD*).
4. **Suppress the blends**: extend the primaries past the band and intersect
   them to recover the sharp edges (Zhu & Menq 2002, *CAD*; Venkataraman &
   Sohoni 2001/2002, *ACM SMA*).
5. On the sharp model, the feature tree (extrude profile, pocket, holes)
   becomes recognizable (Joshi & Chang 1988, *CAD*, AAG tradition).
6. Re-apply the fillets as explicit parametric features with the measured
   radii (OCCT `BRepFilletAPI_MakeFillet`).

Commercial tools (QUICKSURFACE, Geomagic Design X) implement exactly this
ordering interactively, and add one practical shortcut worth copying: for
extruded parts, **a 2-D section through the wall band *is* the unfilleted
profile** — no B-rep surgery needed (QUICKSURFACE workflow step 5; SolidWorks
ScanTo3D Curve Wizard).

### Ranked pipeline for spanner-class parts

**Path A — section-first (recommended primary for extrusion-class parts).**
Exploits the fact that G1 already isolates the wall band and the two fillet
bands (`counts_by_curvature_class == {planar: 8, cylindrical: 1, fillet-band:
2, freeform: 0}` on `spanner-filleted`).

1. **Extrusion axis by consensus** (Horn 1984 EGI): (i) dominant antipodal
   cap-normal pair, (ii) Hough great-circle accumulator over wall normals,
   (iii) PCA of cap-rejected wall normals (axis = smallest-eigenvalue
   eigenvector). Require agreement. *Extends `prismatic.py::fit_extrusion_axis`,
   which currently assumes sharp caps.*
2. **Mid-wall mesh–plane sections** at 3–5 heights (`trimesh.intersections.
   mesh_multiplane`), away from fillet bands; validate the extrusion hypothesis
   by Procrustes congruence of the sections (the Point2Cyl invariant, used
   deterministically); filter segments by source-face normal (`return_faces`).
   The section polygon is the unfilleted profile **including** inner loops (the
   hex pocket appears as a hole loop directly).
3. **Profile fitting**: weld + order loops (`Path3D.to_planar`); RDP
   pre-decimation (Douglas–Peucker 1973); optimal breakpoint DP (Perez–Vidal
   1994); per-segment model selection line → arc (Pratt/Taubin init +
   Levenberg–Marquardt geometric polish; Al-Sharadqah & Chernov 2009) →
   B-spline (Park & Lee 2007 dominant-point refinement) for freeform segments;
   joint tangency re-fit by junction reparametrization.
   *`prismatic.py::fit_closed_line_arc_chain` already does line/arc chains with
   tangent enforcement on cap loops — generalize it to consume section loops.*
4. **Beautification** (Langbein, Marshall & Martin 2004): snap angles to simple
   fractions, cluster equal radii/lengths, snap radii/dimensions to ISO 3
   Renard numbers guarded by fit uncertainty, verify reflection symmetry
   (Mitra et al. 2006 voting) and symmetrize.
5. **Fillet analytics on the bands** (Kós et al. 2000): per-band spine
   extraction, per-section circle fits ⊥ spine tangent → radius `r(s)`;
   constant vs. evolved decision by radius variance; springlines = transverse
   departure from the fitted circle. *G1's `estimatedMinimumRadiusMm` is the
   initializer (already ≈ 1.5 mm ± 5% on the fixture).*
6. **Feature assembly**: emit CADGraph — sketch profile → `extrude` (depth =
   cap-plane separation = 8 mm) → `cutExtrude` for inner loops (hex) →
   `fillet` (radius, edge chains ordered deterministically). *`compiler.py`
   already compiles all four feature kinds, including `FilletFeature` via
   `BRepFilletAPI_MakeFillet`; the G0 fixture generator already demonstrates
   deterministic edge ordering before filleting.*
7. **Proof chain** (existing): `compare_mesh_to_shape` two-sided deviation →
   `export_step_validated` round trip → `audit_step_file` → deterministic
   artifact bytes. Add the STL faceting noise floor and the volume-delta gate
   (§Q5).

**Path B — suppression-first (general fallback; the full Várady doctrine).**
Needed when the part is not a clean extrusion (e.g., the embossed boss breaks
cap planarity badly, or walls are non-prismatic): fit primaries under
constraints (Benkő 2002), suppress blends by extend-and-intersect (Zhu & Menq
2002) using OCCT analytic surfaces (unbounded → no extension instability;
`GeomAPI_IntSS` for the sharp edge), then feed the sharp model to the same
profile/feature stages. OCCT's `BRepAlgoAPI_Defeaturing` implements
extend-and-intersect removal and can validate our own suppression by
round-trip, subject to its documented tangent-face/coverage limits.

**Rejected alternatives (with reasons):**

- **Single-patch B-spline over the whole part** (the current failing
  experiment): bridges concavities structurally — see §Q6. Refuted.
- **Learned segmentation/reconstruction** (Point2CAD, ComplexGen, ParSeNet,
  HPNet, BRepNet, Point2Cyl, …): every candidate fails at least one hard
  constraint — training-data dependence, GPU, non-commercial license, or
  B-rep-as-input circularity. Full assessment in §Q1b. Design *ideas* worth
  borrowing: Point2CAD's extend-intersect-clip assembly (= Path B), DEF's
  distance-to-feature field as a classical filter.
- **CGAL Shape Detection / Polygonal Surface Reconstruction**: GPL (or paid
  GeometryFactory license) contaminates the pipeline; RANSAC is stochastic;
  PSR is planar-only and needs a MIP solver. Reimplement the deterministic
  parts (region growing, plane intersection) in NumPy instead.
- **RANSAC primitive detection in general**: redundant with G1 curvature
  classes + existing analytic fits; keep at most as a cross-check detector
  with fixed seed.

### Milestone decomposition (small, fixture-verified)

| Milestone | Content | Acceptance (procedural ground truth) |
| --- | --- | --- |
| G2.1 Fillet analytics | Spine + per-section radius for `fillet-band` patches; springline curves; constant-vs-evolved report | `spanner-filleted`: two bands, r = 1.5 mm ± tolerance, spine ≈ perimeter offset loops |
| G2.2 Section profile | Axis consensus; mid-wall sections; loop chaining; DP breakpoints; line/arc/B-spline fit | Recovered profile entities match the fixture `featureTree.sketchProfile` (line, arc, line, B-spline) within tessellation noise; hex inner loop recovered as 6 lines, circumdiameter 12 mm |
| G2.3 Constraints + beautification | Junction-tangent joint fit; Renard/angle snapping; symmetry verification | Snapped values equal ground truth (r 1.5, depth 8, hex 12, emboss 18×6×0.4) with recorded fit-uncertainty guards |
| G2.4 Feature assembly | CADGraph emission (extrude → hex cut → fillet) via existing `compiler.py` | Compiles; `BRepCheck` + STEP reimport pass; `compare_mesh_to_shape` two-sided deviation ≤ declared tolerance vs. `spanner-filleted/source.stl` |
| G2.5 Emboss + honesty | Boss detection (cap-plane delta regions) as `bossExtrude`; unsupported-feature diagnostics | `spanner-filleted-embossed` round trip; graceful degradation list for what is *not* claimed |
| G2.6 Reporting upgrade | STL noise floor, ΔV/V gate, per-feature deviation, parsimony counts | +18%-style volume error is gated (fails closed); report states deviation vs. noise floor explicitly |

G2.1–G2.2 are the critical path and are well-trodden; G2.4 reuses the existing
compiler/validation stack; G2.5 is where the honest-failure boundaries get
written down.

---

## (b) Findings per research question

### Q1 — Segmentation-to-features

**Classic methods (all verified):**

- **Variational Shape Approximation** — Cohen-Steiner, Alliez, Desbrun (2004,
  *ACM TOG* 23(3):905–914). <https://doi.org/10.1145/1015706.1015817>. Lloyd
  iterations over proxies with exact L² (covariance) and L²,¹ (normal-field)
  metrics. On filleted parts, L²,¹ groups fillet bands coherently (they are
  developable) but boundaries land mid-blend and proxies are untyped. Useful
  only as a refinement pass, if at all. Quadric-proxy extension: Yan, Liu,
  Wang (2006, GMP). <https://doi.org/10.1007/11802914_6>.
- **Hierarchical clustering by fitting primitives** — Attene, Falcidieno,
  Spagnuolo (2006, *The Visual Computer* 22(3):181–193).
  <https://doi.org/10.1007/s00371-006-0375-x>. Recursive split until each leaf
  fits {plane, sphere, cylinder, cone}; Gauss-map votes for type. The closest
  classical match to Mesh2Param's design — G1's
  planar/cylindrical/fillet-band/freeform classes are essentially its leaf
  types. Deterministic, CPU-cheap (100k faces ≈ 8 s in 2006). Garland et al.
  (2001, I3D, <https://doi.org/10.1145/364338.364345>) quadric-error
  clustering bleeds across tangent fillets by construction — do not use for
  blend-delimited segmentation.
- **The Benkő–Várady doctrine** — *Constrained fitting in reverse engineering*
  (Benkő, Kós, Várady, Andor, Martin 2002, *CAGD* 19(3):173–205,
  <https://doi.org/10.1016/S0167-8396(01)00085-1>): simultaneous fitting of all
  surfaces under auto-detected linearized constraints; this is the layer
  between analytic fits and an engineering-credible B-rep. *Direct segmentation
  of smooth, multiple point regions* (Benkő & Várady 2002, GMP,
  <https://doi.org/10.1109/GMAP.2002.1027508>) and *Segmentation methods for
  smooth point regions of conventional engineering objects* (Benkő & Várady
  2004, *CAD* 36(6):511–523, <https://doi.org/10.1016/S0010-4485(03)00159-3>):
  sharp and smooth (G¹) boundaries are different problems needing different
  indicators; blends are an **auxiliary surface class** recognized by the
  signature κ_across ≈ 1/r, κ_along ≈ 0 — exactly what G1's quadric-fit
  principal curvatures measure. A fillet band's constant-curvature onset is the
  "separating curve" concept made concrete.
- **Foundational surveys** — Várady, Martin, Cox (1997, *CAD* 29(4):255–268,
  <https://doi.org/10.1016/S0010-4485(96)00054-1>) and Várady & Martin (2002,
  *Handbook of CAGD*, pp. 651–681,
  <https://doi.org/10.1016/B978-044451104-1/50027-7>): the feature tree is the
  *declared output* of conventional RE; blend suppression is a standard phase.
  The RE-BENCH benchmark site referenced by this school was unreachable during
  verification — treat as a real-but-unrelocated artifact, cite the papers
  instead.
- **RANSAC / CGAL** — Schnabel, Wahl, Klein (2007, *CGF* 26(2):214–226,
  <https://doi.org/10.1111/j.1467-8659.2007.01016.x>) and the CGAL Shape
  Detection manual (<https://doc.cgal.org/latest/Shape_detection/index.html>):
  octree-guided minimal samples, condensed scoring, connected-component
  support. Stochastic (seed-pinning helps but octree order still matters);
  small blends fall below `min_points`/ε; detected primitives carry no mutual
  constraints. CGAL's own manual notes Region Growing "always returns the same
  result for the same given parameters" — prefer that pattern if a second
  detector is ever needed.
- **Boundary refinement** — Lavoué, Dupont, Baskurt (2005, *CAD*
  37(9):975–987, <https://doi.org/10.1016/j.cad.2004.09.001>): curvature-tensor
  classification + marker-driven growing + **boundary rectification** (data +
  smoothness relabeling) — the stage that moves boundaries from mid-blend to
  the tangent lines. Lai et al. (2008, ACM SPM,
  <https://doi.org/10.1145/1364901.1364927>) random walks: one sparse Laplacian
  solve, deterministic given seeds; a candidate rectification engine.
- **Defeaturing / blend suppression** — Thakur, Banerjee, Gupta (2009, *CAD*
  41(2):65–80, <https://doi.org/10.1016/j.cad.2008.11.009>): taxonomy of
  simplification; robust fully-automatic defeaturing is listed as an **open
  problem** — design for graceful degradation. Zhu & Menq (2002, *CAD*
  34(2):109–123, <https://doi.org/10.1016/S0010-4485(01)00056-2>): fillet
  chains → extend supports → intersect → sharp edge; motivated precisely by
  making downstream feature recognition tractable. Venkataraman, Sohoni, Elber
  (2001, ACM SMA, <https://doi.org/10.1145/376957.376970>) classify blend
  configurations (edge/vertex/split blends); Venkataraman & Sohoni (2002, SMA,
  <https://doi.org/10.1145/566294.566295>) volumetric suppression. Joshi &
  Chang (1988, *CAD* 20(2):58–66,
  <https://doi.org/10.1016/0010-4485(88)90050-4>): the AAG baseline — the hex
  pocket is a clean concave-edge subgraph *once fillets are gone*.

### Q1b — Learned methods: honest practicality assessment

Verified finding: **none are adoptable** under the stated constraints
(deterministic, CPU-only, no training data or model downloads, Apache-2.0
product).

- **Point2CAD** (Liu, Obukhov, Wegner, Schindler 2024, CVPR Spotlight;
  <https://arxiv.org/abs/2312.04962>; code <https://github.com/prs-eth/point2cad>
  — note the prompt's `princeton-vl/Point2CAD` URL is a 404). Hybrid: external
  segmentation backbone (ParSeNet/HPNet weights) + per-shape neural-implicit
  freeform fits + deterministic extend/intersect/clip. README confirms
  CPU-feasible, **but** the license is contradictory and disqualifying: sidebar
  tag Apache-2.0, README states CC-BY-NC 4.0 non-commercial. Per-shape INR
  fitting is not bit-deterministic. Best used as a *design reference* — its
  assembly stage is Path B.
- **Point2Cyl** (Uy et al. 2022, CVPR; <https://arxiv.org/abs/2112.09329>;
  <https://github.com/mikacuy/point2cyl>): **MIT**, pretrained weights in-repo,
  but extrusion-cylinders-only output, tested on CUDA, requires downloaded
  weights. Its geometric invariants (cross-section congruence; coplanar wall
  normals) are reused in Path A as *deterministic* validators.
- **ComplexGen** (Guo et al. 2022, SIGGRAPH; <https://arxiv.org/abs/2205.14573>):
  CUDA-only (MinkowskiEngine), needs Gurobi (commercial), refinement stage
  Windows-only. Hard no.
- **ParSeNet** (Sharma et al. 2020, ECCV; <https://arxiv.org/abs/2003.12181>)
  and **HPNet** (Yan et al. 2021, ICCV; <https://arxiv.org/abs/2105.10620>):
  segmenters, not reconstructors; ABC-derived training data; licenses
  unverified.
- **BRepNet** (Lambourne et al. 2021, CVPR; <https://arxiv.org/abs/2104.00706>;
  CC BY-NC-SA), **UV-Net** (2021, CVPR; <https://arxiv.org/abs/2006.10211>),
  **JoinABLe** (2022, CVPR; <https://arxiv.org/abs/2111.12772>), **Fusion 360
  Gallery** (Willis et al. 2021, SIGGRAPH; <https://arxiv.org/abs/2010.02392>):
  all consume **native B-reps** — circular for STL→STEP. BRepNet's data
  pipeline (OCCT + pythonocc) is philosophically aligned; recyclable only as
  post-hoc feature tagging, and its license blocks that commercially.
- **ExtrudeNet** (Ren et al. 2022, ECCV; <https://arxiv.org/abs/2209.15632>):
  "unsupervised" still means dataset-trained. Research-only.
- Sharp-feature networks **EC-Net** (Yu et al. 2018, ECCV;
  <https://arxiv.org/abs/1807.06010>), **DEF** (Matveev et al. 2022, *ACM TOG*;
  <https://arxiv.org/abs/2011.15081>), **NerVE** (Zhu et al. 2023, CVPR;
  <https://arxiv.org/abs/2303.16465>): edges/consolidation components, ABC
  training data, no verified CPU+license drop-in.
- Generative CAD (**BrepGen** 2024 <https://arxiv.org/abs/2401.15563>,
  **CAD-MLLM** <https://arxiv.org/abs/2411.04954>, **Text2CAD** 2024 NeurIPS
  <https://arxiv.org/abs/2409.17106>): generation, not mesh-conditioned
  reconstruction; non-deterministic; GPU.
- Training-data dependency evidence: **ABC dataset** (Koch et al. 2019, CVPR;
  <https://arxiv.org/abs/1812.06216>) underlies nearly all of the above.
- **"SEDNet": could not be verified to exist** in the CAD reverse-engineering
  context (arXiv, Semantic Scholar, DBLP all searched). Do not cite it without
  a primary source.
- **"Zone graphs": not a neural method.** In the classic AFR literature a zone
  is a region of the Attributed Adjacency Graph where features interact;
  zone-graph decomposition is a deterministic heuristic on an *existing* B-rep
  — relevant only after STEP exists. AAGNet and BrepMFR could not be verified
  within budget (AAGNet is generally cited as a 2023 Elsevier CAD paper; treat
  as unverified). FeatureFox (Fuchs et al. 2026, <https://arxiv.org/abs/2604.26770>)
  corroborates that B-rep-graph feature recognition still requires labeled
  B-reps.

**Bottom line:** the learned literature validates the chosen architecture more
than it threatens it. If exactly one constraint were ever relaxed, "allow
downloaded weights" would make MIT-licensed Point2Cyl usable as a narrow
extrusion prior — but it adds a stochastic stage to a deterministic product for
marginal gain.

### Q2 — Fillet recognition and sharp-edge recovery

**Rolling-ball geometry (verified classics):** a constant-radius fillet is the
envelope of a ball of radius r rolling tangent to both supports S₁, S₂
(Rockwood & Owen 1987, SIAM *Geometric Modeling*, pp. 367–384 — citation
verified via deposited reference lists; Vida, Martin & Várady 1994, *CAD*
26(5):341–365, <https://doi.org/10.1016/0010-4485(94)90023-X>).

- **Spine** (ball-center locus) = intersection of the two offset surfaces
  Oᵢ = pᵢ + r·nᵢ. **Springlines** (contact curves): qᵢ = c − r·nᵢ.
- Cross-section ⊥ spine tangent at c is a circle of radius r tangent to both
  supports (Sanglikar, Koparkar & Joshi 1990, *CAGD* 7(5):399–414,
  <https://doi.org/10.1016/0167-8396(90)90003-A>; Choi & Ju 1989, *CAD*
  21(4):213–220, <https://doi.org/10.1016/0010-4485(89)90046-8>).
- Klass & Kuhn (1992, *CAGD* 9(3):185–193,
  <https://doi.org/10.1016/0167-8396(92)90016-I>): one marching computation
  family yields spine, springlines, **and** the sharp support-intersection
  curve.
- Self-intersection pathology when r exceeds a support's minimum radius of
  curvature (Hermann 1992, via the Vida survey) — screenable with G1's
  per-vertex principal curvatures.

**Radius/spine estimation from measured data — the key reference:** Kós,
Martin & Várady, *Methods to recover constant radius rolling ball blends in
reverse engineering* (2000, *CAGD* 17(2):127–160,
<https://doi.org/10.1016/S0167-8396(99)00043-6>): slice the band with planes ⊥
the estimated spine tangent; each slice's points lie near a circle of radius r;
least-squares circle fit per slice; iterate spine ↔ radius; springlines where
the transverse profile departs from the fitted circle. A variable-radius
companion method exists (Kós 2000, CIRP Design Seminar — bibliographic detail
unverified). Benkő & Várady (2004, above) supply the segmentation-side
justification: separating the band *before* fitting primaries prevents fillet
points from biasing the plane/cylinder fits — the main accuracy hazard for
extend-and-intersect.

**Sharp recovery:** Zhu & Menq (2002, above) is the archetype: delete fillet
faces, extend underlying faces, intersect to rebuild sharp edges, with explicit
sequencing for interacting fillets; fails when an underlying face cannot extend
over the fillet footprint. Várady & Rockwood, *Geometric construction for
setback vertex blending* (1997, *CAD* 29(6):413–425,
<https://doi.org/10.1016/S0010-4485(96)00070-X>): fillets terminate at setback
lines; the corner is an n-sided patch; a Y-junction is the 3-sided generic
case.

**OCCT 7.9 implementation surface (fetched from dev.opencascade.org; refman now
labeled 8.0.0, API identical in the 7.9 lineage):**

- `BRepFilletAPI_MakeFillet(S, ChFi3d_Rational)` — rational keeps cross-sections
  as exact NURBS circles. `Add(r, E)`; evolved blends `Add(R1,R2,E)`,
  `Add((u,r)[] , E)`, `Add(Law_Function, E)` (laws must stay positive; never
  validated). `SetContinuity(GeomAbs_C1, tol)`. **No setback API** — vertex
  blends are automatic, with the documented restriction that a contour endpoint
  shared by **≥ 4 edges is unsupported**, and fillet/face intersection must be
  fully contained in the face (blend overflow). Failure introspection:
  `NbFaultyContours/Vertices`, `StripeStatus(IC)` →
  `ChFiDS_StartsolFailure` (radius too big), `ChFiDS_TwistedSurface`
  (self-intersecting sweep), `ChFiDS_WalkingFailure` (spine marching
  breakdown); partial results via `HasResult()/BadShape()`. Docs quote: "there
  may be instances where the algorithm fails… they only become evident at the
  construction stage."
- Extend-and-intersect: analytic supports are unbounded — "extension" is just
  re-trimming; intersect with `GeomAPI_IntSS(S1, S2, tol)` (user guide,
  verified) or `BRepAlgoAPI_Common/Section` when pcurves/tolerance matter.
  `GeomLib::ExtendSurfByLength` exists for bounded B-splines but converts to
  B-spline and warns extensions "should not be too large" — prefer refitting
  analytic primaries instead.
- `BRepAlgoAPI_Defeaturing` (since 7.3): documented algorithm is literally
  "extend the adjacent faces to cover the feature… rebuild" — i.e., OCCT's own
  suppression; documented limits: adjacent faces "should not be tangent to each
  other", extended faces must cover the feature completely, INTERNAL parts not
  processed, per-feature failure warns `BOPAlgo_AlertUnableToRemoveTheFeature`
  and continues.
- User guide's corner-gap note: differing adjacent fillet radii can leave a gap
  requiring a filling surface (`GeomFill_ConstrainedFilling`).
- `BRepFilletAPI_MakeFilletOn` returned **404** in the current refman — use
  `MakeFillet` (3-D) / `MakeFillet2d` (planar faces) as documented entry
  points.

**Failure modes and mitigations** (full table in §c-A8): variable-radius
misread as constant → per-section radius + evolved replay; Y-junctions →
automatic for ≤ 3 edges; blend overflow → cap r by face width; self-intersecting
ball → screen r vs. 1/κ_min(support); near-tangent supports → dihedral
threshold, skip defilleting; sequenced vs. simultaneous filleting → one
`MakeFillet` build for tangent-continuous edge sets, replay in reverse
suppression order; contaminated circle fits → central-band-only sampling.

### Q3 — Profile recovery for extrusions

All verified; full recipe in §c-A2…A6.

- **Axis detection** — Horn, *Extended Gaussian Images* (1984, *Proc. IEEE*
  72(12):1671–1686, <https://doi.org/10.1109/PROC.1984.13073>): extruded solids
  have an EGI signature of an antipodal cap pair + a wall-normal great circle.
  Consensus of three deterministic detectors recommended. Context: Han, Pratt &
  Regli (2000, *IEEE TRA* 16(6):782–796, <https://doi.org/10.1109/70.897789>)
  on 2.5-D features; Point2Cyl's congruence/coplanarity invariants as
  validators.
- **Sectioning** — `trimesh.intersections.mesh_multiplane` (docs verified:
  <https://trimesh.org/trimesh.intersections.html>): signed-distance straddle
  test per triangle, segments at t = d₀/(d₀−d₁); chaining in `trimesh.path` by
  merge-digit endpoint welding; `Path3D.to_planar().polygons_full` gives
  oriented loops (exterior CCW, holes CW). Engineer around: vertex-on-plane
  degenerates (nudge plane), weld tolerance tied to STL chordal deviation,
  spurious segments filtered by source-face normal (`return_faces=True`, keep
  n·axis ≈ 0), section heights away from fillet bands.
- **Breakpoints** — Douglas & Peucker (1973, *Cartographica* 10(2):112–122,
  <https://doi.org/10.3138/FM57-6770-U75U-7727>) for pre-decimation only;
  Perez & Vidal, *Optimum polygonal approximation of digitized curves* (1994,
  *Pattern Recognition Letters* 15(8):743–750,
  <https://doi.org/10.1016/0167-8655(94)90002-7>) for the optimal DP (O(N²)
  with O(1) prefix-sum segment errors); Teh & Chin (1989, *TPAMI*
  11(8):859–872, <https://doi.org/10.1109/34.31447>) dominant points and
  curvature zero-crossings as candidate generators. **No maintained Python
  implementation of the DP exists — build (~100 lines).**
- **Line/arc model selection** — Rosin & West (1989, *Image and Vision
  Computing* 7(2):109–114, <https://doi.org/10.1016/0262-8856(89)90004-8>):
  prefer the cheaper model unless the richer one reduces residual beyond a
  noise-calibrated threshold (BIC-flavored). Circle fitting: Kåsa (1976,
  <https://doi.org/10.1109/TIM.1976.6312298>) is biased on short arcs — use
  only as initializer; **Pratt** (1987, SIGGRAPH,
  <https://doi.org/10.1145/37401.37420>) and **Taubin** (1991, *TPAMI*
  13(11):1115–1138, <https://doi.org/10.1109/34.103273>) algebraic fits as
  initializers; then the **geometric fit** (orthogonal-distance
  Levenberg–Marquardt) which achieves the Kanatani–Cramér–Rao bound
  (Al-Sharadqah & Chernov 2009, *Electronic J. Statistics* 3:886–911, open
  access, <https://doi.org/10.1214/09-EJS419>; Chernov 2010 monograph,
  <https://doi.org/10.1201/EBK1439835906>). Python: `circle-fit` (PyPI, **MIT**,
  <https://pypi.org/project/circle-fit/>) implements the full Chernov suite
  (`prattSVD`/`taubinSVD` → `lm`) — directly reusable.
- **Freeform segments** — Park & Lee (2007, *CAD* 39(6):439–451,
  <https://doi.org/10.1016/j.cad.2006.12.006>): dominant-point-guided adaptive
  knot refinement over `scipy.interpolate` LSQ B-splines.
- **Tangency + snapping** — junction reparametrization (§c-A5) makes incidence
  + G¹ exact by construction; a KKT formulation is the fallback.
  **Beautification**: Langbein, Marshall & Martin (2004, *CAD* 36(3):261–278,
  <https://doi.org/10.1016/S0010-4485(03)00108-8>): detect regularities with
  tolerances derived from reconstruction error, select a maximal
  DOF-consistent subset, enforce by minimal perturbation; Werghi et al. (1999,
  *CAD* 31(6):363–399, <https://doi.org/10.1016/S0010-4485(99)00038-X>) prior
  art. Symmetry: Mitra, Guibas & Pauly (2006, *SIGGRAPH* 25(3):560–568,
  <https://doi.org/10.1145/1141911.1141924>) voting — 2-D Hough over (θ, ρ) +
  chamfer verification. Standard dimensions: ISO 3 Renard series (R5/R10/R20)
  guarded by fit uncertainty.
- **Constraint solvers** — SolveSpace (GPL-3.0, <https://github.com/solvespace/solvespace>)
  is the reference embeddable solver; dune3d (GPL-3.0,
  <https://github.com/dune3d/dune3d>) proves the OCCT + SolveSpace-solver
  combination. GPL keeps both as *reference only* for this product; the
  reparametrization trick avoids needing a solver at all for chains.

### Q4 — Existing software

Verified via official pages (Wayback snapshots where live sites block bots).

- **QUICKSURFACE** (KVS; workflow + pricing verified): the documented 9-step
  pipeline is the industry template — mesh → interactive/automatic region
  selection → **constrained primitives (⊥/∥/coincident)** → align part CS from
  primitives → **section-plane 2-D sketches with dimensions/constraints** →
  extrude/revolve → trim/boolean → patterns → **fillets tuned by dragging the
  radius against a live deviation map** → STEP. Limitations in their own words:
  "no one-size-fits-all… a time-consuming process… meticulous analysis and
  iterative adjustments." Auto-segmentation and the deviation analyzer are
  Pro-tier (€1,700/yr+). Windows-only.
- **Geomagic Design X** (stewardship moved 3D Systems → Oqton; a 2025 move to
  Hexagon is reported but the product page blocked verification): Modelling
  Wizards ("automated **and guided**"), patented real-time **Accuracy
  Analyzer**, **LiveTransfer** of the *feature history* into SolidWorks.
  Nothing claims automatic fillet recognition. Enterprise pricing,
  Windows-only.
- **Ansys SpaceClaim/Discovery**: "Skin Surface" autosurfacing — shrink-wrap
  NURBS for organic shapes, direct modeling, **no feature tree**. Little to
  copy beyond "autosurface is the accepted organic fallback."
- **Autodesk Fusion "Convert Mesh"** (official help verified): three methods —
  Faceted (one face per triangle), **Prismatic** ("face groups are used to
  infer prismatic features"; Parametric vs Base Feature operation), Organic
  (T-spline). Docs instruct users to hand-curate face groups first — the
  two-stage contract (face groups → merged analytic faces) is worth copying;
  no feature history results.
- **FreeCAD**: Part → ShapeFromMesh (sew) + RefineShape
  (`ShapeUpgrade_UnifySameDomain`) — sewing + same-domain merge only; no true
  RE; merges only planar/cylindrical faces and scan noise defeats it. This is
  the baseline Mesh2Param's faceted fallback already matches.
- **Open source**: CGAL Shape Detection + Polygonal Surface Reconstruction
  (Nan & Wonka's PolyFit: <https://github.com/LiangliangNan/PolyFit>, GPL-3.0,
  MIP solver needed, planar-only, "assumes the model is closed and all
  necessary planes are provided"); CGAL license page confirms the **GPL trap**
  (GeometryFactory commercial license otherwise). occwl (Autodesk AI Lab OCCT
  wrapper): **no license file** — all-rights-reserved. CADmium: archived Sep
  2025, Elastic-2.0, truck kernel. CAD Sketcher (Blender): GPL-3.0,
  experimental. A GitHub-wide scan found **no mature open-source OCCT
  mesh→parametric pipeline** — this is genuine whitespace.
- **Legacy/brief**: SolidWorks ScanTo3D (Mesh Prep → Curve Wizard → Surface
  Wizard → Deviation Analysis; Premium add-in); Siemens NX Convergent Modeling
  (facets as first-class B-rep citizens; "more than just pressing a button…
  highly qualified engineers are required"); CloudCompare C2M signed distances
  and MeshLab's Hausdorff filter as the open validation baseline.

**Pipeline decisions worth copying (ranked):** region-first/feature-second;
constrained primitive relationships before features; part CS derived from
fitted primitives; section-plane sketching; real-time (here: per-feature,
headless) deviation reporting; fillets as explicit features validated against
the mesh; symmetry/pattern detection early; export *history*, not just a solid
(Mesh2Param's CADGraph already is the history); deterministic region growing
over stochastic RANSAC.

### Q5 — Validation metrics and honest acceptance criteria

- **Two-sided sampled deviation is non-negotiable** — Metro (Cignoni,
  Rocchini, Scopigno 1998, *CGF* 17(2):167–174,
  <https://doi.org/10.1111/1467-8659.00236>): sample uniformly by area,
  closest-point distance, both directions, report max + mean (+RMS); MESH
  (Aspert, Santa-Cruz, Ebrahimi 2002, IEEE ICME,
  <https://doi.org/10.1109/ICME.2002.1035879>): symmetric Hausdorff = max of
  the two directed distances, normalize by bbox diagonal. Each direction catches
  a different failure — a bridge adds surface where the source has none
  (result→source); a flattened feature shows in source→result.
  *`comparison.py` already implements this protocol (1000 samples/direction,
  fixed seed) — keep it and report N, seed, direction of worst case.*
- **Integral invariants**: |ΔV|/V and |ΔA|/A — the scalar alarms that would
  have caught the +18% ballooning even when point distances looked acceptable.
- **Signed deviation field** → color map + histogram + % within declared
  tolerance bands: the presentation standard (Geomagic Accuracy Analyzer;
  QUICKSURFACE Live Deviation Analyzer — feature existence verified, panel
  detail unverified; CloudCompare C2M signed distance is the open
  implementation reference).
- **Parsimony/interpretability**: patch/primitive count as cost (VSA framing);
  with ground truth: primitive-type accuracy, parameter errors,
  over/under-segmentation (Fit4CAD protocol — Romanengo et al. 2022,
  *Computers & Graphics* 102:133–143, <https://doi.org/10.1016/j.cag.2021.09.013>;
  ABC as GT source — Koch et al. 2019, <https://arxiv.org/abs/1812.06216>).
  The G0 fixture `featureTree` + `groundTruth` block is exactly this
  benchmark shape.
- **STL faceting noise floor**: per face, δ_f ≈ κ_f · l_f² / 8 (sagitta; exact
  forms s = r(1−cos θ) and s = r − √(r² − (l/2)²) verified). Estimate κ_f from
  the mesh itself (G1's quadric curvatures), l_f = longest face edge; report
  max/mean floor. Then: *"result deviates from STL by X (two-sided, N samples);
  the STL's own faceting floor is estimated as Y; X below or near Y cannot be
  claimed as better accuracy without ground truth."* This is the honest answer
  to "the STL's own faceting is noise around the true surfaces."

### Q6 — Why the single-patch fit ballooned (+18%), and what prevents it

**Confirmed: decomposition is the answer.** Four canonical lines converge
(Várady et al. 1997/2002 — segmentation is the central problem of RE; Attene
2006 — cluster until each region fits one primitive; Cohen-Steiner 2004 —
parsimony = partition into k regions; Eck & Hoppe 1996, *SIGGRAPH*,
<https://doi.org/10.1145/237170.237271> — even fully automatic B-spline
reconstruction solves it by *domain decomposition*, not by a better global
fit). The specific mechanisms of the failure:

- **Tensor-product domain mismatch** (structural): a single B-spline patch is a
  rectangular parametric domain (Piegl & Tiller 1997, *The NURBS Book*,
  <https://doi.org/10.1007/978-3-642-59223-2>); over a concave footprint it has
  no mechanism to hug internal corners and must span the gaps. This alone
  guarantees bridging.
- **Fairness = low-pass shrinkage**: Taubin (1995, *SIGGRAPH*,
  <https://doi.org/10.1145/218380.218473>): membrane/thin-plate regularization
  multiplies Laplacian mode k by (1 − λk) < 1 — every non-constant mode decays;
  concave high-curvature detail erodes first. Taubin's λ|μ fix preserves size
  (pass-band k_PB = 1/λ − 1/μ) but still attenuates exactly the frequencies
  that define fillets. *The fairness term in `surface_fit.py` is this operator;
  it is correct per-patch and wrong as a global model.*
- **Area-minimizing (soap-film) bias**: Zhao, Osher & Fedkiw (2001, IEEE VLSM,
  <https://doi.org/10.1109/VLSM.2001.938900>): weighted-area minimization
  spans and inflates across gaps, necks, and concavities — the variational
  restatement of the observed volume gain. Screened Poisson (Kazhdan & Hoppe
  2013, <https://doi.org/10.1145/2487228.2487237>, abstract verified) shows the
  complementary fix at the data level: interpolation constraints tie the
  surface to samples; envelope constraints (Kazhdan et al. 2020,
  <https://doi.org/10.1111/cgf.14077>) confine it to a tolerance tube.
- **Robust losses do not fix it**: Fleishman, Cohen-Or & Silva (2005,
  *SIGGRAPH*, <https://doi.org/10.1145/1073227>): IRLS/robust norms reject outliers and can preserve creases
  locally, but do not change the domain/topology assumption. *The IRLS in
  `surface_fit.py` was therefore never going to prevent bridging.*

**Practical corollary:** keep fairness + IRLS *inside* per-region patches
(where they belong), and treat volume/area deltas as first-class acceptance
gates — a global smooth fit can look fine on RMS while failing ΔV/V badly.

---

## (c) Algorithms with implementable detail

### A1. Consensus extrusion-axis detection

```
Input: face normals n_i, areas a_i (welded mesh)
1. EGI: accumulate a_i-weighted n_i on the unit sphere.
2. Detector 1 (caps): largest antipodal pair of normal clusters → axis ±a.
3. Detector 2 (Hough): for each pair (n_i, n_j) with |n_i·n_j| < cos(60°):
   vote ±(n_i × n_j)/‖n_i × n_j‖ in a spherical accumulator → peak.
4. Detector 3 (PCA): reject cap-band faces (|n·a₁| > cos(15°)); axis =
   smallest-eigenvalue eigenvector of Σ a_i n_i n_iᵀ over the rest.
Accept iff the three agree within ~2°; else reject extrusion hypothesis.
Validate: sections at k heights must be congruent (Procrustes RMS < tol).
```

### A2. Section → ordered loops

```python
sections = trimesh.intersections.mesh_multiplane(
    mesh, plane_origin=o, plane_normal=axis,
    heights=[z1..zk])                    # mid-wall, away from fillet bands
segs, to_3d = sections[k]
# filter: keep segments whose source face has |n_face·axis| < cos(80°)
path2d, _ = trimesh.path.Path3D(segs).to_planar()
path2d.merge_vertices(digits=weld_digits)  # weld ≈ STL chordal deviation
loops = path2d.polygons_full               # exterior CCW, holes CW
```

Vertex-on-plane degenerates: nudge the plane by ~0.5× weld tolerance. Multiple
heights → keep the section with the most complete loops; cross-check others.

### A3. Optimal breakpoints (Perez–Vidal 1994)

Ordered samples p₁…p_N (unroll the closed loop at a curvature extremum).
Prefix sums of x, y, x², y², xy give e(i,j) = summed squared perpendicular
distance of p_i…p_j to their least-squares line in **O(1)**.

```
Min-# with bounded error ε:   D(1)=0;  D(j) = 1 + min_{i<j, e(i,j)≤ε} D(i)
Min-error with M vertices:    F(1,1)=0; F(m,j) = min_{i<j} [F(m−1,i) + e(i,j)]
```

O(N²) after O(N) prefix sums. Seed candidate sets with Teh–Chin dominant points
and curvature zero-crossings so breakpoints prefer line↔arc transitions.

### A4. Circle fitting (per candidate arc segment)

1. Init: **Pratt** (solve M a = η V a, smallest positive η; V has the
   constraint B²+C²−4AD=1) or **Taubin** (M a = λ N a, smallest λ; reduces to
   an SVD) — both are small generalized eigenproblems, nearly unbiased on short
   arcs. Kåsa's linear 3×3 is acceptable init for near-full circles only.
2. Polish: geometric fit min Σ (d_i − r)², d_i = √((x_i−a)² + (y_i−b)²), LM
   with row J_i = (−(x_i−a)/d_i, −(y_i−b)/d_i, −1) — 2–5 iterations of
   `scipy.optimize.least_squares`. This reaches the KCR bound
   (Al-Sharadqah–Chernov 2009).
3. Library: `circle-fit` (MIT): `prattSVD`/`taubinSVD` → `lm`.

### A5. Segment classification + tangency joint fit

Per DP segment, in order: TLS line (PCA); arc (A4); accept by BIC on residual
vs. parameter count (Rosin–West); else B-spline with dominant-point refinement
(Park–Lee). Then a **joint re-fit** enforcing incidence + G¹ at junctions by
reparametrization — no constraint solver needed:

```
junction k carries (j_k ∈ R², φ_k angle)
line segment k:   p(s) = j_k + s·t(φ_k),            t = (cos φ, sin φ)
arc segment k:    center c_k = j_k + ρ_k·n(φ_k),    n = t rotated 90°, |ρ_k| = r
Solve one unconstrained least_squares over {j_k, φ_k, ρ_k} with residuals =
point-to-primitive distances; junction coincidence and tangency hold exactly.
```

### A6. Fillet spine + radius (Kós et al. 2000)

```
Input: fillet-band patch (from G1), init r₀ = curvatureEvidence.estimatedMinimumRadiusMm
1. Spine init: mid-curve of the band (skeleton of the band's triangulation,
   or iso-curve of transverse curvature maximum).
2. Repeat to convergence (≈ 3–5 iterations):
   a. At stations s_j along the spine, slice band points with planes ⊥ T(s_j).
   b. Circle-fit each slice (A4, 2-D in the slicing plane) → r_j, center c_j.
   c. Update spine = smooth polyline/spline through c_j.
3. r = median(r_j); report IQR. If r_j varies systematically (|dr/ds| above
   noise), classify as evolved → record (s, r) law for BRepFilletAPI::Add(UandR, E).
4. Springlines: along each slice, the transverse profile departs from the
   fitted circle — take the departure points; chain them into the two
   springline curves. (Lavoué-style boundary rectification can refine.)
5. Screen: r < min over supports of 1/κ_min (self-intersection check), and
   r < min adjacent face width (overflow check).
```

### A7. Sharp-edge recovery (Path B, OCCT)

```python
# Primaries are analytic → unbounded, no extension instability
plane1 = Geom_Plane(origin, n1);  cyl2 = Geom_CylindricalSurface(ax, r)
sec = GeomAPI_IntSS(plane1, cyl2, tol)
for i in 1..sec.NbLines():
    curve = sec.Line(i)            # the sharp edge candidate
# Re-trim both faces to the new edge; use BRepAlgoAPI_Common on bounded faces
# when pcurves/tolerances matter. Rebuild shell: BRepBuilderAPI_Sewing +
# ShapeFix_Shape with one global confusion tolerance.
```

Never extend fitted B-splines far (OCCT warns; refit analytic instead).
Near-tangent supports (dihedral → 180°): skip suppression, keep the fillet as
terminal geometry — still a valid, honest tree.

### A8. Fillet replay + failure introspection (OCCT)

```python
mk = BRepFilletAPI_MakeFillet(sharpSolid, ChFi3d_Rational)
for edge in ordered_edges:            # deterministic order (see fixture gen)
    mk.Add(r, edge)                   # or mk.Add(R1, R2, edge) / mk.Add(uAndR, edge)
mk.Build()
assert mk.IsDone()
if mk.NbFaultyContours():
    st = mk.StripeStatus(ic)          # StartsolFailure→reduce r; TwistedSurface→split contour
# Vertex blends are automatic; ≥4 edges at a contour endpoint is unsupported.
```

Cross-validate: `BRepAlgoAPI_Defeaturing` on the result should remove our
replayed fillets (round-trip check), respecting its documented limits.

### A9. Validation/reporting suite additions

```
floor:  δ_f = κ_f · l_f² / 8 per face (κ from G1 curvatures, l longest edge)
        report δ_max, δ_mean as "STL faceting noise floor"
gates:  two-sided deviation (existing compare_mesh_to_shape): rms, p95, p99, max
        |ΔV|/V, |ΔA|/A (existing) — promote to hard gates for the general path
        per-feature deviation report (fillet band vs. replayed fillet, etc.)
report: "result deviates from STL by X (two-sided, N=…, seed=…); STL floor ≈ Y;
        no ground-truth CAD → X ≥ Y expected; nothing below Y is claimed."
parsimony: face count, feature count, parameter count vs. fixture groundTruth
```

---

## (d) Candid risk register

**Well-trodden (build with confidence):** EGI axis consensus; mesh–plane
sectioning; RDP; Perez–Vidal DP; Pratt/Taubin + LM circle fitting;
junction-reparametrized tangency; rolling-ball radius estimation (Kós);
extend-and-intersect on *analytic* supports; OCCT fillet replay with failure
introspection; two-sided deviation metrics; sagitta floor.

**Moderate (standard techniques, real engineering risk):** constrained-fitting
constraint *detection* with defensible tolerances (Benkő/Langbein discipline);
springline refinement / boundary rectification; symmetry verification on
noisy sections; sequencing interacting fillets; emboss/boss detection on
shallow features (0.4 mm emboss vs. tessellation noise — the fixture is the
right probe); freeform profile segments (B-spline knot placement).

**Research-grade / fragile everywhere (including commercial tools):**

- **Fully automatic blend suppression in general** — the Thakur et al. survey
  (2009) lists it as an open problem; Design X and QUICKSURFACE both keep
  fillets *manual* (drag radius against a live deviation map). Mesh2Param's
  auto-proposal + validation is ahead of that practice for the constant-radius
  case, but interacting/variable-radius blends will still need an
  "unsupported → honest partial tree" exit.
- **Vertex blends at ≥ 4-edge corners** — documented OCCT limitation; split
  corners or sequential filleting; corner quality is where kernels differ.
- **Near-tangent support intersections** — ill-conditioned by geometry itself
  (Choi & Ju; OCCT defeaturing docs). Threshold and skip.
- **Variable-radius blends** — estimable (per-section r(s)) and replayable
  (evolved laws), but radius-law identification from noisy mesh data is the
  weakest link; misclassifying variable-as-constant (or vice versa) is the
  expected error. Mitigate by reporting the r(s) variance, not hiding it.
- **Segmentation quality gates everything** — Fusion's docs tell users to
  hand-curate face groups; QUICKSURFACE gates auto-segmentation behind Pro;
  CGAL warns ε-at-noise-level over-segments. G1's hysteretic growth + fragment
  absorption is the right architecture; expect mesh-quality-driven failures on
  real-world STLs beyond the clean fixtures, and keep the fail-closed
  diagnostics culture.
- **Learned methods** — not a risk, a non-option (constraints); revisit only
  if "no downloads" is relaxed, and then only MIT Point2Cyl as a narrow prior.

**Where the plan is deliberately ahead of the state of practice:** no tool —
commercial or open — currently produces a fully automatic, deterministic,
feature-parametric STEP from an STL of a filleted mechanical part. The
literature supports every individual step; the integration risk is real but
decomposed by the G2 milestones, each gated on procedural ground truth.

---

## Verification ledger

- **Classic RE**: all DOIs retrieved via CrossRef/DBLP (VSA, Garland, Attene,
  Benkő×3, Várady×3, Schnabel, Lavoué, Zuckerberger, Lai, Thakur, Zhu & Menq,
  Venkataraman & Sohoni×2, Joshi & Chang, Karniel). RE-BENCH site unreachable —
  flagged unverified.
- **Learned**: arXiv records + GitHub pages fetched (Point2CAD/prs-eth repo,
  ComplexGen, Point2Cyl, BRepNet); licenses read from repo pages. "SEDNet",
  AAGNet, BrepMFR — unverifiable; flagged. ParSeNet/HPNet repo licenses
  unverified; flagged.
- **Fillets/OCCT**: CrossRef for Vida, Rockwood & Owen (via deposited reference
  lists), Sanglikar, Choi & Ju, Klass & Kuhn, Kós et al., Várady & Rockwood,
  Zhu & Menq; dev.opencascade.org pages fetched for `BRepFilletAPI_MakeFillet`,
  `MakeChamfer`, Modeling Algorithms guide, `BRepAlgoAPI_Defeaturing`,
  `BOPAlgo_RemoveFeatures`, `GeomLib` (refman now labeled 8.0.0; API identical
  in 7.9 lineage). `BRepFilletAPI_MakeFilletOn` 404 — flagged.
- **Profile recovery**: Horn, Han et al., Douglas & Peucker, Perez & Vidal,
  Teh & Chin, Park & Lee, Rosin & West, Kåsa, Pratt, Taubin, Al-Sharadqah &
  Chernov, Chernov monograph, Langbein, Werghi, Mitra — CrossRef/DBLP/arXiv.
  trimesh docs, `circle-fit` PyPI, SolveSpace/dune3d repos fetched.
  QUICKSURFACE live site blocked fetches — workflow/pricing verified via
  Wayback snapshots of official pages; scikit-spatial, shapely, planegcs,
  CADmium docs unverified within budget.
- **Software**: Oqton/Geomagic page via Wayback; QUICKSURFACE via Wayback;
  Ansys, Autodesk help, CGAL docs+license, PolyFit, occwl (no license file),
  dune3d, CADmium (archived), CAD Sketcher, ScanTo3D via Wayback, Siemens NX,
  CloudCompare wiki — all fetched. Geomagic Accuracy Analyzer statistics panel
  and Hexagon stewardship page blocked (403) — flagged.
- **Validation/failure**: Metro, MESH, Taubin, Zhao et al., Eck & Hoppe,
  Fleishman, Fit4CAD, ABC, NURBS Book — CrossRef/DOI; Screened Poisson abstract
  verified verbatim on the author's page; sagitta formulas verified.
  Vendor tolerance claims ("0.05 mm-class") treated as marketing, not cited.
