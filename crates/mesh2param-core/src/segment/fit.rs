//! Primitive fitting: plane, cylinder, cone, sphere, torus, each with the
//! acceptance guards that stop a patch from being reported as the wrong thing.
//!
//! Every fit runs on the patch's **vertices**, weighted by incident area, not
//! on its face centroids. A tessellation samples the analytic surface at its
//! vertices, so a coarse cylinder's radius is only recoverable there: a
//! centroid fit under-reports the radius by `cos(facet / 2)`, which is 3.4% on
//! a 12-facet cylinder and instantly fails a 2% radius comparison.

use core::f64::consts::{FRAC_PI_2, PI, TAU};

use super::Primitive;
use super::linalg::{V3, angle_between, jacobi3, perp, solve_small};
use super::stats::{Allow, Stats};

/// A cone flatter than this is a cylinder, and one steeper than its complement
/// is a plane; both have already had their turn by the time the cone is tried.
const MIN_CONE_HALF_ANGLE_DEG: f64 = 2.0;

/// How far apart the two smallest eigenvalues of the face normals' moment
/// matrix have to be before the axis the smaller one names is a direction and
/// not a coin flip.
///
/// The cylinder, the cone and the torus all take their axis from the
/// smallest-eigenvalue eigenvector of a 3x3 moment matrix of the patch's face
/// normals, and first-order perturbation theory puts that eigenvector's
/// sensitivity at `1 / (lambda1 - lambda0)`: a difference of `eps` anywhere in
/// the accumulated sums rotates the axis by about `eps / (lambda1 - lambda0)`.
/// A tessellated cylinder's face normals are *exactly* perpendicular to its
/// axis, so `lambda0` sits at the rounding floor and the ratio is a few times
/// `1e-15`; a cone's `n . axis` is exactly constant, so the same holds of its
/// centred matrix. A patch whose normals wander off one plane — a coarse loft,
/// a thread band, a flat that leaked a chamfer — has no such separation, and
/// then the axis, the circle fitted about it and the face built on it are all
/// decided by the last bits of a sum. That is what made
/// `lofted-pull-handle/mesh-coarse` and `threaded-pipe-cap/mesh-coarse` reach
/// different tiers on macOS and on the Linux runner, the thread band's face
/// landing 660 mm off the mesh there.
///
/// The threshold is what a real quadric band leaves room for, measured rather
/// than chosen. The demanding case is the torus, whose `n . axis` is only
/// *nearly* constant: swept over its tube from
/// 30 to 180 degrees a fillet band's ratio runs 0.05, 0.19, 0.38, 0.45, 0.39 —
/// it peaks at 0.45 around 115 degrees and never goes past it. Seven tenths
/// therefore costs no surface the estimator handles and sits well below the 1
/// at which the smallest and next-smallest directions become interchangeable.
/// The margin above 0.45 is measured too: 0.5 costs `laser-rail/mesh-export`
/// its tier and 0.6 costs `spanner-18mm/mesh-coarse` and
/// `oring-gland-ring/mesh-coarse` recognised surfaces, while 0.8 stops catching
/// the patches on `nist-ftc-10/mesh-coarse` whose refusal doubles its analytic
/// face count. The criterion is not "is the axis accurate" but "is the axis
/// *determined*".
pub(super) const MAX_AXIS_EIGEN_RATIO: f64 = 0.7;

/// The largest radius a curved fit may claim, as a multiple of the patch's own
/// extent across the surface's axis.
///
/// The circle fit behind the cylinder, the cone and the torus solves for
/// `(centre, radius)` from rows `[-cos phi, -sin phi, -1]`, and over a short arc
/// the first and third rows become collinear — the centre slides along one
/// direction and the radius follows it with no residual to pay. The system's
/// condition number goes as `1 / phi^4`, so a radius fitted to a short arc is
/// not in the data at all. `radius_sane` allows 50 bounding-box diagonals, which
/// is not a bound on anything: `laser-rail/mesh-export` fits a 254 mm cylinder
/// and a 322 mm sphere to 6 mm-square patches of a 57 mm part.
///
/// The extent is measured from the samples' own centroid, transverse to the
/// fitted axis, which is how `crate::build::periodic::ring_as_circle` bounds a
/// rim it reads back out of marched samples.
///
/// The scale comes from [`FitOpts::min_spread`]: a band of sweep `phi` has an
/// extent of `r sin(phi / 2)`, so the 8 degrees that guard already demands put
/// the ratio at `1 / sin(4 deg) = 14.3` for a *uniformly sampled* arc. Measured
/// about an area-weighted centroid a real arc's extent comes out shorter than
/// that, so the bound is set at 20 rather than at 14.3: 15 refuses fits the
/// cylinder's own swept-angle gate is happy with and costs
/// `laser-rail/mesh-export` 19 of its 26 analytic faces, and from 20 upwards the
/// corpus does not move again. The sphere, which has neither an axis nor a swept
/// angle of its own, has only this guard.
pub(super) const MAX_RADIUS_EXTENT_FACTOR: f64 = 20.0;

