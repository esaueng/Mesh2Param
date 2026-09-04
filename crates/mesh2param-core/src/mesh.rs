//! Mesh input: bytes in, a triangle mesh plus its cheap statistics out.
//!
//! Nothing here touches the filesystem. Callers (CLI, worker, WASM binding)
//! own the bytes; this crate only ever sees a slice.

use std::collections::HashMap;

use remus_io::ImportLimits;
use remus_math::vec::Point3;
use remus_operations::tessellate::TriangleMesh;
use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};

/// Mesh container formats the core can be asked to read.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MeshFormat {
    /// Binary or ASCII STL. The only format wired up in Phase 1.
    Stl,
    /// 3D Manufacturing Format.
    ThreeMf,
    /// Wavefront OBJ.
    Obj,
    /// Polygon File Format.
    Ply,
}

/// Axis-aligned bounding box of a mesh, in the mesh's own units.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Bbox {
    /// Lower corner.
    pub min: [f64; 3],
    /// Upper corner.
    pub max: [f64; 3],
}

impl Bbox {
    /// Longest edge of the box. Zero for an empty or degenerate mesh.
    #[must_use]
    pub fn extent(&self) -> f64 {
        (0..3).fold(0.0_f64, |acc, i| acc.max(self.max[i] - self.min[i]))
    }

    /// Space diagonal of the box. Zero for an empty or degenerate mesh.
    ///
    /// This is the crate's one scale reference: every tolerance that has to be
    /// expressed as a fraction of "how big is this part" is a fraction of this.
    #[must_use]
    pub fn diagonal(&self) -> f64 {
        let d = [
            self.max[0] - self.min[0],
            self.max[1] - self.min[1],
            self.max[2] - self.min[2],
        ];
        d[0].mul_add(d[0], d[1].mul_add(d[1], d[2] * d[2])).sqrt()
    }
}

/// A parsed triangle mesh plus the statistics every downstream tier needs.
#[derive(Debug, Clone)]
pub struct MeshData {
    /// Triangle count.
    pub triangles: usize,
    /// Axis-aligned bounds.
    pub bbox: Bbox,
    pub(crate) mesh: TriangleMesh,
}

impl MeshData {
    /// The underlying kernel triangle mesh.
    #[must_use]
    pub const fn triangle_mesh(&self) -> &TriangleMesh {
        &self.mesh
    }

    /// Build a mesh from a raw triangle list.
    ///
    /// The soup is taken as given: nothing is welded, reordered or repaired
    /// here. Used by tests and by callers that already hold triangles rather
    /// than file bytes.
    ///
    /// # Errors
    ///
    /// [`CoreError::Parse`] when `indices` is not a whole number of triangles
    /// or references a vertex that does not exist.
    pub fn from_triangles(positions: &[[f64; 3]], indices: &[u32]) -> Result<Self> {
        if !indices.len().is_multiple_of(3) {
            return Err(CoreError::Parse(format!(
                "{} indices is not a whole number of triangles",
                indices.len()
            )));
        }
        if let Some(bad) = indices.iter().find(|&&i| i as usize >= positions.len()) {
            return Err(CoreError::Parse(format!(
                "index {bad} is out of range for {} vertices",
                positions.len()
            )));
        }
        let points: Vec<Point3> = positions
            .iter()
            .map(|p| Point3::new(p[0], p[1], p[2]))
            .collect();
        let bbox = bbox_of(&points);
        Ok(Self {
            triangles: indices.len() / 3,
            bbox,
            mesh: TriangleMesh {
                positions: points,
                normals: Vec::new(),
                indices: indices.to_vec(),
            },
        })
    }

