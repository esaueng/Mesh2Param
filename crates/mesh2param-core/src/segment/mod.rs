//! Segmentation: a triangle mesh in, a set of analytic surface patches out.
//!
//! This is *recognition*, not reconstruction. Nothing is built here; the stage
//! answers "which triangles belong to which surface, and what surface is it",
//! which is what the analytic and mixed rungs of the ladder need before they
//! can build anything.
//!
//! # The stages
//!
//! 1. **Weld and over-segment.** Vertices are welded ([`MeshData::welded`]),
//!    then faces are grouped by union-find over neighbour pairs whose normals
//!    differ by less than [`SegmentOptions::angle_deg`].
//! 2. **Fit.** Each patch gets a plane, cylinder, cone, sphere and torus in
//!    turn, and the first one inside tolerance wins. Patches that fit nothing
//!    are re-cut at a tighter angle and refitted — except across a smoothly
//!    curved neighbourhood, which is one surface and is never cut into planar
//!    shards.
//! 3. **Merge.** Patches whose fitted primitives agree are merged, then
//!    adjacent patches are trial-merged and the merge kept when the union is
//!    still a primitive. This is what turns a coarse cylinder's planar strips
//!    back into one cylinder.
//! 4. **Refine.** Boundary faces move to whichever neighbouring patch's
//!    primitive scores them best, and leftover unfittable patches are absorbed
//!    by an adjacent primitive when the union fits.
//!
//! Every acceptance and merge decision is made against a tolerance derived from
//! the patch's **own** median edge length, not the mesh's; a decision spanning
//! two patches uses the looser of the two. See
//! [`SegmentOptions::tol_chord_factor`].
//!
//! A patch that is mostly smoothly curved and does not fit its plane to a
//! hundredth of that tolerance is not promoted as a plane: it is
//! [`PatchKind::Unknown`] with [`UnknownReason::Freeform`], a surface waiting
//! for a fit this crate does not have. The `curvature` module says what
//! "smoothly curved" measures and why it is the only thing that separates a
//! shard of a b-spline from a small planar face.
//!
//! # Example
//!
//! ```no_run
//! use mesh2param_core::{MeshFormat, SegmentOptions, load_mesh, segment};
//!
//! # fn main() -> Result<(), mesh2param_core::CoreError> {
//! # let bytes: Vec<u8> = Vec::new();
//! let mesh = load_mesh(&bytes, MeshFormat::Stl)?;
//! let seg = segment(&mesh, &SegmentOptions::default())?;
//! println!("{} patches, {:.1}% unknown area",
//!     seg.patches.len(), 100.0 * seg.unknown_area_fraction);
//! # Ok(())
//! # }
//! ```

mod curvature;
mod fit;
mod grow;
pub(crate) mod linalg;
mod stats;
#[cfg(test)]
mod tests;

use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};
use crate::mesh::MeshData;
use fit::FitOpts;
use grow::{Geom, Params};