impl Primitive {
    /// Unsigned distance from `q` to the primitive's surface.
    pub(super) fn residual(self, q: V3) -> f64 {
        match self {
            Self::Plane { normal, offset } => (V3::from_arr(normal).dot(q) - offset).abs(),
            Self::Cylinder {
                axis_point,
                axis_dir,
                radius,
                ..
            } => {
                let rel = q.sub(V3::from_arr(axis_point));
                (rel.reject(V3::from_arr(axis_dir)).norm() - radius).abs()
            }
            Self::Cone {
                apex,
                axis_dir,
                half_angle_deg,
            } => {
                // Distance to the generating line in the axial half-plane. The
                // double nappe is measured, so a point behind the apex is
                // scored against the mirrored cone rather than against the
                // apex itself; patches never straddle an apex in practice.
                let dir = V3::from_arr(axis_dir);
                let rel = q.sub(V3::from_arr(apex));
                let t = rel.dot(dir);
                let rho = rel.reject(dir).norm();
                let (s, c) = half_angle_deg.to_radians().sin_cos();
                rho.mul_add(c, -(t * s)).abs()
            }
            Self::Torus {
                center,
                axis_dir,
                major_radius,
                minor_radius,
            } => {
                let dir = V3::from_arr(axis_dir);
                let rel = q.sub(V3::from_arr(center));
                let t = rel.dot(dir);
                let rho = rel.reject(dir).norm();
                ((rho - major_radius).hypot(t) - minor_radius).abs()
            }
            Self::Sphere { center, radius } => (q.sub(V3::from_arr(center)).norm() - radius).abs(),
            Self::Unknown => f64::INFINITY,
        }
    }

    /// Outward surface normal of the primitive at (the projection of) `q`.
    pub(super) fn normal_at(self, q: V3) -> Option<V3> {
        match self {
            Self::Plane { normal, .. } => Some(V3::from_arr(normal)),
            Self::Cylinder {
                axis_point,
                axis_dir,
                ..
            } => q
                .sub(V3::from_arr(axis_point))
                .reject(V3::from_arr(axis_dir))
                .unit(),
            Self::Cone {
                apex,
                axis_dir,
                half_angle_deg,
            } => {
                let dir = V3::from_arr(axis_dir);
                let e = q.sub(V3::from_arr(apex)).reject(dir).unit()?;
                let (s, c) = half_angle_deg.to_radians().sin_cos();
                e.mul(c).sub(dir.mul(s)).unit()
            }
            Self::Torus {
                center,
                axis_dir,
                major_radius,
                ..
            } => {
                let dir = V3::from_arr(axis_dir);
                let c = V3::from_arr(center);
                let e = q.sub(c).reject(dir).unit()?;
                q.sub(c.add(e.mul(major_radius))).unit()
            }
            Self::Sphere { center, .. } => q.sub(V3::from_arr(center)).unit(),
            Self::Unknown => None,
        }
    }
}

/// The best primitive found for a set of samples, with its residuals.
#[derive(Clone, Copy, Debug)]
pub(super) struct Fit {
    /// The accepted primitive, or [`Primitive::Unknown`].
    pub prim: Primitive,
    /// Area-weighted RMS residual of the best candidate, even when it was
    /// rejected: for an unknown patch this says how far off the nearest
    /// primitive was.
    pub rms: f64,
    /// Largest single-sample residual of the same candidate.
    pub max_res: f64,
    /// The absolute tolerance this fit was judged against, which is derived
    /// from the fitted patch's *own* edge lengths. Carried on the fit because
    /// every later decision about the patch — merging it, moving a face into
    /// it, promoting it — has to use the same budget the fit was accepted on.
    pub tol: f64,
}

impl Fit {
    pub(super) const UNKNOWN: Self = Self {
        prim: Primitive::Unknown,
        rms: f64::INFINITY,
        max_res: f64::INFINITY,
        tol: 0.0,
    };
}

