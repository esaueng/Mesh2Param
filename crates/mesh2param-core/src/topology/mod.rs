//! Topology recovery: recognised patches in, a vertex/edge/loop skeleton out.
//!
//! This is the third rung of the Phase 1 ladder. [`crate::segment`] says which
//! triangles lie on which analytic surface; this stage says where those
//! surfaces *meet*, which is what face construction needs before it can build
//! a single trimmed face.
//!
//! # The stages
//!
//! 1. **Adjacency and chains.** A mesh edge whose two triangles belong to
//!    different patches is a boundary edge. Boundary edges are grouped by the
//!    unordered patch pair they separate and linked into ordered chains of
//!    mesh vertices. A chain ends where a vertex touches three or more
//!    patches, or closes on itself into a ring.
//! 2. **Vertices.** Every chain endpoint becomes a [`Vertex`]. When all its
//!    incident patches are analytic the point is refined by Gauss-Newton onto
//!    the intersection of those surfaces, and the refinement is kept only if
//!    it moves less than [`TopologyOptions::vertex_snap_factor`] tolerances.
//! 3. **Edge curves.** Between two analytic patches the chain is replaced by
//!    the real surface-surface intersection curve, trimmed to the chain. Two
//!    surfaces that meet tangentially (a fillet running out into its wall)
//!    have no well-conditioned intersection and take the fallback instead.
//! 4. **Loops.** Each patch's incident edges are chained into oriented closed
//!    loops. Which loop is outer is *not* decided here.
//!
//! Nothing is built: this stage is still description, not construction.
//!
//! # Example
//!
//! ```no_run
//! use mesh2param_core::{
//!     MeshFormat, SegmentOptions, TopologyOptions, load_mesh, recover, segment,
//! };
//!
//! # fn main() -> Result<(), mesh2param_core::CoreError> {
//! # let bytes: Vec<u8> = Vec::new();
//! let mesh = load_mesh(&bytes, MeshFormat::Stl)?;
//! let seg = segment(&mesh, &SegmentOptions::default())?;
//! let topo = recover(&mesh, &seg, &TopologyOptions::default())?;
//! println!("{} edges, {} tangent", topo.summary.edges, topo.summary.tangent_edges);
//! # Ok(())
//! # }
//! ```

mod chains;
mod curve;
mod loops;
mod surf;
#[cfg(test)]
mod tests;

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};
use crate::mesh::MeshData;
use crate::segment::Segmentation;
use crate::segment::linalg::{V3, solve_small};

/// Knobs for [`recover`].
///
/// Every length is a multiple of one absolute tolerance, which defaults to the
/// tolerance the segmentation was run at ([`Segmentation::tolerance`]) so the
/// two stages agree on what "the same point" means.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TopologyOptions {
    /// Absolute tolerance. `None` takes [`Segmentation::tolerance`].
    pub tolerance: Option<f64>,

    /// How far, in tolerances, a Gauss-Newton refined vertex may move from the
    /// mesh vertex it started at before the refinement is rejected.
    ///
    /// A corner where three fitted surfaces meet is more accurate than the
    /// tessellated corner, but only while the fits are right: a refinement
    /// that runs away is a sign that one of the three surfaces is wrong, and
    /// the mesh vertex is then the safer answer.
    pub vertex_snap_factor: f64,

    /// Below this angle between the two surface normals along a chain, the
    /// two patches are treated as **tangent** and no intersection is
    /// attempted, in degrees.
    ///
    /// Two tangent surfaces intersect in a curve whose position is
    /// ill-conditioned — a fillet running out into its wall moves by the
    /// square root of the fit error — so an intersection there is worse than
    /// the mesh's own samples.
    pub tangent_angle_deg: f64,

    /// How far, in tolerances, the chain samples may sit off an intersection
    /// curve before that curve is rejected as "not the branch this chain is
    /// on".
    pub edge_fit_factor: f64,

    /// Seed-grid resolution handed to the kernel's marching intersection.
    pub grid_res: usize,

    /// Cap on Gauss-Newton iterations per vertex.
    pub refine_iterations: usize,
}

