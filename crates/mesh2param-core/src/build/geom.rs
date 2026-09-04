//! Mesh-side geometry the face builder and the verifier both need.
//!
//! Two things live here that nothing upstream provides: an **outward
//! orientation** for the welded mesh (segmentation never needed one, face
//! construction cannot do without it) and a uniform-grid point-to-triangle
//! query used to measure the result against the source in both directions.

use std::collections::HashMap;

use crate::mesh::WeldedMesh;
use crate::segment::linalg::V3;

/// The welded mesh with a consistent outward winding and its per-triangle
/// frame.
///
/// Orientation is decided once, globally, from the signed volume of the mesh
/// as wound: a closed mesh wound outward encloses a positive volume by the
/// divergence theorem. A mesh whose winding is not globally consistent has no
/// outward direction to find, and nothing downstream can invent one.
pub(super) struct MeshGeom {
    /// Welded vertex positions.
    pub points: Vec<V3>,
    /// Triangles, wound outward.
    pub triangles: Vec<[u32; 3]>,
    /// Unit outward normal per triangle.
    pub normals: Vec<V3>,
    /// Centroid per triangle.
    pub centroids: Vec<V3>,
    /// Area per triangle.
    pub areas: Vec<f64>,
    /// Enclosed volume, positive.
    pub volume: f64,
}

impl MeshGeom {
    pub(super) fn new(welded: &WeldedMesh) -> Self {
        let points: Vec<V3> = welded.positions.iter().map(|p| V3::from_arr(*p)).collect();
        let mut triangles = welded.triangles.clone();
        let signed = signed_volume(&points, &triangles);
        if signed < 0.0 {
            for t in &mut triangles {
                t.swap(1, 2);
            }
        }

        let mut normals = Vec::with_capacity(triangles.len());
        let mut centroids = Vec::with_capacity(triangles.len());
        let mut areas = Vec::with_capacity(triangles.len());
        for t in &triangles {
            let (a, b, c) = corners(&points, *t);
            let cross = b.sub(a).cross(c.sub(a));
            let len = cross.norm();
            areas.push(0.5 * len);
            normals.push(cross.unit().unwrap_or(V3::new(0.0, 0.0, 1.0)));
            centroids.push(a.add(b).add(c).mul(1.0 / 3.0));
        }

        Self {
            volume: signed.abs(),
            points,
            triangles,
            normals,
            centroids,
            areas,
        }
    }

    /// The directed half-edge `(u, v)` to the triangle that owns it.
    ///
    /// With an outward winding a triangle lies to the *left* of each of its
    /// own directed half-edges, so this map is what says which of the two
    /// patches along a boundary chain traverses it counter-clockwise.
    pub(super) fn half_edge_owner(&self) -> HashMap<(u32, u32), u32> {
        let mut out = HashMap::with_capacity(self.triangles.len() * 3);
        for (fi, t) in self.triangles.iter().enumerate() {
            for k in 0..3 {
                out.entry((t[k], t[(k + 1) % 3])).or_insert(fi as u32);
            }
        }
        out
    }
}

fn corners(points: &[V3], t: [u32; 3]) -> (V3, V3, V3) {
    let get = |i: u32| points.get(i as usize).copied().unwrap_or(V3::ZERO);
    (get(t[0]), get(t[1]), get(t[2]))
}

/// Signed volume by the divergence theorem: `sum a . (b x c) / 6`.
fn signed_volume(points: &[V3], triangles: &[[u32; 3]]) -> f64 {
    let mut total = 0.0;
    for t in triangles {
        let (a, b, c) = corners(points, *t);
        total += a.dot(b.cross(c));
    }
    total / 6.0
}

/// Signed volume of a raw triangle list, same convention.
pub(super) fn mesh_volume(positions: &[V3], indices: &[u32]) -> f64 {
    let mut total = 0.0;
    for tri in indices.chunks_exact(3) {
        let get = |i: u32| positions.get(i as usize).copied().unwrap_or(V3::ZERO);
        let (a, b, c) = (get(tri[0]), get(tri[1]), get(tri[2]));
        total += a.dot(b.cross(c));
    }
    (total / 6.0).abs()
}

/// A uniform grid over a triangle soup, for nearest-surface queries.
///
/// No external crate: a hash grid keyed on integer cells, searched in
/// expanding shells and stopped as soon as the shell's own lower bound
/// exceeds the best distance found so far.
pub(super) struct TriGrid {
    tris: Vec<[V3; 3]>,
    cells: HashMap<(i64, i64, i64), Vec<u32>>,
    cell: f64,
}

impl TriGrid {
    /// Build a grid whose cells hold a handful of triangles each.
    pub(super) fn new(tris: Vec<[V3; 3]>, extent: f64) -> Self {
        let n = tris.len().max(1);
        // Roughly one triangle per cell along each axis: the cube root of the
        // count spreads a surface mesh over a shell of cells, which is what
        // the expanding-shell search wants.
        let per_axis = (n as f64).cbrt().max(1.0);
        let cell = if extent.is_finite() && extent > 0.0 {
            (extent / per_axis).max(f64::MIN_POSITIVE)
        } else {
            1.0
        };
        let mut cells: HashMap<(i64, i64, i64), Vec<u32>> = HashMap::new();
        for (i, t) in tris.iter().enumerate() {
            let centroid = t[0].add(t[1]).add(t[2]).mul(1.0 / 3.0);
            cells.entry(key(centroid, cell)).or_default().push(i as u32);
        }
        Self { tris, cells, cell }
    }