/// Knobs for [`segment`].
///
/// Every angle is in degrees and every length is a fraction of something the
/// mesh itself provides: nothing here is an absolute millimetre value, because
/// the same code has to hold on a 6 mm clip and a 900 mm plate.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SegmentOptions {
    /// Dihedral threshold for the initial over-segmentation, in degrees.
    pub angle_deg: f64,

    /// Residual tolerance as a multiple of **each patch's own median edge
    /// length**.
    ///
    /// The tolerance has to follow feature size, not part size, and feature
    /// size varies *within* one part. A fraction of the bounding-box diagonal
    /// is 1.9 mm on a 930 mm part — enough to merge two tangent 50 mm bosses
    /// into one surface — while being far too tight on a part measured in
    /// centimetres; a mesh-wide median edge is 3.7 mm on the same part and
    /// merges the same bosses. A tessellator subdivides small and highly curved
    /// features more finely, so a patch's *own* median edge is short exactly
    /// where the tolerance must be tight and long over the coarse flats where
    /// it must be loose. A patch with fewer than two triangles has too few
    /// edges to say anything and falls back to the mesh-wide median.
    pub tol_chord_factor: f64,
    /// Lower clamp on the tolerance, as a fraction of the bounding-box diagonal.
    ///
    /// A near-degenerate or wildly non-uniform tessellation can drive the
    /// median edge to almost nothing; the clamps keep the derived tolerance
    /// inside the range where the fits behave.
    pub tol_min_frac: f64,
    /// Upper clamp on the tolerance, as a fraction of the bounding-box diagonal.
    pub tol_max_frac: f64,

    /// Minimum angular spread of a patch's face normals before a curved
    /// primitive is considered at all, in degrees. Keeps a flat patch from
    /// becoming a huge-radius cylinder.
    pub min_spread_deg: f64,
    /// Largest tolerated per-facet angular step around a fitted axis, in
    /// degrees. A hex prism puts its vertices on a circle too; only the step
    /// size separates it from a coarse cylinder.
    pub max_facet_deg: f64,
    /// Largest tolerated RMS angle between a face normal and the fitted
    /// primitive's own normal, in degrees.
    pub max_normal_dev_deg: f64,
    /// Residual budget for a curved fit relative to its own radius.
    pub radius_tol_frac: f64,
    /// Minimum angle a torus patch must sweep around its tube circle, in
    /// degrees, before the torus is accepted.
    pub min_minor_sweep_deg: f64,

    /// Direction slack when two fitted primitives are declared the same, in
    /// degrees.
    pub merge_angle_deg: f64,
    /// Half-angle slack when two fitted cones are declared the same, in degrees.
    pub merge_half_angle_deg: f64,
    /// Radius slack, as a fraction, when merging cylinders and spheres.
    pub merge_radius_frac: f64,
    /// Radius slack, as a fraction, when merging tori. Looser than
    /// [`Self::merge_radius_frac`]: a torus has two radii and a fillet band
    /// samples only a sliver of each.
    pub merge_torus_radius_frac: f64,

    /// Cap on merge rounds.
    pub max_merge_rounds: usize,
    /// Boundary refinement rounds.
    pub refine_rounds: usize,
    /// How many times a patch that fitted nothing may be re-cut at a tighter
    /// angle.
    pub split_levels: usize,

    /// Minimum face count before a patch carved out of an unfittable region is
    /// promoted to a primitive.
    ///
    /// Splitting an unfittable region far enough eventually makes every
    /// triangle pair look planar, so a freeform surface shatters into hundreds
    /// of tiny "planes" — the single largest error the Phase 0 spike measured.
    /// A shard that fails any of the three carved-patch gates
    /// ([`Self::min_patch_faces`], [`Self::shard_factor`],
    /// [`Self::min_patch_area_fraction`]) or the residual gate stays
    /// [`PatchKind::Unknown`], which is the honest answer. It may still be
    /// absorbed later by an adjacent patch of the same primitive.
    pub min_patch_faces: usize,
    /// Minimum extent of a carved patch, **in units of its own tolerance**: it
    /// is promoted only when its area is at least `(shard_factor * tol)²`.
    ///
    /// This is the gate that separates a real small face from a shard, and it
    /// has to be resolution-relative rather than a fraction of the part. On the
    /// hammer holder about 200 freeform shards have a median area of 3 mm² on a
    /// 13 938 mm² part, which no global area fraction can cut away without also
    /// cutting real small faces off other parts. What does separate them is
    /// span measured in chords: a genuine planar face on a CAD export is
    /// tessellated with many triangles across it, so it spans many tolerances,
    /// while a shard carved out of a curved region spans only the few chords it
    /// took for the surface to bend past the split angle.
    ///
    /// This is the one gate that applies to **every** patch and not only to a
    /// carved one, and then only to a patch of a single triangle: one triangle
    /// lies on exactly one plane, so it is evidence of a plane only when it is
    /// big enough to be a face in its own right.
    pub shard_factor: f64,
    /// Minimum area, as a fraction of the mesh's total area, before a patch
    /// carved out of an unfittable region is promoted to a primitive.
    ///
    /// An optional extra gate on top of [`Self::shard_factor`], off (`0.0`) by
    /// default: an absolute share of the part is the wrong scale for this
    /// decision, and a part whose real faces are all tiny is punished by it.
    pub min_patch_area_fraction: f64,

    /// Fit face centroids instead of patch vertices.
    ///
    /// Off by default and only worth turning on to reproduce the older
    /// behaviour: a centroid fit under-reports a coarse cylinder's radius by
    /// `cos(facet / 2)`, 3.4% on a 12-facet cylinder.
    pub fit_on_centroids: bool,
}

