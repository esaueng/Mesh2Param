//! Sufficient statistics for a face set, and the screen that keeps a trial
//! merge from paying for a fit it cannot pass.
//!
//! # Why this exists
//!
//! The merge stage trial-merges every adjacent pair of patches and keeps the
//! merge when the union still fits a primitive. Fitting the union costs a pass
//! over its vertices for each of the five primitives, two of them with a
//! Gauss-Newton refinement on top — so a patch of *n* triangles with *k*
//! neighbours costs `O(n k)` per round, and a freeform region that the
//! curvature gate deliberately keeps in one piece has both numbers large.
//! `hammer-holder/mesh-export` spends 98 million triangle-visits there.
//!
//! Almost none of those merges are taken. What separates the ones that might
//! be is computable from a handful of running sums that **add** when two face
//! sets are joined, so a trial merge is screened in constant time and only the
//! survivors are fitted:
//!
//! * the face count, the area and the total sample weight;
//! * the samples' centroid and their second and third moments *about it*;
//! * the area-weighted mean face normal, and the normals' second moment both
//!   raw and about that mean;
//! * the sharpest crease inside the set, and the smoothly curved area.
//!
//! Central moments rather than raw ones because a union's are reached by the
//! parallel-axis shift, which stays conditioned where `M2 - w m (x) m` cancels:
//! the patches this is for sit far from the origin relative to their own size.
//!
//! # What the screen may and may not do
//!
//! It may only refuse a merge the fit would have refused anyway. Every test
//! below is therefore a *necessary* condition for
//! [`accept_merge`](super::grow) — a bound in the direction that can only
//! reject, never a decision of its own:
//!
//! * a crease sharper than one facet step makes the whole set unfittable,
//!   whatever the residuals say, and that is exact;
//! * the plane is fitted **from the moments themselves**, and its residual is
//!   their smallest eigenvalue, which the fit's own pass over the samples
//!   reproduces to within its summation order;
//! * a normal deviation is bounded below through `sin theta <= theta`: a plane's
//!   from `A - n^T N n`, a cylinder's from the smallest eigenvalue of `N`,
//!   both of which the normals' second moment carries exactly;
//! * a cylinder, cone or torus needs an axis its normals actually determine,
//!   and that determination is a property of the same moment matrix;
//! * a sphere's centre and radius come out of the moments algebraically, so
//!   its size guards can be applied without touching a vertex. Its residual
//!   cannot, which is why a large smooth region still reaches the fit — and
//!   why the fits take the axes computed here rather than recomputing them.
//!
//! Where a bound and the fit reach the same number by different summation
//! orders, the bound is given [`SLACK`]: erring towards passing costs a fit
//! that was going to fail, while erring towards rejecting would silently change
//! what the stage recognises.

use core::f64::consts::PI;

use super::curvature::Curvature;
#[cfg(test)]
use super::fit::{FaceRef, Sample};
use super::fit::{FitOpts, MAX_RADIUS_EXTENT_FACTOR, axis_determined, radius_sane};
use super::grow::{Geom, max_crease};
use super::linalg::{V3, angle_between, jacobi3, solve_small};

/// A symmetric 3x3 accumulator.
type M3 = [[f64; 3]; 3];

/// `a + b`.
fn add3(a: M3, b: M3) -> M3 {
    let mut out = a;
    for i in 0..3 {
        for j in 0..3 {
            out[i][j] += b[i][j];
        }
    }
    out
}

/// `m + w d (x) d`: the parallel-axis shift of a second moment.
fn shift2(m: M3, d: V3, w: f64) -> M3 {
    let v = d.arr();
    let mut out = m;
    for i in 0..3 {
        for j in 0..3 {
            out[i][j] += w * v[i] * v[j];
        }
    }
    out
}

/// `m + w v (x) v`, accumulated in place.
fn accumulate(m: &mut M3, v: V3, w: f64) {
    let a = v.arr();
    for i in 0..3 {
        for j in 0..3 {
            m[i][j] += w * a[i] * a[j];
        }
    }
}

/// `v^T m v`.
fn quad(m: M3, v: V3) -> f64 {
    let a = v.arr();
    let mut acc = 0.0;
    for i in 0..3 {
        for j in 0..3 {
            acc += m[i][j] * a[i] * a[j];
        }
    }
    acc
}

/// `m v`.
fn matvec(m: M3, v: V3) -> V3 {
    let a = v.arr();
    let mut out = [0.0_f64; 3];
    for i in 0..3 {
        for j in 0..3 {
            out[i] += m[i][j] * a[j];
        }
    }
    V3::from_arr(out)
}

