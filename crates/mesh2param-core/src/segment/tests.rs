//! Synthetic-solid tests: every mesh is built here, so a failure is a
//! segmentation bug and never a corpus file that changed.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use core::f64::consts::TAU;

use super::{Inventory, PatchKind, Primitive, SegmentOptions, Segmentation, segment};
use crate::mesh::MeshData;

/// A rectangular box, one quad per face, outward winding.
fn box_mesh(sx: f64, sy: f64, sz: f64) -> (Vec<[f64; 3]>, Vec<u32>) {
    let v = vec![
        [0.0, 0.0, 0.0],
        [sx, 0.0, 0.0],
        [sx, sy, 0.0],
        [0.0, sy, 0.0],
        [0.0, 0.0, sz],
        [sx, 0.0, sz],
        [sx, sy, sz],
        [0.0, sy, sz],
    ];
    let i = vec![
        0, 2, 1, 0, 3, 2, // bottom
        4, 5, 6, 4, 6, 7, // top
        0, 1, 5, 0, 5, 4, // -y
        1, 2, 6, 1, 6, 5, // +x
        2, 3, 7, 2, 7, 6, // +y
        3, 0, 4, 3, 4, 7, // -x
    ];
    (v, i)
}

/// A closed cylinder: `facets` side strips plus a fan cap at each end.
fn cylinder_mesh(radius: f64, height: f64, facets: usize) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for i in 0..facets {
        let a = TAU * i as f64 / facets as f64;
        v.push([radius * a.cos(), radius * a.sin(), 0.0]);
        v.push([radius * a.cos(), radius * a.sin(), height]);
    }
    let cb = v.len() as u32;
    v.push([0.0, 0.0, 0.0]);
    let ct = v.len() as u32;
    v.push([0.0, 0.0, height]);

    let mut i = Vec::new();
    for k in 0..facets {
        let (b0, t0) = (2 * k as u32, 2 * k as u32 + 1);
        let n = ((k + 1) % facets) as u32;
        let (b1, t1) = (2 * n, 2 * n + 1);
        i.extend_from_slice(&[b0, b1, t0, b1, t1, t0]);
        i.extend_from_slice(&[cb, b1, b0]);
        i.extend_from_slice(&[ct, t0, t1]);
    }
    (v, i)
}

/// A closed cone frustum: `facets` side strips plus a cap at each end.
fn frustum_mesh(r0: f64, r1: f64, height: f64, facets: usize) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for i in 0..facets {
        let a = TAU * i as f64 / facets as f64;
        v.push([r0 * a.cos(), r0 * a.sin(), 0.0]);
        v.push([r1 * a.cos(), r1 * a.sin(), height]);
    }
    let cb = v.len() as u32;
    v.push([0.0, 0.0, 0.0]);
    let ct = v.len() as u32;
    v.push([0.0, 0.0, height]);

    let mut i = Vec::new();
    for k in 0..facets {
        let (b0, t0) = (2 * k as u32, 2 * k as u32 + 1);
        let n = ((k + 1) % facets) as u32;
        let (b1, t1) = (2 * n, 2 * n + 1);
        i.extend_from_slice(&[b0, b1, t0, b1, t1, t0]);
        i.extend_from_slice(&[cb, b1, b0]);
        i.extend_from_slice(&[ct, t0, t1]);
    }
    (v, i)
}

/// A torus band: a full turn about the axis, `phi0..phi1` around the tube.
///
/// A fillet ring rather than a whole doughnut, which is what a torus is on a
/// real part — and what the axis estimator is honest about handling.
fn torus_band(
    major: f64,
    minor: f64,
    phi0: f64,
    phi1: f64,
    around: usize,
    across: usize,
) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for i in 0..around {
        let th = TAU * i as f64 / around as f64;
        for j in 0..=across {
            let ph = phi1.mul_add(
                j as f64 / across as f64,
                phi0 * (1.0 - j as f64 / across as f64),
            );
            let rho = minor.mul_add(ph.cos(), major);
            v.push([rho * th.cos(), rho * th.sin(), minor * ph.sin()]);
        }
    }
    let stride = (across + 1) as u32;
    let mut i = Vec::new();
    for a in 0..around as u32 {
        let b = (a + 1) % around as u32;
        for j in 0..across as u32 {
            let (p00, p01) = (a * stride + j, a * stride + j + 1);
            let (p10, p11) = (b * stride + j, b * stride + j + 1);
            i.extend_from_slice(&[p00, p10, p01, p10, p11, p01]);
        }
    }
    (v, i)
}

fn run(positions: &[[f64; 3]], indices: &[u32]) -> Segmentation {
    let mesh = MeshData::from_triangles(positions, indices).unwrap();
    segment(&mesh, &SegmentOptions::default()).unwrap()
}

fn inventory(plane: u32, cylinder: u32, cone: u32, torus: u32, sphere: u32) -> Inventory {
    Inventory {
        plane,
        cylinder,
        cone,
        torus,
        sphere,
        unknown: 0,
    }
}

#[test]
fn box_is_six_planes_and_nothing_else() {
    let (v, i) = box_mesh(20.0, 30.0, 40.0);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(6, 0, 0, 0, 0),
        "{:?}",
        seg.inventory
    );
    assert_eq!(seg.patches.len(), 6);
    assert!(seg.unknown_area_fraction.abs() < 1e-12);
    // Every triangle is claimed by exactly one patch.
    let claimed: usize = seg.patches.iter().map(|p| p.faces.len()).sum();
    assert_eq!(claimed, 12);
}