    pub(super) fn is_empty(&self) -> bool {
        self.tris.is_empty()
    }

    /// Distance from `p` to the nearest triangle, or `None` when empty.
    pub(super) fn distance(&self, p: V3) -> Option<f64> {
        if self.tris.is_empty() {
            return None;
        }
        let (kx, ky, kz) = key(p, self.cell);
        let mut best = f64::INFINITY;
        // A triangle can reach into a cell its centroid does not sit in, so a
        // shell whose inner face is already further than `best` is not proof
        // on its own; two extra shells past the first hit is the margin.
        let mut slack = 0_i64;
        let mut r = 0_i64;
        loop {
            let mut touched = false;
            for dx in -r..=r {
                for dy in -r..=r {
                    for dz in -r..=r {
                        if dx.abs() != r && dy.abs() != r && dz.abs() != r {
                            continue;
                        }
                        let Some(bucket) = self.cells.get(&(kx + dx, ky + dy, kz + dz)) else {
                            continue;
                        };
                        touched = true;
                        for &i in bucket {
                            if let Some(t) = self.tris.get(i as usize) {
                                best = best.min(point_triangle_distance(p, t));
                            }
                        }
                    }
                }
            }
            let _ = touched;
            if best.is_finite() {
                let reach = (r as f64) * self.cell;
                if reach > best {
                    slack += 1;
                    if slack > 2 {
                        break;
                    }
                }
            }
            r += 1;
            // The grid is finite; 4096 shells past the query point is far
            // beyond any real mesh and stops a pathological input spinning.
            if r > 4096 {
                break;
            }
        }
        best.is_finite().then_some(best)
    }
}

fn key(p: V3, cell: f64) -> (i64, i64, i64) {
    (
        (p.x / cell).floor() as i64,
        (p.y / cell).floor() as i64,
        (p.z / cell).floor() as i64,
    )
}

/// Closest distance from a point to a triangle (Ericson, region tables).
pub(super) fn point_triangle_distance(p: V3, t: &[V3; 3]) -> f64 {
    let (a, b, c) = (t[0], t[1], t[2]);
    let ab = b.sub(a);
    let ac = c.sub(a);
    let ap = p.sub(a);
    let d1 = ab.dot(ap);
    let d2 = ac.dot(ap);
    if d1 <= 0.0 && d2 <= 0.0 {
        return ap.norm();
    }
    let bp = p.sub(b);
    let d3 = ab.dot(bp);
    let d4 = ac.dot(bp);
    if d3 >= 0.0 && d4 <= d3 {
        return bp.norm();
    }
    let vc = d1.mul_add(d4, -(d3 * d2));
    if vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0 {
        let denom = d1 - d3;
        let v = if denom.abs() > 0.0 { d1 / denom } else { 0.0 };
        return p.sub(a.add(ab.mul(v))).norm();
    }
    let cp = p.sub(c);
    let d5 = ab.dot(cp);
    let d6 = ac.dot(cp);
    if d6 >= 0.0 && d5 <= d6 {
        return cp.norm();
    }
    let vb = d5.mul_add(d2, -(d1 * d6));
    if vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0 {
        let denom = d2 - d6;
        let w = if denom.abs() > 0.0 { d2 / denom } else { 0.0 };
        return p.sub(a.add(ac.mul(w))).norm();
    }
    let va = d3.mul_add(d6, -(d5 * d4));
    if va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0 {
        let denom = (d4 - d3) + (d5 - d6);
        let w = if denom.abs() > 0.0 {
            (d4 - d3) / denom
        } else {
            0.0
        };
        return p.sub(b.add(c.sub(b).mul(w))).norm();
    }
    let denom = va + vb + vc;
    if denom.abs() <= 0.0 {
        return ap.norm();
    }
    let v = vb / denom;
    let w = vc / denom;
    p.sub(a.add(ab.mul(v)).add(ac.mul(w))).norm()
}

/// The `q`-quantile of a sample set, nearest-rank. `samples` is consumed
/// sorted in place.
pub(super) fn quantile(samples: &mut [f64], q: f64) -> f64 {
    if samples.is_empty() {
        return 0.0;
    }
    samples.sort_by(f64::total_cmp);
    let rank = (q * samples.len() as f64).ceil() as usize;
    let idx = rank.clamp(1, samples.len()) - 1;
    samples.get(idx).copied().unwrap_or(0.0)
}

/// Half the Newell normal of a closed 3D polygon: its direction is the
/// polygon's winding and its length is the enclosed area.
///
/// A face's loops are ranked and classified with this — the length says which
/// loop is the biggest, the direction says which of them bounds material.
pub(super) fn polygon_normal(points: &[V3]) -> V3 {
    if points.len() < 3 {
        return V3::ZERO;
    }
    let mut n = V3::ZERO;
    for i in 0..points.len() {
        let a = points[i];
        let b = points[(i + 1) % points.len()];
        n = n.add(a.cross(b));
    }
    n.mul(0.5)
}
