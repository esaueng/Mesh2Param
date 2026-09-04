//! Measuring the built solid against the mesh it came from.
//!
//! The kernel tessellates the result; the two meshes are then compared in
//! **both** directions, because a one-sided distance cannot see a missing
//! feature. Source samples against the result catch a face that was built in
//! the wrong place; result samples against the source catch a face that was
//! invented where the mesh has nothing.

use remus_topology::Topology as KernelTopology;
use remus_topology::solid::SolidId;
use serde::{Deserialize, Serialize};

use super::geom::{MeshGeom, TriGrid, mesh_volume, quantile};
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
}

/// Cap on samples taken in each direction. A quantile does not get better
/// past a few tens of thousands of points, and the grid query is the whole
/// cost of the verify stage.
const MAX_SAMPLES: usize = 40_000;

pub(super) fn measure(
    topo: &KernelTopology,
    solid: SolidId,
    geom: &MeshGeom,
    deflection: f64,
) -> Result<Measured> {
    let tess = remus_operations::tessellate::tessellate_solid(topo, solid, deflection)
        .map_err(|e| CoreError::Kernel(format!("tessellate_solid: {e}")))?;

    let result_points: Vec<V3> = tess
        .positions
        .iter()
        .map(|p| V3::new(p.x(), p.y(), p.z()))
        .collect();
    let volume = mesh_volume(&result_points, &tess.indices);

    let extent = extent_of(&geom.points).max(extent_of(&result_points));

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

    let result_grid = TriGrid::new(result_tris, extent);
    if !result_grid.is_empty() {
        let source_samples: Vec<V3> = geom
            .centroids
            .iter()
            .copied()
            .chain(geom.points.iter().copied())
            .collect();
        for p in stride(&source_samples, MAX_SAMPLES) {
            if let Some(d) = result_grid.distance(p) {
                distances.push(d);
            }
        }
    }

    let source_grid = TriGrid::new(source_tris, extent);
    if !source_grid.is_empty() {
        for p in stride(&result_points, MAX_SAMPLES) {
            if let Some(d) = source_grid.distance(p) {
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
    })
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

fn extent_of(points: &[V3]) -> f64 {
    let mut min = [f64::INFINITY; 3];
    let mut max = [f64::NEG_INFINITY; 3];
    for p in points {
        for (axis, v) in p.arr().iter().enumerate() {
            min[axis] = min[axis].min(*v);
            max[axis] = max[axis].max(*v);
        }
    }
    let mut extent = 0.0_f64;
    for axis in 0..3 {
        let d = max[axis] - min[axis];
        if d.is_finite() {
            extent = extent.max(d);
        }
    }
    if extent > 0.0 { extent } else { 1.0 }
}
