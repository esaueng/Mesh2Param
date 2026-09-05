//! Measuring the built solid against the mesh it came from.
//!
//! The kernel tessellates the result; the two meshes are then compared in
//! **both** directions, because a one-sided distance cannot see a missing
//! feature. Source samples against the result catch a face that was built in
//! the wrong place; result samples against the source catch a face that was
//! invented where the mesh has nothing.

use remus_topology::Topology as KernelTopology;
use remus_topology::face::FaceId;
use remus_topology::solid::SolidId;
use serde::{Deserialize, Serialize};

use super::geom::{MeshGeom, TriTree, mesh_volume, quantile};
use crate::error::{CoreError, Result};
use crate::segment::linalg::V3;

/// How far the built solid sits from the mesh it was reconstructed from.
///
/// Distances are measured symmetrically: source points against the result's
/// tessellation and the result's tessellation vertices against the source.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Deviation {
    /// 95th percentile of the sampled distances.
    pub p95: f64,
    /// Largest sampled distance.
    pub max: f64,
    /// How many distances were sampled.
    pub samples: usize,
}

/// The result of tessellating and measuring one solid.
pub(super) struct Measured {
    pub deviation: Deviation,
    pub volume: f64,
    /// The tessellation the measurement was taken on, kept so a caller that
    /// wants to draw the result does not pay for a second one.
    pub mesh: ResultMesh,
}

/// A tessellation of the reconstructed solid, for display.
///
/// Positions are `f32` triples because every consumer of this is a renderer:
/// the measurement itself is taken in `f64` before the narrowing.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ResultMesh {
    /// Vertex positions, three floats per vertex.
    pub positions: Vec<f32>,
    /// Triangle corners, three indices per triangle.
    pub indices: Vec<u32>,
}

impl ResultMesh {
    /// Build from `f64` points and a flat index list.
    pub(super) fn new(points: &[V3], indices: &[u32]) -> Self {
        let mut positions = Vec::with_capacity(points.len() * 3);
        for p in points {
            for v in p.arr() {
                positions.push(v as f32);
            }
        }
        Self {
            positions,
            indices: indices.to_vec(),
        }
    }

    /// Whether there is anything to draw.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.positions.is_empty() || self.indices.is_empty()
    }
}

/// Cap on samples taken in each direction, so the stage costs the same on a
/// half-million-triangle mesh as on a fifty-thousand one. A quantile does not
/// get better past a few tens of thousands of points, and the nearest-triangle
/// query is the whole cost of the verify stage.
const MAX_SAMPLES: usize = 40_000;

pub(super) fn measure(
    topo: &KernelTopology,
    solid: SolidId,
    geom: &MeshGeom,
    deflection: f64,
) -> Result<Measured> {
    let tess = guarded(|| remus_operations::tessellate::tessellate_solid(topo, solid, deflection))
        .ok_or_else(|| CoreError::Kernel("tessellate_solid panicked".to_string()))?
        .map_err(|e| CoreError::Kernel(format!("tessellate_solid: {e}")))?;

    let result_points: Vec<V3> = tess
        .positions
        .iter()
        .map(|p| V3::new(p.x(), p.y(), p.z()))
        .collect();
    let volume = mesh_volume(&result_points, &tess.indices);

    let result_tris: Vec<[V3; 3]> = tess
        .indices
        .chunks_exact(3)
        .filter_map(|t| {
            Some([
                *result_points.get(t[0] as usize)?,
                *result_points.get(t[1] as usize)?,
                *result_points.get(t[2] as usize)?,
            ])
        })
        .collect();
    let source_tris: Vec<[V3; 3]> = geom
        .triangles
        .iter()
        .filter_map(|t| {
            Some([
                *geom.points.get(t[0] as usize)?,
                *geom.points.get(t[1] as usize)?,
                *geom.points.get(t[2] as usize)?,
            ])
        })
        .collect();

    let mut distances: Vec<f64> = Vec::new();

    let result_tree = TriTree::new(result_tris);
    if !result_tree.is_empty() {
        let source_samples: Vec<V3> = geom
            .centroids
            .iter()
            .copied()
            .chain(geom.points.iter().copied())
            .collect();
        for p in stride(&source_samples, MAX_SAMPLES) {
            if let Some(d) = result_tree.distance(p) {
                distances.push(d);
            }
        }
    }

    let source_tree = TriTree::new(source_tris);
    if !source_tree.is_empty() {
        for p in stride(&result_points, MAX_SAMPLES) {
            if let Some(d) = source_tree.distance(p) {
                distances.push(d);
            }
        }
    }

    let samples = distances.len();
    let max = distances.iter().copied().fold(0.0_f64, f64::max);
    let p95 = quantile(&mut distances, 0.95);

    Ok(Measured {
        deviation: Deviation { p95, max, samples },
        volume,
        mesh: ResultMesh::new(&result_points, &tess.indices),
    })
}

