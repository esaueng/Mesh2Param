//! Periodic faces: the seam a cylinder, cone, torus or sphere is bounded by.
//!
//! A face on a periodic surface is **not** an outer rim with the other rim as
//! a hole. The kernel's own builders express it as one wire that runs down a
//! doubled seam between the rims, and every structured tessellation path in
//! `remus_operations::tessellate` declines a curved face that has inner wires
//! at all — so built as outer-plus-inner, a capped cylinder validates clean
//! and tessellates to about a third of its volume.
//!
//! Three conventions come from the kernel and are reproduced here:
//!
//! * **A rim stays whole.** `extrude` sweeps a full-circle profile into a side
//!   face whose wire is `[seam, rim, seam⁻¹, rim⁻¹]` with both rims still
//!   single closed edges (`crates/operations/src/extrude.rs:1198-1214`), and
//!   `revolve` builds every analytic wall as `[rim, seam, rim⁻¹, seam⁻¹]` the
//!   same way (`crates/operations/src/revolve.rs:1002-1009`). Halving a rim to
//!   give the seam somewhere to land is not what the tessellator reads: what it
//!   reads is a cycle that winds a full turn, which is either one closed circle
//!   or a chain of arcs summing to one
//!   (`crates/operations/src/tessellate/nonplanar.rs:292-299`).
//! * **The seam is one edge, used twice.** `revolve` seams a wall with the
//!   *original profile edge* — a line on a cylinder or a cone, an arc on a
//!   torus (`crates/operations/src/revolve.rs:894-898`) — but the tessellator
//!   does not require the arc: its two-rim torus band takes "the one OPEN edge
//!   used exactly twice" of any curve type and reads only its ends and its
//!   midpoint (`tessellate/nonplanar.rs:683-702`). A straight seam is used
//!   here throughout, on measurement: see [`Builder::seam_edge`]. A wall
//!   running out to the axis is `[rim, seam, seam⁻¹]`, the seam doubled
//!   between the rim and the apex (`revolve.rs:1013-1027`).
//! * **A surface closed in both directions has no rim at all.** A whole torus
//!   is one face whose wire is the fundamental polygon `a b a⁻¹ b⁻¹` on two
//!   degenerate seam edges at a single vertex (`revolve.rs:1181-1199`).
//!
//! Filed upstream as esaueng/remus#264: `validate_solid` accepts the two-rim
//! form without a word, and only the geometry gives it away.

use crate::segment::Primitive;
use crate::segment::linalg::{V3, dist_point_line, perp, solve_small};

/// A rim's seam meridian, chosen from the axis **line** rather than from the
/// axis direction.
///
/// Both rims of one cylinder have to seam on the same half-plane or the seam
/// between them is a chord across the body instead of a ruling on it. Each rim
/// comes from its own surface-surface intersection and its circle normal may
/// point either way along the shared axis — `Frame3::from_normal` builds `x`
/// as `z × candidate`, which flips with `z` — so the sign is canonicalised
/// here before the perpendicular is taken.
pub(super) fn seam_reference(axis: V3) -> Option<V3> {
    let a = canonical(axis.unit()?);
    let candidate = if a.x.abs() < 0.9 {
        V3::new(1.0, 0.0, 0.0)
    } else {
        V3::new(0.0, 1.0, 0.0)
    };
    a.cross(candidate).unit()
}

/// The axis with a sign that does not depend on which way the fit reported it:
/// the largest component is made positive.
fn canonical(a: V3) -> V3 {
    let c = a.arr();
    let mut at = 0_usize;
    for k in 1..3 {
        if c[k].abs() > c[at].abs() {
            at = k;
        }
    }
    if c[at] < 0.0 { a.mul(-1.0) } else { a }
}

/// The axis line of a periodic primitive, as a point on it and a unit
/// direction. A sphere has none: every great circle is a meridian.
pub(super) fn axis_of(prim: Primitive) -> Option<(V3, V3)> {
    match prim {
        Primitive::Cylinder {
            axis_point,
            axis_dir,
            ..
        } => Some((V3::from_arr(axis_point), V3::from_arr(axis_dir).unit()?)),
        Primitive::Cone { apex, axis_dir, .. } => {
            Some((V3::from_arr(apex), V3::from_arr(axis_dir).unit()?))
        }
        Primitive::Torus {
            center, axis_dir, ..
        } => Some((V3::from_arr(center), V3::from_arr(axis_dir).unit()?)),
        _ => None,
    }
}

/// The axis a loop on this surface has to wind about to be a **rim**.
///
/// A cylinder, a cone and a torus each have one; a sphere has none of its own,
/// so the latitude axis through its centre and the loop's own centroid is
/// used, which is the axis any circle on a sphere is a latitude circle of.
pub(super) fn rim_axis(prim: Primitive, points: &[V3]) -> Option<(V3, V3)> {
    if let Some(axis) = axis_of(prim) {
        return Some(axis);
    }
    let Primitive::Sphere { center, .. } = prim else {
        return None;
    };
    let c = V3::from_arr(center);
    let mut sum = V3::ZERO;
    for p in points {
        sum = sum.add(*p);
    }
    let centroid = sum.mul(1.0 / points.len().max(1) as f64);
    Some((c, centroid.sub(c).unit()?))
}