impl Default for SegmentOptions {
    fn default() -> Self {
        Self {
            angle_deg: 12.0,
            tol_chord_factor: 0.35,
            tol_min_frac: 1e-4,
            tol_max_frac: 0.05,
            min_spread_deg: 8.0,
            max_facet_deg: 40.0,
            max_normal_dev_deg: 12.0,
            radius_tol_frac: 0.002,
            min_minor_sweep_deg: 20.0,
            merge_angle_deg: 1.0,
            merge_half_angle_deg: 1.0,
            merge_radius_frac: 0.01,
            merge_torus_radius_frac: 0.02,
            max_merge_rounds: 12,
            refine_rounds: 2,
            split_levels: 3,
            min_patch_faces: 6,
            shard_factor: 5.0,
            min_patch_area_fraction: 0.0,
            fit_on_centroids: false,
        }
    }
}

/// The analytic surface a patch was recognised as.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PatchKind {
    /// A plane.
    Plane,
    /// A cylinder, possibly a partial one.
    Cylinder,
    /// A cone.
    Cone,
    /// A torus.
    Torus,
    /// A sphere.
    Sphere,
    /// Nothing recognised. Not a failure: an unfittable region stays honest
    /// rather than being forced onto a wrong surface.
    Unknown,
}

impl PatchKind {
    /// The kind of a fitted primitive.
    #[must_use]
    pub const fn of(prim: Primitive) -> Self {
        match prim {
            Primitive::Plane { .. } => Self::Plane,
            Primitive::Cylinder { .. } => Self::Cylinder,
            Primitive::Cone { .. } => Self::Cone,
            Primitive::Torus { .. } => Self::Torus,
            Primitive::Sphere { .. } => Self::Sphere,
            Primitive::Unknown => Self::Unknown,
        }
    }
}

/// A fitted analytic surface, in the mesh's own coordinates and units.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Primitive {
    /// `normal . x = offset`, with a unit normal.
    Plane {
        /// Unit normal.
        normal: [f64; 3],
        /// Signed distance from the origin along the normal.
        offset: f64,
    },
    /// A cylinder of revolution.
    #[serde(rename_all = "camelCase")]
    Cylinder {
        /// A point on the axis.
        axis_point: [f64; 3],
        /// Unit axis direction.
        axis_dir: [f64; 3],
        /// Radius.
        radius: f64,
        /// How much of the full turn the patch covers, in degrees.
        sweep_deg: f64,
    },
    /// A cone of revolution, measured from its apex.
    #[serde(rename_all = "camelCase")]
    Cone {
        /// The apex.
        apex: [f64; 3],
        /// Unit axis direction; the cone opens along it.
        axis_dir: [f64; 3],
        /// Angle between the axis and the surface, in degrees.
        half_angle_deg: f64,
    },
    /// A torus: a tube of `minor_radius` swept at `major_radius` about the axis.
    #[serde(rename_all = "camelCase")]
    Torus {
        /// Centre of the ring, on the axis.
        center: [f64; 3],
        /// Unit axis direction.
        axis_dir: [f64; 3],
        /// Distance from the axis to the tube centre.
        major_radius: f64,
        /// Radius of the tube.
        minor_radius: f64,
    },
    /// A sphere.
    Sphere {
        /// Centre.
        center: [f64; 3],
        /// Radius.
        radius: f64,
    },
    /// No primitive was accepted.
    Unknown,
}

