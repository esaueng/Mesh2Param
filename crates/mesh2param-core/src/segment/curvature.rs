//! Discrete per-vertex curvature, and the per-triangle "smoothly curved" score
//! the freeform gates are built on.
//!
//! # Why this exists
//!
//! A shard carved out of a B-spline surface and a genuinely small planar face
//! are the same size, hold the same number of triangles and fit a plane equally
//! well — every size-based gate that separates them costs real CAD faces
//! somewhere else on the corpus (see the README's known limits). They differ in
//! exactly one measurable way: the shard's **neighbourhood** is curved, and the
//! small face's is not.
//!
//! # The estimator
//!
//! Mean curvature comes from the cotangent (normal-cycle) mean-curvature normal
//! and Gaussian curvature from the angle deficit, both over the one-ring and
//! both normalised by Meyer's mixed area:
//!
//! ```text
//! K(v)   = 1 / (2 A_mixed) * sum_j (cot a_ij + cot b_ij) (v - v_j)
//! H(v)   = |K| / 2
//! G(v)   = (2 pi - sum of incident corner angles) / A_mixed
//! kappa1 = H + sqrt(max(H^2 - G, 0)),  kappa2 = H - sqrt(...)
//! ```
//!
//! Both are accumulated in **one pass over the triangles** — each triangle
//! touches its own three corners and nothing else — so the whole estimate is
//! O(triangles) in time and O(vertices) in space, with no adjacency structure
//! beyond the one [`WeldedMesh`](crate::mesh::WeldedMesh) already carries.
//!
//! The normal cycle is the right choice here rather than a local quadric fit:
//! a quadric needs a two-ring to be conditioned, which is the neighbourhood
//! whose size the shards make unreliable in the first place, and it costs a
//! 3x3 solve per vertex. The cotangent form is exact on a developable surface
//! and converges on a smooth one, which is all the gates ask of it.
//!
//! # A crease is not curvature
//!
//! The cotangent operator reports a *large* mean curvature at a box's edge:
//! the one-ring folds, and the operator cannot tell a fold from a very tight
//! bend. So a vertex with any incident dihedral above the facet limit — and any
//! vertex on a boundary or non-manifold edge, whose one-ring does not close and
//! whose angle deficit is therefore meaningless — is **unmeasured** rather than
//! curved or flat.
//!
//! That leaves three states per vertex, and two scores per triangle, because
//! the two gates make opposite claims and need opposite defaults. Curvature is
//! evidence, measured flatness is counter-evidence, and a crease is silence.
//!
//! * **Smooth** — at least one corner curved, no corner flat, no fold across
//!   any of the triangle's own edges. The permissive score, weighed by area to
//!   decide whether a fitted *plane* is real. Refusing a plane is a negative
//!   claim, so silence counts towards it, which matters because the rim of a
//!   curved face is precisely the part whose corners are unmeasured.
//! * **Core** — every corner curved, and no fold. The strict score, and the
//!   only thing that holds two triangles together against a re-cut. That is a
//!   positive and irreversible claim — nothing downstream re-cuts a patch — so
//!   silence must not carry it: a cylinder tangent to a dome has its far rim on
//!   a crease, and one unmeasured corner is all that keeps it from being
//!   swallowed by the dome.
//!
//! Either way:
//!
//! * A chamfer facet on a coarse mesh has creases all round it and no curved
//!   corner anywhere, so it is promoted as the plane it is. So is a coarse
//!   cylinder's rim-to-rim strip, and every face of a box.
//! * A planar face on a curved part has measured-flat corners over its
//!   interior, which veto it however its rim is bounded.
//! * The rim of a curved face — the only part of it that touches its own
//!   boundary — is not thrown away merely for being the rim, which it would be
//!   if silence counted against it. That rim is exactly where the shards used
//!   to survive.

use super::grow::Geom;
use super::linalg::{V3, angle_undirected};

/// How gently a surface may bend and still count as curved, as a multiple of
/// the bounding-box diagonal: a neighbourhood is curved when its radius of
/// curvature is below `k x diagonal`, i.e. `|kappa| > 1 / (k x diagonal)`.
///
/// Two, not a fraction and not a large number. The signal is one-sided, so the
/// threshold only has to sit between two well-separated populations rather than
/// name a physical limit:
///
/// * A planar CAD face is *exactly* planar, and the operator returns exactly
///   zero on coplanar triangles. What is left is the tessellator's own decimal
///   rounding, which the weld absorbs at `1e-6 x diagonal`: a positional error
///   `d` over a chord `h` reads as a curvature of about `d / h^2`, which is
///   `1e-4 / 1` on a 100 mm part meshed at 1 mm — four orders of magnitude
///   under the threshold.
/// * A curved face steep enough to matter to reconstruction has a radius well
///   under the part itself. Two diagonals is the far side of "that is not
///   really a curve any more": a 100 mm part's 200 mm-radius blend is 0.4 mm of
///   sagitta across a 40 mm span, and below that the plane fit's own tolerance
///   accepts the region anyway, so the gate has nothing left to decide.
const CURVATURE_RADIUS_FACTOR: f64 = 2.0;

