//! Mesh input: bytes in, a triangle mesh plus its cheap statistics out.
//!
//! Nothing here touches the filesystem. Callers (CLI, worker, WASM binding)
//! own the bytes; this crate only ever sees a slice.

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
