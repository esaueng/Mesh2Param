//! Edge curves: the real intersection of two fitted surfaces, trimmed to the
//! chain that runs between them, with an honest fallback when there is none.
//!
//! Three routes reach the kernel, because the kernel's `AnalyticSurface` has no plane
//! arm:
//!
//! * plane/plane goes to `plane_plane_intersection` and is always a line;
//! * plane/analytic goes to `exact_plane_analytic_bounded`, which returns an
//!   exact circle or ellipse where one exists and samples otherwise;
//! * analytic/analytic tries the closed-form `exact_*` pair routines first —
//!   they are the only ones that yield an exact circle — and falls back to
//!   `intersect_analytic_analytic_bounded`, whose output is a marched NURBS
//!   and so lands here as a polyline.
//!
//! Tangent pairs never reach any of them. Two surfaces meeting at a shallow
//! angle have an intersection whose *position* is ill-conditioned in the fit
//! error, so the mesh's own samples beat it.

use core::f64::consts::TAU;

use remus_math::analytic_intersection::{
    ExactIntersectionCurve, exact_cone_cone, exact_cone_cylinder, exact_cylinder_cylinder,
    exact_plane_analytic_bounded, exact_sphere_cylinder, exact_torus_cylinder, exact_torus_sphere,
    intersect_analytic_analytic_bounded,
};
use remus_math::curves::Circle3D;
use remus_math::plane::plane_plane_intersection;

use super::surf::{self, Surface};
use super::{Curve, EdgeSource, TopologyOptions};
use crate::segment::Primitive;
use crate::segment::linalg::{V3, angle_undirected, dist_point_line};

/// How many points an exact ellipse is sampled at when it is demoted to a
/// polyline. Nothing downstream consumes an ellipse yet.
const ELLIPSE_SAMPLES: usize = 96;

/// Everything [`build`] needs about one chain.
pub(super) struct Request<'a> {
    /// The chain's mesh vertices, in order.
    pub samples: &'a [V3],
    /// Whether the chain is a ring.
    pub closed: bool,
    /// The refined end vertices, when the chain has any.
    pub ends: Option<(V3, V3)>,
    /// The first patch's fitted primitive.
    pub a: Option<Primitive>,
    /// The second patch's fitted primitive.
    pub b: Option<Primitive>,
    /// The first patch as a kernel surface.
    pub surface_a: Option<&'a Surface>,
    /// The second patch as a kernel surface.
    pub surface_b: Option<&'a Surface>,
    /// Absolute tolerance.
    pub tol: f64,
    /// The run's options.
    pub options: &'a TopologyOptions,
}

/// One recovered curve with the evidence for it.
pub(super) struct Built {
    pub curve: Curve,
    pub tangent: bool,
    pub source: EdgeSource,
    pub rms: f64,
    pub max: f64,
}

/// An intersection branch the kernel offered, before trimming.
enum Cand {
    Line { origin: V3, dir: V3 },
    Circle { center: V3, axis: V3, radius: f64 },
    Points(Vec<V3>),
}

pub(super) fn build(req: Request<'_>) -> Built {
    let tangent = is_tangent(&req);

    if !tangent
        && let (Some(sa), Some(sb)) = (req.surface_a, req.surface_b)
        && let Some(built) = analytic_edge(&req, sa, sb)
    {
        return built;
    }

    let curve = fallback(&req);
    let (rms, max) = deviations(&curve, req.samples);
    Built {
        curve,
        tangent,
        source: if tangent {
            EdgeSource::Tangent
        } else {
            EdgeSource::Fallback
        },
        rms,
        max,
    }
}

/// Mean angle between the two surfaces' normals along the chain.
///
/// Undirected: the two fits have no agreed outward side, and a fillet meeting
/// its wall is tangent whether the normals point the same way or not.
fn is_tangent(req: &Request<'_>) -> bool {
    let (Some(a), Some(b)) = (req.a, req.b) else {
        return false;
    };
    let mut sum = 0.0;
    let mut n = 0_usize;
    for &p in req.samples {
        if let (Some(ga), Some(gb)) = (surf::gradient(a, p), surf::gradient(b, p)) {
            sum += angle_undirected(ga, gb);
            n += 1;
        }
    }
    if n == 0 {
        return false;
    }
    (sum / n as f64).to_degrees() < req.options.tangent_angle_deg
}

