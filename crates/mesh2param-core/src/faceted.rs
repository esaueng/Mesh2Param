//! The faceted tier: the reconstruction floor.
//!
//! Every triangle becomes a planar B-Rep face, same-domain neighbours are
//! merged, and the result is written as AP203 STEP. No surface fitting, no
//! feature recognition — this is the result every higher tier has to beat, and
//! the fallback whenever a higher tier declines a region.

use remus_operations::validate::{Severity, ValidationReport};
use remus_topology::Topology;
use remus_topology::solid::SolidId;
use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};
use crate::mesh::MeshData;

/// How many validation issues are carried on a result before truncating.
const MAX_ISSUES: usize = 10;

/// Reconstruction quality of a produced solid.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Tier {
    /// Every face is a recognised analytic surface.
    Analytic,
    /// Analytic where recognised, faceted elsewhere.
    Mixed,
    /// Planar facets throughout.
    Faceted,
}

/// Knobs for [`faceted_step`].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct FacetedOptions {
    /// Refuse meshes above this triangle count.
    ///
    /// The faceted tier emits roughly one `ADVANCED_FACE` per triangle, so the
    /// STEP file grows about a kilobyte per triangle. The budget is what keeps
    /// a 150k-triangle export from producing a 150 MB file the kernel's own
    /// reader then rejects (esaueng/remus#245).
    pub triangle_budget: usize,
    /// Vertex-welding tolerance handed to the kernel's mesh importer.
    ///
    /// Matches the value the browser build passes today. Absolute, not
    /// scale-relative; feature-relative tolerance is a Phase 1 follow-up.
    pub tolerance: f64,
}

impl Default for FacetedOptions {
    fn default() -> Self {
        Self {
            triangle_budget: 200_000,
            tolerance: 1e-7,
        }
    }
}

/// Outcome of a faceted reconstruction.
#[derive(Debug, Clone)]
pub struct FacetedResult {
    /// Faces straight off the mesh import, before merging.
    pub faces_imported: u64,
    /// Faces after same-domain merging.
    pub faces_unified: u64,
    /// Whether the final solid passes kernel validation with no errors.
    pub valid: bool,
    /// Up to [`MAX_ISSUES`] validation issues, severity-prefixed.
    pub issues: Vec<String>,
    /// The AP203 STEP file.
    pub step: Vec<u8>,
    /// Always [`Tier::Faceted`] here; present so callers handle every tier
    /// uniformly once the analytic tier lands.
    pub tier: Tier,
}

fn face_count(topo: &Topology, solid: SolidId) -> u64 {
    remus_topology::explorer::solid_faces(topo, solid).map_or(0, |f| f.len() as u64)
}

fn issues_of(report: &ValidationReport) -> Vec<String> {
    report
        .issues
        .iter()
        .take(MAX_ISSUES)
        .map(|i| {
            let sev = match i.severity {
                Severity::Error => "error",
                Severity::Warning => "warn",
            };
            let one_line = i.description.replace('\n', " ");
            format!("{sev}: {one_line}")
        })
        .collect()
}