/// How far a winding sum may miss a whole number of turns.
const WINDING_SLACK: f64 = 0.1;

/// Whether an ordered closed loop winds exactly one full turn about an axis.
///
/// This is the question the kernel asks of its own tessellation candidates —
/// "a rim is any cycle whose net surface-u winding is a full revolution"
/// (`crates/operations/src/tessellate/nonplanar.rs:326-335`) — and it is the
/// one that separates a band's rim from a bore through the same wall, whatever
/// the edges under it turned out to be. A rim reaches this stage as one closed
/// circle when nothing lands on it and as a chain of arcs when something does;
/// both wind, and a hole winds nothing.
pub(super) fn winds_full_turn(points: &[V3], origin: V3, dir: V3) -> bool {
    (total_winding(points, origin, dir).abs() - core::f64::consts::TAU).abs() < WINDING_SLACK
}

/// Signed turning of an ordered closed loop about an axis, in radians.
fn total_winding(points: &[V3], origin: V3, dir: V3) -> f64 {
    if points.len() < 3 {
        return 0.0;
    }
    let mut total = 0.0;
    for k in 0..points.len() {
        let a = points[k].sub(origin).reject(dir);
        let b = points[(k + 1) % points.len()].sub(origin).reject(dir);
        if a.norm() < 1e-12 || b.norm() < 1e-12 {
            continue;
        }
        total += a.cross(b).dot(dir).atan2(a.dot(b));
    }
    total
}

/// Whether a face on this surface is seamed at all.
///
/// Every periodic primitive is; a plane and an unrecognised patch are not.
pub(super) const fn is_periodic(prim: Primitive) -> bool {
    matches!(
        prim,
        Primitive::Cylinder { .. }
            | Primitive::Cone { .. }
            | Primitive::Sphere { .. }
            | Primitive::Torus { .. }
    )
}

/// The point a one-rim periodic face runs out to: a cone's apex.
///
/// A sphere's pole is deliberately **not** here. The kernel has a structured
/// path for the cone's degenerate wire — `tessellate_cone_apex_fan_shared`
/// wants "exactly one closed rim circle; every other edge must be a (seam)
/// line" (`crates/operations/src/tessellate/nonplanar.rs:507`) — and none for
/// a sphere: a one-rim spherical face reaches
/// `tessellate_sphere_cap_shared`, whose latitude path needs a second trimmed
/// face on the same sphere and whose web path refuses anything wider than
/// about 80 degrees (`nonplanar.rs:2604`). Seaming a big cap to its pole
/// measures worse than leaving it alone, so it is left alone.
pub(super) fn degenerate_point(prim: Primitive) -> Option<V3> {
    match prim {
        Primitive::Cone { apex, .. } => Some(V3::from_arr(apex)),
        _ => None,
    }
}

/// Whether a patch's surface closes in both parameter directions, so a face on
/// it has no rim anywhere — a whole doughnut, which the kernel expresses as a
/// single face bounded by a fundamental polygon.
pub(super) const fn is_closed_periodic(prim: Primitive) -> bool {
    matches!(prim, Primitive::Torus { .. })
}

/// How far a ring's samples may sit off the circle fitted through them, as a
/// fraction of the run tolerance, before the ring is kept as a polyline.
///
/// A quarter rather than the whole: the question is not "could this be a
/// circle inside the budget" — a coarse polygonal bore could — but "is this a
/// circle the marcher sampled", and that answers itself two orders of
/// magnitude tighter.
const RING_CIRCLE_FACTOR: f64 = 0.25;

/// The smallest sample count a ring has to have before it is worth testing.
const RING_MIN_SAMPLES: usize = 8;

/// The largest radius a ring may be fitted at, as a multiple of its own extent
/// about its centroid. A full turn's extent is its radius; a nearly straight
/// run of samples fits an enormous circle every one of them sits on.
const RING_EXTENT_FACTOR: f64 = 4.0;