/// The intersection route. `None` when nothing the kernel returned fits the
/// chain, which sends the caller to the fallback.
fn analytic_edge(req: &Request<'_>, sa: &Surface, sb: &Surface) -> Option<Built> {
    let cands = candidates(req, sa, sb);
    let budget = req.options.edge_fit_factor * req.tol;

    let mut best: Option<(f64, &Cand)> = None;
    for cand in &cands {
        let mean = mean_distance(cand, req.samples);
        if !mean.is_finite() {
            continue;
        }
        if best.as_ref().is_none_or(|(m, _)| mean < *m) {
            best = Some((mean, cand));
        }
    }
    let (mean, cand) = best?;
    if mean > budget {
        return None;
    }

    let (curve, source) = trim(req, cand)?;
    let (rms, max) = deviations(&curve, req.samples);
    if rms > budget {
        return None;
    }
    Some(Built {
        curve,
        tangent: false,
        source,
        rms,
        max,
    })
}

fn candidates(req: &Request<'_>, sa: &Surface, sb: &Surface) -> Vec<Cand> {
    match (sa, sb) {
        (
            Surface::Plane {
                normal: n1,
                offset: d1,
            },
            Surface::Plane {
                normal: n2,
                offset: d2,
            },
        ) => plane_plane_intersection(surf::vector(*n1), *d1, surf::vector(*n2), *d2, 1e-9)
            .map(|(p, dir)| {
                vec![Cand::Line {
                    origin: surf::from_point(p),
                    dir: V3::new(dir.x(), dir.y(), dir.z()),
                }]
            })
            .unwrap_or_default(),
        (Surface::Plane { normal, offset }, other) => {
            plane_analytic(other, *normal, *offset, req.samples)
        }
        (other, Surface::Plane { normal, offset }) => {
            plane_analytic(other, *normal, *offset, req.samples)
        }
        (a, b) => analytic_analytic(req, a, b),
    }
}

fn plane_analytic(s: &Surface, normal: V3, offset: f64, samples: &[V3]) -> Vec<Cand> {
    let Some(ana) = s.analytic() else {
        return Vec::new();
    };
    // A plane cutting a cone can produce an unbounded parabola or hyperbola;
    // the bound keeps the sampling finite without dropping the span the chain
    // actually covers.
    let cone_v_max = match s {
        Surface::Cone(_) => {
            let mut v: f64 = 0.0;
            for &p in samples {
                if let Some(x) = s.hint_v(p) {
                    v = v.max(x.abs());
                }
            }
            (v > 0.0).then_some(v * 1.5)
        }
        _ => None,
    };
    exact_plane_analytic_bounded(ana, surf::vector(normal), offset, cone_v_max)
        .map(|curves| curves.iter().map(exact_to_cand).collect())
        .unwrap_or_default()
}

fn analytic_analytic(req: &Request<'_>, sa: &Surface, sb: &Surface) -> Vec<Cand> {
    if let Some(exact) = exact_pair(sa, sb)
        && !exact.is_empty()
    {
        return exact.iter().map(exact_to_cand).collect();
    }
    let (Some(a), Some(b)) = (sa.analytic(), sb.analytic()) else {
        return Vec::new();
    };
    let hint_a = v_hint(sa, req.samples);
    let hint_b = v_hint(sb, req.samples);
    intersect_analytic_analytic_bounded(a, b, req.options.grid_res, hint_a, hint_b)
        .map(|curves| {
            curves
                .into_iter()
                .map(|c| Cand::Points(c.points.iter().map(|p| surf::from_point(p.point)).collect()))
                .filter(|c| match c {
                    Cand::Points(p) => p.len() >= 2,
                    _ => true,
                })
                .collect()
        })
        .unwrap_or_default()
}

/// The closed-form routines for the pairs the kernel has one for. These are
/// the only analytic/analytic route that can produce an exact circle; the
/// marcher only ever produces a fitted NURBS.
fn exact_pair(sa: &Surface, sb: &Surface) -> Option<Vec<ExactIntersectionCurve>> {
    let out =
        match (sa, sb) {
            (Surface::Cylinder(a), Surface::Cylinder(b)) => exact_cylinder_cylinder(a, b),
            (Surface::Cone(c), Surface::Cylinder(y)) | (Surface::Cylinder(y), Surface::Cone(c)) => {
                exact_cone_cylinder(c, y)
            }
            (Surface::Sphere(s), Surface::Cylinder(y))
            | (Surface::Cylinder(y), Surface::Sphere(s)) => exact_sphere_cylinder(s, y),
            (Surface::Torus(t), Surface::Cylinder(y))
            | (Surface::Cylinder(y), Surface::Torus(t)) => exact_torus_cylinder(t, y),
            (Surface::Torus(t), Surface::Sphere(s)) | (Surface::Sphere(s), Surface::Torus(t)) => {
                exact_torus_sphere(t, s)
            }
            (Surface::Cone(a), Surface::Cone(b)) => exact_cone_cone(a, b),
            _ => return None,
        };
    out.ok().flatten()
}

