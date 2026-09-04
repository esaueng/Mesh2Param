//! Synthetic-solid tests: every mesh is built here, so a failure is a
//! topology bug and never a corpus file that changed.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use core::f64::consts::TAU;

use super::{Curve, EdgeSource, Topology, TopologyOptions, recover};
use crate::mesh::MeshData;
use crate::segment::{PatchKind, SegmentOptions, Segmentation, segment};

/// Push a quad `a, b, c, d` as two triangles keeping the quad's winding.
fn quad(idx: &mut Vec<u32>, a: u32, b: u32, c: u32, d: u32) {
    idx.extend_from_slice(&[a, b, c, a, c, d]);
}

fn run(
    positions: &[[f64; 3]],
    indices: &[u32],
    seg_opts: &SegmentOptions,
) -> (Segmentation, Topology) {
    let mesh = MeshData::from_triangles(positions, indices).unwrap();
    let seg = segment(&mesh, seg_opts).unwrap();
    let topo = recover(&mesh, &seg, &TopologyOptions::default()).unwrap();
    (seg, topo)
}

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

/// A rectangular block with a round through hole on the z axis.
///
/// The outer wall, the two faces and the bore all share the same `n` samples
/// around, so the annular faces are a clean quad strip.
fn holed_box(a: f64, b: f64, h: f64, r: f64, n: usize) -> (Vec<[f64; 3]>, Vec<u32>) {
    assert!(
        n.is_multiple_of(4),
        "the perimeter needs a corner every n/4 samples"
    );
    let k = n / 4;
    let mut ring: Vec<[f64; 2]> = Vec::with_capacity(n);
    for j in 0..k {
        ring.push([a * j as f64 / k as f64, 0.0]);
    }
    for j in 0..k {
        ring.push([a, b * j as f64 / k as f64]);
    }
    for j in 0..k {
        ring.push([a * (1.0 - j as f64 / k as f64), b]);
    }
    for j in 0..k {
        ring.push([0.0, b * (1.0 - j as f64 / k as f64)]);
    }

    let mut hole: Vec<[f64; 2]> = Vec::with_capacity(n);
    for j in 0..n {
        let t = TAU * j as f64 / n as f64;
        hole.push([r.mul_add(t.cos(), a * 0.5), r.mul_add(t.sin(), b * 0.5)]);
    }

    let mut v: Vec<[f64; 3]> = Vec::with_capacity(4 * n);
    for p in &ring {
        v.push([p[0], p[1], 0.0]);
    }
    for p in &ring {
        v.push([p[0], p[1], h]);
    }
    for p in &hole {
        v.push([p[0], p[1], 0.0]);
    }
    for p in &hole {
        v.push([p[0], p[1], h]);
    }
    let nn = n as u32;
    let (bp, tp, bc, tc) = (0, nn, 2 * nn, 3 * nn);

    let mut i = Vec::new();
    for j in 0..nn {
        let j1 = (j + 1) % nn;
        quad(&mut i, bp + j, bp + j1, tp + j1, tp + j); // outer wall
        quad(&mut i, tp + j, tp + j1, tc + j1, tc + j); // top face
        quad(&mut i, bp + j, bc + j, bc + j1, bp + j1); // bottom face
        quad(&mut i, bc + j, tc + j, tc + j1, bc + j1); // bore
    }
    (v, i)
}

/// A prism whose `(a, b)` corner is replaced by a quarter round tangent to
/// both walls: the fillet case, in its coarsest honest form.
fn filleted_block(a: f64, b: f64, h: f64, r: f64, arc: usize) -> (Vec<[f64; 3]>, Vec<u32>) {
    let mut profile: Vec<[f64; 2]> = vec![[0.0, 0.0], [a, 0.0]];
    for j in 0..=arc {
        let t = core::f64::consts::FRAC_PI_2 * j as f64 / arc as f64;
        profile.push([r.mul_add(t.cos(), a - r), r.mul_add(t.sin(), b - r)]);
    }
    profile.push([0.0, b]);

    let n = profile.len() as u32;
    let mut v: Vec<[f64; 3]> = Vec::with_capacity(2 * profile.len());
    for p in &profile {
        v.push([p[0], p[1], 0.0]);
    }
    for p in &profile {
        v.push([p[0], p[1], h]);
    }

    let mut i = Vec::new();
    for j in 0..n {
        let j1 = (j + 1) % n;
        quad(&mut i, j, j1, n + j1, n + j);
    }
    for j in 1..n - 1 {
        i.extend_from_slice(&[0, j + 1, j]); // bottom cap, -z
        i.extend_from_slice(&[n, n + j, n + j + 1]); // top cap, +z
    }
    (v, i)
}

fn kinds(seg: &Segmentation) -> Vec<PatchKind> {
    seg.patches.iter().map(|p| p.kind).collect()
}

#[test]
fn box_recovers_twelve_lines_and_eight_corners() {
    let (v, i) = box_mesh(20.0, 14.0, 8.0);
    let (seg, topo) = run(&v, &i, &SegmentOptions::default());

    assert_eq!(seg.patches.len(), 6, "kinds {:?}", kinds(&seg));
    assert_eq!(topo.edges.len(), 12);
    assert_eq!(topo.vertices.len(), 8);
    assert_eq!(topo.summary.analytic_edges, 12);
    assert_eq!(topo.summary.tangent_edges, 0);
    assert_eq!(topo.summary.vertices_refined, 8);
    assert!(
        topo.edges
            .iter()
            .all(|e| matches!(e.curve, Curve::Line { .. }) && e.source == EdgeSource::Analytic)
    );
    assert!(
        topo.summary.max_edge_deviation < 1e-9,
        "deviation {}",
        topo.summary.max_edge_deviation
    );
    assert_eq!(topo.summary.patches_open, 0);
    assert_eq!(topo.summary.patches_closed, 6);
    assert!(topo.patch_loops.iter().all(|p| p.loops.len() == 1));
}

