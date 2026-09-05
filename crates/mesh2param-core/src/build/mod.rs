//! Face construction: the fourth rung of the Phase 1 ladder, and the first
//! analytic STEP the core writes.
//!
//! [`crate::segment`] says which triangles lie on which surface,
//! [`crate::recover`] says where those surfaces meet; this stage **builds**.
//!
//! # The algorithm
//!
//! 1. **Edges once, shared.** Every recovered edge becomes kernel topology
//!    exactly once, and both adjacent faces reference that same edge. Sewing
//!    afterwards has nothing left to guess, so it is not run at all: see
//!    "Assembly" below.
//! 2. **Faces from patches.** A patch with a recognised primitive and closed
//!    loops becomes one trimmed face — plane, cylinder, cone, sphere or
//!    torus — with the largest loop as its outer wire and the rest as inner
//!    wires, oriented so its normal agrees with the mesh triangles it came
//!    from.
//! 3. **Everything else is triangles.** An `Unknown` patch, a patch whose
//!    boundary does not close, and a patch whose face construction fails are
//!    all emitted as one planar face per mesh triangle, on the same shared
//!    vertices and edges, so the shell still closes.
//! 4. **Assemble, validate, repair, retry.** Shell, solid, `unify_faces`, then
//!    `validate_solid`. A merge that makes the solid invalid is thrown away; a
//!    shell that came out inside out is reversed; an invalid solid is retried
//!    once with the analytic faces the validator complained about demoted to
//!    triangles, and falls back to [`crate::faceted_step`] if that does not
//!    help.
//! 5. **Verify.** The result is tessellated and measured against the source
//!    mesh in both directions, and its volume compared against what that
//!    measured deviation can account for. A failure is localised to the faces
//!    that are off the mesh and retried once with those demoted.
//!
//! # Tiers
//!
//! | tier | meaning |
//! | --- | --- |
//! | [`Tier::Analytic`] | every face is a recognised surface |
//! | [`Tier::Mixed`] | analytic where recognition held, triangles elsewhere |
//! | [`Tier::Faceted`] | no analytic face survived |

mod assemble;
mod geom;
mod periodic;
#[cfg(test)]
mod tests;
mod verify;

use std::collections::{BTreeMap, BTreeSet};

use remus_operations::validate::{Severity, ValidationReport};
use remus_topology::Topology as KernelTopology;
use remus_topology::solid::SolidId;
use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};
use crate::faceted::{FacetedOptions, Tier, faceted_step};
use crate::mesh::MeshData;
use crate::progress::{Progress, Stage};
use crate::segment::{Inventory, PatchKind, SegmentOptions, Segmentation, segment_with_progress};
use crate::topology::{Topology as PatchTopology, TopologyOptions, recover};

pub use verify::{Deviation, ResultMesh};

/// Where assembly begins inside [`Stage::Build`]'s own 0..1 range: the weld,
/// the mesh geometry and the boundary chains come first, and on a large mesh
/// they are a visible part of the stage.
const BUILD_ASSEMBLY_START: f32 = 0.1;

/// How many validation issues are carried on a result before truncating.
const MAX_ISSUES: usize = 10;

/// How much volume error one unit of measured surface deviation is allowed to
/// account for, per unit of `surface_area / volume`.
///
/// Displace every point of a closed surface by at most `d` and the volume it
/// bounds moves by at most `d * A`, so `d * A / V` is the relative volume
/// error a deviation of `d` can produce on its own. The factor above one is the
/// slack on that first-order bound: a curved surface adds a second-order term,
/// and the deviation is a sampled maximum rather than an exhaustive one. Half
/// again is enough to cover the case this exists for — a polygonal bore
/// reconstructed as the cylinder it was cut from, where the mesh is the thing
/// that is small — and every corpus mesh that reaches the widened budget passes
/// or fails it by an order of magnitude, not by this factor.
const DEVIATION_VOLUME_FACTOR: f64 = 1.5;

/// The volume error no measured deviation may excuse.
///
/// A result that encloses twice, or half, what the mesh does is a different
/// shape, not a differently-sampled one. Without it the reasoning above excuses
/// anything far enough away: a cylinder fitted at twice the radius sits a whole
/// radius off the mesh, so its own deviation buys it a budget several times the
/// error it has.
const MAX_EXPLAINED_VOLUME_ERROR: f64 = 1.0;

/// Wall clock, where there is one. `wasm32-unknown-unknown` has no clock at
/// all and `Instant::now` traps there, so the browser build reports zero
/// rather than the core carrying a platform shim.
#[cfg(not(target_arch = "wasm32"))]
struct Stopwatch(std::time::Instant);