/// Why a region was left [`PatchKind::Unknown`].
///
/// Recorded so the stages above can tell the three apart: a freeform region is
/// a *surface* waiting for a fit the crate does not have yet (a NURBS), while a
/// shard is a fragment of one and a no-fit region is a region nothing was
/// recognised in at all.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum UnknownReason {
    /// The region is smoothly curved and its plane fit was refused on that
    /// basis: a B-spline or blend surface, not a set of small flats. The build
    /// stage may later fit a general surface here.
    Freeform,
    /// A fragment carved out of an unfittable region that did not clear the
    /// promotion gates.
    Shard,
    /// No primitive fitted the region within tolerance.
    NoFit,
}

/// One recognised region of the mesh.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Patch {
    /// Index of this patch in [`Segmentation::patches`]. Patches are ordered
    /// by descending area, so ids are stable across runs.
    pub id: u32,
    /// What the patch was recognised as.
    pub kind: PatchKind,
    /// Welded triangle indices belonging to this patch.
    pub faces: Vec<u32>,
    /// Total area of those triangles.
    pub area: f64,
    /// Area-weighted RMS distance from the samples to the fitted surface.
    ///
    /// Reported even for an [`PatchKind::Unknown`] patch, where it is the best
    /// rejected candidate's residual: how far off the nearest primitive was.
    /// `None` when no candidate produced a finite residual at all.
    pub rms_residual: Option<f64>,
    /// Largest single-sample distance to the same surface.
    pub max_residual: Option<f64>,
    /// The fitted surface.
    pub primitive: Primitive,
    /// Why the patch is [`PatchKind::Unknown`]; `None` exactly when it is not.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<UnknownReason>,
    /// Share of the patch's area that lies in a smoothly curved neighbourhood.
    ///
    /// Diagnostic: this is the number the freeform gate is a threshold on.
    pub smooth_curved_fraction: f64,
}

/// How many patches of each kind a segmentation found.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Inventory {
    /// Planes.
    pub plane: u32,
    /// Cylinders.
    pub cylinder: u32,
    /// Cones.
    pub cone: u32,
    /// Tori.
    pub torus: u32,
    /// Spheres.
    pub sphere: u32,
    /// Regions nothing was recognised in.
    pub unknown: u32,
}

impl Inventory {
    fn count(&mut self, kind: PatchKind) {
        match kind {
            PatchKind::Plane => self.plane += 1,
            PatchKind::Cylinder => self.cylinder += 1,
            PatchKind::Cone => self.cone += 1,
            PatchKind::Torus => self.torus += 1,
            PatchKind::Sphere => self.sphere += 1,
            PatchKind::Unknown => self.unknown += 1,
        }
    }
}

