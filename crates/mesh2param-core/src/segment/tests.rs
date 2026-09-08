//! Synthetic-solid tests: every mesh is built here, so a failure is a
//! segmentation bug and never a corpus file that changed.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use core::f64::consts::TAU;

use super::fit::{FaceRef, FitOpts, Sample, fit_patch};
use super::linalg::V3;
use super::stats::{Allow, Stats};
use super::{
    Inventory, Patch, PatchKind, Primitive, SegmentOptions, Segmentation, UnknownReason, segment,
};
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
    // never invented. Since the freeform gates it is recognised — the cap is one
    // smooth curved region from the start, so it is never carved into the
    // shards the split stage used to leave `Unknown`, and it fits the sphere it
    // is.
    let cap = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Sphere)
        .expect("the spherical cap");
    match cap.primitive {
        Primitive::Sphere { radius, .. } => assert!((radius - 10.0).abs() < 0.1, "radius {radius}"),
        other => panic!("expected a sphere, got {other:?}"),
    }
    assert_eq!(
        seg.inventory,
        inventory(1, 1, 0, 0, 1),
        "the base, the side and the cap, and nothing invented: {:?}",
        seg.inventory
    );
}

/// A hexagonal prism with a 45-degree chamfer at each end: six flats, two end
/// faces and twelve chamfer facets, all planar.
///
/// The chamfer is cut on the apothem, so each chamfer facet is a planar
/// trapezoid; the outer ring sits at `chamfer` above the base, the inner ring
/// on it.
fn chamfered_hex_prism(circumradius: f64, height: f64, chamfer: f64) -> (Vec<[f64; 3]>, Vec<u32>) {
    let apothem = circumradius * (TAU / 12.0).cos();
    let inner = (apothem - chamfer) / (TAU / 12.0).cos();
    let ring = |r: f64, z: f64, v: &mut Vec<[f64; 3]>| {
        for k in 0..6 {
            let a = TAU * f64::from(k) / 6.0;
            v.push([r * a.cos(), r * a.sin(), z]);
        }
    };
    let mut v = Vec::new();
    ring(inner, 0.0, &mut v); // 0..6   bottom cap rim
    ring(circumradius, chamfer, &mut v); // 6..12  bottom chamfer top
    ring(circumradius, height - chamfer, &mut v); // 12..18 side top
    ring(inner, height, &mut v); // 18..24 top cap rim
    let cb = v.len() as u32;
    v.push([0.0, 0.0, 0.0]);
    let ct = v.len() as u32;
    v.push([0.0, 0.0, height]);

    let mut i = Vec::new();
    for k in 0..6_u32 {
        let n = (k + 1) % 6;
        // Three rings of quads, wound as in `cylinder_mesh`: outward.
        for base in [0_u32, 6, 12] {
            let (b0, b1) = (base + k, base + n);
            let (t0, t1) = (base + 6 + k, base + 6 + n);
            i.extend_from_slice(&[b0, b1, t0, b1, t1, t0]);
        }
        i.extend_from_slice(&[cb, n, k]); // bottom cap, normal -z
        i.extend_from_slice(&[ct, 18 + k, 18 + n]); // top cap, normal +z
    }
    (v, i)
}

/// A chamfer ring is not a sphere.
///
/// Every vertex of a hexagonal prism lies on one sphere — that is what being
/// inscribed means — so a sphere fitted to a chamfer ring has *zero* residual
/// at every sample, and the normal deviation at the facet centroids is under
/// six degrees. Nothing but the 60-degree crease between the facets says the
/// ring is twelve planes and not two spheres, which is what this solid used to
/// report.
#[test]
fn chamfered_hex_prism_is_twenty_planes_and_no_spheres() {
    let (v, i) = chamfered_hex_prism(7.5, 35.0, 1.1);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        // 6 hex flats + 2 end faces + 12 chamfer facets.
        inventory(20, 0, 0, 0, 0),
        "{:?}",
        seg.inventory
    );
    assert!(seg.unknown_area_fraction.abs() < 1e-12);
}