/// Resolved (absolute, radian) tolerances for one mesh.
#[derive(Clone, Copy, Debug)]
pub(super) struct FitOpts {
    /// Absolute residual budget, derived from the mesh's own edge lengths.
    pub tol: f64,
    /// Minimum angular spread of face normals before a curved primitive may be
    /// considered at all (radians).
    pub min_spread: f64,
    /// Largest tolerated per-facet angular step around an axis (radians).
    pub max_facet_step: f64,
    /// The sharpest crease *inside* the patch being fitted: the largest angle
    /// between the normals of two triangles that share an edge (radians).
    ///
    /// Filled in per patch by the caller, which is the only place mesh
    /// adjacency is known. Zero means "no adjacency information", which is
    /// never a reason to reject.
    pub max_crease: f64,
    /// Largest tolerated RMS angle between a face normal and the fitted
    /// primitive's own normal (radians). This is what keeps a cone or torus
    /// band out of the sphere bucket: both sit inside the distance tolerance,
    /// only their normals give them away.
    pub max_normal_dev: f64,
    /// Residual budget relative to a fitted radius.
    pub radius_tol_frac: f64,
    /// Minimum swept angle around the tube circle before a torus is accepted
    /// (radians).
    pub min_minor_sweep: f64,
    /// The mesh's bounding-box diagonal, as a sanity bound on fitted radii.
    pub bbox_diag: f64,
}

/// One weighted sample point.
pub(super) struct Sample {
    /// Position.
    pub p: V3,
    /// Weight: the share of patch area incident on this vertex.
    pub w: f64,
}

/// One triangle reduced to what the fits need.
#[derive(Clone, Copy)]
pub(super) struct FaceRef {
    /// Unit normal.
    pub n: V3,
    /// Centroid.
    pub c: V3,
    /// Area.
    pub a: f64,
}

/// Area-weighted RMS angle between the face normals and the primitive's own
/// normal at each face centroid (radians).
fn normal_dev(prim: Primitive, faces: &[FaceRef]) -> f64 {
    let mut acc = 0.0;
    let mut wsum = 0.0;
    for f in faces {
        let Some(n) = prim.normal_at(f.c) else {
            return PI;
        };
        let a = angle_between(f.n, n);
        let a = a.min(PI - a);
        acc += f.a * a * a;
        wsum += f.a;
    }
    if wsum <= 0.0 { PI } else { (acc / wsum).sqrt() }
}

/// One fitted candidate: the surface, how well it fits, and the budget it has
/// to fit within.
///
/// The budget travels with the candidate because it is relative to the
/// primitive's own size, and only the fit knows that size. The absolute
/// tolerance is generous on a large part with small features, so a curved fit
/// must additionally pin its radius: without that, two tangent 50 mm bosses on
/// a 900 mm plate fit one 125 mm cylinder inside the absolute budget. A plane
/// has no size of its own and is held to the absolute budget alone.
#[derive(Clone, Copy)]
struct Cand {
    prim: Primitive,
    rms: f64,
    max_res: f64,
    budget: f64,
}

impl Cand {
    fn new(prim: Primitive, pts: &[Sample], wsum: f64, budget: f64) -> Self {
        let (rms, max_res) = residuals(prim, pts, wsum);
        Self {
            prim,
            rms,
            max_res,
            budget,
        }
    }
}

fn weight_sum(pts: &[Sample]) -> f64 {
    pts.iter().map(|s| s.w).sum()
}

fn weighted_centroid(pts: &[Sample], wsum: f64) -> V3 {
    let mut m = V3::ZERO;
    for s in pts {
        m = m.add(s.p.mul(s.w));
    }
    m.mul(1.0 / wsum)
}

fn residuals(prim: Primitive, pts: &[Sample], wsum: f64) -> (f64, f64) {
    let mut acc = 0.0;
    let mut worst: f64 = 0.0;
    for s in pts {
        let r = prim.residual(s.p);
        acc += s.w * r * r;
        worst = worst.max(r);
    }
    ((acc / wsum).sqrt(), worst)
}

/// Cyclic gaps between angles on a circle, sorted descending (radians).
fn angle_gaps(mut angles: Vec<f64>) -> Vec<f64> {
    if angles.len() < 2 {
        return vec![TAU];
    }
    angles.sort_by(f64::total_cmp);
    let mut gaps: Vec<f64> = angles.windows(2).map(|w| w[1] - w[0]).collect();
    if let (Some(&first), Some(&last)) = (angles.first(), angles.last()) {
        gaps.push(TAU - (last - first));
    }
    gaps.sort_by(|a, b| b.total_cmp(a));
    gaps
}