/// The result of [`segment`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Segmentation {
    /// The patches, ordered by descending area.
    pub patches: Vec<Patch>,
    /// Patch id per triangle of the **welded** mesh — the mesh
    /// [`MeshData::welded`] produces, which has degenerate triangles dropped,
    /// not the input triangle soup.
    pub face_patch: Vec<u32>,
    /// Mean dominant principal curvature magnitude per **welded** triangle, in
    /// reciprocal mesh units, and zero wherever curvature is not defined (a
    /// corner on a crease, a boundary, or a degenerate triangle).
    ///
    /// Diagnostic only: nothing downstream reads it, and it is what makes the
    /// freeform gates inspectable on a real part.
    pub face_curvature: Vec<f64>,
    /// Whether each **welded** triangle sits in a smoothly curved
    /// neighbourhood: at least one corner measured past
    /// `1 / (2 x bbox diagonal)`, no corner measured flat, and no edge of the
    /// triangle folding past `maxFacetDeg`. This is the score the freeform gate
    /// weighs by area, and [`Patch::smooth_curved_fraction`] is that weighing.
    pub face_smooth_curved: Vec<bool>,
    /// Patch counts by kind.
    pub inventory: Inventory,
    /// Share of the total area that no primitive was recognised in.
    pub unknown_area_fraction: f64,
    /// The mesh-wide absolute residual tolerance, from
    /// [`SegmentOptions::tol_chord_factor`] and the mesh's median edge length.
    ///
    /// Reported as the scale of the run, but it is not what most patches were
    /// judged against: each patch is judged against the same factor times *its
    /// own* median edge length, and this value is only the fallback for patches
    /// with fewer than two triangles.
    pub tolerance: f64,
}

/// Non-finite residuals are reported as absent rather than as a number no
/// JSON encoder can represent.
fn finite(v: f64) -> Option<f64> {
    v.is_finite().then_some(v)
}

fn check(value: f64, name: &str) -> Result<()> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(CoreError::Validation(format!(
            "segment option {name} must be finite and positive, got {value}"
        )))
    }
}

fn check_nonneg(value: f64, name: &str) -> Result<()> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(CoreError::Validation(format!(
            "segment option {name} must be finite and not negative, got {value}"
        )))
    }
}

/// How much better than the general tolerance a carved shard's own fit has to
/// be before it is believed.
///
/// A shard of a smooth surface fits a plane "well" only because it is tiny: the
/// sagitta over a short span is far below the tolerance whatever the curvature.
/// Demanding a fraction of the budget rather than the whole budget is what
/// tells a genuinely flat few triangles from a flat-looking sample of a curve.
const SHARD_RESIDUAL_FRAC: f64 = 0.25;

/// How much of a patch's area has to be smoothly curved before its **plane**
/// fit is refused and the patch is called [`UnknownReason::Freeform`].
///
/// A majority, with room to spare, because the score is deliberately silent at
/// a region's rim: the corners there sit on the creases that bound the face, so
/// the border ring of every patch scores zero however curved the surface is. A
/// b-spline face therefore reads as somewhat less than fully curved — three
/// fifths is what a small one still clears — while a planar face reads as
/// nothing at all, and a plane-to-fillet-to-plane leak, where the fillet is a
/// narrow band between two large flats, stays well under the bar and is still
/// split into its parts by stage 2b.
///
/// Only the plane is gated. A cylinder, cone, sphere or torus fit is *supposed*
/// to land on a curved region, and its own residual, axis conditioning and
/// normal deviation already say whether it did.
const FREEFORM_AREA_FRACTION: f64 = 0.6;

/// How far off its own plane a patch has to be, as a fraction of its tolerance,
/// before curvature is allowed to demote it.
///
/// A hundredth, which is not a tolerance but a *separation*, and the two
/// populations it separates are far apart. A planar face on a CAD export is
/// planar exactly: the corpus's real planes fit to `1e-14` mm, machine epsilon
/// on their own coordinates, and even a binary STL's float32 rounding reaches
/// only a few times `1e-5` of a tolerance. A shard of a smooth surface fits its
/// plane to a few per cent of one — small enough to be accepted, far too large
/// to be rounding.
///
/// This is what keeps the gate off a narrow flat bounded by fillets, whose
/// every vertex is on a tangent rim and therefore reads curved: the flange's
/// 4 mm annulus fits its plane to 0.8% of its tolerance and keeps it, while the
/// hammer holder's shards fit theirs to between 3.5% and 25% and lose it.
const FREEFORM_RESIDUAL_FLOOR: f64 = 1e-2;