/// How far two adjacent triangles' curvatures may differ and still be called
/// one surface.
///
/// Half again in the radius, no more. This is what separates two surfaces
/// that meet *tangentially*, where the normals are continuous and the dihedral
/// says nothing at all: a fillet of radius `r` blended into a face of radius
/// `R` steps the curvature by `R / r` across the join, and a fillet is a
/// fillet precisely because it is much tighter than what it blends. Along one
/// surface the curvature varies chord by chord, not by factors.
const CURVATURE_STEP_RATIO: f64 = 1.5;

/// Per-triangle curvature evidence for one mesh.
pub(super) struct Curvature {
    /// Mean over the triangle's three corners of the dominant principal
    /// curvature magnitude, `max(|kappa1|, |kappa2|)`, in reciprocal mesh
    /// units. A corner where curvature is not measurable — a crease, an open or
    /// non-manifold edge — contributes zero.
    pub kappa: Vec<f64>,
    /// Whether the triangle lies in a smoothly curved neighbourhood: at least
    /// one corner measured past the curvature threshold, no corner measured
    /// flat, and no edge of the triangle folded past the facet limit.
    ///
    /// This is the score the promotion gate weighs, and it is deliberately the
    /// permissive of the two: refusing to call a region a plane is a *negative*
    /// claim, and the rim of a curved face — whose corners sit on the creases
    /// that bound it and are therefore unmeasured — has to count towards it.
    pub smooth: Vec<bool>,
    /// Whether the triangle's whole neighbourhood is measured curved: **every**
    /// corner past the threshold, and no fold.
    ///
    /// The strict score, and the one the grouping uses. Fusing two triangles
    /// into one region is a *positive* claim — it says they are two samples of
    /// a single surface — and it is not reversible: nothing downstream re-cuts
    /// a patch. An unmeasured corner is not enough to make it. The asymmetry is
    /// what keeps a cylinder tangent to a dome out of the dome's region while
    /// still refusing to plate the dome's own rim.
    pub core: Vec<bool>,
}

impl Curvature {
    /// Area of `faces` that is smoothly curved, as a fraction of their total.
    ///
    /// Zero for an empty or degenerate set, which is the answer that keeps a
    /// patch out of the freeform bucket.
    pub(super) fn smooth_area_fraction(&self, g: &Geom, faces: &[u32]) -> f64 {
        let mut smooth = 0.0;
        let mut total = 0.0;
        for &f in faces {
            let Some(face) = g.faces.get(f as usize) else {
                continue;
            };
            total += face.area;
            if self.smooth.get(f as usize).copied().unwrap_or(false) {
                smooth += face.area;
            }
        }
        if total > 0.0 { smooth / total } else { 0.0 }
    }

    /// Do these two edge-adjacent triangles belong to one smooth curved region?
    ///
    /// Both have to be curved throughout — [`Self::core`] already says no edge
    /// of either folds past the facet limit — and they have to be curved by
    /// *comparable amounts*. Curvature varies smoothly along one surface and
    /// steps at the join between two, which is the only thing that separates
    /// them where they meet tangentially: a fillet of radius `r` blended into a
    /// face of radius `R` has continuous normals across the join and nothing
    /// else to give it away. Without the ratio the rule fuses every fillet into
    /// its neighbour and the corpus loses its tori outright.
    pub(super) fn same_freeform(&self, a: u32, b: u32) -> bool {
        let (Some(true), Some(true)) = (
            self.core.get(a as usize).copied(),
            self.core.get(b as usize).copied(),
        ) else {
            return false;
        };
        let (Some(&ka), Some(&kb)) = (self.kappa.get(a as usize), self.kappa.get(b as usize))
        else {
            return false;
        };
        ka.min(kb) > 0.0 && ka.max(kb) <= CURVATURE_STEP_RATIO * ka.min(kb)
    }
}

/// One vertex's accumulators.
#[derive(Clone, Copy, Default)]
struct Vert {
    /// Cotangent-weighted sum of `(v - v_j)` over the one-ring.
    lap: V3,
    /// Sum of the incident corner angles.
    angles: f64,
    /// Meyer's mixed area.
    area: f64,
    /// A crease, boundary or non-manifold vertex carries no curvature.
    creased: bool,
}