fn exact_to_cand(curve: &ExactIntersectionCurve) -> Cand {
    match curve {
        ExactIntersectionCurve::Circle(c) => Cand::Circle {
            center: surf::from_point(c.center()),
            axis: V3::new(c.normal().x(), c.normal().y(), c.normal().z()),
            radius: c.radius(),
        },
        ExactIntersectionCurve::Ellipse(e) => Cand::Points(
            (0..=ELLIPSE_SAMPLES)
                .map(|i| surf::from_point(e.evaluate(TAU * i as f64 / ELLIPSE_SAMPLES as f64)))
                .collect(),
        ),
        ExactIntersectionCurve::Points(pts) => {
            Cand::Points(pts.iter().map(|p| surf::from_point(*p)).collect())
        }
    }
}

/// The chain's own extent in a surface's `v`, padded, as a marching hint.
fn v_hint(s: &Surface, samples: &[V3]) -> Option<(f64, f64)> {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for &p in samples {
        let v = s.hint_v(p)?;
        lo = lo.min(v);
        hi = hi.max(v);
    }
    if !lo.is_finite() || !hi.is_finite() {
        return None;
    }
    let pad = 0.25f64.mul_add(hi - lo, 0.05 * lo.abs().max(hi.abs())) + 1e-6;
    Some((lo - pad, hi + pad))
}

fn mean_distance(cand: &Cand, samples: &[V3]) -> f64 {
    if samples.is_empty() {
        return f64::INFINITY;
    }
    let mut sum = 0.0;
    for &p in samples {
        let d = match cand {
            Cand::Line { origin, dir } => dist_point_line(p, *origin, *dir),
            Cand::Circle {
                center,
                axis,
                radius,
            } => circle_distance(p, *center, *axis, *radius),
            Cand::Points(pts) => polyline_distance(p, pts),
        };
        if !d.is_finite() {
            return f64::INFINITY;
        }
        sum += d;
    }
    sum / samples.len() as f64
}

fn circle_distance(p: V3, center: V3, axis: V3, radius: f64) -> f64 {
    let rel = p.sub(center);
    let t = rel.dot(axis);
    let rho = rel.reject(axis).norm();
    (rho - radius).hypot(t)
}

fn polyline_distance(p: V3, pts: &[V3]) -> f64 {
    if pts.is_empty() {
        return f64::INFINITY;
    }
    if pts.len() == 1 {
        return p.sub(pts[0]).norm();
    }
    let mut best = f64::INFINITY;
    for w in pts.windows(2) {
        best = best.min(segment_distance(p, w[0], w[1]));
    }
    best
}

fn segment_distance(p: V3, a: V3, b: V3) -> f64 {
    let ab = b.sub(a);
    let len2 = ab.dot(ab);
    if len2 <= 0.0 {
        return p.sub(a).norm();
    }
    let t = (p.sub(a).dot(ab) / len2).clamp(0.0, 1.0);
    p.sub(a.add(ab.mul(t))).norm()
}

/// Cut the chosen branch down to the span this chain covers.
fn trim(req: &Request<'_>, cand: &Cand) -> Option<(Curve, EdgeSource)> {
    let (start, end) = span(req)?;
    match cand {
        Cand::Line { origin, dir } => {
            let on = |q: V3| origin.add(dir.mul(q.sub(*origin).dot(*dir)));
            Some((
                Curve::Line {
                    start: on(start).arr(),
                    end: on(end).arr(),
                },
                EdgeSource::Analytic,
            ))
        }
        Cand::Circle {
            center,
            axis,
            radius,
        } => trim_circle(req, *center, *axis, *radius, start, end),
        Cand::Points(pts) => {
            let cut = trim_points(pts, start, end, req.closed);
            (cut.len() >= 2).then(|| (Curve::Polyline { points: arr(&cut) }, EdgeSource::Marching))
        }
    }
}

/// The two points the edge runs between: its refined vertices when it has
/// them, otherwise the chain's own ends.
fn span(req: &Request<'_>) -> Option<(V3, V3)> {
    if let Some(ends) = req.ends {
        return Some(ends);
    }
    let first = req.samples.first().copied()?;
    let last = req.samples.last().copied()?;
    Some((first, last))
}