fn trace(m: M3) -> f64 {
    m[0][0] + m[1][1] + m[2][2]
}

fn scale3(m: M3, s: f64) -> M3 {
    let mut out = m;
    for row in &mut out {
        for v in row.iter_mut() {
            *v *= s;
        }
    }
    out
}

/// The third central moment `T = sum w e |e|^2` shifted to a centre `d` further
/// away, given that set's own second central moment.
///
/// `sum w (e + d) |e + d|^2` expands to `T + 2 P d + d tr(P) + w |d|^2 d` once
/// the terms in `sum w e`, which is zero by construction, drop out.
fn shift3(t: V3, p2: M3, d: V3, w: f64) -> V3 {
    t.add(matvec(p2, d).mul(2.0))
        .add(d.mul(trace(p2)))
        .add(d.mul(w * d.dot(d)))
}

/// How much slack the screen allows itself against a fit's own thresholds.
///
/// A part per million, which is not a tolerance: the two sides compute the same
/// quantity and differ only in the order they sum it and, for a plane whose
/// second moment barely separates two directions, in an eigenvector that is
/// itself a coin flip. Nothing in the corpus sits within a part per million of
/// a fit threshold, and a decision that did would not be reproducible anyway.
const SLACK: f64 = 1.0 + 1e-6;

/// Running sums over one face set, all of which add when two sets are joined.
///
/// Everything here is either exactly additive or, where it cannot be
/// ([`Self::cone`], [`Self::radius`], [`Self::crease`]), a bound in the
/// direction the screen needs: an upper bound on a quantity a fit requires to
/// be small, a lower bound on one it requires to be large.
pub(super) struct Stats {
    /// Triangles in the set.
    pub faces: usize,
    /// Upper bound on the number of distinct samples the fits will see. A
    /// vertex shared by two triangles is counted twice here and once there,
    /// which is the safe direction for a `samples >= k` guard.
    pub samples: usize,
    /// Total area.
    pub area: f64,
    /// Total sample weight. Equal to the area — every triangle spreads its own
    /// area over its samples — but kept separately because it is the divisor
    /// the fits use.
    pub w: f64,
    /// Weighted centroid of the samples.
    pub centroid: V3,
    /// Second moment of the samples about [`Self::centroid`].
    pub p2: M3,
    /// Third moment `sum w (p - centroid) |p - centroid|^2`, which is what the
    /// sphere's algebraic fit needs beyond the second.
    pub p3: V3,
    /// Upper bound on the largest sample distance from [`Self::centroid`].
    pub radius: f64,
    /// Area-weighted mean face normal. Not a unit vector: its length is itself
    /// evidence of how much the normals spread.
    pub nbar: V3,
    /// Raw area-weighted second moment of the face normals — the matrix a
    /// cylinder takes its axis from.
    pub n2: M3,
    /// The same about [`Self::nbar`] — the matrix a cone or torus takes its
    /// axis from.
    pub n2c: M3,
    /// Upper bound on the largest angle between a face normal and
    /// [`Self::nbar`].
    pub cone: f64,
    /// Sharpest crease inside the set: exact for a single patch or for the
    /// union of two adjacent ones, and a lower bound once a chain of merges
    /// has been folded together, which is the direction that only ever refuses
    /// to reject.
    pub crease: f64,
    /// Area lying in a smoothly curved neighbourhood.
    pub smooth_area: f64,
}

/// Run `f` over the samples one triangle contributes, exactly as
/// [`super::grow`] gathers them: its centroid, or its three corners each
/// carrying a third of its area.
fn for_each_sample(g: &Geom, f: u32, centroids: bool, mut visit: impl FnMut(V3, f64)) {
    let Some(face) = g.faces.get(f as usize) else {
        return;
    };
    if centroids {
        visit(face.centroid, face.area);
        return;
    }
    for v in face.v {
        if let Some(&p) = g.verts.get(v as usize) {
            visit(p, face.area / 3.0);
        }
    }
}