impl Default for TopologyOptions {
    fn default() -> Self {
        Self {
            tolerance: None,
            vertex_snap_factor: 3.0,
            tangent_angle_deg: 5.0,
            edge_fit_factor: 2.0,
            grid_res: 16,
            refine_iterations: 12,
        }
    }
}

/// The geometry of a recovered edge, in the mesh's own coordinates.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Curve {
    /// A straight segment.
    Line {
        /// First endpoint.
        start: [f64; 3],
        /// Second endpoint.
        end: [f64; 3],
    },
    /// A circular arc, or a full circle when `end_angle - start_angle` is a
    /// full turn.
    ///
    /// Angles are measured in the frame the kernel derives from `axis` alone —
    /// the frame `Circle3D::new(center, axis, radius)` builds — so a consumer
    /// that rebuilds the circle from these five numbers reproduces the same
    /// parameterisation. `end_angle` is always greater than `start_angle`; the
    /// arc runs counter-clockwise about `axis`.
    #[serde(rename_all = "camelCase")]
    Circle {
        /// Centre.
        center: [f64; 3],
        /// Unit axis; the arc runs counter-clockwise about it.
        axis: [f64; 3],
        /// Radius.
        radius: f64,
        /// Start angle in radians.
        start_angle: f64,
        /// End angle in radians, always above `start_angle`.
        end_angle: f64,
    },
    /// An ordered point chain. A closed one repeats its first point last.
    Polyline {
        /// The points.
        points: Vec<[f64; 3]>,
    },
}

/// Where an edge's curve came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EdgeSource {
    /// A closed-form surface-surface intersection: an exact line or circle.
    Analytic,
    /// The two patches meet tangentially, so no intersection was attempted.
    Tangent,
    /// No intersection was available or none matched the chain: the mesh
    /// samples, projected onto an analytic side when there is one.
    Fallback,
    /// A real intersection the kernel could only produce as samples (an
    /// ellipse, a marched quartic): kept as a polyline for now.
    Marching,
}

/// A point where three or more patches meet.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Vertex {
    /// Index of this vertex in [`Topology::vertices`].
    pub id: u32,
    /// Position.
    pub point: [f64; 3],
    /// Patch ids meeting here, ascending.
    pub patches: Vec<u32>,
    /// Whether Gauss-Newton refinement was accepted. `false` means the point
    /// is the mesh vertex as welded.
    pub refined: bool,
}

/// One recovered edge: the curve two patches meet along.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Edge {
    /// Index of this edge in [`Topology::edges`].
    pub id: u32,
    /// The two patches this edge separates, ascending.
    pub patches: (u32, u32),
    /// Start and end vertex ids. `None` for a ring: a closed edge with no
    /// vertex on it, which is what a full cylinder's rim is.
    pub vertices: Option<(u32, u32)>,
    /// The geometry.
    pub curve: Curve,
    /// Whether the two patches meet tangentially here.
    pub tangent: bool,
    /// Where [`Self::curve`] came from.
    pub source: EdgeSource,
    /// RMS distance from the chain's mesh samples to [`Self::curve`].
    pub rms_deviation: f64,
    /// Largest single-sample distance to the same curve.
    pub max_deviation: f64,
    /// How many mesh vertices the chain had.
    pub samples: usize,
}

/// An oriented loop of edges on one patch.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Loop {
    /// Edge ids with a traversal flag: `true` runs from the edge's first
    /// vertex to its second.
    pub edges: Vec<(u32, bool)>,
    /// Whether the walk returned to where it started.
    pub closed: bool,
}

/// The loops found on one patch.
///
/// Which loop is the outer one is deliberately not decided here: that needs
/// the face's own surface parameterisation, which is the next rung's job.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PatchLoops {
    /// The patch.
    pub patch: u32,
    /// Its loops, in discovery order.
    pub loops: Vec<Loop>,
    /// How many of them failed to close.
    pub open_loops: usize,
}