fn trim_circle(
    req: &Request<'_>,
    center: V3,
    axis: V3,
    radius: f64,
    start: V3,
    end: V3,
) -> Option<(Curve, EdgeSource)> {
    // Rebuilt from centre/axis/radius alone so the emitted angles are in the
    // frame a consumer gets back from the same three numbers.
    let circle = Circle3D::new(surf::point(center), surf::vector(axis), radius).ok()?;
    let normal = circle.normal();
    let axis_out = V3::new(normal.x(), normal.y(), normal.z());

    let (start_angle, end_angle) = if req.closed {
        (0.0, TAU)
    } else {
        let a0 = circle.project(surf::point(start));
        let a1 = circle.project(surf::point(end));
        let sweep = (a1 - a0).rem_euclid(TAU);
        if sweep < 1e-12 {
            (a0, a0 + TAU)
        } else {
            // Two arcs join the same pair of angles; the chain's own midpoint
            // says which of them this edge is.
            let mid = req.samples.get(req.samples.len() / 2).copied();
            let inside =
                mid.is_none_or(|m| (circle.project(surf::point(m)) - a0).rem_euclid(TAU) <= sweep);
            if inside {
                (a0, a0 + sweep)
            } else {
                (a1, a1 + (TAU - sweep))
            }
        }
    };

    Some((
        Curve::Circle {
            center: surf::from_point(circle.center()).arr(),
            axis: axis_out.arr(),
            radius,
            start_angle,
            end_angle,
        },
        EdgeSource::Analytic,
    ))
}

/// Slice a marched chain down to the run between the two end points.
fn trim_points(pts: &[V3], start: V3, end: V3, closed: bool) -> Vec<V3> {
    if closed || pts.len() < 2 {
        return pts.to_vec();
    }
    let nearest = |q: V3| -> usize {
        let mut best = 0;
        let mut bd = f64::INFINITY;
        for (i, &p) in pts.iter().enumerate() {
            let d = p.sub(q).norm();
            if d < bd {
                bd = d;
                best = i;
            }
        }
        best
    };
    let i0 = nearest(start);
    let i1 = nearest(end);
    if i0 == i1 {
        return pts.to_vec();
    }
    let mut cut: Vec<V3> = if i0 < i1 {
        pts[i0..=i1].to_vec()
    } else {
        let mut v = pts[i1..=i0].to_vec();
        v.reverse();
        v
    };
    // The trimmed run has to actually reach the vertices, not the sample
    // nearest them.
    if let Some(f) = cut.first_mut() {
        *f = start;
    }
    if let Some(l) = cut.last_mut() {
        *l = end;
    }
    cut
}

/// The mesh's own samples, projected onto whichever side is analytic and fits
/// them better.
fn fallback(req: &Request<'_>) -> Curve {
    let pick = [req.a, req.b]
        .into_iter()
        .flatten()
        .filter(|p| !matches!(p, Primitive::Unknown))
        .map(|p| (mean_abs_distance(p, req.samples), p))
        .filter(|(d, _)| d.is_finite())
        .min_by(|x, y| x.0.total_cmp(&y.0))
        .map(|(_, p)| p);

    let mut points: Vec<V3> = match pick {
        Some(prim) => req
            .samples
            .iter()
            .map(|&p| surf::project(prim, p))
            .collect(),
        None => req.samples.to_vec(),
    };
    // The refined vertices are the shared truth between adjacent edges; a
    // fallback that stopped at its own projected samples would leave a gap.
    if !req.closed {
        if let Some((s, e)) = req.ends {
            if let Some(f) = points.first_mut() {
                *f = s;
            }
            if let Some(l) = points.last_mut() {
                *l = e;
            }
        }
    } else if let Some(&first) = points.first() {
        points.push(first);
    }
    Curve::Polyline {
        points: arr(&points),
    }
}

fn mean_abs_distance(prim: Primitive, samples: &[V3]) -> f64 {
    if samples.is_empty() {
        return f64::INFINITY;
    }
    let mut sum = 0.0;
    for &p in samples {
        match surf::signed_distance(prim, p) {
            Some(d) if d.is_finite() => sum += d.abs(),
            _ => return f64::INFINITY,
        }
    }
    sum / samples.len() as f64
}

fn arr(points: &[V3]) -> Vec<[f64; 3]> {
    points.iter().map(|p| p.arr()).collect()
}

/// How far the chain's mesh samples sit off the curve that was emitted.
pub(super) fn deviations(curve: &Curve, samples: &[V3]) -> (f64, f64) {
    if samples.is_empty() {
        return (0.0, 0.0);
    }
    let mut sum2 = 0.0;
    let mut max = 0.0_f64;
    for &p in samples {
        let d = match curve {
            Curve::Line { start, end } => {
                segment_distance(p, V3::from_arr(*start), V3::from_arr(*end))
            }
            Curve::Circle {
                center,
                axis,
                radius,
                ..
            } => circle_distance(p, V3::from_arr(*center), V3::from_arr(*axis), *radius),
            Curve::Polyline { points } => {
                let pts: Vec<V3> = points.iter().map(|q| V3::from_arr(*q)).collect();
                polyline_distance(p, &pts)
            }
        };
        if !d.is_finite() {
            return (f64::INFINITY, f64::INFINITY);
        }
        sum2 += d * d;
        max = max.max(d);
    }
    ((sum2 / samples.len() as f64).sqrt(), max)
}