/// Swept angle covered by `angles`: the full turn minus the widest gap, unless
/// every gap is comparable, in which case the samples close on themselves.
fn swept(angles: Vec<f64>) -> f64 {
    let gaps = angle_gaps(angles);
    let biggest = gaps.first().copied().unwrap_or(TAU);
    let second = gaps.get(1).copied().unwrap_or(0.0);
    if biggest <= 2.0 * second {
        TAU
    } else {
        TAU - biggest
    }
}

/// Whether the smallest of three ascending eigenvalues names a direction the
/// data actually distinguishes. See [`MAX_AXIS_EIGEN_RATIO`].
///
/// The moment matrices themselves are on [`Stats`], which is where a trial
/// merge can reach them without a pass over the faces: a cylinder's is the raw
/// area-weighted second moment of the face normals — raw on purpose, so that it
/// still resolves an axis from as few as two facets — and a cone's or a torus's
/// is the same about the mean normal, because `n . axis` is exactly constant on
/// a cone rather than zero, which the raw form gets wrong past 35 degrees.
pub(super) fn axis_determined(vals: [f64; 3]) -> bool {
    let (lo, next) = (vals[0].max(0.0), vals[1].max(0.0));
    next > 0.0 && lo <= MAX_AXIS_EIGEN_RATIO * next
}

/// The patch's own extent about its centroid, transverse to `dir`.
///
/// This is the span the radius of a circle fitted in that plane has to be
/// supported by. See [`MAX_RADIUS_EXTENT_FACTOR`].
fn transverse_extent(pts: &[Sample], wsum: f64, dir: V3) -> f64 {
    let m = weighted_centroid(pts, wsum);
    pts.iter()
        .map(|s| s.p.sub(m).reject(dir).norm())
        .fold(0.0_f64, f64::max)
}

/// Whether a fitted radius is supported by the span the samples cover.
fn radius_supported(radius: f64, extent: f64) -> bool {
    extent > 0.0 && radius <= MAX_RADIUS_EXTENT_FACTOR * extent
}

/// Lower bound on the RMS angle between the face normals and *any* surface of
/// revolution about the line through `m` in direction `dir`.
///
/// A surface of revolution's normal at a point lies in the plane spanned by the
/// axis and the point's own radial direction, so it is perpendicular to the
/// circumferential direction `tau = dir x (c - m)` there — whichever way round
/// it points, which is what [`normal_dev`] measures. The angle from a face
/// normal to that whole plane is therefore a floor under its angle to the
/// surface, and `sin theta <= theta` turns the sines into the same sum
/// [`normal_dev`] takes.
///
/// Both the cone and the torus put their axis through the samples' centroid —
/// the apex at `m + t dir`, the ring centre at `m + axial dir` — so `m` is
/// known before either has fitted anything, and this costs one pass over the
/// *faces* where the fits themselves cost several over the samples. On a
/// freeform region trial-merged with each of its neighbours in turn, that is
/// the difference between refusing it cheaply and refitting it every time.
fn revolution_dev_floor(faces: &[FaceRef], dir: V3, m: V3) -> f64 {
    let mut acc = 0.0;
    let mut wsum = 0.0;
    for f in faces {
        wsum += f.a;
        if let Some(tau) = dir.cross(f.c.sub(m)).unit() {
            let s = f.n.dot(tau);
            acc += f.a * s * s;
        }
    }
    if wsum > 0.0 { (acc / wsum).sqrt() } else { 0.0 }
}

/// How much slack a screening bound allows itself: it is derived exactly, so
/// only the arithmetic can put it on the wrong side of a threshold.
const BOUND_SLACK: f64 = 1.0 + 1e-9;

/// A patch is a genuine polygonal prism or pyramid, not a coarsely tessellated
/// cylinder or cone, when its facets step further than `max_facet_step` around
/// the axis: both put their vertices exactly on a circle, only the step size
/// separates them.
fn facet_step_ok(faces: &[FaceRef], dir: V3, u: V3, v: V3, o: FitOpts) -> bool {
    let angles: Vec<f64> = faces
        .iter()
        .filter_map(|f| {
            f.n.reject(dir)
                .unit()
                .map(|t| t.dot(v).atan2(t.dot(u)) + PI)
        })
        .collect();
    let gaps = angle_gaps(angles);
    // The widest gap is the unswept arc; the next one is the facet step.
    let step = gaps.get(1).copied().or_else(|| gaps.first().copied());
    step.is_some_and(|s| s <= o.max_facet_step)
}

