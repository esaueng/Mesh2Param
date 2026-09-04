//! Unit tests for face construction, on triangle lists built in the test.
//!
//! Every mesh here is generated rather than loaded, so the expected face
//! inventory is known exactly and a change in the numbers is a change in
//! behaviour rather than in a fixture.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use core::f64::consts::TAU;

use super::*;
use crate::mesh::MeshData;

/// A triangle soup under construction, in the winding the mesh will keep.
#[derive(Default)]
struct Soup {
    points: Vec<[f64; 3]>,
    indices: Vec<u32>,
}

impl Soup {
    fn vertex(&mut self, p: [f64; 3]) -> u32 {
        for (i, q) in self.points.iter().enumerate() {
            if (0..3).all(|k| (p[k] - q[k]).abs() < 1e-12) {
                return i as u32;
            }
        }
        self.points.push(p);
        (self.points.len() - 1) as u32
    }

    fn tri(&mut self, a: [f64; 3], b: [f64; 3], c: [f64; 3]) {
        let (ia, ib, ic) = (self.vertex(a), self.vertex(b), self.vertex(c));
        self.indices.extend_from_slice(&[ia, ib, ic]);
    }

    /// A quad wound `a -> b -> c -> d`, split into two triangles.
    fn quad(&mut self, a: [f64; 3], b: [f64; 3], c: [f64; 3], d: [f64; 3]) {
        self.tri(a, b, c);
        self.tri(a, c, d);
    }

    fn mesh(&self) -> MeshData {
        MeshData::from_triangles(&self.points, &self.indices).unwrap()
    }
}

fn run(mesh: &MeshData) -> ReconstructResult {
    reconstruct(mesh, &ReconstructOptions::default()).unwrap()
}

/// The unit cube, outward winding.
fn cube() -> MeshData {
    let mut s = Soup::default();
    let p = |x: f64, y: f64, z: f64| [x, y, z];
    // -z and +z
    s.quad(p(0., 0., 0.), p(0., 1., 0.), p(1., 1., 0.), p(1., 0., 0.));
    s.quad(p(0., 0., 1.), p(1., 0., 1.), p(1., 1., 1.), p(0., 1., 1.));
    // -y and +y
    s.quad(p(0., 0., 0.), p(1., 0., 0.), p(1., 0., 1.), p(0., 0., 1.));
    s.quad(p(0., 1., 0.), p(0., 1., 1.), p(1., 1., 1.), p(1., 1., 0.));
    // -x and +x
    s.quad(p(0., 0., 0.), p(0., 0., 1.), p(0., 1., 1.), p(0., 1., 0.));
    s.quad(p(1., 0., 0.), p(1., 1., 0.), p(1., 1., 1.), p(1., 0., 1.));
    s.mesh()
}

/// A capped cylinder about the z axis.
fn capped_cylinder(radius: f64, height: f64, facets: usize) -> MeshData {
    let mut s = Soup::default();
    let at = |k: usize, z: f64| {
        let a = TAU * (k % facets) as f64 / facets as f64;
        [radius * a.cos(), radius * a.sin(), z]
    };
    for k in 0..facets {
        s.quad(at(k, 0.0), at(k + 1, 0.0), at(k + 1, height), at(k, height));
        s.tri([0.0, 0.0, 0.0], at(k + 1, 0.0), at(k, 0.0));
        s.tri([0.0, 0.0, height], at(k, height), at(k + 1, height));
    }
    s.mesh()
}