/// Two parallel flats joined by one narrow 45-degree chamfer strip.
///
/// The strip is a fortieth of the area of the flats it borders, so it moves the
/// area-weighted RMS of a merged plane fit by almost nothing and the
/// area-weighted normal deviation by under seven degrees: both flats used to
/// swallow it, leaving two planes where there are three. The strip's fold is a
/// 45-degree crease and that is the only thing that says so.
#[test]
fn a_chamfer_strip_is_not_absorbed_by_the_flats_it_joins() {
    let step = 1.0;
    let (mut v, mut i) = (Vec::new(), Vec::new());
    // Three strips running in y, meeting along x = 0 and x = step.
    let profile = [(-40.0, 0.0), (0.0, 0.0), (step, -step), (41.0, -step)];
    for &(x, z) in &profile {
        v.push([x, 0.0, z]);
        v.push([x, 20.0, z]);
    }
    for k in 0..3_u32 {
        let (a, b) = (2 * k, 2 * k + 2);
        i.extend_from_slice(&[a, b, a + 1, b, b + 1, a + 1]);
    }
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(3, 0, 0, 0, 0),
        "the chamfer strip was absorbed: {:?}",
        seg.inventory
    );
}

/// A ribbon whose cross-section runs across a flat top, down a stepped chamfer
/// and on to a flat side.
///
/// The chamfer's facets are `steps` equal turns of `total_deg / steps`, which
/// the caller keeps under [`SegmentOptions::angle_deg`] so the whole band and
/// the top face come out of the dihedral pass as **one** patch — the leak
/// stage 2b exists to undo. The last facet is left more than `maxFacetDeg`
/// from the side face.
fn stepped_chamfer_ribbon(
    length: f64,
    top: f64,
    side: f64,
    steps: usize,
    total_deg: f64,
    facet: f64,
) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut profile = vec![(-top, side), (0.0, side)];
    let (mut y, mut z) = (0.0_f64, side);
    for k in 0..steps {
        let a = (total_deg * (k as f64 + 0.5) / steps as f64).to_radians();
        y += facet * a.cos();
        z -= facet * a.sin();
        profile.push((y, z));
    }
    profile.push((y, 0.0));

    let mut v = Vec::new();
    for &(py, pz) in &profile {
        v.push([0.0, py, pz]);
        v.push([length, py, pz]);
    }
    let mut i = Vec::new();
    for k in 0..(profile.len() as u32 - 1) {
        let (a, b) = (2 * k, 2 * k + 2);
        i.extend_from_slice(&[a, b, a + 1, b, b + 1, a + 1]);
    }
    (v, i)
}

/// Boundary refinement may not put a crease into a patch.
///
/// A face moves to whichever neighbouring patch's primitive scores it best,
/// and that score says nothing about the angle the face meets its new patch
/// at: the last facet of this chamfer sits close enough to the side face's
/// plane to be scored well by it, and moves there — 40.5 degrees out of
/// plane. Nothing after this stage re-cuts a patch, so the fold is permanent,
/// and the crease rule in `fit_patch` then refuses **the whole side face**
/// rather than the one triangle that spoiled it. Before the guard this solid
/// loses 38% of its area to `Unknown`; the mechanism is what took four corpus
/// meshes down a reconstruction tier.
#[test]
fn refinement_never_folds_a_face_into_a_plane() {
    // Five 11-degree steps: each is under the 12-degree dihedral threshold, so
    // the band leaks into the top face's patch, and the last one lands 40.5
    // degrees from the side face — just past `maxFacetDeg`.
    let (v, i) = stepped_chamfer_ribbon(60.0, 30.0, 20.0, 5, 55.0, 0.4);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(2, 0, 0, 0, 0),
        "the top and side faces are two planes: {:?}",
        seg.inventory
    );
    assert!(
        seg.unknown_area_fraction.abs() < 1e-12,
        "a whole face was refused over one folded triangle: {} unknown",
        seg.unknown_area_fraction
    );
}

/// A closed blob whose radius is modulated so that no part of it is any
/// primitive, tessellated coarsely enough that neighbouring triangles are
/// pervasively further apart than `angleDeg`.
fn lumpy_blob(radius: f64, bump: f64, lon: usize, lat: usize) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for j in 0..=lat {
        let t = core::f64::consts::PI * j as f64 / lat as f64;
        for i in 0..lon {
            let u = TAU * i as f64 / lon as f64;
            let r = radius * bump.mul_add((3.0 * u).sin() * (2.0 * t).cos(), 1.0);
            v.push([r * t.sin() * u.cos(), r * t.sin() * u.sin(), r * t.cos()]);
        }
    }
    let mut i = Vec::new();
    let n = lon as u32;
    for j in 0..lat as u32 {
        for k in 0..n {
            let nk = (k + 1) % n;
            let (a, b) = (j * n + k, j * n + nk);
            let (c, d) = ((j + 1) * n + k, (j + 1) * n + nk);
            i.extend_from_slice(&[a, c, b, b, c, d]);
        }
    }
    (v, i)
}