/// Weighted 2-D circle fit: algebraic (Kasa) least squares refined by
/// Gauss-Newton on the true point-to-circle distance.
///
/// The algebraic fit minimises the residual of `x^2 + y^2`, not of the
/// distance, and is biased on short arcs — exactly the partial-cylinder and
/// fillet-band case — so the refinement is not optional.
fn fit_circle(xy: &[(f64, f64, f64)]) -> Option<(f64, f64, f64)> {
    let wsum: f64 = xy.iter().map(|(_, _, w)| *w).sum();
    if wsum <= 0.0 || xy.len() < 3 {
        return None;
    }
    let mx = xy.iter().map(|(x, _, w)| x * w).sum::<f64>() / wsum;
    let my = xy.iter().map(|(_, y, w)| y * w).sum::<f64>() / wsum;

    let mut mat = [[0.0_f64; 4]; 4];
    let mut rhs = [0.0_f64; 4];
    for (x, y, w) in xy {
        let (dx, dy) = (x - mx, y - my);
        let row = [dx, dy, 1.0];
        let z = dx.mul_add(dx, dy * dy);
        for i in 0..3 {
            for j in 0..3 {
                mat[i][j] += w * row[i] * row[j];
            }
            rhs[i] += w * row[i] * z;
        }
    }
    let sol = solve_small(3, &mat, &rhs)?;
    let (mut cx, mut cy) = (0.5 * sol[0], 0.5 * sol[1]);
    let rsq = sol[2] + cx.mul_add(cx, cy * cy);
    if !rsq.is_finite() || rsq <= 0.0 {
        return None;
    }
    let mut r = rsq.sqrt();

    for _ in 0..24 {
        let mut mat = [[0.0_f64; 4]; 4];
        let mut rhs = [0.0_f64; 4];
        for (x, y, w) in xy {
            let (dx, dy) = (x - mx - cx, y - my - cy);
            let d = dx.hypot(dy);
            if d < 1e-12 {
                continue;
            }
            let j = [-dx / d, -dy / d, -1.0];
            let res = d - r;
            for i in 0..3 {
                for k in 0..3 {
                    mat[i][k] += w * j[i] * j[k];
                }
                rhs[i] -= w * j[i] * res;
            }
        }
        let Some(step) = solve_small(3, &mat, &rhs) else {
            break;
        };
        cx += step[0];
        cy += step[1];
        r += step[2];
        if !(cx.is_finite() && cy.is_finite() && r.is_finite()) {
            return None;
        }
        if step[0].abs() + step[1].abs() + step[2].abs() < 1e-12 * (1.0 + r.abs()) {
            break;
        }
    }
    Some((cx + mx, cy + my, r))
}

pub(super) fn radius_sane(r: f64, o: FitOpts) -> bool {
    r.is_finite() && r >= 1e-9 && r <= 50.0 * o.bbox_diag
}

/// Weighted plane fit: PCA, normal is the smallest-eigenvalue direction.
///
/// The screen solves the same eigen-problem on the samples' second moment,
/// which it carries, and gets the same plane to within the two summation
/// orders. It is left to do so rather than handing the answer over: the
/// residual it needs is `sqrt(lambda0 / w)`, which is the eigenvalue itself and
/// so insensitive to an eigenvector the moment barely determines, while the
/// plane a patch is *reported* as should stay the one the samples themselves
/// give, to the last bit.
fn fit_plane(pts: &[Sample]) -> Option<Cand> {
    if pts.len() < 3 {
        return None;
    }
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let m = weighted_centroid(pts, wsum);
    let mut c = [[0.0_f64; 3]; 3];
    for s in pts {
        let d = s.p.sub(m).arr();
        for i in 0..3 {
            for j in 0..3 {
                c[i][j] += s.w * d[i] * d[j];
            }
        }
    }
    for row in &mut c {
        for v in row.iter_mut() {
            *v /= wsum;
        }
    }
    let (_, vecs) = jacobi3(c);
    let n = vecs[0].unit()?;
    let prim = Primitive::Plane {
        normal: n.arr(),
        offset: n.dot(m),
    };
    Some(Cand::new(prim, pts, wsum, f64::INFINITY))
}