/// Cotangent of the angle between `u` and `v`, clamped to what a nearly
/// degenerate corner can support.
///
/// A sliver's cotangent runs away to `1 / sin(eps)`, and one sliver in a
/// one-ring would otherwise decide that vertex's whole curvature. The clamp is
/// the standard one: a corner under about half a degree is treated as half a
/// degree.
fn cotangent(u: V3, v: V3) -> f64 {
    let sin = u.cross(v).norm();
    (u.dot(v) / sin.max(1e-2 * u.norm() * v.norm())).clamp(-100.0, 100.0)
}

/// Mark every vertex that sits on a crease, an open edge or a non-manifold one,
/// and report per triangle whether it is itself folded away from a neighbour.
///
/// Walks each triangle's neighbours, finds the edge they share by intersecting
/// the corner sets (three by three, so still O(triangles) with the neighbour
/// lists the weld already produced), and marks both of its endpoints when the
/// pair folds past `max_crease`. An edge with anything other than exactly one
/// neighbour marks its endpoints too: an open or non-manifold one-ring does not
/// close, so its angle deficit measures the hole rather than the surface. The
/// triangle-level flag is only about folds — a hole in the mesh is not a crease
/// in the surface.
fn mark_creases(g: &Geom, max_crease: f64, verts: &mut [Vert]) -> Vec<bool> {
    let mut folded = vec![false; g.faces.len()];
    for (fi, face) in g.faces.iter().enumerate() {
        // `covered[k]` counts neighbours across the edge from corner `k` to
        // corner `k + 1`.
        let mut covered = [0_u32; 3];
        for &h in g.neighbours_of(fi as u32) {
            let Some(other) = g.faces.get(h as usize) else {
                continue;
            };
            // The shared edge is the one whose both endpoints the neighbour
            // also owns. Three comparisons of three, so no allocation and no
            // edge map: this stays a linear pass over the mesh.
            let mut shared = None;
            for k in 0..3 {
                let e = (face.v[k], face.v[(k + 1) % 3]);
                if other.v.contains(&e.0) && other.v.contains(&e.1) {
                    if let Some(slot) = covered.get_mut(k) {
                        *slot += 1;
                    }
                    shared = Some(e);
                    break;
                }
            }
            let Some((a, b)) = shared else { continue };
            // A degenerate triangle's normal is arbitrary, so it can neither
            // create a crease nor hide one.
            if face.area > 0.0
                && other.area > 0.0
                && angle_undirected(face.normal, other.normal) > max_crease
            {
                if let Some(slot) = folded.get_mut(fi) {
                    *slot = true;
                }
                for v in [a, b] {
                    if let Some(slot) = verts.get_mut(v as usize) {
                        slot.creased = true;
                    }
                }
            }
        }
        for (k, &count) in covered.iter().enumerate() {
            if count != 1 {
                for v in [face.v[k], face.v[(k + 1) % 3]] {
                    if let Some(slot) = verts.get_mut(v as usize) {
                        slot.creased = true;
                    }
                }
            }
        }
    }
    folded
}