/// A triangular prism: two triangular ends and three rectangular sides.
fn triangular_prism(side: f64, length: f64) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for k in 0..3 {
        let a = TAU * f64::from(k) / 3.0;
        v.push([side * a.cos(), side * a.sin(), 0.0]);
        v.push([side * a.cos(), side * a.sin(), length]);
    }
    let mut i = Vec::new();
    for k in 0..3_u32 {
        let n = (k + 1) % 3;
        let (b0, t0, b1, t1) = (2 * k, 2 * k + 1, 2 * n, 2 * n + 1);
        i.extend_from_slice(&[b0, b1, t0, b1, t1, t0]);
    }
    i.extend_from_slice(&[0, 4, 2]); // bottom, one triangle
    i.extend_from_slice(&[1, 3, 5]); // top, one triangle
    (v, i)
}

/// A lone triangle is not evidence of a plane.
///
/// Where adjacent triangles are pervasively further apart than `angleDeg`, the
/// dihedral pass on its own cuts a coarsely tessellated freeform surface into
/// single triangles: no merge can join them, the split stage never touches
/// them, so nothing marks them `carved` and none of the shard gates ever look
/// at them. This blob has no flat face anywhere on it and used to report
/// **55** planes covering every square millimetre of it.
///
/// The gate is span, not face count: the prism's ends are one triangle each
/// and are real faces, and they are large.
#[test]
fn a_lone_triangle_is_promoted_only_when_it_is_a_face() {
    let (v, i) = lumpy_blob(10.0, 0.25, 8, 6);
    let seg = run(&v, &i);
    for patch in &seg.patches {
        assert!(
            patch.faces.len() > 1 || patch.kind == PatchKind::Unknown,
            "a single triangle of the blob was promoted to {:?}",
            patch.kind
        );
    }
    assert!(
        seg.inventory.plane < 30,
        "the blob is still a fan of planes: {:?}",
        seg.inventory
    );
    assert!(
        seg.unknown_area_fraction > 0.15,
        "a freeform blob reported almost no unknown area: {}",
        seg.unknown_area_fraction
    );

    let (v, i) = triangular_prism(20.0, 50.0);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(5, 0, 0, 0, 0),
        "the prism's one-triangle ends were thrown away: {:?}",
        seg.inventory
    );
}

/// A triangulated height field `z = f(x, y)` over a square, reduced to what the
/// fits take: area-weighted vertex samples and per-triangle normal records.
fn patch_of(points: &[[f64; 3]], tris: &[[usize; 3]]) -> (Vec<Sample>, Vec<FaceRef>) {
    let v = |i: usize| V3::from_arr(points[i]);
    let mut weights = vec![0.0_f64; points.len()];
    let mut faces = Vec::with_capacity(tris.len());
    for t in tris {
        let (a, b, c) = (v(t[0]), v(t[1]), v(t[2]));
        let cross = b.sub(a).cross(c.sub(a));
        let area = 0.5 * cross.norm();
        let Some(n) = cross.unit() else { continue };
        for i in t {
            weights[*i] += area / 3.0;
        }
        faces.push(FaceRef {
            n,
            c: a.add(b).add(c).mul(1.0 / 3.0),
            a: area,
        });
    }
    let pts = points
        .iter()
        .enumerate()
        .filter(|(i, _)| weights[*i] > 0.0)
        .map(|(i, p)| Sample {
            p: V3::from_arr(*p),
            w: weights[i],
        })
        .collect();
    (pts, faces)
}

fn fit_opts(tol: f64) -> FitOpts {
    let o = SegmentOptions::default();
    FitOpts {
        tol,
        min_spread: o.min_spread_deg.to_radians(),
        max_facet_step: o.max_facet_deg.to_radians(),
        max_crease: 0.0,
        max_normal_dev: o.max_normal_dev_deg.to_radians(),
        radius_tol_frac: o.radius_tol_frac,
        min_minor_sweep: o.min_minor_sweep_deg.to_radians(),
        bbox_diag: 100.0,
    }
}