/// Cylinder fit: axis from the normal covariance, radius from a circle fit in
/// the plane perpendicular to it.
fn fit_cylinder(pts: &[Sample], faces: &[FaceRef], o: FitOpts, s: &Stats) -> Option<Cand> {
    if pts.len() < 4 || faces.len() < 2 {
        return None;
    }
    let (dir, _) = s.cylinder_axis()?;
    let u = perp(dir);
    let v = dir.cross(u).unit()?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }

    let xy: Vec<(f64, f64, f64)> = pts.iter().map(|s| (s.p.dot(u), s.p.dot(v), s.w)).collect();
    let (cx, cy, r) = fit_circle(&xy)?;
    if !radius_sane(r, o) || !radius_supported(r, transverse_extent(pts, wsum, dir)) {
        return None;
    }
    if !facet_step_ok(faces, dir, u, v, o) {
        return None;
    }
    let centre = u.mul(cx).add(v.mul(cy));

    let sweep = swept(
        pts.iter()
            .filter_map(|s| {
                s.p.sub(centre)
                    .reject(dir)
                    .unit()
                    .map(|t| t.dot(v).atan2(t.dot(u)) + PI)
            })
            .collect(),
    );

    // The positional half of the conditioning, and the one the README recorded
    // as missing: a patch has to wrap `min_spread` around *the axis it was
    // given*, not merely turn its normals that far about their own mean. The
    // motor mount's 23 mm flat leaked a chamfer, its normals turn 12.9 degrees
    // while it wraps 7.3, and the 444 mm cylinder fitted through it puts a face
    // 37 000 mm from the part. The torus is gated the same way by
    // `min_minor_sweep`; the sphere has no axis and is left to the extent bound.
    if sweep < o.min_spread {
        return None;
    }
    let prim = Primitive::Cylinder {
        axis_point: centre.arr(),
        axis_dir: dir.arr(),
        radius: r,
        sweep_deg: sweep.to_degrees(),
    };
    Some(Cand::new(prim, pts, wsum, o.radius_tol_frac * r))
}

/// Cone fit: axis from the normal covariance, then apex and half-angle by
/// least squares on the `(axial position, radial distance)` pairs, which lie on
/// a straight line `rho = tan(half angle) * (t - t_apex)` for a true cone.
///
/// That line, the mean radius and the transverse extent all come out of one
/// streaming pass over the samples. Materialising the pairs first is what a
/// trial merge cannot afford: the union of a freeform region and one of its
/// neighbours has tens of thousands of them and is about to be refused.
fn fit_cone(pts: &[Sample], faces: &[FaceRef], o: FitOpts, s: &Stats) -> Option<Cand> {
    if pts.len() < 4 || faces.len() < 3 {
        return None;
    }
    let mut dir = s.conic_axis()?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let u = perp(dir);
    let v = dir.cross(u).unit()?;
    // Both of these are independent of everything below and counted over faces
    // rather than samples, so they go first: a patch that steps too far per
    // facet is a pyramid, and one whose normals miss every axial plane is not a
    // surface of revolution at all — no pass over its vertices will change
    // either. Both are blind to the axis's sign, which the line fit below may
    // flip.
    if !facet_step_ok(faces, dir, u, v, o) {
        return None;
    }
    let m = weighted_centroid(pts, wsum);
    if revolution_dev_floor(faces, dir, m) > o.max_normal_dev * BOUND_SLACK {
        return None;
    }

    // One streaming pass for all three things the cone needs from its samples:
    // the `(axial, radial)` line fit, the mean radius its budget is relative
    // to, and the transverse extent that radius has to be supported by.
    let (mut sw, mut sx, mut sy, mut sxx, mut sxy) = (0.0, 0.0, 0.0, 0.0, 0.0);
    let mut extent = 0.0_f64;
    for sample in pts {
        let rel = sample.p.sub(m);
        let (t, rho, w) = (rel.dot(dir), rel.reject(dir).norm(), sample.w);
        sw += w;
        sx += w * t;
        sy += w * rho;
        sxx += w * t * t;
        sxy += w * t * rho;
        extent = extent.max(rho);
    }
    let det = sxx.mul_add(sw, -(sx * sx));
    if sw <= 0.0 || det.abs() < 1e-300 {
        return None;
    }
    let mut slope = sxy.mul_add(sw, -(sx * sy)) / det;
    let intercept = sxx.mul_add(sy, -(sx * sxy)) / det;
    // Orient the axis so the cone opens along +dir. Mirroring the axial
    // coordinate negates the slope and leaves the intercept — the radius at the
    // reference point — untouched.
    if slope < 0.0 {
        dir = dir.mul(-1.0);
        slope = -slope;
    }
    let half_angle = slope.atan();
    let lo = MIN_CONE_HALF_ANGLE_DEG.to_radians();
    if !(half_angle > lo && half_angle < FRAC_PI_2 - lo) {
        return None;
    }
    let t_apex = -intercept / slope;
    if !t_apex.is_finite() {
        return None;
    }
    let apex = m.add(dir.mul(t_apex));

    // A cone has no single radius: its local radius runs from zero at the apex.
    // The mean distance to the axis over the patch is the scale that matters,
    // and holding the fit to a fraction of it stops the cone — the most
    // accommodating of the developable surfaces — from swallowing everything
    // the absolute tolerance would let it.
    let mean_rho = sy / wsum;
    // The same radial conditioning the cylinder is held to, on the local
    // radius a cone does have: a band wrapping a few degrees around its axis
    // determines neither the axis it wraps nor the distance to it.
    if !radius_supported(mean_rho, extent) {
        return None;
    }
    let prim = Primitive::Cone {
        apex: apex.arr(),
        axis_dir: dir.arr(),
        half_angle_deg: half_angle.to_degrees(),
    };
    Some(Cand::new(prim, pts, wsum, o.radius_tol_frac * mean_rho))
}