#[cfg(not(target_arch = "wasm32"))]
impl Stopwatch {
    fn start() -> Self {
        Self(std::time::Instant::now())
    }
    fn ms(&self) -> f64 {
        self.0.elapsed().as_secs_f64() * 1000.0
    }
}

#[cfg(target_arch = "wasm32")]
struct Stopwatch;

#[cfg(target_arch = "wasm32")]
impl Stopwatch {
    const fn start() -> Self {
        Self
    }
    const fn ms(&self) -> f64 {
        0.0
    }
}

/// Knobs for [`build_solid`].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BuildOptions {
    /// Absolute tolerance. `None` takes [`Segmentation::tolerance`], so this
    /// stage agrees with the two below it on what "the same point" means.
    pub tolerance: Option<f64>,

    /// Chord deflection for the verification tessellation. `None` takes the
    /// run tolerance, clamped to a thousandth of the part.
    pub deflection: Option<f64>,

    /// Measure the result against the source mesh. Costs a tessellation plus
    /// two grid sweeps; off makes [`BuildResult::deviation`] `None`.
    pub verify: bool,

    /// Merge same-surface adjacent faces before validating.
    ///
    /// This is what collapses a triangulated region's facets back into
    /// coplanar faces; it is also the stage that has broken Euler bookkeeping
    /// on faces with many inner loops upstream (esaueng/remus#246), so it is a
    /// knob rather than a fixture.
    pub unify: bool,

    /// Interpolate a polyline edge with a degree-3 NURBS curve where the
    /// kernel accepts one, instead of a chain of straight edges.
    ///
    /// **Off by default**, on measurement: a NURBS boundary edge on a
    /// cylindrical face is counted as a rim candidate by the kernel's band
    /// tessellator, and the fillet block then tessellates 0.5 mm off a 4 mm
    /// part where the same points as straight edges are 0.03 mm off. The
    /// curve itself is checked against its own samples before it is kept, so
    /// the error is in what the kernel does with the edge, not in the fit.
    pub polyline_nurbs: bool,

    /// Refuse meshes above this triangle count.
    pub triangle_budget: usize,

    /// Cap on demote-and-rebuild rounds before the faceted fallback.
    pub max_rounds: usize,

    /// Largest volume error, relative to the source mesh, a reconstruction may
    /// have and still be reported above the faceted tier.
    ///
    /// A solid can pass every topological check and still be the wrong shape —
    /// a hex prism recognised as a cylinder is closed, manifold, orientable and
    /// half again too big. Verification is what catches that, and a tier claim
    /// that survives it is one a caller can act on.
    pub max_volume_error: f64,

    /// Largest deviation p95, as a fraction of the bounding-box diagonal, a
    /// reconstruction may have and still be reported above the faceted tier.
    pub max_deviation_fraction: f64,
}

impl Default for BuildOptions {
    fn default() -> Self {
        Self {
            tolerance: None,
            deflection: None,
            verify: true,
            unify: true,
            polyline_nurbs: false,
            triangle_budget: 200_000,
            max_rounds: 3,
            max_volume_error: 0.05,
            max_deviation_fraction: 0.02,
        }
    }
}

/// Outcome of a face-construction run.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BuildResult {
    /// Best tier that held.
    pub tier: Tier,
    /// Faces built from a recognised analytic surface.
    pub faces_analytic: usize,
    /// Faces emitted as single mesh triangles.
    pub faces_triangle: usize,
    /// Faces in the finished solid, after merging.
    pub faces_final: usize,
    /// Whether the finished solid passes kernel validation with no errors.
    pub valid: bool,
    /// Up to [`MAX_ISSUES`] validation issues, severity-prefixed.
    pub issues: Vec<String>,
    /// Why the run did not stay at the tier it was aiming for.
    pub fallback_reason: Option<String>,
    /// Distance between the result and the source mesh. `None` when
    /// verification was off or the tessellation failed.
    pub deviation: Option<Deviation>,
    /// Volume the result encloses.
    pub volume: f64,
    /// Volume the source mesh encloses.
    pub source_volume: f64,
    /// The AP203 STEP file.
    #[serde(skip)]
    pub step: Vec<u8>,
    /// Length of [`Self::step`].
    pub step_bytes: usize,
    /// Whether the kernel's own reader read the file back.
    pub round_trip_ok: bool,
    /// Why each patch that could not become an analytic face did not, one
    /// entry per distinct reason, with its count.
    pub face_failures: Vec<String>,
    /// Edges emitted as an interpolating NURBS curve.
    pub edges_nurbs: usize,
    /// Edges emitted as a chain of straight edges through a curve's points.
    pub edges_curve_chain: usize,
    /// Wall clock for construction, milliseconds.
    pub ms_build: f64,
    /// Wall clock for verification, milliseconds.
    pub ms_verify: f64,
    /// A tessellation of the result, for display. Empty when verification was
    /// off or the kernel declined to tessellate; at the faceted tier it is the
    /// source mesh, which is what that tier's STEP file contains.
    ///
    /// Not serialised: it is display data, not a measurement, and every
    /// baseline this type is compared against is a measurement.
    #[serde(skip)]
    pub mesh: ResultMesh,
}

