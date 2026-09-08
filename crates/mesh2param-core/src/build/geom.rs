//! Mesh-side geometry the face builder and the verifier both need.
//!
//! Two things live here that nothing upstream provides: an **outward
//! orientation** for the welded mesh (segmentation never needed one, face
//! construction cannot do without it) and a point-to-triangle nearest-distance
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
    /// Total surface area.
    pub surface_area: f64,
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
            surface_area: areas.iter().sum(),
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

/// A bounding-volume hierarchy over a triangle soup, for nearest-surface
/// queries.
///
/// No external crate: a median-split BVH over triangle centroids, queried
/// depth-first with the nearer child taken first and any node whose box is
/// already further than the best distance found pruned outright.
///
/// A uniform grid was tried here first and is the wrong structure for this
/// input. Verification queries a *reconstructed* solid's tessellation, where
/// triangle size spans several orders of magnitude — a large planar face is
/// two triangles, a filleted one thousands — and where a single face built on
/// a grazing surface can sit kilometres from a hundred-millimetre part. No one
/// cell size serves that: sized for the small triangles the large ones smear
/// across thousands of cells, sized for the large ones each cell holds
/// thousands of small ones, and an expanding-shell search starting from an
/// outlier walks the whole lattice. A hierarchy adapts to both without a
/// tuning constant, and its answer is the exact nearest distance rather than
/// one that depends on how many shells the search was willing to spend.
pub(super) struct TriTree {
    /// Triangles, reordered during the build so each leaf owns a contiguous
    /// run of them.
    tris: Vec<[V3; 3]>,
    nodes: Vec<Node>,
}

/// Triangles per leaf. Small enough that a leaf scan is cheap, large enough
/// that the tree stays shallow.
const LEAF_TRIS: usize = 8;

struct Node {
    min: [f64; 3],
    max: [f64; 3],
    /// First triangle for a leaf, first child for an internal node; an
    /// internal node's two children are adjacent.
    start: u32,
    /// Triangles in the leaf, or zero for an internal node.
    count: u32,
}

impl Node {
    /// Distance from `p` to the node's box, zero inside it. A lower bound on
    /// the distance to every triangle underneath it, which is what makes the
    /// pruning sound.
    fn distance(&self, p: V3) -> f64 {
        let at = p.arr();
        let mut total = 0.0;
        for axis in 0..3 {
            let lo = self.min.get(axis).copied().unwrap_or(0.0);
            let hi = self.max.get(axis).copied().unwrap_or(0.0);
            let v = at.get(axis).copied().unwrap_or(0.0);
            let d = (lo - v).max(v - hi).max(0.0);
            if d.is_finite() {
                total += d * d;
            }
        }
        total.sqrt()
    }
}

impl TriTree {
    /// Build the hierarchy. Linear in the triangle count up to the sorting.
    pub(super) fn new(mut tris: Vec<[V3; 3]>) -> Self {
        let mut nodes = Vec::new();
        if !tris.is_empty() {
            let len = tris.len();
            nodes.push(Node {
                min: [0.0; 3],
                max: [0.0; 3],
                start: 0,
                count: 0,
            });
            build(&mut tris, &mut nodes, 0, 0, len, 0);
        }
        Self { tris, nodes }
    }

    pub(super) fn is_empty(&self) -> bool {
        self.tris.is_empty()
    }

    /// Distance from `p` to the nearest triangle, or `None` when empty.
    pub(super) fn distance(&self, p: V3) -> Option<f64> {
        let root = self.nodes.first()?;
        let mut best = f64::INFINITY;
        // Depth-first, nearer child first, pruned against `best`. The stack
        // holds each pending node with the box distance it was pushed at, so a
        // node that a later leaf has already beaten is dropped without being
        // opened.
        let mut stack: Vec<(u32, f64)> = vec![(0, root.distance(p))];
        while let Some((index, bound)) = stack.pop() {
            if bound >= best {
                continue;
            }
            let Some(node) = self.nodes.get(index as usize) else {
                continue;
            };
            if node.count > 0 {
                let from = node.start as usize;
                let to = from.saturating_add(node.count as usize);
                if let Some(leaf) = self.tris.get(from..to) {
                    for t in leaf {
                        best = best.min(point_triangle_distance(p, t));
                    }
                }
                continue;
            }
            let left = node.start;
            let right = node.start.saturating_add(1);
            let dl = self
                .nodes
                .get(left as usize)
                .map_or(f64::INFINITY, |n| n.distance(p));
            let dr = self
                .nodes
                .get(right as usize)
                .map_or(f64::INFINITY, |n| n.distance(p));
            // Push the further child first so the nearer one is popped first
            // and gives the tighter `best` to prune the other with.
            if dl <= dr {
                stack.push((right, dr));
                stack.push((left, dl));
            } else {
                stack.push((left, dl));
                stack.push((right, dr));
            }
        }
        best.is_finite().then_some(best)
    }
}