/// A nearly flat strip with a trace of curvature: 500 units of radius across a
/// 20-unit strip, so the samples wrap 2.3 degrees around an axis 500 away.
///
/// `minSpreadDeg` is the *angular* half of this pair and refuses the strip on
/// its own, so it is turned off here: what is under test is the radial half,
/// which is what catches a radius no span in the patch supports — the motor
/// mount's 444 mm cylinder on a 23 mm flat, whose fold pushed the plane out of
/// tolerance and left the circle fit following the flat majority. Without the
/// guard the fit returns exactly the 500 the strip was drawn from and a face
/// built on it sits half a metre off a 20-unit part.
#[test]
fn a_nearly_flat_strip_is_never_a_huge_radius_cylinder() {
    let (radius, width, length) = (500.0_f64, 20.0_f64, 40.0_f64);
    let sweep = width / radius;
    let steps = 10_usize;
    let mut points = Vec::new();
    for i in 0..=steps {
        let a = sweep * (i as f64 / steps as f64 - 0.5);
        for j in 0..=steps {
            let y = length * (j as f64 / steps as f64 - 0.5);
            points.push([radius * a.sin(), y, radius * a.cos() - radius]);
        }
    }
    let at = |i: usize, j: usize| i * (steps + 1) + j;
    let mut tris = Vec::new();
    for i in 0..steps {
        for j in 0..steps {
            tris.push([at(i, j), at(i + 1, j), at(i + 1, j + 1)]);
            tris.push([at(i, j), at(i + 1, j + 1), at(i, j + 1)]);
        }
    }
    let (pts, faces) = patch_of(&points, &tris);

    // Tight enough that the plane is out of tolerance, so the curved fits are
    // genuinely reached rather than pre-empted by the plane.
    let sagitta = width * width / (8.0 * radius);
    let mut o = fit_opts(sagitta / 10.0);
    o.min_spread = 0.0;
    let fit = fit_patch(
        &pts,
        &faces,
        o,
        &Stats::from_samples(&pts, &faces, 0.0),
        Allow::ALL,
    );
    assert!(
        matches!(fit.prim, Primitive::Unknown),
        "a nearly flat strip came back as {:?}",
        fit.prim
    );

    // With a budget the plane fits inside, it is a plane and nothing else.
    let mut o = fit_opts(2.0 * sagitta);
    o.min_spread = 0.0;
    let fit = fit_patch(
        &pts,
        &faces,
        o,
        &Stats::from_samples(&pts, &faces, 0.0),
        Allow::ALL,
    );
    assert!(
        matches!(fit.prim, Primitive::Plane { .. }),
        "expected a plane, got {:?}",
        fit.prim
    );
}

/// The other side of the same guard: a genuinely cylindrical patch, coarse
/// enough that only two facets meet along any edge, still fits.
#[test]
fn a_twelve_facet_cylinder_still_fits_under_the_conditioning_guard() {
    let (radius, height, facets) = (10.0_f64, 20.0_f64, 12_usize);
    let mut points = Vec::new();
    for k in 0..=facets {
        let a = TAU * (k % facets) as f64 / facets as f64;
        points.push([radius * a.cos(), radius * a.sin(), 0.0]);
        points.push([radius * a.cos(), radius * a.sin(), height]);
    }
    let mut tris = Vec::new();
    for k in 0..facets {
        let (b0, t0, b1, t1) = (2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 3);
        tris.push([b0, b1, t0]);
        tris.push([b1, t1, t0]);
    }
    let (pts, faces) = patch_of(&points, &tris);
    let fit = fit_patch(
        &pts,
        &faces,
        fit_opts(0.35 * radius * TAU / facets as f64),
        &Stats::from_samples(&pts, &faces, 0.0),
        Allow::ALL,
    );
    match fit.prim {
        Primitive::Cylinder {
            radius: r,
            axis_dir,
            ..
        } => {
            assert!((r - radius).abs() < 1e-6, "radius {r}");
            assert!(axis_dir[2].abs() > 0.999_999, "axis {axis_dir:?}");
        }
        other => panic!("expected a cylinder, got {other:?}"),
    }
}

/// How much of the dome's pole is left out, in degrees.
///
/// A pole is a tessellation singularity, not a surface feature: the triangles
/// there are slivers whose normals wobble past the facet limit, so the whole
/// neighbourhood reads as creased and the test would be measuring the sliver
/// fan rather than the freeform gate.
const POLAR_HOLE_DEG: f64 = 20.0;

