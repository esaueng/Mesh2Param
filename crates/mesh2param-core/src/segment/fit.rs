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
use super::linalg::{V3, angle_between, fit_line, jacobi3, perp, solve_small};

/// A cone flatter than this is a cylinder, and one steeper than its complement
/// is a plane; both have already had their turn by the time the cone is tried.
const MIN_CONE_HALF_ANGLE_DEG: f64 = 2.0;

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

/// Area-weighted second moment of the face normals about the origin.
///
/// A cylinder's normals are all perpendicular to its axis, so the axis is the
/// direction of zero second moment. Raw rather than centred on purpose: it
/// still resolves an axis from as few as two facets, which is what lets a
/// coarse cylinder be rebuilt one strip at a time.
fn axis_from_normals_raw(faces: &[FaceRef]) -> Option<V3> {
    let mut c = [[0.0_f64; 3]; 3];
    for f in faces {
        let v = f.n.arr();
        for i in 0..3 {
            for j in 0..3 {
                c[i][j] += f.a * v[i] * v[j];
            }
        }
    }
    let (_, vecs) = jacobi3(c);
    vecs[0].unit()
}

/// Area-weighted covariance of the face normals *about their mean*.
///
/// `n . axis` is exactly constant on a cone (`-sin(half angle)`) and nearly so
/// on a fillet-like torus band, so the axis is the zero-variance direction of
/// the centred covariance whatever the cone's angle. The raw second moment
/// picks the wrong direction for a cone steeper than 35 degrees. Needs three
/// independent normals, which is why the cylinder keeps the raw form.
///
/// A torus swept more than about 140 degrees around its tube defeats this too:
/// the variance along the axis then exceeds the variance across it. Fillets and
/// rounds, which is what tori are in practice, stay well inside that.
fn axis_from_normals_centred(faces: &[FaceRef]) -> Option<V3> {
    let asum: f64 = faces.iter().map(|f| f.a).sum();
    if asum <= 0.0 {
        return None;
    }
    let mut mean = V3::ZERO;
    for f in faces {
        mean = mean.add(f.n.mul(f.a));
    }
    mean = mean.mul(1.0 / asum);
    let mut c = [[0.0_f64; 3]; 3];
    for f in faces {
        let d = f.n.sub(mean).arr();
        for i in 0..3 {
            for j in 0..3 {
                c[i][j] += f.a * d[i] * d[j];
            }
        }
    }
    let (_, vecs) = jacobi3(c);
    vecs[0].unit()
}

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

fn radius_sane(r: f64, o: FitOpts) -> bool {
    r.is_finite() && r >= 1e-9 && r <= 50.0 * o.bbox_diag
}

/// Weighted plane fit: PCA, normal is the smallest-eigenvalue direction.
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
fn fit_cylinder(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Option<Cand> {
    if pts.len() < 4 || faces.len() < 2 {
        return None;
    }
    let dir = axis_from_normals_raw(faces)?;
    let u = perp(dir);
    let v = dir.cross(u).unit()?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }

    let xy: Vec<(f64, f64, f64)> = pts.iter().map(|s| (s.p.dot(u), s.p.dot(v), s.w)).collect();
    let (cx, cy, r) = fit_circle(&xy)?;
    if !radius_sane(r, o) {
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
fn fit_cone(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Option<Cand> {
    if pts.len() < 4 || faces.len() < 3 {
        return None;
    }
    let mut dir = axis_from_normals_centred(faces)?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let m = weighted_centroid(pts, wsum);

    let tr: Vec<(f64, f64, f64)> = pts
        .iter()
        .map(|s| {
            let rel = s.p.sub(m);
            (rel.dot(dir), rel.reject(dir).norm(), s.w)
        })
        .collect();
    let (mut slope, intercept) = fit_line(&tr)?;
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

    let u = perp(dir);
    let v = dir.cross(u).unit()?;
    if !facet_step_ok(faces, dir, u, v, o) {
        return None;
    }

    // A cone has no single radius: its local radius runs from zero at the apex.
    // The mean distance to the axis over the patch is the scale that matters,
    // and holding the fit to a fraction of it stops the cone — the most
    // accommodating of the developable surfaces — from swallowing everything
    // the absolute tolerance would let it.
    let mean_rho = tr.iter().map(|&(_, rho, w)| rho * w).sum::<f64>() / wsum;
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
    if !radius_sane(r, o) {
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
fn fit_torus(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Option<Cand> {
    if pts.len() < 6 || faces.len() < 3 {
        return None;
    }
    let dir = axis_from_normals_centred(faces)?;
    let wsum = weight_sum(pts);
    if wsum <= 0.0 {
        return None;
    }
    let m = weighted_centroid(pts, wsum);

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
/// The order — plane, cylinder, cone, sphere, torus — is deliberate. Picking
/// the numerically smallest RMS instead lets a short cylindrical band win as a
/// large sphere, because a sphere has one more free parameter and so never fits
/// worse; a fillet band likewise wins as a torus, which has two more. The
/// simplest model that is inside tolerance is the right answer, so the order is
/// by how much freedom each surface has to flatter itself.
pub(super) fn fit_patch(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Fit {
    let curved_ok = normal_spread(faces) > o.min_spread;

    let mut fallback: Option<Cand> = None;
    let mut note = |c: Option<Cand>| -> Option<Cand> {
        let c = c.filter(|x| x.rms.is_finite())?;
        if fallback.is_none_or(|f: Cand| c.rms < f.rms) {
            fallback = Some(c);
        }
        (c.rms <= o.tol && c.rms <= c.budget && normal_dev(c.prim, faces) <= o.max_normal_dev)
            .then_some(c)
    };

    let mut chosen = note(fit_plane(pts));
    if chosen.is_none() && curved_ok {
        chosen = note(fit_cylinder(pts, faces, o));
    }
    if chosen.is_none() && curved_ok {
        chosen = note(fit_cone(pts, faces, o));
    }
    if chosen.is_none() && curved_ok {
        chosen = note(fit_sphere(pts, o));
    }
    if chosen.is_none() && curved_ok {
        chosen = note(fit_torus(pts, faces, o));
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