/// Estimate curvature over the whole mesh and score every triangle.
///
/// `max_crease` is the facet limit in radians ([`super::SegmentOptions::max_facet_deg`]),
/// and `bbox_diag` sets the curvature threshold; both are the mesh's own scale,
/// never an absolute length.
pub(super) fn estimate(g: &Geom, max_crease: f64, bbox_diag: f64) -> Curvature {
    let mut verts = vec![Vert::default(); g.verts.len()];
    let folded = mark_creases(g, max_crease, &mut verts);

    for face in &g.faces {
        let (Some(&a), Some(&b), Some(&c)) = (
            g.verts.get(face.v[0] as usize),
            g.verts.get(face.v[1] as usize),
            g.verts.get(face.v[2] as usize),
        ) else {
            continue;
        };
        if face.area <= 0.0 {
            continue;
        }
        let p = [a, b, c];
        // Corner angles and their cotangents, corner `i` opposite edge `i`.
        let mut cot = [0.0_f64; 3];
        let mut ang = [0.0_f64; 3];
        for i in 0..3 {
            let (u, v) = (p[(i + 1) % 3].sub(p[i]), p[(i + 2) % 3].sub(p[i]));
            cot[i] = cotangent(u, v);
            ang[i] = super::linalg::angle_between(u, v);
        }
        let obtuse = ang.iter().position(|&x| x > core::f64::consts::FRAC_PI_2);
        for i in 0..3 {
            let Some(slot) = verts.get_mut(face.v[i] as usize) else {
                continue;
            };
            slot.angles += ang[i];
            // Mixed area: the Voronoi region where the triangle is acute, and
            // the obtuse-safe split of Meyer et al. where it is not.
            slot.area += match obtuse {
                Some(o) if o == i => 0.5 * face.area,
                Some(_) => 0.25 * face.area,
                None => {
                    let e1 = p[(i + 1) % 3].sub(p[i]);
                    let e2 = p[(i + 2) % 3].sub(p[i]);
                    e2.dot(e2)
                        .mul_add(cot[(i + 1) % 3], e1.dot(e1) * cot[(i + 2) % 3])
                        / 8.0
                }
            };
            // The cotangent Laplacian: the two edges at this corner are
            // weighted by the cotangent of the angle facing them.
            let d1 = p[i].sub(p[(i + 1) % 3]).mul(cot[(i + 2) % 3]);
            let d2 = p[i].sub(p[(i + 2) % 3]).mul(cot[(i + 1) % 3]);
            slot.lap = slot.lap.add(d1).add(d2);
        }
    }

    let threshold = if bbox_diag > 0.0 {
        1.0 / (CURVATURE_RADIUS_FACTOR * bbox_diag)
    } else {
        f64::INFINITY
    };
    let state: Vec<Corner> = verts.iter().map(|v| classify(*v, threshold)).collect();

    let mut face_kappa = Vec::with_capacity(g.faces.len());
    let mut face_smooth = Vec::with_capacity(g.faces.len());
    let mut face_core = Vec::with_capacity(g.faces.len());
    for (fi, face) in g.faces.iter().enumerate() {
        let mut sum = 0.0;
        let mut flat = false;
        let mut curved = false;
        let mut all_curved = true;
        for v in face.v {
            match state.get(v as usize).copied().unwrap_or(Corner::Unknown) {
                Corner::Curved(k) => {
                    sum += k;
                    curved = true;
                }
                Corner::Flat(k) => {
                    sum += k;
                    flat = true;
                    all_curved = false;
                }
                Corner::Unknown => all_curved = false,
            }
        }
        face_kappa.push(sum / 3.0);
        // Curvature is evidence, measured flatness is counter-evidence, and a
        // crease is silence. A corner on a crease or an open edge has no
        // one-ring to measure, so it neither qualifies a triangle nor
        // disqualifies it: what it must not do is veto the whole rim of every
        // curved face, which is the only part of a face that touches its own
        // boundary. One measured-flat corner *is* a veto — that is a real
        // measurement saying the surface does not bend here — so a planar face
        // is safe however it is bounded, and a chamfer facet, whose corners are
        // all creases and none of them curved, is safe too.
        let unfolded = face.area > 0.0 && !folded.get(fi).copied().unwrap_or(false);
        face_smooth.push(unfolded && curved && !flat);
        face_core.push(unfolded && all_curved);
    }
    Curvature {
        kappa: face_kappa,
        smooth: face_smooth,
        core: face_core,
    }
}

/// What one vertex says about the surface around it.
#[derive(Clone, Copy, PartialEq)]
enum Corner {
    /// Measured, and bending past the threshold: `max(|kappa1|, |kappa2|)`.
    Curved(f64),
    /// Measured, and not bending.
    Flat(f64),
    /// Not measurable here: a crease, an open edge, a non-manifold edge, or a
    /// vertex with no area.
    Unknown,
}

/// Classify one vertex from its accumulated one-ring.
fn classify(v: Vert, threshold: f64) -> Corner {
    let k = principal_magnitude(v);
    match k {
        Some(k) if k >= threshold => Corner::Curved(k),
        Some(k) => Corner::Flat(k),
        None => Corner::Unknown,
    }
}

/// `max(|kappa1|, |kappa2|)` at one vertex, or `None` where curvature is not
/// defined there.
fn principal_magnitude(v: Vert) -> Option<f64> {
    if v.creased || v.area <= 0.0 || !v.area.is_finite() {
        return None;
    }
    let mean = 0.5 * v.lap.mul(1.0 / (2.0 * v.area)).norm();
    let gauss = (core::f64::consts::TAU - v.angles) / v.area;
    if !mean.is_finite() || !gauss.is_finite() {
        return None;
    }
    // `kappa1 = H + sqrt(H^2 - G)` and `kappa2 = H - sqrt(H^2 - G)`, with H
    // taken positive: the sign of the mean curvature is the surface's
    // orientation, not evidence about how sharply it bends. The discriminant
    // goes slightly negative on a near-umbilic vertex through rounding alone.
    let root = mean.mul_add(mean, -gauss).max(0.0).sqrt();
    Some((mean + root).max((mean - root).abs()))
}