/// A dome whose radius is gently modulated, tessellated finely enough that
/// every adjacent pair of triangles is far inside `angleDeg`.
///
/// An open surface on purpose: this is the freeform case with nothing else on
/// the part to hide behind. `phi` runs from [`POLAR_HOLE_DEG`] to `open_deg`.
fn bumpy_dome(
    radius: f64,
    bump: f64,
    open_deg: f64,
    lon: usize,
    lat: usize,
) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut v = Vec::new();
    for j in 0..=lat {
        let t = (POLAR_HOLE_DEG + (open_deg - POLAR_HOLE_DEG) * j as f64 / lat as f64).to_radians();
        for i in 0..lon {
            let u = TAU * i as f64 / lon as f64;
            let r = radius * bump.mul_add((3.0 * u).sin() * (2.0 * t).cos(), 1.0);
            v.push([r * t.sin() * u.cos(), r * t.sin() * u.sin(), r * t.cos()]);
        }
    }
    let n = lon as u32;
    let mut i = Vec::new();
    for j in 0..lat as u32 {
        for k in 0..n {
            let nk = (k + 1) % n;
            let (a, b) = (j * n + k, j * n + nk);
            let (c, d) = ((j + 1) * n + k, (j + 1) * n + nk);
            i.extend_from_slice(&[a, c, b, b, c, d]);
        }
    }
    (v, i)
}

/// A smooth curved surface has no planes on it, at any tessellation density.
///
/// This is the failure the curvature gates exist for. Fine tessellation is the
/// *hard* direction, not the easy one: every neighbouring pair is inside
/// `angleDeg`, so the region arrives as one patch, fits nothing, and is carved
/// at a progressively tighter angle until each shard is flat to a small
/// fraction of its own tolerance — the shards then clear every size and
/// residual gate there is. Only their curvature says they are samples of a
/// curve rather than faces on the part.
#[test]
fn a_finely_tessellated_dome_has_no_planes_on_it() {
    let (v, i) = bumpy_dome(10.0, 0.12, 80.0, 48, 16);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory.plane, 0,
        "the dome shattered into planes: {:?}",
        seg.inventory
    );
    assert!(
        seg.unknown_area_fraction > 0.9,
        "a dome that fits no primitive is not mostly unknown: {}",
        seg.unknown_area_fraction
    );
    let freeform = seg
        .patches
        .iter()
        .filter(|p| p.reason == Some(UnknownReason::Freeform))
        .map(|p| p.area)
        .sum::<f64>();
    let total = seg.patches.iter().map(|p| p.area).sum::<f64>();
    assert!(
        freeform > 0.9 * total,
        "the dome is unknown but not reported as freeform: {freeform} of {total}"
    );
}

/// A box with one vertical edge rounded: a prism over a profile that is three
/// straight runs and one quarter-circle arc.
///
/// `facets` steps over the 90 degrees, kept under `angleDeg` so the fillet is
/// tangent to both flats it joins and the dihedral pass cannot cut it off them.
fn box_with_one_fillet(
    sx: f64,
    sy: f64,
    sz: f64,
    r: f64,
    facets: usize,
    levels: usize,
) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut profile = vec![[0.0, 0.0], [sx, 0.0]];
    for k in 0..=facets {
        let a = core::f64::consts::FRAC_PI_2 * k as f64 / facets as f64;
        profile.push([(sx - r) + r * a.cos(), (sy - r) + r * a.sin()]);
    }
    profile.push([0.0, sy]);

    // The extrusion is subdivided in z, as a tessellator subdivides a face it
    // has to keep inside a chord tolerance in both directions. It is also what
    // gives the fillet band vertices of its own: a band two rows tall has every
    // vertex on the rim where a cap folds away, so there is nowhere on it that
    // any one-ring estimator can measure.
    let n = profile.len() as u32;
    let rows = levels as u32 + 1;
    let mut v = Vec::new();
    for p in &profile {
        for l in 0..rows {
            v.push([p[0], p[1], sz * f64::from(l) / f64::from(rows - 1)]);
        }
    }
    let cb = v.len() as u32;
    v.push([0.0, 0.0, 0.0]);
    let ct = v.len() as u32;
    v.push([0.0, 0.0, sz]);

    let mut i = Vec::new();
    for k in 0..n {
        let m = (k + 1) % n;
        for l in 0..rows - 1 {
            let (b0, t0) = (k * rows + l, k * rows + l + 1);
            let (b1, t1) = (m * rows + l, m * rows + l + 1);
            i.extend_from_slice(&[b0, b1, t0, b1, t1, t0]);
        }
        i.extend_from_slice(&[cb, m * rows, k * rows]);
        i.extend_from_slice(&[ct, k * rows + rows - 1, m * rows + rows - 1]);
    }
    (v, i)
}

