//! Fitted primitives as kernel surfaces, plus the signed distance field the
//! vertex refinement needs.
//!
//! The kernel's [`AnalyticSurface`] has no plane arm — planes reach the
//! intersection routines through `exact_plane_analytic_bounded` and
//! `plane_plane_intersection` instead — so a plane is carried here as its own
//! variant rather than as a kernel surface.

use remus_math::analytic_intersection::AnalyticSurface;
use remus_math::surfaces::{ConicalSurface, CylindricalSurface, SphericalSurface, ToroidalSurface};
use remus_math::vec::{Point3, Vec3};

use crate::segment::Primitive;
use crate::segment::linalg::V3;

pub(super) fn point(v: V3) -> Point3 {
    Point3::new(v.x, v.y, v.z)
}

pub(super) fn vector(v: V3) -> Vec3 {
    Vec3::new(v.x, v.y, v.z)
}

pub(super) fn from_point(p: Point3) -> V3 {
    V3::new(p.x(), p.y(), p.z())
}

/// A fitted primitive in the form the kernel's intersection routines take.
pub(super) enum Surface {
    /// `normal . x = offset`.
    Plane { normal: V3, offset: f64 },
    /// A cylinder.
    Cylinder(CylindricalSurface),
    /// A cone.
    Cone(ConicalSurface),
    /// A sphere.
    Sphere(SphericalSurface),
    /// A torus.
    Torus(ToroidalSurface),
}

impl Surface {
    /// The kernel handle, or `None` for a plane.
    pub(super) fn analytic(&self) -> Option<AnalyticSurface<'_>> {
        match self {
            Self::Plane { .. } => None,
            Self::Cylinder(c) => Some(AnalyticSurface::Cylinder(c)),
            Self::Cone(c) => Some(AnalyticSurface::Cone(c)),
            Self::Sphere(s) => Some(AnalyticSurface::Sphere(s)),
            Self::Torus(t) => Some(AnalyticSurface::Torus(t)),
        }
    }

    /// The `v` parameter a point projects to, for the marching v-range hints.
    ///
    /// Only the cylinder and the cone have one worth bounding: their default
    /// ranges are a couple of units wide and a real face is not. The sphere
    /// and the torus are angular in `v` and already fully covered.
    pub(super) fn hint_v(&self, p: V3) -> Option<f64> {
        match self {
            Self::Cylinder(c) => Some(c.project_point(point(p)).1),
            Self::Cone(c) => Some(c.project_point(point(p)).1),
            Self::Plane { .. } | Self::Sphere(_) | Self::Torus(_) => None,
        }
    }
}

/// The kernel surface for a fitted primitive, or `None` when there is none.
///
/// The cone half-angle is complemented on the way across: this crate measures
/// it from the **axis** to the surface, and the kernel measures it from the
/// radial plane.
pub(super) fn surface_of(prim: Primitive) -> Option<Surface> {
    match prim {
        Primitive::Plane { normal, offset } => Some(Surface::Plane {
            normal: V3::from_arr(normal),
            offset,
        }),
        Primitive::Cylinder {
            axis_point,
            axis_dir,
            radius,
            ..
        } => CylindricalSurface::new(
            point(V3::from_arr(axis_point)),
            vector(V3::from_arr(axis_dir)),
            radius,
        )
        .ok()
        .map(Surface::Cylinder),
        Primitive::Cone {
            apex,
            axis_dir,
            half_angle_deg,
        } => ConicalSurface::new(
            point(V3::from_arr(apex)),
            vector(V3::from_arr(axis_dir)),
            (90.0 - half_angle_deg).to_radians(),
        )
        .ok()
        .map(Surface::Cone),
        Primitive::Sphere { center, radius } => {
            SphericalSurface::new(point(V3::from_arr(center)), radius)
                .ok()
                .map(Surface::Sphere)
        }
        Primitive::Torus {
            center,
            axis_dir,
            major_radius,
            minor_radius,
        } => ToroidalSurface::with_axis(
            point(V3::from_arr(center)),
            major_radius,
            minor_radius,
            vector(V3::from_arr(axis_dir)),
        )
        .ok()
        .map(Surface::Torus),
        Primitive::Unknown => None,
    }
}

/// Signed distance from `q` to the primitive: positive outside.
///
/// The cone's is the signed distance to the generating line in the axial
/// half-plane, which is what makes the Gauss-Newton step well-scaled: the
/// unsigned residual has a kink at the surface and no usable gradient there.
pub(super) fn signed_distance(prim: Primitive, q: V3) -> Option<f64> {
    match prim {
        Primitive::Plane { normal, offset } => Some(V3::from_arr(normal).dot(q) - offset),
        Primitive::Cylinder {
            axis_point,
            axis_dir,
            radius,
            ..
        } => {
            let rel = q.sub(V3::from_arr(axis_point));
            Some(rel.reject(V3::from_arr(axis_dir)).norm() - radius)
        }
        Primitive::Cone {
            apex,
            axis_dir,
            half_angle_deg,
        } => {
            let dir = V3::from_arr(axis_dir);
            let rel = q.sub(V3::from_arr(apex));
            let t = rel.dot(dir);
            let rho = rel.reject(dir).norm();
            let (s, c) = half_angle_deg.to_radians().sin_cos();
            Some(rho.mul_add(c, -(t * s)))
        }
        Primitive::Torus {
            center,
            axis_dir,
            major_radius,
            minor_radius,
        } => {
            let dir = V3::from_arr(axis_dir);
            let rel = q.sub(V3::from_arr(center));
            let t = rel.dot(dir);
            let rho = rel.reject(dir).norm();
            Some((rho - major_radius).hypot(t) - minor_radius)
        }
        Primitive::Sphere { center, radius } => Some(q.sub(V3::from_arr(center)).norm() - radius),
        Primitive::Unknown => None,
    }
}

/// Gradient of [`signed_distance`]: the outward unit normal at `q`.
pub(super) fn gradient(prim: Primitive, q: V3) -> Option<V3> {
    match prim {
        Primitive::Plane { normal, .. } => V3::from_arr(normal).unit(),
        Primitive::Cylinder {
            axis_point,
            axis_dir,
            ..
        } => q
            .sub(V3::from_arr(axis_point))
            .reject(V3::from_arr(axis_dir))
            .unit(),
        Primitive::Cone {
            apex,
            axis_dir,
            half_angle_deg,
        } => {
            let dir = V3::from_arr(axis_dir);
            let e = q.sub(V3::from_arr(apex)).reject(dir).unit()?;
            let (s, c) = half_angle_deg.to_radians().sin_cos();
            e.mul(c).sub(dir.mul(s)).unit()
        }
        Primitive::Torus {
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
        Primitive::Sphere { center, .. } => q.sub(V3::from_arr(center)).unit(),
        Primitive::Unknown => None,
    }
}

/// Newton-project `q` onto the primitive. Falls back to `q` when the gradient
/// is undefined (a point on a cylinder's own axis, say).
pub(super) fn project(prim: Primitive, q: V3) -> V3 {
    let mut p = q;
    for _ in 0..4 {
        let (Some(f), Some(g)) = (signed_distance(prim, p), gradient(prim, p)) else {
            return q;
        };
        if !f.is_finite() {
            return q;
        }
        p = p.sub(g.mul(f));
        if f.abs() < 1e-14 {
            break;
        }
    }
    if p.arr().iter().all(|c| c.is_finite()) {
        p
    } else {
        q
    }
}