impl Stats {
    /// Accumulate the statistics of one face set.
    ///
    /// Two passes: the first fixes the centroid and the mean normal, the second
    /// takes the moments about them.
    pub(super) fn of(g: &Geom, curv: &Curvature, faces: &[u32], centroids: bool) -> Self {
        let mut area = 0.0;
        let mut w = 0.0;
        let mut psum = V3::ZERO;
        let mut nsum = V3::ZERO;
        let mut smooth_area = 0.0;
        let mut samples = 0_usize;
        for &f in faces {
            let Some(face) = g.faces.get(f as usize) else {
                continue;
            };
            area += face.area;
            nsum = nsum.add(face.normal.mul(face.area));
            if curv.smooth.get(f as usize).copied().unwrap_or(false) {
                smooth_area += face.area;
            }
            for_each_sample(g, f, centroids, |p, weight| {
                w += weight;
                psum = psum.add(p.mul(weight));
                samples += 1;
            });
        }
        let centroid = if w > 0.0 { psum.mul(1.0 / w) } else { V3::ZERO };
        let nbar = if area > 0.0 {
            nsum.mul(1.0 / area)
        } else {
            V3::ZERO
        };

        let mut p2 = [[0.0_f64; 3]; 3];
        let mut p3 = V3::ZERO;
        let mut n2 = [[0.0_f64; 3]; 3];
        let mut n2c = [[0.0_f64; 3]; 3];
        let mut radius: f64 = 0.0;
        let mut cone: f64 = 0.0;
        let unit_nbar = nbar.unit();
        for &f in faces {
            let Some(face) = g.faces.get(f as usize) else {
                continue;
            };
            accumulate(&mut n2, face.normal, face.area);
            accumulate(&mut n2c, face.normal.sub(nbar), face.area);
            if let Some(m) = unit_nbar {
                cone = cone.max(angle_between(face.normal, m));
            }
            for_each_sample(g, f, centroids, |p, weight| {
                let d = p.sub(centroid);
                accumulate(&mut p2, d, weight);
                p3 = p3.add(d.mul(weight * d.dot(d)));
                radius = radius.max(d.norm());
            });
        }
        Self {
            faces: faces.len(),
            samples,
            area,
            w,
            centroid,
            p2,
            p3,
            radius,
            nbar,
            n2,
            n2c,
            // A mean normal too short to point anywhere says nothing about how
            // far the normals wander, so the bound has to be the whole turn.
            cone: if unit_nbar.is_some() { cone } else { PI },
            crease: max_crease(g, faces),
            smooth_area,
        }
    }

    /// The statistics of two face sets joined, in constant time.
    ///
    /// `boundary_crease` is the sharpest fold across an edge shared by the two
    /// sets; the caller has it from the same scan that found the pair.
    pub(super) fn combined(a: &Self, b: &Self, boundary_crease: f64) -> Self {
        let w = a.w + b.w;
        let centroid = if w > 0.0 {
            a.centroid.mul(a.w).add(b.centroid.mul(b.w)).mul(1.0 / w)
        } else {
            V3::ZERO
        };
        let (da, db) = (a.centroid.sub(centroid), b.centroid.sub(centroid));
        let area = a.area + b.area;
        let nbar = if area > 0.0 {
            a.nbar.mul(a.area).add(b.nbar.mul(b.area)).mul(1.0 / area)
        } else {
            V3::ZERO
        };
        let (ea, eb) = (a.nbar.sub(nbar), b.nbar.sub(nbar));
        // A normal's angle to the joint mean is at most its angle to its own
        // patch's mean plus the angle between the two means.
        let cone = if nbar.unit().is_some() {
            (a.cone + angle_between(a.nbar, nbar))
                .max(b.cone + angle_between(b.nbar, nbar))
                .min(PI)
        } else {
            PI
        };
        Self {
            faces: a.faces + b.faces,
            samples: a.samples + b.samples,
            area,
            w,
            centroid,
            p2: add3(shift2(a.p2, da, a.w), shift2(b.p2, db, b.w)),
            p3: shift3(a.p3, a.p2, da, a.w).add(shift3(b.p3, b.p2, db, b.w)),
            radius: (a.radius + da.norm()).max(b.radius + db.norm()),
            nbar,
            n2: add3(a.n2, b.n2),
            n2c: add3(shift2(a.n2c, ea, a.area), shift2(b.n2c, eb, b.area)),
            cone,
            crease: a.crease.max(b.crease).max(boundary_crease),
            smooth_area: a.smooth_area + b.smooth_area,
        }
    }