/// A fillet is a surface, not a row of narrow planes — and gating it must not
/// cost the flats it joins.
///
/// The band is tangent to both neighbouring flats, so nothing in the dihedral
/// pass separates the three, and every facet of it is a long thin quad that
/// fits a plane to well inside tolerance. It has to come back as one cylinder
/// or as one freeform region, and the box's six planes have to survive intact:
/// a real planar face has no curvature over its interior, so the gate never
/// looks at it.
#[test]
fn a_filleted_box_keeps_six_planes_and_never_plates_the_fillet() {
    let (v, i) = box_with_one_fillet(20.0, 16.0, 12.0, 3.0, 12, 8);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory.plane, 6,
        "the box lost or gained a flat: {:?}",
        seg.inventory
    );
    let band: Vec<&Patch> = seg
        .patches
        .iter()
        .filter(|p| p.kind == PatchKind::Cylinder || p.reason == Some(UnknownReason::Freeform))
        .collect();
    assert_eq!(
        band.len(),
        1,
        "the fillet is not one cylinder or one freeform region: {:?}",
        seg.inventory
    );
    // Half of the band — a quarter turn of radius 3 over a height of 12 — comes
    // back as that one patch. The other half is absorbed by the two flats it is
    // tangent to, each facet of it lying inside their own plane tolerance; that
    // is older behaviour and unrelated to curvature, which is why the bar here
    // is a third of the band rather than all of it.
    let want = core::f64::consts::FRAC_PI_2 * 3.0 * 12.0;
    assert!(
        band[0].area > want / 3.0,
        "only {} of a {want} fillet band survives as a surface",
        band[0].area
    );
    // And whatever the flats absorbed, none of them is a plane *on* the curve.
    for plane in seg.patches.iter().filter(|p| p.kind == PatchKind::Plane) {
        assert!(
            plane.smooth_curved_fraction < 0.5,
            "a plane was promoted over a curved region: {:?}",
            plane
        );
    }
}

/// Creases beat curvature: a coarse cylinder is still a cylinder.
///
/// Twelve facets is a 30 degree step, wider than `angleDeg` and inside
/// `maxFacetDeg`, which is exactly the range the freeform grouping reaches
/// into. It must not reach *this*: the side is a cylinder and the merge stage
/// has to be left free to rebuild it strip by strip. Every vertex of the side
/// lies on the rim where a cap folds away at 90 degrees, so no vertex of it
/// carries curvature at all and the grouping never fires.
#[test]
fn a_coarse_cylinder_is_not_swallowed_by_the_freeform_grouping() {
    let (v, i) = cylinder_mesh(10.0, 20.0, 12);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(2, 1, 0, 0, 0),
        "the coarse cylinder was lost: {:?}",
        seg.inventory
    );
    let cyl = seg
        .patches
        .iter()
        .find(|p| p.kind == PatchKind::Cylinder)
        .expect("a cylinder patch");
    assert!(
        cyl.smooth_curved_fraction.abs() < 1e-12,
        "a rim-to-rim strip scored as smoothly curved: {}",
        cyl.smooth_curved_fraction
    );
}

/// A thin flat plate is six planes and no curvature anywhere.
///
/// The plate is where a curvature estimate normalised by a vertex area goes
/// wrong if it is going to: the rim vertices carry a sliver of area and the
/// aspect ratio is 200:1. Nothing on it bends, so nothing on it may score as
/// bent.
#[test]
fn a_thin_flat_plate_stays_six_planes() {
    let (v, i) = box_mesh(100.0, 80.0, 0.5);
    let seg = run(&v, &i);
    assert_eq!(
        seg.inventory,
        inventory(6, 0, 0, 0, 0),
        "{:?}",
        seg.inventory
    );
    assert!(
        seg.face_smooth_curved.iter().all(|&s| !s),
        "a flat plate has a smoothly curved triangle on it"
    );
    assert!(
        seg.face_curvature.iter().all(|&k| k < 1e-9),
        "a flat plate reports curvature"
    );
}