/// The faces at least one of whose tessellated points lies further than
/// `budget` from the source mesh.
///
/// This is the localised form of the same measurement [`measure`] aggregates:
/// it says *which* faces put the result off the part, so a failed verification
/// can be retried with those demoted instead of giving the whole reconstruction
/// up. Only the result-against-source direction is attributable — a feature the
/// result is missing belongs to no face of it — which is the direction a face
/// built in the wrong place shows up in.
///
/// A face built thirty metres off a hundred-millimetre part is the normal case
/// here rather than the pathological one, which is why the query structure has
/// to prune on distance rather than search outward from the point.
pub(super) fn faces_off_mesh(
    topo: &KernelTopology,
    solid: SolidId,
    geom: &MeshGeom,
    deflection: f64,
    budget: f64,
) -> Vec<FaceId> {
    let Ok(faces) = remus_topology::explorer::solid_faces(topo, solid) else {
        return Vec::new();
    };
    let grouped = guarded(|| {
        remus_operations::tessellate::tessellate_solid_grouped_with_tolerance(
            topo,
            solid,
            deflection,
            remus_math::chord::DEFAULT_ANGULAR_TOL,
        )
    });
    let Some(Ok((tess, offsets))) = grouped else {
        return Vec::new();
    };

    let points: Vec<V3> = tess
        .positions
        .iter()
        .map(|p| V3::new(p.x(), p.y(), p.z()))
        .collect();
    let source_tris: Vec<[V3; 3]> = geom
        .triangles
        .iter()
        .filter_map(|t| {
            Some([
                *geom.points.get(t[0] as usize)?,
                *geom.points.get(t[1] as usize)?,
                *geom.points.get(t[2] as usize)?,
            ])
        })
        .collect();
    let tree = TriTree::new(source_tris);
    if tree.is_empty() {
        return Vec::new();
    }

    // One answer per tessellation vertex: adjacent faces share their boundary
    // points, and the nearest-triangle query is the whole cost here.
    let mut over: Vec<Option<bool>> = vec![None; points.len()];
    let mut out = Vec::new();
    for (i, window) in offsets.windows(2).enumerate() {
        let (Some(&fid), Some(slice)) = (
            faces.get(i),
            tess.indices.get(window[0] as usize..window[1] as usize),
        ) else {
            continue;
        };
        let far = slice.iter().any(|&index| {
            let at = index as usize;
            let Some(&point) = points.get(at) else {
                return false;
            };
            if let Some(known) = over.get(at).copied().flatten() {
                return known;
            }
            let answer = tree.distance(point).is_some_and(|d| d > budget);
            if let Some(slot) = over.get_mut(at) {
                *slot = Some(answer);
            }
            answer
        });
        if far {
            out.push(fid);
        }
    }
    out
}

/// Run a kernel call that is known to index out of bounds on some inputs.
///
/// `tessellate` walks a face's own boundary chain and indexes past its end on a
/// handful of corpus faces (`crates/operations/src/tessellate/nonplanar.rs:2187`,
/// esaueng/remus). That is an upstream defect, not an answer, and a
/// reconstruction library may not take the calling process down over one face:
/// `None` means "the kernel could not say", which every caller here already
/// handles as a stage that declined.
fn guarded<T>(call: impl FnOnce() -> T) -> Option<T> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(call)).ok()
}

/// Evenly spaced subsample, so a cap never biases the quantile toward one
/// region of the part.
fn stride(points: &[V3], cap: usize) -> Vec<V3> {
    if points.len() <= cap || cap == 0 {
        return points.to_vec();
    }
    let step = points.len().div_ceil(cap).max(1);
    points.iter().copied().step_by(step).collect()
}