    /// Weld the triangle soup into a connected mesh: shared vertices merged,
    /// degenerate triangles dropped, per-triangle neighbours resolved.
    ///
    /// STL carries no connectivity at all — every triangle repeats its three
    /// corners — so every stage that reasons about adjacency (segmentation
    /// above all) has to reconstruct it first. The weld tolerance is
    /// `1e-6 x bbox diagonal`: tight enough that it can only ever merge corners
    /// that were meant to be the same point, loose enough to absorb the decimal
    /// rounding of an ASCII STL.
    ///
    /// # Errors
    ///
    /// [`CoreError::Validation`] when the mesh has no triangles, a degenerate
    /// bounding box, or nothing left after degenerate triangles are dropped.
    pub fn welded(&self) -> Result<WeldedMesh> {
        weld_mesh(&self.mesh, self.bbox.diagonal())
    }
}

/// A welded triangle mesh: unique vertices, valid triangles, adjacency.
///
/// Positions are plain arrays rather than a vector type so that this stays a
/// description of the mesh, not of anyone's maths library.
#[derive(Debug, Clone)]
pub struct WeldedMesh {
    /// Unique vertex positions.
    pub positions: Vec<[f64; 3]>,
    /// Triangles as welded vertex indices. Degenerate ones are already gone.
    pub triangles: Vec<[u32; 3]>,
    /// Neighbouring triangle indices per triangle, ascending, deduplicated.
    ///
    /// Sorted on purpose: downstream traversal order decides floating-point
    /// summation order, and a hash-order-dependent result would make every
    /// committed baseline unreproducible.
    pub neighbours: Vec<Vec<u32>>,
    /// Edges with more than two owning triangles. Linked pairwise anyway.
    pub non_manifold_edges: usize,
    /// Triangles dropped as degenerate (repeated corner, or zero area).
    pub dropped_triangles: usize,
}

/// Weld vertices within `tol` on a uniform hash grid.
///
/// Returns the welded positions and a map from input index to welded index.
fn weld_points(points: &[Point3], tol: f64) -> (Vec<[f64; 3]>, Vec<u32>) {
    let cell = if tol > 0.0 { tol } else { 1.0 };
    let key = |p: &[f64; 3]| -> (i64, i64, i64) {
        (
            (p[0] / cell).floor() as i64,
            (p[1] / cell).floor() as i64,
            (p[2] / cell).floor() as i64,
        )
    };
    let mut grid: HashMap<(i64, i64, i64), Vec<u32>> = HashMap::new();
    let mut out: Vec<[f64; 3]> = Vec::new();
    let mut map: Vec<u32> = Vec::with_capacity(points.len());
    let tol2 = tol * tol;
    for point in points {
        let p = point.0;
        let (kx, ky, kz) = key(&p);
        let mut found: Option<u32> = None;
        'search: for dx in -1_i64..=1 {
            for dy in -1_i64..=1 {
                for dz in -1_i64..=1 {
                    let Some(bucket) = grid.get(&(kx + dx, ky + dy, kz + dz)) else {
                        continue;
                    };
                    for &idx in bucket {
                        let Some(q) = out.get(idx as usize) else {
                            continue;
                        };
                        let d = [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
                        if d[0].mul_add(d[0], d[1].mul_add(d[1], d[2] * d[2])) <= tol2 {
                            found = Some(idx);
                            break 'search;
                        }
                    }
                }
            }
        }
        let idx = if let Some(i) = found {
            i
        } else {
            let i = out.len() as u32;
            out.push(p);
            grid.entry((kx, ky, kz)).or_default().push(i);
            i
        };
        map.push(idx);
    }
    (out, map)
}