/// Sphere fit by algebraic (Kasa) least squares.
fn fit_sphere(pts: &[Sample], o: FitOpts) -> Option<Cand> {
    if pts.len() < 5 {
        return None;
    }
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let m = weighted_centroid(pts, wsum);

    let mut mat = [[0.0_f64; 4]; 4];
    let mut rhs = [0.0_f64; 4];
    for s in pts {
        let d = s.p.sub(m);
        let row = [d.x, d.y, d.z, 1.0];
        let z = d.dot(d);
        for i in 0..4 {
            for j in 0..4 {
                mat[i][j] += s.w * row[i] * row[j];
            }
            rhs[i] += s.w * row[i] * z;
        }
    }
    let sol = solve_small(4, &mat, &rhs)?;
    let c = V3::new(0.5 * sol[0], 0.5 * sol[1], 0.5 * sol[2]);
    let rsq = sol[3] + c.dot(c);
    if !rsq.is_finite() || rsq <= 0.0 {
        return None;
    }
    let r = rsq.sqrt();
    // A sphere has no axis, so the span that has to support its radius is the
    // patch's whole extent about its own centroid.
    let extent = pts
        .iter()
        .map(|s| s.p.sub(m).norm())
        .fold(0.0_f64, f64::max);
    if !radius_sane(r, o) || !radius_supported(r, extent) {
        return None;
    }
    let prim = Primitive::Sphere {
        center: c.add(m).arr(),
        radius: r,
    };
    Some(Cand::new(prim, pts, wsum, o.radius_tol_frac * r))
}

/// Torus fit: axis from the normal covariance, centre on that axis from the
/// samples' centroid, then the tube circle by the same circle fit the cylinder
/// uses — in the `(radial distance, axial offset)` half-plane, where a torus is
/// a circle of the minor radius centred at the major radius.
fn fit_torus(pts: &[Sample], faces: &[FaceRef], o: FitOpts, s: &Stats) -> Option<Cand> {
    if pts.len() < 6 || faces.len() < 3 {
        return None;
    }
    let dir = s.conic_axis()?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let m = weighted_centroid(pts, wsum);
    // The same floor the cone is refused by, and for the same reason: the ring
    // centre sits on the axis through `m`, so the circumferential direction at
    // every face is known before the tube circle is fitted.
    if revolution_dev_floor(faces, dir, m) > o.max_normal_dev * BOUND_SLACK {
        return None;
    }

    let rt: Vec<(f64, f64, f64)> = pts
        .iter()
        .map(|s| {
            let rel = s.p.sub(m);
            (rel.reject(dir).norm(), rel.dot(dir), s.w)
        })
        .collect();
    let (major, axial, minor) = fit_circle(&rt)?;
    if !radius_sane(minor, o) || !radius_sane(major, o) || minor >= major {
        return None;
    }
    // The **major** radius is what the samples have to span, exactly as a
    // cylinder's radius does; the minor radius is the tube's, and its own
    // conditioning is `min_minor_sweep` below, which says the same thing in
    // the angle rather than in the span.
    if !radius_supported(major, transverse_extent(pts, wsum, dir)) {
        return None;
    }
    // A cylinder's (rho, t) samples form a straight line, which a circle of
    // huge major and minor radius fits perfectly. Only the angle actually swept
    // around the tube circle separates the two, so require a real arc of it.
    let sweep = swept(
        rt.iter()
            .map(|&(rho, t, _)| (t - axial).atan2(rho - major) + PI)
            .collect(),
    );
    if sweep < o.min_minor_sweep {
        return None;
    }

    let prim = Primitive::Torus {
        center: m.add(dir.mul(axial)).arr(),
        axis_dir: dir.arr(),
        major_radius: major,
        minor_radius: minor,
    };
    Some(Cand::new(prim, pts, wsum, o.radius_tol_frac * minor))
}