/// A square plate with a cylindrical bore through it.
///
/// The outline is sampled at the same angles as the bore so the top and
/// bottom faces are one strip between two rings; `facets` must be a multiple
/// of four so the square's corners land exactly on samples.
fn plate_with_bore(half: f64, radius: f64, height: f64, facets: usize) -> MeshData {
    assert!(facets.is_multiple_of(4));
    let mut s = Soup::default();
    let angle = |k: usize| TAU * (k % facets) as f64 / facets as f64;
    let bore = |k: usize, z: f64| {
        let a = angle(k);
        [radius * a.cos(), radius * a.sin(), z]
    };
    let outline = |k: usize, z: f64| {
        let a = angle(k);
        let scale = half / a.cos().abs().max(a.sin().abs());
        [scale * a.cos(), scale * a.sin(), z]
    };
    for k in 0..facets {
        // Outer wall, outward normal.
        s.quad(
            outline(k, 0.0),
            outline(k + 1, 0.0),
            outline(k + 1, height),
            outline(k, height),
        );
        // Bore wall: outward for the solid means toward the axis.
        s.quad(
            bore(k, 0.0),
            bore(k, height),
            bore(k + 1, height),
            bore(k + 1, 0.0),
        );
        // Top annulus, +z.
        s.quad(
            bore(k, height),
            outline(k, height),
            outline(k + 1, height),
            bore(k + 1, height),
        );
        // Bottom annulus, -z.
        s.quad(
            bore(k, 0.0),
            bore(k + 1, 0.0),
            outline(k + 1, 0.0),
            outline(k, 0.0),
        );
    }
    s.mesh()
}

/// A block whose top-right edge is rounded to a quarter cylinder.
///
/// The fillet meets both the top face and the side face tangentially, which
/// is exactly the case that has no usable surface-surface intersection: those
/// two edges come back as polylines.
fn filleted_block(facets: usize, steps: usize) -> MeshData {
    let (lx, ly, lz, r) = (4.0_f64, 4.0_f64, 2.0_f64, 1.0_f64);
    let axis = [lx - r, lz - r];
    let mut s = Soup::default();

    // The end profile, counter-clockwise in xz seen from -y. Straight runs are
    // subdivided so no patch's own median chord is long enough to hide the
    // fillet's sagitta inside the fit tolerance.
    let mut profile: Vec<[f64; 2]> = Vec::new();
    let line = |from: [f64; 2], to: [f64; 2], out: &mut Vec<[f64; 2]>| {
        let n = steps.max(1);
        for k in 0..n {
            let t = k as f64 / n as f64;
            out.push([
                from[0] + (to[0] - from[0]) * t,
                from[1] + (to[1] - from[1]) * t,
            ]);
        }
    };
    line([0.0, 0.0], [lx, 0.0], &mut profile);
    line([lx, 0.0], [lx, lz - r], &mut profile);
    for k in 0..facets {
        let a = (core::f64::consts::PI / 2.0) * (1.0 - k as f64 / facets as f64);
        profile.push([axis[0] + r * a.sin(), axis[1] + r * a.cos()]);
    }
    line([lx - r, lz], [0.0, lz], &mut profile);
    line([0.0, lz], [0.0, 0.0], &mut profile);

    // Fanned from the profile's centroid rather than a corner: a corner fan
    // makes slivers, and a sliver's normal is what a segmenter trips over.
    let cx = profile.iter().map(|p| p[0]).sum::<f64>() / profile.len() as f64;
    let cz = profile.iter().map(|p| p[1]).sum::<f64>() / profile.len() as f64;
    for k in 0..profile.len() {
        let n = (k + 1) % profile.len();
        s.tri(
            [cx, 0.0, cz],
            [profile[k][0], 0.0, profile[k][1]],
            [profile[n][0], 0.0, profile[n][1]],
        );
        s.tri(
            [cx, ly, cz],
            [profile[n][0], ly, profile[n][1]],
            [profile[k][0], ly, profile[k][1]],
        );
    }
    for k in 0..profile.len() {
        let n = (k + 1) % profile.len();
        for j in 0..steps.max(1) {
            let y0 = ly * j as f64 / steps.max(1) as f64;
            let y1 = ly * (j + 1) as f64 / steps.max(1) as f64;
            let at = |i: usize, y: f64| [profile[i][0], y, profile[i][1]];
            s.quad(at(k, y0), at(k, y1), at(n, y1), at(n, y0));
        }
    }
    s.mesh()
}

