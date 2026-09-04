//! Typed errors for the reconstruction core.

use crate::mesh::MeshFormat;

/// Result alias used throughout the crate.
pub type Result<T> = core::result::Result<T, CoreError>;

/// Every way a reconstruction can fail.
///
/// Kernel failures are flattened to strings on purpose: the kernel's own error
/// types are part of a pinned revision, and leaking them into this crate's
/// public API would make a pin bump a breaking change for every caller.
#[derive(Debug, thiserror::Error)]
pub enum CoreError {
    /// Reading or writing bytes failed.
    #[error("i/o error: {0}")]
    Io(String),

    /// The input bytes are not a well-formed mesh file.
    #[error("parse error: {0}")]
    Parse(String),

    /// The mesh parsed but could not be lifted to a B-Rep solid.
    #[error("mesh import failed: {0}")]
    Import(String),

    /// A kernel operation (validate, unify, write) returned an error.
    #[error("kernel error: {0}")]
    Kernel(String),

    /// The mesh is larger than the configured triangle budget.
    #[error("mesh has {triangles} triangles, over the budget of {limit}")]
    Budget {
        /// Triangle count of the submitted mesh.
        triangles: usize,
        /// Configured maximum.
        limit: usize,
    },

    /// The reconstruction produced a result that fails its own invariants.
    #[error("validation failed: {0}")]
    Validation(String),

    /// The requested input format is not implemented yet.
    #[error("unsupported mesh format: {0:?}")]
    Unsupported(MeshFormat),
}