/// Angular spread of the area-weighted face normals, in radians.
pub(super) fn normal_spread(faces: &[FaceRef]) -> f64 {
    let mut mean = V3::ZERO;
    let mut asum = 0.0;
    for f in faces {
        mean = mean.add(f.n.mul(f.a));
        asum += f.a;
    }
    if asum <= 0.0 {
        return 0.0;
    }
    let Some(m) = mean.mul(1.0 / asum).unit() else {
        return PI;
    };
    let worst = faces
        .iter()
        .map(|f| angle_between(f.n, m))
        .fold(0.0_f64, f64::max);
    (2.0 * worst).min(PI)
}

/// Fit every primitive in turn and take the **first** that clears the guards.
///
/// `allow` is what the screen has already ruled out from the set's running
/// sums: a primitive it has refused cannot be chosen here, so it is not tried.
/// The fallback residual a screened fit reports is therefore the nearest of the
/// candidates that were still open, which is all a trial merge — the only
/// caller that screens — ever looks at, and then only when one is accepted.
///
/// The order — plane, cylinder, cone, sphere, torus — is deliberate. Picking
/// the numerically smallest RMS instead lets a short cylindrical band win as a
/// large sphere, because a sphere has one more free parameter and so never fits
/// worse; a fillet band likewise wins as a torus, which has two more. The
/// simplest model that is inside tolerance is the right answer, so the order is
/// by how much freedom each surface has to flatter itself.
pub(super) fn fit_patch(
    pts: &[Sample],
    faces: &[FaceRef],
    o: FitOpts,
    s: &Stats,
    allow: Allow,
) -> Fit {
    // No analytic surface has an edge on it, so a patch holding a crease
    // sharper than one facet step is two surfaces, whatever the residuals say —
    // and the residuals do say otherwise, in both directions:
    //
    // * A fit is scored at the mesh's vertices, and a polyhedron inscribed in a
    //   curved surface touches it at *every* vertex. The twelve vertices of a
    //   hexagonal chamfer ring lie exactly on a sphere, so the sphere fits them
    //   with zero residual and swallows six real planes.
    // * The RMS is area-weighted, so a narrow strip folded off a large flat
    //   barely registers. A 1.5 mm chamfer on the end of a 33 mm hex flat is
    //   absorbed into that flat as a "plane" at 12% of the tolerance.
    //
    // This is what `max_facet_step` already says about a coarsely tessellated
    // cylinder or cone, measured at the mesh's own edges instead of around a
    // fitted axis — so it also covers the sphere and the torus, which have no
    // axis to project their normals onto, and the plane, which has no facet
    // step at all.
    let creased = o.max_crease > o.max_facet_step;
    let curved_ok = normal_spread(faces) > o.min_spread;

    let mut fallback: Option<Cand> = None;
    let mut note = |c: Option<Cand>| -> Option<Cand> {
        let c = c.filter(|x| x.rms.is_finite())?;
        if fallback.is_none_or(|f: Cand| c.rms < f.rms) {
            fallback = Some(c);
        }
        (!creased
            && c.rms <= o.tol
            && c.rms <= c.budget
            && normal_dev(c.prim, faces) <= o.max_normal_dev)
            .then_some(c)
    };

    let mut chosen = if allow.plane {
        note(fit_plane(pts))
    } else {
        None
    };
    if chosen.is_none() && curved_ok && allow.cylinder {
        chosen = note(fit_cylinder(pts, faces, o, s));
    }
    if chosen.is_none() && curved_ok && allow.cone {
        chosen = note(fit_cone(pts, faces, o, s));
    }
    if chosen.is_none() && curved_ok && allow.sphere {
        chosen = note(fit_sphere(pts, o));
    }
    if chosen.is_none() && curved_ok && allow.torus {
        chosen = note(fit_torus(pts, faces, o, s));
    }

    match (chosen, fallback) {
        (Some(c), _) => Fit {
            prim: c.prim,
            rms: c.rms,
            max_res: c.max_res,
            tol: o.tol,
        },
        (None, Some(c)) => Fit {
            prim: Primitive::Unknown,
            rms: c.rms,
            max_res: c.max_res,
            tol: o.tol,
        },
        (None, None) => Fit {
            tol: o.tol,
            ..Fit::UNKNOWN
        },
    }
}
