//! Welded triangle mesh: vertex merge, per-face geometry, edge -> face adjacency.

use std::collections::HashMap;

use crate::linalg::V3;

pub struct Face {
    pub v: [u32; 3],
    pub normal: V3,
    pub area: f64,
    pub centroid: V3,
}

pub struct Mesh {
    pub verts: Vec<V3>,
    pub faces: Vec<Face>,
    /// Neighbouring face indices per face, one entry per shared edge.
    pub neighbours: Vec<Vec<usize>>,
    pub bbox_diag: f64,
    pub raw_triangles: usize,
    pub non_manifold_edges: usize,
}

/// Weld vertices within `tol` using a uniform hash grid; returns the welded
/// positions and a map from input index to welded index.
fn weld(points: &[V3], tol: f64) -> (Vec<V3>, Vec<u32>) {
    let cell = if tol > 0.0 { tol } else { 1.0 };
    let key = |p: V3| -> (i64, i64, i64) {
        #[allow(clippy::cast_possible_truncation)]
        (
            (p.x / cell).floor() as i64,
            (p.y / cell).floor() as i64,
            (p.z / cell).floor() as i64,
        )
    };
    let mut grid: HashMap<(i64, i64, i64), Vec<u32>> = HashMap::new();
    let mut out: Vec<V3> = Vec::new();
    let mut map: Vec<u32> = Vec::with_capacity(points.len());
    let tol2 = tol * tol;
    for &p in points {
        let (kx, ky, kz) = key(p);
        let mut found: Option<u32> = None;
        'search: for dx in -1_i64..=1 {
            for dy in -1_i64..=1 {
                for dz in -1_i64..=1 {
                    if let Some(bucket) = grid.get(&(kx + dx, ky + dy, kz + dz)) {
                        for &idx in bucket {
                            let q = out[idx as usize];
                            let d = p.sub(q);
                            if d.dot(d) <= tol2 {
                                found = Some(idx);
                                break 'search;
                            }
                        }
                    }
                }
            }
        }
        let idx = match found {
            Some(i) => i,
            None => {
                #[allow(clippy::cast_possible_truncation)]
                let i = out.len() as u32;
                out.push(p);
                grid.entry((kx, ky, kz)).or_default().push(i);
                i
            }
        };
        map.push(idx);
    }
    (out, map)
}

impl Mesh {
    /// Build a welded mesh from raw STL triangle soup.
    ///
    /// Degenerate triangles (repeated welded vertex, or zero area) are dropped.
    pub fn build(positions: &[V3], indices: &[u32]) -> Result<Self, String> {
        if indices.len() < 3 {
            return Err("mesh has no triangles".into());
        }
        let mut lo = V3::new(f64::MAX, f64::MAX, f64::MAX);
        let mut hi = V3::new(f64::MIN, f64::MIN, f64::MIN);
        for p in positions {
            lo = V3::new(lo.x.min(p.x), lo.y.min(p.y), lo.z.min(p.z));
            hi = V3::new(hi.x.max(p.x), hi.y.max(p.y), hi.z.max(p.z));
        }
        let bbox_diag = hi.sub(lo).norm();
        if !bbox_diag.is_finite() || bbox_diag <= 0.0 {
            return Err("mesh bounding box is degenerate".into());
        }
        let (verts, map) = weld(positions, 1e-6 * bbox_diag);

        let raw_triangles = indices.len() / 3;
        let mut faces: Vec<Face> = Vec::with_capacity(raw_triangles);
        for tri in indices.chunks_exact(3) {
            let (a, b, c) = (
                *map.get(tri[0] as usize).unwrap_or(&0),
                *map.get(tri[1] as usize).unwrap_or(&0),
                *map.get(tri[2] as usize).unwrap_or(&0),
            );
            if a == b || b == c || a == c {
                continue;
            }
            let (pa, pb, pc) = (verts[a as usize], verts[b as usize], verts[c as usize]);
            let cross = pb.sub(pa).cross(pc.sub(pa));
            let area = 0.5 * cross.norm();
            let Some(normal) = cross.unit() else { continue };
            if area <= 0.0 {
                continue;
            }
            faces.push(Face {
                v: [a, b, c],
                normal,
                area,
                centroid: pa.add(pb).add(pc).mul(1.0 / 3.0),
            });
        }
        if faces.is_empty() {
            return Err("all triangles degenerate after welding".into());
        }

        let mut edges: HashMap<(u32, u32), Vec<usize>> = HashMap::new();
        for (fi, f) in faces.iter().enumerate() {
            for k in 0..3 {
                let (a, b) = (f.v[k], f.v[(k + 1) % 3]);
                let e = if a < b { (a, b) } else { (b, a) };
                edges.entry(e).or_default().push(fi);
            }
        }
        let mut neighbours = vec![Vec::new(); faces.len()];
        let mut non_manifold_edges = 0_usize;
        for owners in edges.values() {
            if owners.len() > 2 {
                non_manifold_edges += 1;
            }
            for (i, &fi) in owners.iter().enumerate() {
                for &fj in owners.iter().skip(i + 1) {
                    neighbours[fi].push(fj);
                    neighbours[fj].push(fi);
                }
            }
        }

        Ok(Self {
            verts,
            faces,
            neighbours,
            bbox_diag,
            raw_triangles,
            non_manifold_edges,
        })
    }
}
