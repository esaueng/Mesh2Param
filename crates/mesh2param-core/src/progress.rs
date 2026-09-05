//! Stage progress, for callers that run the ladder somewhere a user is
//! watching.
//!
//! The core has no clock on the browser target and no threads anywhere, so a
//! long run is otherwise a silent one. [`Progress`] is the one channel out of
//! it: a borrowed callback, invoked at stage boundaries and at a coarse
//! per-pass granularity inside the two stages that dominate the wall clock.
//!
//! Reporting is advisory. Nothing in the core reads it back, no decision
//! depends on it, and a run with [`Progress::none`] takes exactly the same
//! path as one with a sink attached.

use serde::{Deserialize, Serialize};

/// A named stage of a reconstruction run, in the order they occur.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Stage {
    /// Mesh bytes are being decoded. Reported by the caller that owns the
    /// bytes, since [`crate::load_mesh`] is a single call.
    Parse,
    /// Vertices are being welded and adjacency resolved.
    Weld,
    /// Triangles are being grouped into analytic surface patches.
    Segment,
    /// Patch boundaries are being recovered.
    Topology,
    /// Faces and the solid are being built.
    Build,
    /// The result is being tessellated and measured against the mesh.
    Verify,
    /// The STEP file is being written.
    Step,
}

impl Stage {
    /// The stage's name, as callers outside Rust see it.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Parse => "parse",
            Self::Weld => "weld",
            Self::Segment => "segment",
            Self::Topology => "topology",
            Self::Build => "build",
            Self::Verify => "verify",
            Self::Step => "step",
        }
    }
}

/// A borrowed progress sink.
///
/// Fractions are per stage, not per run: each stage runs its own `0.0` to
/// `1.0`. They are monotonic within a stage but the stages are not evenly
/// sized, so a caller that wants one overall number has to weight them itself.
pub struct Progress<'a>(Option<&'a mut dyn FnMut(Stage, f32)>);

impl<'a> Progress<'a> {
    /// A sink that reports nothing.
    #[must_use]
    pub const fn none() -> Self {
        Self(None)
    }

    /// Report to `sink`.
    #[must_use]
    pub const fn new(sink: &'a mut dyn FnMut(Stage, f32)) -> Self {
        Self(Some(sink))
    }

    /// Report `stage` at `fraction`, clamped into `0.0..=1.0`.
    pub fn at(&mut self, stage: Stage, fraction: f32) {
        if let Some(sink) = self.0.as_mut() {
            sink(stage, fraction.clamp(0.0, 1.0));
        }
    }

    /// Report the `n`th of `total` passes through a stage, mapped onto
    /// `lo..=hi` of that stage's own range. A zero `total` reports `lo`.
    pub fn pass(&mut self, stage: Stage, lo: f32, hi: f32, n: usize, total: usize) {
        let span = hi - lo;
        let done = if total == 0 {
            0.0
        } else {
            (n as f32 / total as f32).clamp(0.0, 1.0)
        };
        self.at(stage, span.mul_add(done, lo));
    }

    /// Borrow this sink for the length of a nested call.
    pub fn reborrow(&mut self) -> Progress<'_> {
        match self.0 {
            Some(ref mut sink) => Progress(Some(&mut **sink)),
            None => Progress(None),
        }
    }
}

impl core::fmt::Debug for Progress<'_> {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.debug_tuple("Progress").field(&self.0.is_some()).finish()
    }
}