#[test]
fn coarse_cylinder_with_caps_is_one_cylinder_and_two_planes() {
    // Twelve facets is a 30 degree step: the dihedral pass cannot group the
    // side at all, so this only passes if the merge stage rebuilds it.
    let (v, i) = cylinder_mesh(10.0, 20.0, 12);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(2, 1, 0, 0, 0),
        "{:?}",
        seg.inventory
    );

    let cyl = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Cylinder)
        .expect("a cylinder patch");
    assert_eq!(cyl.faces.len(), 24);
    match cyl.primitive {
        Primitive::Cylinder {
            radius, axis_dir, ..
        } => {
            // Fitting on vertices is what recovers the true radius; a centroid
            // fit would report 10 * cos(15 degrees) = 9.66 here.
            assert!((radius - 10.0).abs() < 1e-6, "radius {radius}");
            assert!(axis_dir[2].abs() > 0.999_999, "axis {axis_dir:?}");
        }
        other => panic!("expected a cylinder, got {other:?}"),
    }
}

#[test]
fn cone_frustum_is_one_cone_and_two_planes() {
    let (v, i) = frustum_mesh(20.0, 10.0, 20.0, 36);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(2, 0, 1, 0, 0),
        "{:?}",
        seg.inventory
    );

    let cone = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Cone)
        .expect("a cone patch");
    match cone.primitive {
        Primitive::Cone {
            apex,
            axis_dir,
            half_angle_deg,
        } => {
            // r shrinks 20 -> 10 over a height of 20, so the half angle is
            // atan(1/2) and the apex sits 40 above the base.
            let want = 0.5_f64.atan().to_degrees();
            assert!(
                (half_angle_deg - want).abs() < 0.05,
                "half angle {half_angle_deg}"
            );
            assert!(axis_dir[2].abs() > 0.999, "axis {axis_dir:?}");
            assert!(apex[0].hypot(apex[1]) < 1e-6, "apex off axis: {apex:?}");
            assert!((apex[2] - 40.0).abs() < 0.05, "apex height {}", apex[2]);
        }
        other => panic!("expected a cone, got {other:?}"),
    }
}

#[test]
fn torus_ring_is_one_torus() {
    let (v, i) = torus_band(20.0, 5.0, 0.0, core::f64::consts::FRAC_PI_2, 96, 16);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(0, 0, 0, 1, 0),
        "{:?}",
        seg.inventory
    );

    let torus = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Torus)
        .expect("a torus patch");
    match torus.primitive {
        Primitive::Torus {
            major_radius,
            minor_radius,
            axis_dir,
            center,
        } => {
            assert!((major_radius - 20.0).abs() < 0.01, "major {major_radius}");
            assert!((minor_radius - 5.0).abs() < 0.01, "minor {minor_radius}");
            assert!(axis_dir[2].abs() > 0.999, "axis {axis_dir:?}");
            assert!(center[2].abs() < 0.01, "centre {center:?}");
        }
        other => panic!("expected a torus, got {other:?}"),
    }
}

/// A cylinder closed by a spherical cap of the same radius, plus a flat base.
///
/// `facets` around and `rings` bands over the cap's 90 degrees, both stepping
/// by less than `angleDeg`, so the dihedral pass cannot cut the cap off the
/// side it is tangent to: side and dome arrive as one region that is neither a
/// cylinder nor a sphere. That is the freeform case in miniature — a blob that
/// fits nothing, gets carved into shards, and whose shards are each flat to
/// far inside any sane tolerance.
fn capped_cylinder(
    radius: f64,
    height: f64,
    facets: usize,
    rings: usize,
) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    // One ring at the base of the side, then `rings` rings from the equator of
    // the cap up to (but not including) the pole.
    let levels = 1 + rings;
    for i in 0..facets {
        let a = TAU * i as f64 / facets as f64;
        let (ca, sa) = (a.cos(), a.sin());
        v.push([radius * ca, radius * sa, 0.0]);
        for k in 0..rings {
            let phi = core::f64::consts::FRAC_PI_2 * k as f64 / rings as f64;
            let (r, z) = (radius * phi.cos(), height + radius * phi.sin());
            v.push([r * ca, r * sa, z]);
        }
    }
    let pole = v.len() as u32;
    v.push([0.0, 0.0, height + radius]);
    let base = v.len() as u32;
    v.push([0.0, 0.0, 0.0]);

    let stride = levels as u32;
    let mut i = Vec::new();
    for k in 0..facets as u32 {
        let n = (k + 1) % facets as u32;
        let (c0, c1) = (k * stride, n * stride);
        for l in 0..stride - 1 {
            i.extend_from_slice(&[c0 + l, c1 + l, c0 + l + 1]);
            i.extend_from_slice(&[c1 + l, c1 + l + 1, c0 + l + 1]);
        }
        i.extend_from_slice(&[c0 + stride - 1, c1 + stride - 1, pole]);
        i.extend_from_slice(&[base, c1, c0]);
    }
    (v, i)
}

/// The whole point of the carved-patch gates: a curved region that fits nothing
/// must come back `Unknown`, not as a fan of tiny "planes".
///
/// Without the gates this solid reports **nine** planes on a body whose only
/// flat face is its base.
#[test]
fn sphere_cap_shards_never_become_planes() {
    let (v, i) = capped_cylinder(10.0, 20.0, 36, 10);
    let seg = run(&v, &i);

    assert_eq!(
        seg.inventory.plane, 1,
        "shards of the cap were promoted to planes: {:?}",
        seg.inventory
    );
    let base_area = core::f64::consts::PI * 100.0;
    let plane = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Plane)
        .expect("the flat base");
    assert!(
        (plane.area - base_area).abs() < 0.05 * base_area,
        "the one plane is not the base: area {} of {base_area}",
        plane.area
    );
    // The cap itself is not lost: it is either recognised or honestly unknown,
    // never invented.
    assert!(
        seg.unknown_area_fraction > 0.0,
        "nothing was left unknown, so the shards went somewhere"
    );
}