/// Fill node `at` for `tris[from..to]`, recursing into two children unless the
/// range is small enough to be a leaf.
///
/// `depth` only guards against a range the split cannot separate — coincident
/// centroids — which would otherwise recurse forever on one side.
fn build(
    tris: &mut [[V3; 3]],
    nodes: &mut Vec<Node>,
    at: usize,
    from: usize,
    to: usize,
    depth: u32,
) {
    let (min, max) = bounds_of(tris.get(from..to).unwrap_or_default());
    let count = to.saturating_sub(from);
    if count <= LEAF_TRIS || depth >= 64 {
        if let Some(node) = nodes.get_mut(at) {
            node.min = min;
            node.max = max;
            node.start = u32::try_from(from).unwrap_or(u32::MAX);
            node.count = u32::try_from(count).unwrap_or(u32::MAX);
        }
        return;
    }

    // Split at the median centroid along the box's longest axis: it keeps the
    // tree balanced whatever the triangle size distribution, which is the
    // property a uniform grid could not offer here.
    let mut axis = 0;
    let mut widest = f64::NEG_INFINITY;
    for a in 0..3 {
        let w = max.get(a).copied().unwrap_or(0.0) - min.get(a).copied().unwrap_or(0.0);
        if w > widest {
            widest = w;
            axis = a;
        }
    }
    let mid = from + count / 2;
    if let Some(range) = tris.get_mut(from..to) {
        let k = mid - from;
        range.select_nth_unstable_by(k, |a, b| {
            centroid_axis(a, axis).total_cmp(&centroid_axis(b, axis))
        });
    }

    let left = u32::try_from(nodes.len()).unwrap_or(u32::MAX);
    for _ in 0..2 {
        nodes.push(Node {
            min: [0.0; 3],
            max: [0.0; 3],
            start: 0,
            count: 0,
        });
    }
    if let Some(node) = nodes.get_mut(at) {
        node.min = min;
        node.max = max;
        node.start = left;
        node.count = 0;
    }
    build(tris, nodes, left as usize, from, mid, depth + 1);
    build(tris, nodes, left as usize + 1, mid, to, depth + 1);
}

fn centroid_axis(t: &[V3; 3], axis: usize) -> f64 {
    let sum: f64 = t
        .iter()
        .map(|p| p.arr().get(axis).copied().unwrap_or(0.0))
        .sum();
    sum / 3.0
}

/// The axis-aligned box around a run of triangles. An empty run gives a
/// degenerate box at the origin, which no query can be nearer to than to a
/// real one it is competing with, because such a node holds nothing.
fn bounds_of(tris: &[[V3; 3]]) -> ([f64; 3], [f64; 3]) {
    let mut min = [f64::INFINITY; 3];
    let mut max = [f64::NEG_INFINITY; 3];
    for t in tris {
        for p in t {
            for (axis, v) in p.arr().iter().enumerate() {
                if !v.is_finite() {
                    continue;
                }
                if let (Some(lo), Some(hi)) = (min.get_mut(axis), max.get_mut(axis)) {
                    *lo = lo.min(*v);
                    *hi = hi.max(*v);
                }
            }
        }
    }
    for axis in 0..3 {
        if let (Some(lo), Some(hi)) = (min.get_mut(axis), max.get_mut(axis))
            && (!lo.is_finite() || !hi.is_finite())
        {
            *lo = 0.0;
            *hi = 0.0;
        }
    }
    (min, max)
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

#[cfg(test)]
#[allow(clippy::expect_used)]
mod tests {
    use super::{TriTree, point_triangle_distance};
    use crate::segment::linalg::V3;

    /// A deterministic scatter of triangles whose sizes span four orders of
    /// magnitude, plus one sitting kilometres away — the shape of a
    /// reconstructed solid's tessellation, and the case the uniform grid this
    /// replaced could neither bin nor search.
    fn soup() -> Vec<[V3; 3]> {
        let mut out = Vec::new();
        let mut seed = 0x2545_f491_4f6c_dd1d_u64;
        let mut next = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            (seed >> 11) as f64 / (1_u64 << 53) as f64
        };
        for i in 0..400 {
            let scale = if i % 40 == 0 { 30.0 } else { 0.01 };
            let a = V3::new(next() * 100.0, next() * 100.0, next() * 100.0);
            out.push([
                a,
                a.add(V3::new(next() * scale, next() * scale, 0.0)),
                a.add(V3::new(0.0, next() * scale, next() * scale)),
            ]);
        }
        let far = V3::new(-4000.0, 900.0, 12.0);
        out.push([
            far,
            far.add(V3::new(1.0, 0.0, 0.0)),
            far.add(V3::new(0.0, 2.0, 0.0)),
        ]);
        out
    }

    fn brute(p: V3, tris: &[[V3; 3]]) -> f64 {
        tris.iter()
            .map(|t| point_triangle_distance(p, t))
            .fold(f64::INFINITY, f64::min)
    }

    #[test]
    fn tree_matches_brute_force() {
        let tris = soup();
        let tree = TriTree::new(tris.clone());
        let probes = [
            V3::new(50.0, 50.0, 50.0),
            V3::new(0.0, 0.0, 0.0),
            V3::new(-1.0, 120.0, 7.5),
            // Far outside everything: the query must prune to the answer
            // rather than search outward towards it.
            V3::new(-3990.0, 905.0, 12.0),
            V3::new(1e5, -1e5, 1e5),
            V3::new(12.25, 88.5, 3.125),
        ];
        for p in probes {
            let want = brute(p, &tris);
            let got = tree.distance(p).expect("non-empty tree answers");
            assert!(
                (got - want).abs() <= 1e-9 * want.max(1.0),
                "at {p:?}: tree {got} vs brute force {want}"
            );
        }
    }

    #[test]
    fn empty_tree_declines() {
        let tree = TriTree::new(Vec::new());
        assert!(tree.is_empty());
        assert_eq!(tree.distance(V3::new(1.0, 2.0, 3.0)), None);
    }
}