/// A closed ring of samples read back as the circle it is, as
/// `(centre, axis, radius)`.
///
/// Topology recovery hands a rim over as a `Curve::Circle` when the kernel had
/// a closed-form intersection for it and as a **marched** `Curve::Polyline`
/// when it did not — a cone against a coaxial cylinder is exactly a circle and
/// still comes back as a thousand points, because the general marcher's output
/// is a fitted NURBS, never a circle. Built literally, that rim is a thousand
/// `EdgeCurve::Line` edges, and the kernel's band mesher counts only circles
/// and NURBS as rim candidates and reads every line as a seam
/// (`crates/operations/src/tessellate/nonplanar.rs:344-352`): the band
/// declines and the CDT fallback meshes the wrong region.
/// `stepped-shaft-spacer/mesh-default` is 14.5% off its own volume that way
/// and 0.5% off with the rim read back.
///
/// The caller decides *which* rings are offered here — see
/// [`Builder::rim_needs_marching`], which is what keeps the promotion off the
/// rings the marcher was not the only route to.
pub(super) fn ring_as_circle(points: &[V3], tol: f64) -> Option<(V3, V3, f64)> {
    if points.len() < RING_MIN_SAMPLES || !(tol.is_finite() && tol > 0.0) {
        return None;
    }
    let budget = RING_CIRCLE_FACTOR * tol;

    let mut sum = V3::ZERO;
    for p in points {
        sum = sum.add(*p);
    }
    let centroid = sum.mul(1.0 / points.len() as f64);
    let extent = points
        .iter()
        .map(|p| p.sub(centroid).norm())
        .fold(0.0_f64, f64::max);

    // The ring's own area vector is its plane normal; a ring enclosing no area
    // is not a rim whatever else it is.
    let mut area = V3::ZERO;
    for k in 0..points.len() {
        let a = points[k].sub(centroid);
        let b = points[(k + 1) % points.len()].sub(centroid);
        area = area.add(a.cross(b));
    }
    let axis = area.unit()?;
    if points
        .iter()
        .any(|p| p.sub(centroid).dot(axis).abs() > budget)
    {
        return None;
    }

    let ex = perp(axis);
    let ey = axis.cross(ex);
    let xy: Vec<(f64, f64)> = points
        .iter()
        .map(|p| {
            let d = p.sub(centroid);
            (d.dot(ex), d.dot(ey))
        })
        .collect();
    let (cx, cy, radius) = kasa(&xy)?;
    if !radius.is_finite() || radius <= budget || radius > RING_EXTENT_FACTOR * extent {
        return None;
    }
    if xy
        .iter()
        .any(|(x, y)| ((x - cx).hypot(y - cy) - radius).abs() > budget)
    {
        return None;
    }
    let center = centroid.add(ex.mul(cx)).add(ey.mul(cy));
    // And it has to go all the way round. At least once: a marcher that closes
    // its ring by carrying on past the seed walks it twice, which
    // `stepped-shaft-spacer/mesh-default` does, and the circle is the same
    // circle either way.
    winds_at_least_once(points, center, axis).then_some((center, axis, radius))
}

/// Whether an ordered closed loop winds at least one full turn about an axis.
fn winds_at_least_once(points: &[V3], origin: V3, dir: V3) -> bool {
    total_winding(points, origin, dir).abs() >= core::f64::consts::TAU - WINDING_SLACK
}

/// Algebraic (Kasa) circle fit. No refinement: the caller checks every sample
/// against the result and throws the fit away if any of them misses, so a fit
/// biased enough to matter cannot be kept.
fn kasa(xy: &[(f64, f64)]) -> Option<(f64, f64, f64)> {
    let n = xy.len() as f64;
    let mx = xy.iter().map(|(x, _)| *x).sum::<f64>() / n;
    let my = xy.iter().map(|(_, y)| *y).sum::<f64>() / n;
    let mut mat = [[0.0_f64; 4]; 4];
    let mut rhs = [0.0_f64; 4];
    for (x, y) in xy {
        let (dx, dy) = (x - mx, y - my);
        let row = [dx, dy, 1.0];
        let z = dx.mul_add(dx, dy * dy);
        for i in 0..3 {
            for j in 0..3 {
                mat[i][j] += row[i] * row[j];
            }
            rhs[i] += row[i] * z;
        }
    }
    let sol = solve_small(3, &mat, &rhs)?;
    let (cx, cy) = (0.5 * sol[0], 0.5 * sol[1]);
    let rsq = sol[2] + cx.mul_add(cx, cy * cy);
    (rsq.is_finite() && rsq > 0.0).then(|| (cx + mx, cy + my, rsq.sqrt()))
}

/// How far a promoted rim's circle axis may sit off the surface's own fitted
/// axis, as a sine: about three degrees.
const COAXIAL_SIN: f64 = 0.05;

/// How far a promoted rim's centre may sit off the surface's axis line, as a
/// fraction of its own radius.
const COAXIAL_FRAC: f64 = 0.02;

/// Whether a circle is coaxial with a periodic primitive's own axis — the
/// latitude circle a rim of that surface has to be.
pub(super) fn is_rim_of(prim: Primitive, center: V3, axis: V3, radius: f64, tol: f64) -> bool {
    let Some(unit) = axis.unit() else {
        return false;
    };
    match prim {
        Primitive::Sphere { center: c, .. } => {
            // Every circle on a sphere is one of its latitude circles; all that
            // is asked is that its plane passes the centre the right way.
            dist_point_line(V3::from_arr(c), center, unit) <= (COAXIAL_FRAC * radius).max(4.0 * tol)
        }
        _ => axis_of(prim).is_some_and(|(origin, dir)| {
            unit.cross(dir).norm() < COAXIAL_SIN
                && dist_point_line(center, origin, dir) <= (COAXIAL_FRAC * radius).max(4.0 * tol)
        }),
    }
}