/// Knobs for [`reconstruct`]: one per rung of the ladder.
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReconstructOptions {
    /// Recognition.
    pub segment: SegmentOptions,
    /// Topology recovery.
    pub topology: TopologyOptions,
    /// Face construction.
    pub build: BuildOptions,
    /// The floor, used when a rung above it declines.
    pub faceted: FacetedOptions,
}

/// The whole ladder in one call.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReconstructResult {
    /// The build, whichever tier it landed at.
    pub build: BuildResult,
    /// Patches recognised, `None` when segmentation itself failed.
    pub patches: Option<usize>,
    /// Edges recovered, `None` when topology recovery failed or never ran.
    pub edges: Option<usize>,
    /// Wall clock for recognition, milliseconds.
    pub ms_segment: f64,
    /// Wall clock for topology recovery, milliseconds.
    pub ms_topology: f64,
    /// What recognition found, `None` when segmentation itself failed.
    pub inventory: Option<Inventory>,
    /// Share of the mesh's surface area no primitive was recognised on. Zero
    /// when segmentation failed.
    pub unknown_area_fraction: f64,
}

fn issues_of(report: &ValidationReport) -> Vec<String> {
    report
        .issues
        .iter()
        .take(MAX_ISSUES)
        .map(|i| {
            let sev = match i.severity {
                Severity::Error => "error",
                Severity::Warning => "warn",
            };
            format!("{sev}: {}", i.description.replace('\n', " "))
        })
        .collect()
}

/// The first error the validator reported, as one line.
fn first_issue(report: &ValidationReport) -> String {
    report
        .issues
        .iter()
        .find(|i| i.severity == Severity::Error)
        .or_else(|| report.issues.first())
        .map_or_else(
            || "no issue text".to_string(),
            |i| i.description.replace('\n', " "),
        )
}

fn face_count(topo: &KernelTopology, solid: SolidId) -> usize {
    remus_topology::explorer::solid_faces(topo, solid).map_or(0, |f| f.len())
}

