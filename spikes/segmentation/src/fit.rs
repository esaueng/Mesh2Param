//! Primitive fitting: plane, cylinder, sphere, with the acceptance guards that
//! stop a flat patch from being reported as a huge-radius cylinder.

use std::f64::consts::{PI, TAU};

use crate::linalg::{V3, angle_between, jacobi3, perp, solve_small};

#[derive(Clone, Copy, Debug)]
pub enum Prim {
    Plane { n: V3, d: f64 },
    Cylinder { p: V3, dir: V3, r: f64, sweep_deg: f64 },
    Sphere { c: V3, r: f64 },
    Unknown,
}

impl Prim {
    pub const fn name(self) -> &'static str {
        match self {
            Self::Plane { .. } => "plane",
            Self::Cylinder { .. } => "cylinder",
            Self::Sphere { .. } => "sphere",
            Self::Unknown => "unknown",
        }
    }

    /// Unsigned distance from `q` to the primitive's surface.
    pub fn residual(self, q: V3) -> f64 {
        match self {
            Self::Plane { n, d } => (n.dot(q) - d).abs(),
            Self::Cylinder { p, dir, r, .. } => {
                let rel = q.sub(p);
                let radial = rel.sub(dir.mul(rel.dot(dir)));
                (radial.norm() - r).abs()
            }
            Self::Sphere { c, r } => (q.sub(c).norm() - r).abs(),
            Self::Unknown => f64::INFINITY,
        }
    }

    /// Outward surface normal of the primitive at (the projection of) `q`.
    pub fn normal_at(self, q: V3) -> Option<V3> {
        match self {
            Self::Plane { n, .. } => Some(n),
            Self::Cylinder { p, dir, .. } => {
                let rel = q.sub(p);
                rel.sub(dir.mul(rel.dot(dir))).unit()
            }
            Self::Sphere { c, .. } => q.sub(c).unit(),
            Self::Unknown => None,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Fit {
    pub prim: Prim,
    /// Weighted RMS residual of the best candidate, even when it was rejected.
    pub rms: f64,
    pub max_res: f64,
}

impl Fit {
    pub const UNKNOWN: Self = Self {
        prim: Prim::Unknown,
        rms: f64::INFINITY,
        max_res: f64::INFINITY,
    };
}

#[derive(Clone, Copy)]
pub struct FitOpts {
    /// Absolute residual budget (`tol_frac * bbox_diag`).
    pub tol: f64,
    /// Minimum angular spread of face normals for a curved primitive (radians).
    pub min_spread: f64,
    /// Largest tolerated per-facet angular step around a cylinder axis (radians).
    pub max_facet_step: f64,
    /// Largest tolerated RMS angle between a face normal and the fitted
    /// primitive's normal (radians). This is what keeps a cone or a torus band
    /// out of the sphere bucket: both can sit inside the distance tolerance,
    /// only their normals give them away.
    pub max_normal_dev: f64,
    /// Residual budget relative to a fitted radius.
    pub radius_tol_frac: f64,
    pub bbox_diag: f64,
}

pub struct Sample {
    pub p: V3,
    pub w: f64,
}

/// One triangle reduced to what the fits need: normal, centroid, area.
pub struct FaceRef {
    pub n: V3,
    pub c: V3,
    pub a: f64,
}

/// Area-weighted RMS angle between the face normals and the primitive's own
/// normal at each face centroid (radians).
fn normal_dev(prim: Prim, faces: &[FaceRef]) -> f64 {
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

/// Residual budget expressed relative to the primitive's own size.
///
/// `tol_frac * bbox_diag` is generous on a large part with small features: on a
/// 900 mm plate it is nearly 2 mm, enough for two tangent 50 mm bosses to fit
/// one 125 mm cylinder. Requiring the radius to be pinned to `radius_tol_frac`
/// keeps a fitted radius meaningful whatever the part size.
fn relative_budget(prim: Prim, o: FitOpts) -> f64 {
    match prim {
        Prim::Cylinder { r, .. } | Prim::Sphere { r, .. } => o.radius_tol_frac * r,
        _ => f64::INFINITY,
    }
}

/// Weighted plane fit: PCA, normal is the smallest-eigenvalue direction.
fn fit_plane(pts: &[Sample]) -> Option<(Prim, f64, f64)> {
    if pts.len() < 3 {
        return None;
    }
    let wsum: f64 = pts.iter().map(|s| s.w).sum();
    if wsum <= 0.0 {
        return None;
    }
    let mut m = V3::ZERO;
    for s in pts {
        m = m.add(s.p.mul(s.w));
    }
    m = m.mul(1.0 / wsum);
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
    let prim = Prim::Plane { n, d: n.dot(m) };
    let (rms, max_res) = residuals(prim, pts, wsum);
    Some((prim, rms, max_res))
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

/// Cylinder fit: axis from the area-weighted normal covariance, then a
/// weighted Kasa circle fit in the plane perpendicular to the axis.
fn fit_cylinder(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Option<(Prim, f64, f64)> {
    if pts.len() < 4 || faces.len() < 2 {
        return None;
    }
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
    let dir = vecs[0].unit()?;
    let u = perp(dir);
    let v = dir.cross(u).unit()?;

    let wsum: f64 = pts.iter().map(|s| s.w).sum();
    if wsum <= 0.0 {
        return None;
    }
    let xy: Vec<(f64, f64, f64)> = pts.iter().map(|s| (s.p.dot(u), s.p.dot(v), s.w)).collect();
    let mx = xy.iter().map(|(x, _, w)| x * w).sum::<f64>() / wsum;
    let my = xy.iter().map(|(_, y, w)| y * w).sum::<f64>() / wsum;

    let mut mat = [[0.0_f64; 4]; 4];
    let mut rhs = [0.0_f64; 4];
    for (x, y, w) in &xy {
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
    let (cx, cy) = (0.5 * sol[0], 0.5 * sol[1]);
    let rsq = sol[2] + cx.mul_add(cx, cy * cy);
    if !rsq.is_finite() || rsq <= 0.0 {
        return None;
    }
    // The algebraic fit is biased on short arcs (it minimizes the residual of
    // x^2+y^2, not of the distance), which is exactly the partial-cylinder
    // case; a few Gauss-Newton steps on the true geometric distance fix it.
    let (cx, cy, r) = refine_circle(&xy, mx, my, cx, cy, rsq.sqrt());
    if !r.is_finite() || r < 1e-9 || r > 50.0 * o.bbox_diag {
        return None;
    }
    let centre = u.mul(cx + mx).add(v.mul(cy + my));

    // A facet step wider than `max_facet_step` means the patch is a genuine
    // polygonal prism (hex nut), not a coarsely tessellated cylinder: both put
    // their vertices exactly on a circle, only the step size separates them.
    let normal_angles: Vec<f64> = faces
        .iter()
        .filter_map(|f| {
            let n = f.n;
            let radial = n.sub(dir.mul(n.dot(dir)));
            radial.unit().map(|t| t.dot(v).atan2(t.dot(u)) + PI)
        })
        .collect();
    let ngaps = angle_gaps(normal_angles);
    let facet_step = ngaps.get(1).copied().or_else(|| ngaps.first().copied())?;
    if facet_step > o.max_facet_step {
        return None;
    }

    // Sweep from the sample points: the widest gap is the unswept arc, unless
    // every gap is comparable, in which case the patch closes on itself.
    let point_angles: Vec<f64> = pts
        .iter()
        .filter_map(|s| {
            let rel = s.p.sub(centre);
            let radial = rel.sub(dir.mul(rel.dot(dir)));
            radial.unit().map(|t| t.dot(v).atan2(t.dot(u)) + PI)
        })
        .collect();
    let pgaps = angle_gaps(point_angles);
    let biggest = pgaps.first().copied().unwrap_or(TAU);
    let second = pgaps.get(1).copied().unwrap_or(0.0);
    let sweep = if biggest <= 2.0 * second { TAU } else { TAU - biggest };

    let prim = Prim::Cylinder {
        p: centre,
        dir,
        r,
        sweep_deg: sweep.to_degrees(),
    };
    let (rms, max_res) = residuals(prim, pts, wsum);
    Some((prim, rms, max_res))
}

/// Gauss-Newton refinement of a 2-D circle against true point-to-circle distance.
/// Coordinates are relative to `(mx, my)`; returns the same frame.
fn refine_circle(
    xy: &[(f64, f64, f64)],
    mx: f64,
    my: f64,
    mut cx: f64,
    mut cy: f64,
    mut r: f64,
) -> (f64, f64, f64) {
    for _ in 0..24 {
        let mut mat = [[0.0_f64; 4]; 4];
        let mut rhs = [0.0_f64; 4];
        for (x, y, w) in xy {
            let (dx, dy) = (x - mx - cx, y - my - cy);
            let d = dx.hypot(dy);
            if d < 1e-12 {
                continue;
            }
            // d(residual)/d(cx, cy, r)
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
            return (f64::NAN, f64::NAN, f64::NAN);
        }
        if step[0].abs() + step[1].abs() + step[2].abs() < 1e-12 * (1.0 + r.abs()) {
            break;
        }
    }
    (cx, cy, r)
}

/// Sphere fit by algebraic (Kasa) least squares.
fn fit_sphere(pts: &[Sample], o: FitOpts) -> Option<(Prim, f64, f64)> {
    if pts.len() < 5 {
        return None;
    }
    let wsum: f64 = pts.iter().map(|s| s.w).sum();
    if wsum <= 0.0 {
        return None;
    }
    let mut m = V3::ZERO;
    for s in pts {
        m = m.add(s.p.mul(s.w));
    }
    m = m.mul(1.0 / wsum);

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
    if !r.is_finite() || r < 1e-9 || r > 50.0 * o.bbox_diag {
        return None;
    }
    let prim = Prim::Sphere { c: c.add(m), r };
    let (rms, max_res) = residuals(prim, pts, wsum);
    Some((prim, rms, max_res))
}

fn residuals(prim: Prim, pts: &[Sample], wsum: f64) -> (f64, f64) {
    let mut acc = 0.0;
    let mut worst: f64 = 0.0;
    for s in pts {
        let r = prim.residual(s.p);
        acc += s.w * r * r;
        worst = worst.max(r);
    }
    ((acc / wsum).sqrt(), worst)
}

/// Angular spread of the area-weighted face normals, in radians.
pub fn normal_spread(faces: &[FaceRef]) -> f64 {
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

/// Fit all three primitives and take the first that clears the guards.
///
/// The order is deliberate — plane, then cylinder, then sphere. Picking the
/// numerically smallest RMS instead lets a short cylindrical band win as a
/// large sphere (a sphere has one more free parameter, so it never fits worse),
/// so the simplest model that is inside tolerance wins.
pub fn fit_patch(pts: &[Sample], faces: &[FaceRef], o: FitOpts) -> Fit {
    let curved_ok = normal_spread(faces) > o.min_spread;

    let mut fallback: Option<(Prim, f64, f64)> = None;
    let mut note = |c: Option<(Prim, f64, f64)>| -> Option<(Prim, f64, f64)> {
        let c = c.filter(|x| x.1.is_finite())?;
        if fallback.is_none_or(|f| c.1 < f.1) {
            fallback = Some(c);
        }
        (c.1 <= o.tol && c.1 <= relative_budget(c.0, o) && normal_dev(c.0, faces) <= o.max_normal_dev)
            .then_some(c)
    };

    let mut chosen = note(fit_plane(pts));
    if chosen.is_none() && curved_ok {
        chosen = note(fit_cylinder(pts, faces, o));
    }
    if chosen.is_none() && curved_ok {
        chosen = note(fit_sphere(pts, o));
    }

    match (chosen, fallback) {
        (Some((prim, rms, max_res)), _) => Fit { prim, rms, max_res },
        (None, Some((_, rms, max_res))) => Fit {
            prim: Prim::Unknown,
            rms,
            max_res,
        },
        (None, None) => Fit::UNKNOWN,
    }
}