/// Totals for one [`recover`] run.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TopologySummary {
    /// Edges recovered.
    pub edges: usize,
    /// Edges whose curve came from a real surface-surface intersection:
    /// [`EdgeSource::Analytic`] plus [`EdgeSource::Marching`].
    pub analytic_edges: usize,
    /// Edges marked tangent.
    pub tangent_edges: usize,
    /// Edges that fell back to the mesh samples.
    pub fallback_edges: usize,
    /// Vertices whose Gauss-Newton refinement was accepted.
    pub vertices_refined: usize,
    /// Patches all of whose loops closed.
    pub patches_closed: usize,
    /// Patches with at least one open loop.
    pub patches_open: usize,
    /// Largest [`Edge::max_deviation`] over all edges. Zero with no edges.
    pub max_edge_deviation: f64,
}

/// The result of [`recover`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Topology {
    /// Vertices, ordered by first discovery.
    pub vertices: Vec<Vertex>,
    /// Edges, ordered by patch pair then discovery.
    pub edges: Vec<Edge>,
    /// Loops per patch, one entry per patch in [`Segmentation::patches`].
    pub patch_loops: Vec<PatchLoops>,
    /// Totals.
    pub summary: TopologySummary,
}

fn check(value: f64, name: &str) -> Result<()> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(CoreError::Validation(format!(
            "topology option {name} must be finite and positive, got {value}"
        )))
    }
}

/// Recover the vertex/edge/loop skeleton implied by a segmentation.
///
/// # Errors
///
/// - [`CoreError::Validation`] when an option is not a finite positive number,
///   when the derived tolerance is not usable, or when `seg` does not describe
///   the same mesh (its `face_patch` has to be one entry per welded triangle).
pub fn recover(mesh: &MeshData, seg: &Segmentation, options: &TopologyOptions) -> Result<Topology> {
    check(options.vertex_snap_factor, "vertexSnapFactor")?;
    check(options.tangent_angle_deg, "tangentAngleDeg")?;
    check(options.edge_fit_factor, "edgeFitFactor")?;
    if options.grid_res < 2 {
        return Err(CoreError::Validation(format!(
            "topology option gridRes must be at least 2, got {}",
            options.grid_res
        )));
    }

    let tol = options.tolerance.unwrap_or(seg.tolerance);
    check(tol, "tolerance")?;

    let welded = mesh.welded()?;
    if seg.face_patch.len() != welded.triangles.len() {
        return Err(CoreError::Validation(format!(
            "segmentation covers {} faces but the welded mesh has {}",
            seg.face_patch.len(),
            welded.triangles.len()
        )));
    }

    let adjacency = chains::build(&welded, &seg.face_patch, seg.patches.len());
    let surfaces: Vec<Option<surf::Surface>> = seg
        .patches
        .iter()
        .map(|p| surf::surface_of(p.primitive))
        .collect();

    let points: Vec<V3> = welded.positions.iter().map(|p| V3::from_arr(*p)).collect();

    let (vertices, vertex_of_mesh) =
        build_vertices(&adjacency, &points, seg, &surfaces, tol, options);

    let mut edges = Vec::with_capacity(adjacency.chains.len());
    for chain in &adjacency.chains {
        let samples: Vec<V3> = chain
            .verts
            .iter()
            .filter_map(|v| points.get(*v as usize).copied())
            .collect();
        let ends = if chain.closed {
            None
        } else {
            match (chain.verts.first(), chain.verts.last()) {
                (Some(a), Some(b)) => match (vertex_of_mesh.get(a), vertex_of_mesh.get(b)) {
                    (Some(&ia), Some(&ib)) => Some((ia, ib)),
                    _ => None,
                },
                _ => None,
            }
        };
        let end_points = ends.map(|(a, b)| {
            (
                vertices
                    .get(a as usize)
                    .map_or(V3::ZERO, |v| V3::from_arr(v.point)),
                vertices
                    .get(b as usize)
                    .map_or(V3::ZERO, |v| V3::from_arr(v.point)),
            )
        });

        let built = curve::build(curve::Request {
            samples: &samples,
            closed: chain.closed,
            ends: end_points,
            a: seg
                .patches
                .get(chain.patches.0 as usize)
                .map(|p| p.primitive),
            b: seg
                .patches
                .get(chain.patches.1 as usize)
                .map(|p| p.primitive),
            surface_a: surfaces
                .get(chain.patches.0 as usize)
                .and_then(Option::as_ref),
            surface_b: surfaces
                .get(chain.patches.1 as usize)
                .and_then(Option::as_ref),
            tol,
            options,
        });

        edges.push(Edge {
            id: edges.len() as u32,
            patches: chain.patches,
            vertices: ends,
            curve: built.curve,
            tangent: built.tangent,
            source: built.source,
            rms_deviation: built.rms,
            max_deviation: built.max,
            samples: samples.len(),
        });
    }

    let patch_loops = loops::assemble(&edges, seg.patches.len());

    let mut summary = TopologySummary {
        edges: edges.len(),
        vertices_refined: vertices.iter().filter(|v| v.refined).count(),
        ..TopologySummary::default()
    };
    for e in &edges {
        match e.source {
            EdgeSource::Analytic | EdgeSource::Marching => summary.analytic_edges += 1,
            EdgeSource::Tangent => summary.tangent_edges += 1,
            EdgeSource::Fallback => summary.fallback_edges += 1,
        }
        if e.max_deviation.is_finite() && e.max_deviation > summary.max_edge_deviation {
            summary.max_edge_deviation = e.max_deviation;
        }
    }
    for pl in &patch_loops {
        if pl.open_loops == 0 {
            summary.patches_closed += 1;
        } else {
            summary.patches_open += 1;
        }
    }

    Ok(Topology {
        vertices,
        edges,
        patch_loops,
        summary,
    })
}