/// Segment a mesh into analytic surface patches.
///
/// # Errors
///
/// - [`CoreError::Validation`] when an option is not a finite positive number,
///   or when the mesh has no usable triangles once welded.
pub fn segment(mesh: &MeshData, options: &SegmentOptions) -> Result<Segmentation> {
    check(options.angle_deg, "angleDeg")?;
    check(options.tol_chord_factor, "tolChordFactor")?;
    check(options.tol_min_frac, "tolMinFrac")?;
    check(options.tol_max_frac, "tolMaxFrac")?;
    check(options.radius_tol_frac, "radiusTolFrac")?;
    check_nonneg(options.shard_factor, "shardFactor")?;
    check_nonneg(options.min_patch_area_fraction, "minPatchAreaFraction")?;
    if options.tol_min_frac > options.tol_max_frac {
        return Err(CoreError::Validation(format!(
            "segment option tolMinFrac ({}) is above tolMaxFrac ({})",
            options.tol_min_frac, options.tol_max_frac
        )));
    }

    let welded = mesh.welded()?;
    let geom = Geom::new(&welded);
    let bbox_diag = mesh.bbox.diagonal();
    let total_area = geom.total_area();
    if !total_area.is_finite() || total_area <= 0.0 {
        return Err(CoreError::Validation("mesh has zero surface area".into()));
    }

    let tol_lo = options.tol_min_frac * bbox_diag;
    let tol_hi = options.tol_max_frac * bbox_diag;
    // The mesh-wide value is only the fallback for patches too small to have a
    // median edge of their own; every patch is judged against its own.
    let mesh_edge = geom.median_edge_length();
    let tolerance = (options.tol_chord_factor * mesh_edge).clamp(tol_lo, tol_hi);

    let params = Params {
        angle_rad: options.angle_deg.to_radians(),
        tol_chord_factor: options.tol_chord_factor,
        tol_lo,
        tol_hi,
        mesh_edge,
        opts: FitOpts {
            tol: tolerance,
            min_spread: options.min_spread_deg.to_radians(),
            max_facet_step: options.max_facet_deg.to_radians(),
            max_normal_dev: options.max_normal_dev_deg.to_radians(),
            // Filled in per patch by the fitting stages, which are the only
            // place the mesh's face adjacency is known.
            max_crease: 0.0,
            radius_tol_frac: options.radius_tol_frac,
            min_minor_sweep: options.min_minor_sweep_deg.to_radians(),
            bbox_diag,
        },
        merge_angle_rad: options.merge_angle_deg.to_radians(),
        merge_half_angle_rad: options.merge_half_angle_deg.to_radians(),
        merge_radius_frac: options.merge_radius_frac,
        merge_torus_radius_frac: options.merge_torus_radius_frac,
        max_merge_rounds: options.max_merge_rounds,
        refine_rounds: options.refine_rounds,
        split_levels: options.split_levels,
        fit_on_centroids: options.fit_on_centroids,
    };

    let curv = curvature::estimate(&geom, params.opts.max_facet_step, bbox_diag);
    let grown = grow::run(&geom, &curv, &params);

    let min_area = options.min_patch_area_fraction * total_area;
    let mut inventory = Inventory::default();
    let mut unknown_area = 0.0;
    let mut face_patch = vec![0_u32; welded.triangles.len()];
    let mut patches = Vec::with_capacity(grown.patches.len());

    for (id, faces) in grown.patches.into_iter().enumerate() {
        let fit = grown.fits.get(id).copied().unwrap_or(fit::Fit::UNKNOWN);
        let carved = grown.carved.get(id).copied().unwrap_or(false);
        let area = faces
            .iter()
            .filter_map(|&f| geom.faces.get(f as usize))
            .map(|f| f.area)
            .sum::<f64>();

        // A shard carved out of an unfittable region has to earn its promotion:
        // it must be several triangles, span many of its own tolerances, and
        // fit distinctly better than the tolerance it is judged against.
        // Failing any of those it is noise from over-splitting, not a face.
        //
        // One triangle is gated whatever cut it out, because a single triangle
        // lies on exactly one plane and so is no evidence of one at all. Where
        // adjacent triangles are pervasively further apart than `angle_deg`,
        // the dihedral pass alone cuts a coarsely tessellated freeform surface
        // into lone triangles, no merge will join them, and nothing marks them
        // `carved` — 18 of the 108 "planes" on the airtag keychain are one
        // triangle each. It still keeps a genuinely small face that spans its
        // own tolerances: a triangular gusset is one triangle too, and it is
        // large.
        //
        // The face-count and residual gates stay `carved`-only. Measured over
        // the corpus, requiring `min_patch_faces` of every patch costs the real
        // two-triangle rectangles a CAD tessellator emits by the dozen — the
        // heat sink's 41 planes drop to 27 and the manifold block's inventory
        // error doubles — and requiring the span of every patch costs the same
        // meshes their narrow ones.
        let min_span = options.shard_factor * fit.tol;
        let spans = area >= min_span * min_span;

        // The freeform gate. A plane fitted over a region that is mostly
        // smoothly curved is a *sample* of that curve, not a face on it: over a
        // short span the sagitta is far under any tolerance, which is why no
        // residual and no size gate separates the two. Curvature does. The
        // region keeps its area and is reported as one honest `Unknown`
        // surface, for the build stage to fit a general surface to later.
        // Two conditions, because "mostly curved" alone is not enough. A narrow
        // flat face bounded by a fillet on each side has *no* interior: every
        // corner of it sits on a tangent rim, where the one-ring really is
        // curved because half of it belongs to the fillet, so the face reads as
        // fully smooth and loses its plane. What separates it from a shard is
        // how well it fits: the flange's 4 mm-wide annulus fits its plane to
        // 0.8% of its tolerance, and the hammer holder's shards fit theirs to
        // between 3.5% and 25%. A plane that exact is a plane; a surface
        // sampled over a short span is not.
        let smooth_curved_fraction = grown
            .stats
            .get(id)
            .map_or(0.0, stats::Stats::smooth_fraction);
        let exactly_planar = fit.rms <= FREEFORM_RESIDUAL_FLOOR * fit.tol;
        let freeform = smooth_curved_fraction > FREEFORM_AREA_FRACTION && !exactly_planar;
        let refused_plane = freeform && matches!(fit.prim, Primitive::Plane { .. });

        let promoted = !refused_plane
            && (faces.len() >= 2 || spans)
            && (!carved
                || (faces.len() >= options.min_patch_faces
                    && spans
                    && area >= min_area
                    && fit.rms <= SHARD_RESIDUAL_FRAC * fit.tol));
        let primitive = if promoted {
            fit.prim
        } else {
            Primitive::Unknown
        };
        let kind = PatchKind::of(primitive);
        let reason = if promoted {
            None
        } else if freeform {
            Some(UnknownReason::Freeform)
        } else if matches!(fit.prim, Primitive::Unknown) {
            Some(UnknownReason::NoFit)
        } else {
            Some(UnknownReason::Shard)
        };

        inventory.count(kind);
        if kind == PatchKind::Unknown {
            unknown_area += area;
        }
        for &f in &faces {
            if let Some(slot) = face_patch.get_mut(f as usize) {
                *slot = id as u32;
            }
        }
        patches.push(Patch {
            id: id as u32,
            kind,
            faces,
            area,
            rms_residual: finite(fit.rms),
            max_residual: finite(fit.max_res),
            primitive,
            reason,
            smooth_curved_fraction,
        });
    }

    Ok(Segmentation {
        patches,
        face_patch,
        face_curvature: curv.kappa,
        face_smooth_curved: curv.smooth,
        inventory,
        unknown_area_fraction: unknown_area / total_area,
        tolerance,
    })
}