/// Group a list of reasons into `"reason x N"` lines, most common first.
fn grouped(reasons: &[(u32, &'static str)]) -> Vec<String> {
    let mut counts: BTreeMap<&'static str, usize> = BTreeMap::new();
    for (_, reason) in reasons {
        *counts.entry(reason).or_default() += 1;
    }
    let mut out: Vec<(usize, &'static str)> = counts.into_iter().map(|(k, v)| (v, k)).collect();
    out.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(b.1)));
    out.into_iter()
        .map(|(n, reason)| format!("{reason} x{n}"))
        .collect()
}

/// Kernel edge indices the validator named in its own error text.
///
/// The report is prose, not structured data: only the checks that name an
/// edge can be localised, which is why the caller has a blanket fallback.
fn reported_edges(report: &ValidationReport) -> BTreeSet<usize> {
    let mut out = BTreeSet::new();
    for issue in &report.issues {
        if issue.severity != Severity::Error {
            continue;
        }
        let mut rest = issue.description.as_str();
        while let Some(at) = rest.find("edge ") {
            rest = &rest[at + 5..];
            let digits: String = rest.chars().take_while(char::is_ascii_digit).collect();
            if let Ok(n) = digits.parse::<usize>() {
                out.insert(n);
            }
        }
    }
    out
}

/// Build a B-Rep solid from a segmented mesh and its recovered topology.
///
/// # Errors
///
/// - [`CoreError::Budget`] when the mesh exceeds `options.triangle_budget`.
/// - [`CoreError::Validation`] when `seg` or `topo` do not describe this mesh.
/// - [`CoreError::Import`] when no face could be built at all.
/// - [`CoreError::Kernel`] when the kernel refuses to validate or write.
///
/// A solid that is produced but invalid is not an error: the run falls back
/// down the ladder and says so in [`BuildResult::fallback_reason`].
pub fn build_solid(
    mesh: &MeshData,
    seg: &Segmentation,
    topo: &PatchTopology,
    options: &BuildOptions,
) -> Result<BuildResult> {
    build_solid_with_progress(mesh, seg, topo, options, &mut Progress::none())
}

/// [`build_solid`], reporting [`Stage::Build`], [`Stage::Verify`] and
/// [`Stage::Step`] as it goes.
///
/// The result is the same one [`build_solid`] returns: the sink is advisory
/// and no decision here reads it back.
///
/// # Errors
///
/// The same as [`build_solid`].
pub fn build_solid_with_progress(
    mesh: &MeshData,
    seg: &Segmentation,
    topo: &PatchTopology,
    options: &BuildOptions,
    progress: &mut Progress<'_>,
) -> Result<BuildResult> {
    if mesh.triangles > options.triangle_budget {
        return Err(CoreError::Budget {
            triangles: mesh.triangles,
            limit: options.triangle_budget,
        });
    }
    let tol = options.tolerance.unwrap_or(seg.tolerance);
    if !tol.is_finite() || tol <= 0.0 {
        return Err(CoreError::Validation(format!(
            "build tolerance must be finite and positive, got {tol}"
        )));
    }

    progress.at(Stage::Build, 0.0);
    let build_clock = Stopwatch::start();
    let welded = mesh.welded()?;
    if seg.face_patch.len() != welded.triangles.len() {
        return Err(CoreError::Validation(format!(
            "segmentation covers {} faces but the welded mesh has {}",
            seg.face_patch.len(),
            welded.triangles.len()
        )));
    }
    let geom = geom::MeshGeom::new(&welded);
    let chains = crate::topology::chains::build(&welded, &seg.face_patch, seg.patches.len());
    let ctx = assemble::Context::new(
        &geom,
        seg,
        topo,
        &chains.chains,
        tol,
        options.polyline_nurbs,
    )?;

    let mut analytic = vec![false; seg.patches.len()];
    let mut failures: Vec<(u32, &'static str)> = Vec::new();
    for patch in &seg.patches {
        match ctx.eligible(patch) {
            None => {
                if let Some(slot) = analytic.get_mut(patch.id as usize) {
                    *slot = true;
                }
            }
            Some(reason) => failures.push((patch.id, reason)),
        }
    }

    if !analytic.iter().any(|a| *a) {
        let ms_build = build_clock.ms();
        return faceted_result(
            mesh,
            &geom,
            options,
            "no patch was eligible for an analytic face".to_string(),
            grouped(&failures),
            ms_build,
        );
    }

    let mut retried_after_invalid = false;
    let mut retried_after_verify = false;
    let mut last: Option<(KernelTopology, SolidId, assemble::Attempt, ValidationReport)> = None;
    let mut fallback_reason: Option<String> = None;
    let mut measured: Option<verify::Measured> = None;
    let mut ms_verify = 0.0;

    // A thousandth of the part is the usual display deflection, and the
    // measurement has to be finer than what it is measuring: at the run
    // tolerance the result's own faceting would dominate the number.
    let diagonal = mesh.bbox.diagonal();
    let deflection = options
        .deflection
        .unwrap_or_else(|| tol.min(1e-3 * diagonal).max(1e-6 * diagonal));
    let deviation_budget = options.max_deviation_fraction * diagonal;

    // One round per demotion pass, plus one that is not allowed to demote
    // again: a round that ends by demoting has to be followed by a round that
    // ends with a solid, or the run finishes holding nothing.
    let rounds = options.max_rounds.max(1) + 1;
    for round in 0..rounds {
        progress.pass(Stage::Build, BUILD_ASSEMBLY_START, 1.0, round, rounds);
        let mut attempt = assemble::attempt(&ctx, &analytic)?;
        let final_round = round + 1 == rounds;
        // Assembly has already demoted these and rebuilt itself around them,
        // so this only records them and keeps the caller's own set in step —
        // the unmerged rebuild below has to make the same choices to be the
        // same solid. No round is spent on it.
        for (patch, reason) in &attempt.demoted {
            failures.push((*patch, reason));
            if let Some(slot) = analytic.get_mut(*patch as usize) {
                *slot = false;
            }
        }

        if options.unify {
            remus_operations::heal::unify_faces(&mut attempt.topo, attempt.solid)
                .map_err(|e| CoreError::Kernel(format!("unify_faces: {e}")))?;
        }
        let mut report = remus_operations::validate::validate_solid(&attempt.topo, attempt.solid)
            .map_err(|e| CoreError::Kernel(format!("validate_solid: {e}")))?;

        // Merging same-surface faces is a tidy-up, not a step the result
        // depends on, and it must not be the thing that makes the solid
        // invalid. `unify_faces` loses track of the inner loops it moves onto a
        // merged face (esaueng/remus#246), and the Euler check then reads the
        // solid as the wrong genus: measured on
        // `hydraulic-manifold-block/mesh-default`, which is a valid mixed solid
        // unmerged and Euler-invalid merged. Assembly is deterministic, so the
        // unmerged solid is one rebuild away.
        if options.unify && !report.is_valid() {
            let plain = assemble::attempt(&ctx, &analytic)?;
            let plain_report = remus_operations::validate::validate_solid(&plain.topo, plain.solid)
                .map_err(|e| CoreError::Kernel(format!("validate_solid: {e}")))?;
            if plain_report.is_valid() {
                fallback_reason.get_or_insert_with(|| {
                    format!(
                        "merging same-surface faces made the solid invalid ({}); \
                         kept the unmerged faces",
                        first_issue(&report)
                    )
                });
                attempt = plain;
                report = plain_report;
            }
        }

        // The safety net under every per-patch orientation decision: a shell
        // that closes, is manifold and is consistently wound can still face
        // inward, and then encloses a negative volume. That is one global sign,
        // so it is repaired globally rather than demoted face by face.
        if inside_out(&report) {
            assemble::reverse_shell(&mut attempt.topo, attempt.solid)?;
            let after = remus_operations::validate::validate_solid(&attempt.topo, attempt.solid)
                .map_err(|e| CoreError::Kernel(format!("validate_solid: {e}")))?;
            if inside_out(&after) {
                // Reversing did not settle the sign, so it was not one global
                // flip; put the shell back and let the ordinary retry run.
                assemble::reverse_shell(&mut attempt.topo, attempt.solid)?;
            } else {
                fallback_reason.get_or_insert_with(|| {
                    "the assembled shell was inside out and was \
                                            reversed before validating"
                        .to_string()
                });
                report = after;
            }
        }

        if !report.is_valid() {
            // A single retry with the faces the validator named demoted. The
            // report is prose, so the fallback is every curved face: a plane
            // bounded by the mesh polygon is the one analytic face that cannot
            // be in the wrong place.
            if !retried_after_invalid && !final_round {
                retried_after_invalid = true;
                let demote = invalid_demotions(&attempt, &report, seg, &analytic);
                let still_analytic = analytic
                    .iter()
                    .enumerate()
                    .any(|(i, on)| *on && !demote.contains(&(i as u32)));
                if !demote.is_empty() && still_analytic {
                    fallback_reason = Some(format!(
                        "first solid was invalid ({}); retried with the reported faces demoted",
                        first_issue(&report)
                    ));
                    for patch in demote {
                        failures.push((patch, "validator reported the face's edges"));
                        if let Some(slot) = analytic.get_mut(patch as usize) {
                            *slot = false;
                        }
                    }
                    continue;
                }
            }
            let ms_build = build_clock.ms();
            let reason = format!("solid invalid after retry: {}", first_issue(&report));
            return faceted_result(mesh, &geom, options, reason, grouped(&failures), ms_build);
        }

        // The tier is a claim about the shape, not only about the topology, so
        // a result that is measurably not the part does not get to keep it.
        let verify_clock = Stopwatch::start();
        let m = if options.verify {
            progress.at(Stage::Verify, 0.0);
            let m = verify::measure(&attempt.topo, attempt.solid, &geom, deflection).ok();
            progress.at(Stage::Verify, 1.0);
            m
        } else {
            None
        };
        ms_verify += verify_clock.ms();

        if let Some(m) = &m {
            let volume_error = relative_volume_error(m.volume, geom.volume);
            let over_volume = volume_error > options.max_volume_error;
            let over_deviation = m.deviation.p95 > deviation_budget;
            if over_volume || over_deviation {
                // Verification is measured over the whole solid, but it is
                // rarely the whole solid that is wrong: one face built on a
                // surface that grazes its own patch can sit metres off a
                // hundred-millimetre part and carry the aggregate with it.
                // Localise it the way an invalid solid is localised — demote
                // the faces that are demonstrably not on the mesh and rebuild —
                // before giving the whole reconstruction up.
                if !retried_after_verify && !final_round {
                    retried_after_verify = true;
                    let demote = off_mesh_demotions(
                        &attempt,
                        &geom,
                        deflection,
                        deviation_budget,
                        &analytic,
                    );
                    let still_analytic = analytic
                        .iter()
                        .enumerate()
                        .any(|(i, on)| *on && !demote.contains(&(i as u32)));
                    if !demote.is_empty() && still_analytic {
                        fallback_reason = Some(format!(
                            "first solid failed verification (volume off by {:.1}%, deviation p95 \
                             {:.4}); retried with the {} face(s) off the mesh demoted",
                            volume_error * 100.0,
                            m.deviation.p95,
                            demote.len()
                        ));
                        for patch in demote {
                            failures.push((patch, "face lies off the source mesh"));
                            if let Some(slot) = analytic.get_mut(patch as usize) {
                                *slot = false;
                            }
                        }
                        continue;
                    }
                }
                let budget = volume_budget(options, m, &geom);
                if over_deviation || volume_error > budget {
                    let ms_build = build_clock.ms();
                    let reason = format!(
                        "reconstruction failed verification: volume off by {:.1}% (budget \
                         {:.1}%), deviation p95 {:.4} (budget {deviation_budget:.4})",
                        volume_error * 100.0,
                        budget * 100.0,
                        m.deviation.p95,
                    );
                    return faceted_result(
                        mesh,
                        &geom,
                        options,
                        reason,
                        grouped(&failures),
                        ms_build,
                    );
                }
            }
        }

        measured = m;
        let topo_out = std::mem::replace(&mut attempt.topo, KernelTopology::new());
        let solid = attempt.solid;
        last = Some((topo_out, solid, attempt, report));
        break;
    }

    let Some((topo_out, solid, attempt, report)) = last else {
        let ms_build = build_clock.ms();
        return faceted_result(
            mesh,
            &geom,
            options,
            "face construction produced no solid".to_string(),
            grouped(&failures),
            ms_build,
        );
    };

    progress.at(Stage::Build, 1.0);
    progress.at(Stage::Step, 0.0);
    let step = remus_io::step::writer::write_step(&topo_out, &[solid])
        .map_err(|e| CoreError::Kernel(format!("write_step: {e}")))?;
    let round_trip_ok = {
        let mut probe = KernelTopology::new();
        remus_io::step::reader::read_step(&step, &mut probe).is_ok()
    };
    let faces_final = face_count(&topo_out, solid);
    let ms_build = build_clock.ms() - ms_verify;

    let tier = if attempt.faces_analytic == 0 {
        Tier::Faceted
    } else if attempt.faces_triangle == 0 {
        Tier::Analytic
    } else {
        Tier::Mixed
    };
    if attempt.dropped_triangles > 0 {
        failures.push((u32::MAX, "mesh triangle collapsed onto a merged vertex"));
    }

    let step = step.into_bytes();
    progress.at(Stage::Step, 1.0);
    Ok(BuildResult {
        tier,
        faces_analytic: attempt.faces_analytic,
        faces_triangle: attempt.faces_triangle,
        faces_final,
        valid: true,
        issues: issues_of(&report),
        fallback_reason,
        deviation: measured.as_ref().map(|m| m.deviation),
        volume: measured.as_ref().map_or(0.0, |m| m.volume),
        source_volume: geom.volume,
        step_bytes: step.len(),
        step,
        round_trip_ok,
        face_failures: grouped(&failures),
        edges_nurbs: attempt.runs_nurbs,
        edges_curve_chain: attempt.runs_curve_chain,
        ms_build,
        ms_verify,
        mesh: measured.map(|m| m.mesh).unwrap_or_default(),
    })
}

/// Whether the validator says the outer shell faces inward.
///
/// The check is the kernel's own: it integrates the real face geometry, which
/// is a better answer than any second estimate from a tessellation, and it is
/// silent rather than wrong when the sign cannot be established.
fn inside_out(report: &ValidationReport) -> bool {
    report
        .issues
        .iter()
        .any(|i| i.severity == Severity::Error && i.description.contains("inside out"))
}

/// `|built - source| / source`, zero when the source encloses nothing.
fn relative_volume_error(built: f64, source: f64) -> f64 {
    if source > 0.0 {
        (built - source).abs() / source
    } else {
        0.0
    }
}

/// The volume error this reconstruction is allowed, given how far it actually
/// sits from the mesh.
///
/// A volume difference is only evidence of a *wrong shape* when it is larger
/// than the measured surface deviation can produce. The case this exists for is
/// the coarse bore: a twelve-sided hole reconstructed as the cylinder it was
/// tessellated from is right, and the mesh is the thing that is 5% out, but the
/// deviation over the whole surface stays at the chord sagitta. Below
/// [`BuildOptions::max_volume_error`] nothing is asked, and above
/// [`MAX_EXPLAINED_VOLUME_ERROR`] nothing is excused.
fn volume_budget(
    options: &BuildOptions,
    measured: &verify::Measured,
    geom: &geom::MeshGeom,
) -> f64 {
    if geom.volume <= 0.0 || !measured.deviation.max.is_finite() {
        return options.max_volume_error;
    }
    let explained =
        DEVIATION_VOLUME_FACTOR * measured.deviation.max * geom.surface_area / geom.volume;
    explained.clamp(options.max_volume_error, MAX_EXPLAINED_VOLUME_ERROR)
}

/// The analytic patches whose faces are demonstrably not on the source mesh.
fn off_mesh_demotions(
    attempt: &assemble::Attempt,
    geom: &geom::MeshGeom,
    deflection: f64,
    budget: f64,
    analytic: &[bool],
) -> Vec<u32> {
    let mut out: BTreeSet<u32> = BTreeSet::new();
    for fid in verify::faces_off_mesh(&attempt.topo, attempt.solid, geom, deflection, budget) {
        if let Some(&patch) = attempt.face_patch.get(&fid.index())
            && analytic.get(patch as usize).copied().unwrap_or(false)
        {
            out.insert(patch);
        }
    }
    out.into_iter().collect()
}

/// The analytic patches to demote after an invalid solid.
///
/// The validator names an edge in some of its checks and only a count in
/// others, so the localised set is used when there is one and every curved
/// face is demoted when there is not — a plane bounded by the mesh polygon is
/// the one analytic face that cannot be geometrically wrong.
fn invalid_demotions(
    attempt: &assemble::Attempt,
    report: &ValidationReport,
    seg: &Segmentation,
    analytic: &[bool],
) -> Vec<u32> {
    let named = reported_edges(report);
    let mut out: BTreeSet<u32> = BTreeSet::new();
    if !named.is_empty() {
        let edge_faces = assemble::map_edge_patches(&attempt.topo, attempt.solid);
        for edge in &named {
            let Some(faces) = edge_faces.get(edge) else {
                continue;
            };
            for f in faces {
                if let Some(&patch) = attempt.face_patch.get(&f.index())
                    && analytic.get(patch as usize).copied().unwrap_or(false)
                {
                    out.insert(patch);
                }
            }
        }
    }
    if out.is_empty() {
        for patch in &seg.patches {
            if analytic.get(patch.id as usize).copied().unwrap_or(false)
                && patch.kind != PatchKind::Plane
            {
                out.insert(patch.id);
            }
        }
    }
    out.into_iter().collect()
}

/// The floor, wrapped as a [`BuildResult`] so a caller handles one type.
fn faceted_result(
    mesh: &MeshData,
    geom: &geom::MeshGeom,
    options: &BuildOptions,
    reason: String,
    face_failures: Vec<String>,
    ms_build: f64,
) -> Result<BuildResult> {
    let faceted = faceted_step(
        mesh,
        &FacetedOptions {
            triangle_budget: options.triangle_budget,
            ..FacetedOptions::default()
        },
    )?;
    Ok(BuildResult {
        tier: Tier::Faceted,
        faces_analytic: 0,
        faces_triangle: faceted.faces_imported as usize,
        faces_final: faceted.faces_unified as usize,
        valid: faceted.valid,
        issues: faceted.issues,
        fallback_reason: Some(reason),
        deviation: None,
        volume: geom.volume,
        source_volume: geom.volume,
        step_bytes: faceted.step.len(),
        step: faceted.step,
        round_trip_ok: false,
        face_failures,
        edges_nurbs: 0,
        edges_curve_chain: 0,
        ms_build,
        ms_verify: 0.0,
        // The faceted STEP is one planar face per source triangle, so the
        // source mesh is exactly what it draws.
        mesh: ResultMesh::new(&geom.points, &flat_indices(&geom.triangles)),
    })
}

/// A triangle list flattened to the index layout renderers want.
fn flat_indices(triangles: &[[u32; 3]]) -> Vec<u32> {
    triangles.iter().flat_map(|t| t.iter().copied()).collect()
}

/// Run the whole ladder: recognition, topology, face construction, with the
/// faceted floor under every rung.
///
/// # Errors
///
/// Propagates [`CoreError::Budget`] and a mesh that cannot be read at all.
/// A stage that declines is not an error: the run falls to the tier below it
/// and records why in [`BuildResult::fallback_reason`].
pub fn reconstruct(mesh: &MeshData, options: &ReconstructOptions) -> Result<ReconstructResult> {
    reconstruct_with_progress(mesh, options, &mut Progress::none())
}

/// [`reconstruct`], reporting every [`Stage`] as it goes.
///
/// The result is the same one [`reconstruct`] returns. Fractions are per
/// stage, and the run is finished when [`Stage::Step`] reaches `1.0`.
///
/// # Errors
///
/// The same as [`reconstruct`].
pub fn reconstruct_with_progress(
    mesh: &MeshData,
    options: &ReconstructOptions,
    progress: &mut Progress<'_>,
) -> Result<ReconstructResult> {
    if mesh.triangles > options.build.triangle_budget {
        return Err(CoreError::Budget {
            triangles: mesh.triangles,
            limit: options.build.triangle_budget,
        });
    }

    let seg_clock = Stopwatch::start();
    let seg = segment_with_progress(mesh, &options.segment, &mut progress.reborrow());
    let ms_segment = seg_clock.ms();
    let seg = match seg {
        Ok(seg) => seg,
        Err(e) => {
            return Ok(ReconstructResult {
                build: fallback_all(mesh, options, format!("segmentation failed: {e}"))?,
                patches: None,
                edges: None,
                ms_segment,
                ms_topology: 0.0,
                inventory: None,
                unknown_area_fraction: 0.0,
            });
        }
    };

    progress.at(Stage::Topology, 0.0);
    let topo_clock = Stopwatch::start();
    let topo = recover(mesh, &seg, &options.topology);
    let ms_topology = topo_clock.ms();
    progress.at(Stage::Topology, 1.0);
    let topo = match topo {
        Ok(topo) => topo,
        Err(e) => {
            return Ok(ReconstructResult {
                build: fallback_all(mesh, options, format!("topology recovery failed: {e}"))?,
                patches: Some(seg.patches.len()),
                edges: None,
                ms_segment,
                ms_topology,
                inventory: Some(seg.inventory),
                unknown_area_fraction: seg.unknown_area_fraction,
            });
        }
    };
    let edges = topo.edges.len();

    let build = match build_solid_with_progress(
        mesh,
        &seg,
        &topo,
        &options.build,
        &mut progress.reborrow(),
    ) {
        Ok(result) => result,
        Err(CoreError::Budget {
            triangles, limit, ..
        }) => return Err(CoreError::Budget { triangles, limit }),
        Err(e) => fallback_all(mesh, options, format!("face construction failed: {e}"))?,
    };

    // Every path out of the ladder ends here, including the ones that fell to
    // the faceted floor without the build stage writing a thing, so this is
    // the one report a caller can treat as "finished".
    progress.at(Stage::Step, 1.0);
    Ok(ReconstructResult {
        build,
        patches: Some(seg.patches.len()),
        edges: Some(edges),
        ms_segment,
        ms_topology,
        inventory: Some(seg.inventory),
        unknown_area_fraction: seg.unknown_area_fraction,
    })
}

fn fallback_all(
    mesh: &MeshData,
    options: &ReconstructOptions,
    reason: String,
) -> Result<BuildResult> {
    let faceted = faceted_step(mesh, &options.faceted)?;
    let source = mesh.welded().map(|w| geom::MeshGeom::new(&w)).ok();
    let source_volume = source.as_ref().map_or(0.0, |g| g.volume);
    let result_mesh = source.as_ref().map_or_else(ResultMesh::default, |g| {
        ResultMesh::new(&g.points, &flat_indices(&g.triangles))
    });
    Ok(BuildResult {
        tier: Tier::Faceted,
        faces_analytic: 0,
        faces_triangle: faceted.faces_imported as usize,
        faces_final: faceted.faces_unified as usize,
        valid: faceted.valid,
        issues: faceted.issues,
        fallback_reason: Some(reason),
        deviation: None,
        volume: source_volume,
        source_volume,
        step_bytes: faceted.step.len(),
        step: faceted.step,
        round_trip_ok: false,
        face_failures: Vec::new(),
        edges_nurbs: 0,
        edges_curve_chain: 0,
        ms_build: 0.0,
        ms_verify: 0.0,
        mesh: result_mesh,
    })
}