/// Chain endpoints become vertices; the ones surrounded by analytic patches
/// are refined onto the intersection of those surfaces first, then everything
/// closer together than `tol` is merged.
fn build_vertices(
    adjacency: &chains::Adjacency,
    points: &[V3],
    seg: &Segmentation,
    surfaces: &[Option<surf::Surface>],
    tol: f64,
    options: &TopologyOptions,
) -> (Vec<Vertex>, BTreeMap<u32, u32>) {
    let mut order: Vec<u32> = Vec::new();
    let mut seen: BTreeMap<u32, usize> = BTreeMap::new();
    for chain in &adjacency.chains {
        if chain.closed {
            continue;
        }
        for v in [chain.verts.first(), chain.verts.last()]
            .into_iter()
            .flatten()
        {
            if !seen.contains_key(v) {
                seen.insert(*v, order.len());
                order.push(*v);
            }
        }
    }

    let mut raw: Vec<(V3, Vec<u32>, bool)> = Vec::with_capacity(order.len());
    for &mesh_v in &order {
        let start = points.get(mesh_v as usize).copied().unwrap_or(V3::ZERO);
        let patches: Vec<u32> = adjacency
            .vertex_patches
            .get(mesh_v as usize)
            .map(|s| s.iter().copied().collect())
            .unwrap_or_default();
        let prims: Option<Vec<_>> = patches
            .iter()
            .map(|p| {
                surfaces
                    .get(*p as usize)
                    .and_then(Option::as_ref)
                    .and_then(|_| seg.patches.get(*p as usize).map(|q| q.primitive))
            })
            .collect();
        let refined = prims
            .filter(|p| p.len() >= 3)
            .and_then(|p| refine_vertex(start, &p, tol, options));
        match refined {
            Some(p) => raw.push((p, patches, true)),
            None => raw.push((start, patches, false)),
        }
    }

    merge_vertices(raw, &order, tol)
}