    /// The same statistics from samples and faces that are already in hand.
    ///
    /// Only the unit tests, which build a patch by hand rather than out of a
    /// mesh; the moments are the same sums in the same order.
    #[cfg(test)]
    pub(super) fn from_samples(pts: &[Sample], faces: &[FaceRef], crease: f64) -> Self {
        let area: f64 = faces.iter().map(|f| f.a).sum();
        let w: f64 = pts.iter().map(|s| s.w).sum();
        let mut psum = V3::ZERO;
        for s in pts {
            psum = psum.add(s.p.mul(s.w));
        }
        let mut nsum = V3::ZERO;
        for f in faces {
            nsum = nsum.add(f.n.mul(f.a));
        }
        let centroid = if w > 0.0 { psum.mul(1.0 / w) } else { V3::ZERO };
        let nbar = if area > 0.0 {
            nsum.mul(1.0 / area)
        } else {
            V3::ZERO
        };
        let mut p2 = [[0.0_f64; 3]; 3];
        let mut p3 = V3::ZERO;
        let mut radius: f64 = 0.0;
        for s in pts {
            let d = s.p.sub(centroid);
            accumulate(&mut p2, d, s.w);
            p3 = p3.add(d.mul(s.w * d.dot(d)));
            radius = radius.max(d.norm());
        }
        let mut n2 = [[0.0_f64; 3]; 3];
        let mut n2c = [[0.0_f64; 3]; 3];
        let mut cone: f64 = 0.0;
        let unit_nbar = nbar.unit();
        for f in faces {
            accumulate(&mut n2, f.n, f.a);
            accumulate(&mut n2c, f.n.sub(nbar), f.a);
            if let Some(m) = unit_nbar {
                cone = cone.max(angle_between(f.n, m));
            }
        }
        Self {
            faces: faces.len(),
            samples: pts.len(),
            area,
            w,
            centroid,
            p2,
            p3,
            radius,
            nbar,
            n2,
            n2c,
            cone: if unit_nbar.is_some() { cone } else { PI },
            crease,
            smooth_area: 0.0,
        }
    }

    /// Share of the set's area that lies in a smoothly curved neighbourhood.
    pub(super) fn smooth_fraction(&self) -> f64 {
        if self.area > 0.0 {
            self.smooth_area / self.area
        } else {
            0.0
        }
    }

    /// The plane the samples' second moment names, with the area-weighted RMS
    /// distance of the samples from it.
    ///
    /// `sum w (n . p - n . m)^2` is `n^T P2 n`, so the residual is in the moment
    /// already and costs no pass over the samples. The residual is the moment's
    /// smallest eigenvalue and so does not care that the moment may name a
    /// slightly different normal than a direct pass over the samples would;
    /// [`SLACK`] covers the rest.
    pub(super) fn plane(&self) -> Option<(V3, f64)> {
        if !(self.w.is_finite() && self.w > 0.0) {
            return None;
        }
        let (_, vecs) = jacobi3(scale3(self.p2, 1.0 / self.w));
        let n = vecs[0].unit()?;
        Some((n, (quad(self.p2, n).max(0.0) / self.w).sqrt()))
    }

    /// The axis a cylinder takes: the direction of least second moment of the
    /// raw face normals, when the normals determine it at all.
    ///
    /// Also returns that smallest eigenvalue, which is `sum a (n . axis)^2` and
    /// so bounds how far the normals lie off the plane perpendicular to the
    /// axis — the deviation any cylinder through this patch must pay.
    pub(super) fn cylinder_axis(&self) -> Option<(V3, f64)> {
        let (vals, vecs) = jacobi3(self.n2);
        axis_determined(vals)
            .then(|| vecs[0].unit())
            .flatten()
            .map(|d| (d, vals[0]))
    }

    /// The axis a cone or a torus takes: the same direction for the normals'
    /// moment *about their mean*, where `n . axis` is constant rather than zero.
    pub(super) fn conic_axis(&self) -> Option<V3> {
        let (vals, vecs) = jacobi3(self.n2c);
        axis_determined(vals).then(|| vecs[0].unit()).flatten()
    }

    /// Upper bound on the angular spread of the face normals, measured exactly
    /// as [`super::fit::normal_spread`] measures it.
    pub(super) fn spread_ceiling(&self) -> f64 {
        (2.0 * self.cone).min(PI)
    }

    /// Lower bound on the RMS angle between the face normals and a surface
    /// whose own normal is everywhere perpendicular to `axis` — a cylinder.
    ///
    /// `lambda` is `sum a (n . axis)^2`: the sine of the angle from a normal to
    /// that whole perpendicular plane, which no choice of surface normal in it
    /// can beat, and `sin theta <= theta`.
    fn axial_dev_floor(&self, lambda: f64) -> f64 {
        if self.area > 0.0 {
            (lambda / self.area).max(0.0).sqrt()
        } else {
            0.0
        }
    }

    /// Lower bound on the RMS angle between the face normals and the fixed
    /// direction `n` — a plane's.
    fn plane_dev_floor(&self, n: V3) -> f64 {
        self.axial_dev_floor(self.area - quad(self.n2, n))
    }