/// Lift a triangle mesh to a STEP solid at the faceted tier.
///
/// The chain is `import_mesh` → validate → `unify_faces` → validate →
/// `write_step`.
///
/// `heal_solid` is deliberately **not** in the chain. On faceted input it opens
/// or splits closed shells: 69 of the 111 corpus solids that import as valid
/// come out of healing invalid (38 with boundary edges, 31 failing Euler).
/// Filed as esaueng/remus#244; re-measure with the corpus scoreboard before
/// putting it back.
///
/// # Errors
///
/// - [`CoreError::Budget`] when the mesh exceeds `options.triangle_budget`.
/// - [`CoreError::Import`] when the mesh cannot be lifted to a solid.
/// - [`CoreError::Kernel`] when validation, unification or STEP writing fails.
///
/// An invalid — but produced — solid is *not* an error: it comes back with
/// `valid: false` and its issues, because a scoreboard needs to see the
/// difference between "the kernel refused" and "the kernel produced something
/// questionable".
pub fn faceted_step(mesh: &MeshData, options: &FacetedOptions) -> Result<FacetedResult> {
    if mesh.triangles > options.triangle_budget {
        return Err(CoreError::Budget {
            triangles: mesh.triangles,
            limit: options.triangle_budget,
        });
    }

    let mut topo = Topology::new();
    let solid = remus_io::stl::import::import_mesh(&mut topo, &mesh.mesh, options.tolerance)
        .map_err(|e| CoreError::Import(e.to_string()))?;
    let faces_imported = face_count(&topo, solid);

    // Validated before unifying as well, so a regression can be attributed to
    // the import or to the merge rather than to "somewhere in the chain".
    remus_operations::validate::validate_solid(&topo, solid)
        .map_err(|e| CoreError::Kernel(format!("validate after import: {e}")))?;

    remus_operations::heal::unify_faces(&mut topo, solid)
        .map_err(|e| CoreError::Kernel(format!("unify_faces: {e}")))?;
    let faces_unified = face_count(&topo, solid);

    let report = remus_operations::validate::validate_solid(&topo, solid)
        .map_err(|e| CoreError::Kernel(format!("validate after unify: {e}")))?;

    let step = remus_io::step::writer::write_step(&topo, &[solid])
        .map_err(|e| CoreError::Kernel(format!("write_step: {e}")))?;

    Ok(FacetedResult {
        faces_imported,
        faces_unified,
        valid: report.is_valid(),
        issues: issues_of(&report),
        step: step.into_bytes(),
        tier: Tier::Faceted,
    })
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod tests {
    use super::*;
    use crate::mesh::{MeshFormat, load_mesh};

    /// Build binary STL bytes: 80-byte header, u32 count, then 50 bytes per
    /// triangle (normal + three vertices as f32, plus a u16 attribute word).
    fn binary_stl(tris: &[([f64; 3], [[f64; 3]; 3])]) -> Vec<u8> {
        let mut out = vec![0_u8; 80];
        out.extend_from_slice(&u32::try_from(tris.len()).unwrap().to_le_bytes());
        for (normal, verts) in tris {
            for c in normal {
                out.extend_from_slice(&(*c as f32).to_le_bytes());
            }
            for v in verts {
                for c in v {
                    out.extend_from_slice(&(*c as f32).to_le_bytes());
                }
            }
            out.extend_from_slice(&0_u16.to_le_bytes());
        }
        out
    }

    /// STL coordinates are f32, so a bbox read back from one is only ever
    /// f32-exact; compare through a tolerance rather than bit-for-bit.
    fn assert_close(actual: [f64; 3], expected: [f64; 3]) {
        for axis in 0..3 {
            assert!(
                (actual[axis] - expected[axis]).abs() < 1e-9,
                "axis {axis}: {actual:?} != {expected:?}"
            );
        }
    }

    /// Unit tetrahedron on the origin corner, outward normals, consistent winding.
    fn tetrahedron_stl() -> Vec<u8> {
        let a = [0.0, 0.0, 0.0];
        let b = [1.0, 0.0, 0.0];
        let c = [0.0, 1.0, 0.0];
        let d = [0.0, 0.0, 1.0];
        let s = 1.0 / 3.0_f64.sqrt();
        binary_stl(&[
            ([0.0, 0.0, -1.0], [a, c, b]),
            ([0.0, -1.0, 0.0], [a, b, d]),
            ([-1.0, 0.0, 0.0], [a, d, c]),
            ([s, s, s], [b, c, d]),
        ])
    }

    #[test]
    fn tetrahedron_produces_a_valid_step_solid() {
        let mesh = load_mesh(&tetrahedron_stl(), MeshFormat::Stl).unwrap();
        assert_eq!(mesh.triangles, 4);
        assert_close(mesh.bbox.min, [0.0, 0.0, 0.0]);
        assert_close(mesh.bbox.max, [1.0, 1.0, 1.0]);

        let result = faceted_step(&mesh, &FacetedOptions::default()).unwrap();
        assert_eq!(result.tier, Tier::Faceted);
        assert_eq!(result.faces_imported, 4);
        assert!(result.valid, "issues: {:?}", result.issues);
        assert!(
            result.step.starts_with(b"ISO-10303-21"),
            "STEP header is {:?}",
            String::from_utf8_lossy(&result.step[..result.step.len().min(32)])
        );
    }

    #[test]
    fn budget_is_enforced_before_any_kernel_work() {
        let mesh = load_mesh(&tetrahedron_stl(), MeshFormat::Stl).unwrap();
        let options = FacetedOptions {
            triangle_budget: 3,
            ..FacetedOptions::default()
        };
        assert!(matches!(
            faceted_step(&mesh, &options),
            Err(CoreError::Budget {
                triangles: 4,
                limit: 3
            })
        ));
    }

    #[test]
    fn non_stl_formats_are_reported_as_unsupported() {
        assert!(matches!(
            load_mesh(b"", MeshFormat::Obj),
            Err(CoreError::Unsupported(MeshFormat::Obj))
        ));
    }
}