/// Gauss-Newton on the sum of squared signed distances to every incident
/// surface. `None` when the system is singular or the step runs further than
/// [`TopologyOptions::vertex_snap_factor`] tolerances.
fn refine_vertex(
    start: V3,
    prims: &[crate::segment::Primitive],
    tol: f64,
    options: &TopologyOptions,
) -> Option<V3> {
    let mut p = start;
    for _ in 0..options.refine_iterations {
        let mut a = [[0.0_f64; 4]; 4];
        let mut rhs = [0.0_f64; 4];
        let mut rows = 0_usize;
        for prim in prims {
            let (f, g) = match (surf::signed_distance(*prim, p), surf::gradient(*prim, p)) {
                (Some(f), Some(g)) => (f, g),
                _ => return None,
            };
            let gv = g.arr();
            for i in 0..3 {
                for j in 0..3 {
                    a[i][j] += gv[i] * gv[j];
                }
                rhs[i] -= f * gv[i];
            }
            rows += 1;
        }
        if rows < 3 {
            return None;
        }
        // Levenberg damping: three coplanar-normal surfaces (a fillet band
        // between two parallel walls) leave the normal equations singular, and
        // an undamped solve there walks the vertex off the part.
        let trace = a[0][0] + a[1][1] + a[2][2];
        if !trace.is_finite() || trace <= 0.0 {
            return None;
        }
        let damp = 1e-9 * trace;
        for i in 0..3 {
            a[i][i] += damp;
        }
        let step = solve_small(3, &a, &rhs)?;
        let delta = V3::new(step[0], step[1], step[2]);
        if !delta.arr().iter().all(|c| c.is_finite()) {
            return None;
        }
        p = p.add(delta);
        if delta.norm() < 1e-12 * tol.max(1.0) {
            break;
        }
    }
    let moved = p.sub(start).norm();
    if moved.is_finite() && moved <= options.vertex_snap_factor * tol {
        Some(p)
    } else {
        None
    }
}

/// Merge raw vertices closer together than `tol` on a uniform hash grid.
fn merge_vertices(
    raw: Vec<(V3, Vec<u32>, bool)>,
    order: &[u32],
    tol: f64,
) -> (Vec<Vertex>, BTreeMap<u32, u32>) {
    let cell = if tol > 0.0 { tol } else { 1.0 };
    let mut grid: BTreeMap<(i64, i64, i64), Vec<u32>> = BTreeMap::new();
    let mut vertices: Vec<Vertex> = Vec::new();
    let mut counts: Vec<f64> = Vec::new();
    let mut map: BTreeMap<u32, u32> = BTreeMap::new();

    for (idx, (point, patches, refined)) in raw.into_iter().enumerate() {
        let k = (
            (point.x / cell).floor() as i64,
            (point.y / cell).floor() as i64,
            (point.z / cell).floor() as i64,
        );
        let mut hit: Option<u32> = None;
        'search: for dx in -1_i64..=1 {
            for dy in -1_i64..=1 {
                for dz in -1_i64..=1 {
                    let Some(bucket) = grid.get(&(k.0 + dx, k.1 + dy, k.2 + dz)) else {
                        continue;
                    };
                    for &id in bucket {
                        let Some(v) = vertices.get(id as usize) else {
                            continue;
                        };
                        if V3::from_arr(v.point).sub(point).norm() <= tol {
                            hit = Some(id);
                            break 'search;
                        }
                    }
                }
            }
        }
        let id = if let Some(id) = hit {
            if let (Some(v), Some(n)) = (vertices.get_mut(id as usize), counts.get_mut(id as usize))
            {
                // Running mean: a merged corner sits between the points that
                // were merged into it, not on whichever one arrived first.
                *n += 1.0;
                let w = 1.0 / *n;
                let mean = V3::from_arr(v.point).mul(1.0 - w).add(point.mul(w));
                v.point = mean.arr();
                for p in patches {
                    if !v.patches.contains(&p) {
                        v.patches.push(p);
                    }
                }
                v.patches.sort_unstable();
                v.refined = v.refined && refined;
            }
            id
        } else {
            let id = vertices.len() as u32;
            vertices.push(Vertex {
                id,
                point: point.arr(),
                patches,
                refined,
            });
            counts.push(1.0);
            grid.entry(k).or_default().push(id);
            id
        };
        if let Some(&mesh_v) = order.get(idx) {
            map.insert(mesh_v, id);
        }
    }
    (vertices, map)
}