    /// The sphere the moments name algebraically, by the same Kasa least
    /// squares [`super::fit`] solves — reachable in closed form because its
    /// normal equations need nothing beyond the third moment.
    fn sphere(&self) -> Option<(V3, f64)> {
        if !(self.w.is_finite() && self.w > 0.0) {
            return None;
        }
        let mut mat = [[0.0_f64; 4]; 4];
        let mut rhs = [0.0_f64; 4];
        for i in 0..3 {
            for j in 0..3 {
                mat[i][j] = self.p2[i][j];
            }
            rhs[i] = self.p3.arr()[i];
        }
        mat[3][3] = self.w;
        rhs[3] = trace(self.p2);
        let sol = solve_small(4, &mat, &rhs)?;
        let c = V3::new(0.5 * sol[0], 0.5 * sol[1], 0.5 * sol[2]);
        let rsq = sol[3] + c.dot(c);
        if !rsq.is_finite() || rsq <= 0.0 {
            return None;
        }
        Some((c.add(self.centroid), rsq.sqrt()))
    }

    /// Could a sphere clear its size guards on this set? Its residual cannot be
    /// bounded from the moments, so this is all the screen can say about it.
    fn sphere_possible(&self, o: FitOpts) -> bool {
        self.sphere().is_some_and(|(_, r)| {
            radius_sane(r, o) && self.radius > 0.0 && r <= MAX_RADIUS_EXTENT_FACTOR * self.radius
        })
    }
}

/// Which primitives could still be accepted on this face set at tolerance
/// `o.tol`.
///
/// Every `false` here is a necessary condition for
/// [`super::fit::fit_patch`] failing to choose that primitive, so the fit may
/// skip it outright: a merge this refuses is a merge the fit would have
/// refused. A `true` says only that the fit has to be run.
#[derive(Clone, Copy)]
// Five independent yes/no answers about five independent primitives; there is
// no state machine here to refactor them into.
#[allow(clippy::struct_excessive_bools)]
pub(super) struct Allow {
    /// The plane may still be chosen.
    pub plane: bool,
    /// The cylinder may still be chosen.
    pub cylinder: bool,
    /// The cone may still be chosen.
    pub cone: bool,
    /// The torus may still be chosen.
    pub torus: bool,
    /// The sphere may still be chosen.
    pub sphere: bool,
}

impl Allow {
    /// Every primitive: what a patch that is being fitted for its own sake,
    /// rather than trial-merged, is judged under. Such a fit also reports the
    /// residual of the *nearest rejected* candidate, which a screened fit no
    /// longer knows.
    pub(super) const ALL: Self = Self {
        plane: true,
        cylinder: true,
        cone: true,
        torus: true,
        sphere: true,
    };

    /// Nothing at all: the set fits no primitive whatever the residuals say.
    const NONE: Self = Self {
        plane: false,
        cylinder: false,
        cone: false,
        torus: false,
        sphere: false,
    };

    /// Is any primitive still open?
    pub(super) const fn any(self) -> bool {
        self.plane || self.cylinder || self.cone || self.torus || self.sphere
    }
}

/// Screen a face set: which primitives its running sums still leave open.
pub(super) fn screen(s: &Stats, o: FitOpts) -> Allow {
    // No analytic surface has an edge on it: a set holding a crease sharper
    // than one facet step fits nothing, whatever its residuals.
    if s.crease > o.max_facet_step {
        return Allow::NONE;
    }
    if !(s.w > 0.0 && s.area > 0.0) {
        // Nothing measurable; let the fit have its own say.
        return Allow::ALL;
    }

    let plane = s.samples >= 3
        && s.plane().is_some_and(|(n, rms)| {
            rms <= o.tol * SLACK && s.plane_dev_floor(n) <= o.max_normal_dev * SLACK
        });
    // Below here only curved primitives are left, and none of them is even
    // tried unless the normals turn far enough.
    if s.spread_ceiling() <= o.min_spread {
        return Allow {
            plane,
            ..Allow::NONE
        };
    }
    // A cylinder's normals are perpendicular to its axis, so the smallest
    // eigenvalue of their second moment is a floor under the deviation any
    // cylinder through this set has to pay.
    let cylinder = s.faces >= 2
        && s.samples >= 4
        && s.cylinder_axis()
            .is_some_and(|(_, lo)| s.axial_dev_floor(lo) <= o.max_normal_dev * SLACK);
    // The cone and the torus share an axis and differ only in how many samples
    // they need.
    let conic = s.faces >= 3 && s.conic_axis().is_some();
    Allow {
        plane,
        cylinder,
        cone: conic && s.samples >= 4,
        torus: conic && s.samples >= 6,
        sphere: s.samples >= 5 && s.sphere_possible(o),
    }
}