#[test]
fn capped_cylinder_recovers_two_full_circles() {
    let (v, i) = cylinder_mesh(6.0, 10.0, 24);
    let (seg, topo) = run(&v, &i, &SegmentOptions::default());

    assert_eq!(seg.patches.len(), 3, "kinds {:?}", kinds(&seg));
    assert_eq!(topo.edges.len(), 2);
    assert!(topo.vertices.is_empty());
    assert_eq!(topo.summary.patches_closed, 3);
    assert_eq!(topo.summary.patches_open, 0);
    for e in &topo.edges {
        assert!(e.vertices.is_none(), "a rim edge carries no vertex");
        assert_eq!(e.source, EdgeSource::Analytic);
        match e.curve {
            Curve::Circle {
                radius,
                start_angle,
                end_angle,
                ..
            } => {
                assert!((radius - 6.0).abs() < 1e-6, "radius {radius}");
                assert!((end_angle - start_angle - TAU).abs() < 1e-12);
            }
            ref other => panic!("expected a full circle, got {other:?}"),
        }
    }
    // The bore patch owns both rims; each cap owns one.
    let mut counts: Vec<usize> = topo.patch_loops.iter().map(|p| p.loops.len()).collect();
    counts.sort_unstable();
    assert_eq!(counts, vec![1, 1, 2]);
}

#[test]
fn through_hole_gives_each_face_an_inner_loop() {
    let (v, i) = holed_box(24.0, 24.0, 8.0, 5.0, 24);
    let (seg, topo) = run(&v, &i, &SegmentOptions::default());

    assert_eq!(seg.patches.len(), 7, "kinds {:?}", kinds(&seg));
    assert_eq!(topo.summary.patches_open, 0, "loops {:?}", topo.patch_loops);

    let bore = seg
        .patches
        .iter()
        .position(|p| p.kind == PatchKind::Cylinder)
        .expect("the bore is recognised as a cylinder");
    let bore_loops = &topo.patch_loops[bore];
    assert_eq!(bore_loops.loops.len(), 2, "the bore closes with two rims");
    assert!(bore_loops.loops.iter().all(|l| l.closed));

    let rings: Vec<_> = topo.edges.iter().filter(|e| e.vertices.is_none()).collect();
    assert_eq!(rings.len(), 2, "one rim at each end of the bore");
    assert!(
        rings
            .iter()
            .all(|e| matches!(e.curve, Curve::Circle { .. }))
    );

    // The two faces the hole passes through each carry the outer wall loop
    // plus one inner loop; the four side walls carry one loop each.
    let mut counts: Vec<usize> = topo.patch_loops.iter().map(|p| p.loops.len()).collect();
    counts.sort_unstable();
    assert_eq!(counts, vec![1, 1, 1, 1, 2, 2, 2]);
    assert_eq!(topo.vertices.len(), 8, "the block still has eight corners");
}

#[test]
fn fillet_edges_are_tangent_and_still_close() {
    let (v, i) = filleted_block(20.0, 20.0, 10.0, 5.0, 3);
    let (seg, topo) = run(&v, &i, &SegmentOptions::default());

    assert_eq!(seg.patches.len(), 7, "kinds {:?}", kinds(&seg));
    assert_eq!(
        topo.summary.tangent_edges,
        2,
        "the fillet runs out into two walls; edges {:?}",
        topo.edges
            .iter()
            .map(|e| (e.patches, e.tangent, e.source))
            .collect::<Vec<_>>()
    );
    for e in topo.edges.iter().filter(|e| e.tangent) {
        assert_eq!(e.source, EdgeSource::Tangent);
        assert!(matches!(e.curve, Curve::Polyline { .. }));
    }
    assert_eq!(topo.summary.patches_open, 0, "loops {:?}", topo.patch_loops);

    let fillet = seg
        .patches
        .iter()
        .position(|p| p.kind == PatchKind::Cylinder)
        .expect("the round is recognised as a cylinder");
    assert!(topo.patch_loops[fillet].loops.iter().all(|l| l.closed));

    // The round meets each cap in a quarter circle: the arc trimming has to
    // pick the 90 degree span the chain is on, never its 270 degree complement.
    let arcs: Vec<f64> = topo
        .edges
        .iter()
        .filter_map(|e| match e.curve {
            Curve::Circle {
                start_angle,
                end_angle,
                radius,
                ..
            } if (radius - 5.0).abs() < 1e-6 => Some(end_angle - start_angle),
            _ => None,
        })
        .collect();
    assert_eq!(arcs.len(), 2, "one arc on each cap");
    for sweep in arcs {
        assert!(
            (sweep - core::f64::consts::FRAC_PI_2).abs() < 1e-9,
            "sweep {sweep}"
        );
    }
}

#[test]
fn options_are_validated() {
    let (v, i) = box_mesh(10.0, 10.0, 10.0);
    let mesh = MeshData::from_triangles(&v, &i).unwrap();
    let seg = segment(&mesh, &SegmentOptions::default()).unwrap();
    let bad = TopologyOptions {
        tangent_angle_deg: -1.0,
        ..TopologyOptions::default()
    };
    assert!(recover(&mesh, &seg, &bad).is_err());
}
