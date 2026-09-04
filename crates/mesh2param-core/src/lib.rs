//! Phase 1 core of the Mesh2Param reconstruction overhaul.
//!
//! Mesh bytes in, STEP bytes out, on a B-Rep kernel pinned by revision. The
//! crate is deliberately pure: no filesystem, no threads, no globals, so the
//! same code runs in a native test, in a worker process, and in the browser
//! (`wasm32-unknown-unknown`) with nothing stubbed out.
//!
//! # The ladder
//!
//! A part is reconstructed at the best tier that will hold, falling back
//! region by region:
//!
//! 1. **Analytic** ([`Tier::Analytic`]) — every face is a recognised surface
//!    (plane, cylinder, cone, sphere, torus). The target for Phase 1 exit.
//! 2. **Mixed** ([`Tier::Mixed`]) — analytic where recognition succeeded,
//!    faceted for the regions it declined. Unfittable regions stay honest
//!    rather than being forced onto a wrong surface.
//! 3. **Faceted** ([`Tier::Faceted`]) — planar facets throughout. Implemented
//!    here, in [`faceted_step`]; the floor everything else is measured against.
//!
//! Only the faceted rung exists today. The corpus scoreboard
//! (`tests/scoreboard.rs`) is what says whether a new rung is an improvement.
//!
//! # Example
//!
//! ```no_run
//! use mesh2param_core::{FacetedOptions, MeshFormat, faceted_step, load_mesh};
//!
//! # fn main() -> Result<(), mesh2param_core::CoreError> {
//! # let bytes: Vec<u8> = Vec::new();
//! let mesh = load_mesh(&bytes, MeshFormat::Stl)?;
//! let result = faceted_step(&mesh, &FacetedOptions::default())?;
//! assert!(result.step.starts_with(b"ISO-10303-21"));
//! # Ok(())
//! # }
//! ```

pub mod error;
pub mod faceted;
pub mod mesh;

pub use error::{CoreError, Result};
pub use faceted::{FacetedOptions, FacetedResult, Tier, faceted_step};
pub use mesh::{Bbox, MeshData, MeshFormat, load_mesh};