#[test]
fn a_box_becomes_six_analytic_faces() {
    let mesh = cube();
    let out = run(&mesh);
    let b = &out.build;
    assert_eq!(b.tier, Tier::Analytic, "failures: {:?}", b.face_failures);
    assert_eq!(b.faces_analytic, 6);
    assert_eq!(b.faces_triangle, 0);
    assert_eq!(b.faces_final, 6);
    assert!(b.valid, "issues: {:?}", b.issues);
    let deviation = b.deviation.expect("verification ran");
    assert!(
        deviation.max < 1e-9,
        "a box's faces are exact, got {deviation:?}"
    );
    assert!((b.volume - 1.0).abs() < 1e-9, "volume {}", b.volume);
    assert!((b.source_volume - 1.0).abs() < 1e-12);
    assert!(b.step.starts_with(b"ISO-10303-21"));
    assert!(b.round_trip_ok, "the kernel's reader refused its own file");
}

#[test]
fn a_capped_cylinder_becomes_three_analytic_faces() {
    let mesh = capped_cylinder(1.0, 2.0, 48);
    let out = run(&mesh);
    let b = &out.build;
    assert_eq!(b.tier, Tier::Analytic, "failures: {:?}", b.face_failures);
    assert_eq!(b.faces_analytic, 3, "failures: {:?}", b.face_failures);
    assert_eq!(b.faces_triangle, 0);
    assert!(b.valid, "issues: {:?}", b.issues);
    assert!(b.round_trip_ok);
    // The mesh under-reports the true volume by the chord sagitta; the built
    // solid must be at least as large and within a facet of it.
    let exact = core::f64::consts::PI * 2.0;
    assert!(
        (b.volume - exact).abs() / exact < 0.01,
        "volume {} against {exact}",
        b.volume
    );
}

#[test]
fn a_plate_with_a_bore_keeps_the_bore_as_one_cylinder() {
    let mesh = plate_with_bore(2.0, 1.0, 2.0, 32);
    let out = run(&mesh);
    let b = &out.build;
    assert!(b.valid, "issues: {:?}", b.issues);
    assert_eq!(b.tier, Tier::Analytic, "failures: {:?}", b.face_failures);
    // Six planes and one cylinder: the bore's two rims bound a single face,
    // and the top and bottom faces carry the matching rim as an inner wire.
    assert_eq!(
        b.faces_final, 7,
        "faces {} analytic {} triangle {}, failures {:?}",
        b.faces_final, b.faces_analytic, b.faces_triangle, b.face_failures
    );
    assert!(b.round_trip_ok);
}

#[test]
fn a_tangent_fillet_still_builds_a_valid_solid() {
    let mesh = filleted_block(24, 16);
    let out = run(&mesh);
    let b = &out.build;
    assert!(b.valid, "issues: {:?}", b.issues);
    assert!(
        matches!(b.tier, Tier::Analytic | Tier::Mixed),
        "tier {:?}, failures {:?}",
        b.tier,
        b.face_failures
    );
    // Six planes and the fillet's quarter cylinder. Both tangent boundaries
    // come back as polylines — the intersection of two tangent surfaces is
    // ill-conditioned, so topology recovery declines it — and they reach the
    // kernel as chains of straight edges through the mesh's own samples.
    assert_eq!(b.faces_final, 7, "failures: {:?}", b.face_failures);
    assert_eq!(b.edges_curve_chain, 2);
    assert_eq!(b.edges_nurbs, 0);
    let deviation = b.deviation.expect("verification ran");
    assert!(
        deviation.p95 < 0.05,
        "the fillet's own facet step is 0.002; got {deviation:?}"
    );
    assert!(b.round_trip_ok);
}

#[test]
fn the_triangle_budget_is_enforced_before_any_work() {
    let mesh = cube();
    let options = ReconstructOptions {
        build: BuildOptions {
            triangle_budget: 3,
            ..BuildOptions::default()
        },
        ..ReconstructOptions::default()
    };
    assert!(matches!(
        reconstruct(&mesh, &options),
        Err(CoreError::Budget {
            triangles: 12,
            limit: 3
        })
    ));
}