fn weld_mesh(mesh: &TriangleMesh, bbox_diagonal: f64) -> Result<WeldedMesh> {
    if mesh.indices.len() < 3 {
        return Err(CoreError::Validation("mesh has no triangles".into()));
    }
    if !bbox_diagonal.is_finite() || bbox_diagonal <= 0.0 {
        return Err(CoreError::Validation(
            "mesh bounding box is degenerate".into(),
        ));
    }
    let (positions, map) = weld_points(&mesh.positions, 1e-6 * bbox_diagonal);

    let raw = mesh.indices.len() / 3;
    let mut triangles: Vec<[u32; 3]> = Vec::with_capacity(raw);
    for tri in mesh.indices.chunks_exact(3) {
        let (a, b, c) = (
            *map.get(tri[0] as usize).unwrap_or(&0),
            *map.get(tri[1] as usize).unwrap_or(&0),
            *map.get(tri[2] as usize).unwrap_or(&0),
        );
        if a == b || b == c || a == c {
            continue;
        }
        let (Some(pa), Some(pb), Some(pc)) = (
            positions.get(a as usize),
            positions.get(b as usize),
            positions.get(c as usize),
        ) else {
            continue;
        };
        let u = [pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]];
        let v = [pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]];
        let cross = [
            u[1].mul_add(v[2], -(u[2] * v[1])),
            u[2].mul_add(v[0], -(u[0] * v[2])),
            u[0].mul_add(v[1], -(u[1] * v[0])),
        ];
        let len2 = cross[0].mul_add(cross[0], cross[1].mul_add(cross[1], cross[2] * cross[2]));
        if !len2.is_finite() || len2 <= 0.0 {
            continue;
        }
        triangles.push([a, b, c]);
    }
    if triangles.is_empty() {
        return Err(CoreError::Validation(
            "all triangles degenerate after welding".into(),
        ));
    }

    let mut edges: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    for (fi, t) in triangles.iter().enumerate() {
        for k in 0..3 {
            let (a, b) = (t[k], t[(k + 1) % 3]);
            let e = if a < b { (a, b) } else { (b, a) };
            edges.entry(e).or_default().push(fi as u32);
        }
    }
    let mut neighbours = vec![Vec::new(); triangles.len()];
    let mut non_manifold_edges = 0_usize;
    for owners in edges.values() {
        if owners.len() > 2 {
            non_manifold_edges += 1;
        }
        for (i, &fi) in owners.iter().enumerate() {
            for &fj in owners.iter().skip(i + 1) {
                neighbours[fi as usize].push(fj);
                neighbours[fj as usize].push(fi);
            }
        }
    }
    for list in &mut neighbours {
        list.sort_unstable();
        list.dedup();
    }

    Ok(WeldedMesh {
        positions,
        dropped_triangles: raw - triangles.len(),
        triangles,
        neighbours,
        non_manifold_edges,
    })
}

fn bbox_of(positions: &[Point3]) -> Bbox {
    let mut min = [f64::INFINITY; 3];
    let mut max = [f64::NEG_INFINITY; 3];
    for p in positions {
        for axis in 0..3 {
            min[axis] = min[axis].min(p.0[axis]);
            max[axis] = max[axis].max(p.0[axis]);
        }
    }
    if positions.is_empty() {
        return Bbox {
            min: [0.0; 3],
            max: [0.0; 3],
        };
    }
    Bbox { min, max }
}

/// Parse mesh bytes into a [`MeshData`].
///
/// Only [`MeshFormat::Stl`] is implemented in Phase 1; the other variants
/// return [`CoreError::Unsupported`] so callers can already name the format
/// they hold without the core silently guessing.
///
/// # Errors
///
/// - [`CoreError::Parse`] when the bytes are malformed or exceed the kernel's
///   hostile-input limits.
/// - [`CoreError::Unsupported`] for a format that is not wired up yet.
pub fn load_mesh(bytes: &[u8], format: MeshFormat) -> Result<MeshData> {
    match format {
        MeshFormat::Stl => {
            let mesh = remus_io::stl::reader::read_stl_with_limits(bytes, ImportLimits::default())
                .map_err(|e| CoreError::Parse(e.to_string()))?;
            Ok(MeshData {
                triangles: mesh.indices.len() / 3,
                bbox: bbox_of(&mesh.positions),
                mesh,
            })
        }
        other => Err(CoreError::Unsupported(other)),
    }
}
