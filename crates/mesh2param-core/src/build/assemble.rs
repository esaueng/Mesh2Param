//! Kernel assembly: vertices, edges, wires, faces, shell.
//!
//! Every topology edge becomes a **run** of kernel edges created exactly once
//! and reused by both adjacent faces, so the two faces share the edge
//! topologically and the shell closes by construction rather than by a
//! geometric guess afterwards.

use std::collections::{BTreeMap, HashMap, HashSet};

use remus_math::curves::Circle3D;
use remus_math::nurbs::fitting::interpolate;
use remus_math::surfaces::{ConicalSurface, CylindricalSurface, SphericalSurface, ToroidalSurface};
use remus_math::vec::{Point3, Vec3};
use remus_topology::Topology as KernelTopology;
use remus_topology::edge::{Edge as KernelEdge, EdgeCurve, EdgeId};
use remus_topology::face::{Face, FaceId, FaceSurface};
use remus_topology::shell::Shell;
use remus_topology::solid::{Solid, SolidId};
use remus_topology::vertex::{Vertex as KernelVertex, VertexId};
use remus_topology::wire::{OrientedEdge, Wire};

use super::geom::{MeshGeom, polygon_normal};
use super::periodic;
use crate::error::{CoreError, Result};
use crate::segment::linalg::V3;
use crate::segment::{Patch, PatchKind, Primitive, Segmentation};
use crate::topology::chains::Chain;
use crate::topology::{Curve, EdgeSource, Topology as PatchTopology};

/// How far, in run tolerances, an arc's end vertex may sit off the circle it
/// is trimmed on before the fitted curve is refused and the mesh chain used
/// instead. The STEP writer refuses an edge whose authoritative parameter
/// misses its vertex, so the edge tolerance has to cover the miss — and a
/// tolerance far above the run's is a fit that is not worth exporting.
const MAX_ARC_ENDPOINT_FACTOR: f64 = 8.0;

/// What an edge's kernel geometry ended up being.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum RunKind {
    /// A single straight edge.
    Line,
    /// A single circular edge, full turn or arc.
    Circle,
    /// A single interpolating NURBS edge.
    Nurbs,
    /// A chain of straight edges through the curve's own points.
    CurveChain,
    /// A chain of straight edges through the mesh boundary vertices.
    MeshChain,
}

/// A patch loop chained into kernel topology.
struct Walked {
    /// The kernel vertex the wire starts and ends at.
    entry: VertexId,
    /// The wire, in the face's outward sense.
    wire: Vec<OrientedEdge>,
    /// The recovered edges it walks, with the direction each is walked in.
    order: Vec<(u32, bool)>,
}

/// A full-turn rim: one closed circular edge carrying its own seam vertex.
#[derive(Debug, Clone, Copy)]
struct Rim {
    /// The kernel vertex the closed edge opens and closes at.
    seam: VertexId,
    /// Where that vertex sits.
    point: V3,
}

/// One of a face's loops as kernel topology, with the rim it is when it is
/// one.
#[derive(Clone)]
struct BuiltLoop {
    /// The area vector of the loop's own mesh polygon, for ranking.
    normal: V3,
    /// The kernel vertex the wire starts and ends at.
    entry: VertexId,
    /// The wire, in the face's outward sense.
    wire: Vec<OrientedEdge>,
    /// Set when the loop is a single full-turn rim of this face's surface.
    rim: Option<Rim>,
}

/// One topology edge as kernel topology, oriented along its chain.
pub(super) struct EdgeRun {
    /// Kernel edges with a traversal flag, in the chain's own direction.
    pub segments: Vec<(EdgeId, bool)>,
    /// Kernel vertex the run starts at, walking forward.
    pub start: VertexId,
    /// Kernel vertex the run ends at, walking forward.
    pub end: VertexId,
    pub kind: RunKind,
}

impl EdgeRun {
    fn oriented(&self, forward: bool) -> Vec<OrientedEdge> {
        if forward {
            self.segments
                .iter()
                .map(|&(e, f)| OrientedEdge::new(e, f))
                .collect()
        } else {
            self.segments
                .iter()
                .rev()
                .map(|&(e, f)| OrientedEdge::new(e, !f))
                .collect()
        }
    }

    const fn entry(&self, forward: bool) -> VertexId {
        if forward { self.start } else { self.end }
    }

    const fn exit(&self, forward: bool) -> VertexId {
        if forward { self.end } else { self.start }
    }
}

/// Everything the assembly reads that does not change between attempts.
pub(super) struct Context<'a> {
    pub geom: &'a MeshGeom,
    pub seg: &'a Segmentation,
    pub patch_topo: &'a PatchTopology,
    pub chains: &'a [Chain],
    /// For each topology edge, the patch whose counter-clockwise traversal
    /// runs along the chain's own vertex order. `None` when the mesh could
    /// not say.
    pub ccw_patch: Vec<Option<u32>>,
    /// Mesh vertex -> topology vertex, for chain endpoints.
    pub mesh_to_topo: HashMap<u32, u32>,
    /// Patches whose every boundary mesh edge is covered by a chain.
    pub fully_chained: Vec<bool>,
    pub tol: f64,
    pub polyline_nurbs: bool,
}

impl<'a> Context<'a> {
    pub(super) fn new(
        geom: &'a MeshGeom,
        seg: &'a Segmentation,
        patch_topo: &'a PatchTopology,
        chains: &'a [Chain],
        tol: f64,
        polyline_nurbs: bool,
    ) -> Result<Self> {
        if chains.len() != patch_topo.edges.len() {
            return Err(CoreError::Validation(format!(
                "topology has {} edges but the mesh yields {} boundary chains",
                patch_topo.edges.len(),
                chains.len()
            )));
        }
        let owner = geom.half_edge_owner();
        let mut ccw_patch = Vec::with_capacity(chains.len());
        let mut mesh_to_topo: HashMap<u32, u32> = HashMap::new();
        for (i, chain) in chains.iter().enumerate() {
            let edge = patch_topo.edges.get(i).ok_or_else(|| {
                CoreError::Validation("topology edge missing for a chain".to_string())
            })?;
            if edge.patches != chain.patches {
                return Err(CoreError::Validation(format!(
                    "topology edge {i} separates {:?} but its chain separates {:?}",
                    edge.patches, chain.patches
                )));
            }
            let owner_patch = match (chain.verts.first(), chain.verts.get(1)) {
                (Some(&a), Some(&b)) => owner
                    .get(&(a, b))
                    .and_then(|&t| seg.face_patch.get(t as usize).copied())
                    .filter(|p| *p == chain.patches.0 || *p == chain.patches.1),
                _ => None,
            };
            ccw_patch.push(owner_patch);
            if let (Some(&first), Some(&last), Some((va, vb))) =
                (chain.verts.first(), chain.verts.last(), edge.vertices)
            {
                mesh_to_topo.insert(first, va);
                mesh_to_topo.insert(last, vb);
            }
        }

        let fully_chained = fully_chained(geom, seg, chains);

        Ok(Self {
            geom,
            seg,
            patch_topo,
            chains,
            ccw_patch,
            mesh_to_topo,
            fully_chained,
            tol,
            polyline_nurbs,
        })
    }

    /// Whether a patch can be attempted as a single analytic face at all.
    ///
    /// The four gates are the ones a face cannot be built without: a
    /// recognised surface, a boundary that closes, a boundary the chain
    /// builder actually covered, and an orientation the mesh could give.
    pub(super) fn eligible(&self, patch: &Patch) -> Option<&'static str> {
        if patch.kind == PatchKind::Unknown {
            return Some("patch is unknown");
        }
        let Some(loops) = self.patch_topo.patch_loops.get(patch.id as usize) else {
            return Some("no loops recovered");
        };
        // A surface closed in both parameter directions has no boundary to
        // recover: a whole doughnut is one face bounded by a fundamental
        // polygon, not by any loop the mesh can hand over.
        if loops.loops.is_empty() && !periodic::is_closed_periodic(patch.primitive) {
            return Some("no loops recovered");
        }
        if loops.open_loops > 0 {
            return Some("open loop");
        }
        if !self
            .fully_chained
            .get(patch.id as usize)
            .copied()
            .unwrap_or(false)
        {
            return Some("boundary not fully chained");
        }
        for l in &loops.loops {
            for &(eid, _) in &l.edges {
                if self
                    .ccw_patch
                    .get(eid as usize)
                    .copied()
                    .flatten()
                    .is_none()
                {
                    return Some("edge orientation unknown");
                }
            }
        }
        if surface_of(patch.primitive, false).is_none() {
            return Some("surface construction refused");
        }
        None
    }
}

/// A patch is only a face candidate when every boundary mesh edge it owns was
/// turned into a chain. `chains::build` skips a mesh edge with three or more
/// patches on it, and a face built without that stretch of its boundary is a
/// hole in the shell, not a face.
fn fully_chained(geom: &MeshGeom, seg: &Segmentation, chains: &[Chain]) -> Vec<bool> {
    let mut covered: HashSet<(u32, u32)> = HashSet::new();
    for chain in chains {
        let n = chain.verts.len();
        let last = if chain.closed { n } else { n.saturating_sub(1) };
        for k in 0..last {
            let a = chain.verts[k];
            let b = chain.verts[(k + 1) % n];
            covered.insert(if a < b { (a, b) } else { (b, a) });
        }
    }
    let mut ok = vec![true; seg.patches.len()];
    let mut owners: HashMap<(u32, u32), Vec<u32>> = HashMap::new();
    for (fi, t) in geom.triangles.iter().enumerate() {
        let Some(&patch) = seg.face_patch.get(fi) else {
            continue;
        };
        for k in 0..3 {
            let (a, b) = (t[k], t[(k + 1) % 3]);
            owners
                .entry(if a < b { (a, b) } else { (b, a) })
                .or_default()
                .push(patch);
        }
    }
    for (edge, patches) in &owners {
        let mut distinct: Vec<u32> = patches.clone();
        distinct.sort_unstable();
        distinct.dedup();
        let is_boundary = distinct.len() > 1 || patches.len() != 2;
        if is_boundary && !covered.contains(edge) {
            for p in distinct {
                if let Some(slot) = ok.get_mut(p as usize) {
                    *slot = false;
                }
            }
        }
    }
    ok
}

/// One assembly attempt over a chosen set of analytic patches.
pub(super) struct Attempt {
    pub topo: KernelTopology,
    pub solid: SolidId,
    pub faces_analytic: usize,
    pub faces_triangle: usize,
    /// Patches whose face construction failed, with the reason.
    pub demoted: Vec<(u32, &'static str)>,
    /// Kernel face index -> the patch it came from.
    pub face_patch: HashMap<usize, u32>,
    /// How many edges came out as each kind.
    pub runs_nurbs: usize,
    pub runs_curve_chain: usize,
    /// Triangles dropped because two of their corners merged to one vertex.
    pub dropped_triangles: usize,
}

pub(super) fn attempt(ctx: &Context<'_>, analytic: &[bool]) -> Result<Attempt> {
    let mut b = Builder::new(ctx);
    b.build_runs(analytic);

    let mut faces: Vec<FaceId> = Vec::new();
    let mut demoted = Vec::new();
    let mut faces_analytic = 0_usize;
    let mut triangulate: Vec<u32> = Vec::new();

    for patch in &ctx.seg.patches {
        if !analytic.get(patch.id as usize).copied().unwrap_or(false) {
            triangulate.push(patch.id);
            continue;
        }
        match b.analytic_face(patch) {
            Ok(fid) => {
                faces.push(fid);
                faces_analytic += 1;
            }
            Err(reason) => {
                demoted.push((patch.id, reason));
                triangulate.push(patch.id);
            }
        }
    }

    let mut faces_triangle = 0_usize;
    for patch in triangulate {
        let added = b.triangle_faces(patch);
        faces_triangle += added.len();
        faces.extend(added);
    }

    if faces.is_empty() {
        return Err(CoreError::Import("no faces could be built".to_string()));
    }

    let Builder {
        mut topo,
        face_patch,
        runs_nurbs,
        runs_curve_chain,
        dropped_triangles,
        ..
    } = b;
    let shell = Shell::new(faces).map_err(|e| CoreError::Kernel(format!("shell: {e}")))?;
    let shell_id = topo.add_shell(shell);
    let solid = topo.add_solid(Solid::new(shell_id, Vec::new()));

    Ok(Attempt {
        topo,
        solid,
        faces_analytic,
        faces_triangle,
        demoted,
        face_patch,
        runs_nurbs,
        runs_curve_chain,
        dropped_triangles,
    })
}

struct Builder<'a> {
    ctx: &'a Context<'a>,
    topo: KernelTopology,
    /// Topology vertex -> kernel vertex.
    topo_vertex: Vec<Option<VertexId>>,
    /// Mesh vertex -> kernel vertex, for points that are not corners.
    mesh_vertex: HashMap<u32, VertexId>,
    /// Canonical kernel vertex pair -> the straight edge between them.
    straight: HashMap<(usize, usize), EdgeId>,
    /// Topology edge -> its kernel run, when one could be built.
    runs: Vec<Option<EdgeRun>>,
    face_patch: HashMap<usize, u32>,
    runs_nurbs: usize,
    runs_curve_chain: usize,
    dropped_triangles: usize,
}

impl<'a> Builder<'a> {
    fn new(ctx: &'a Context<'a>) -> Self {
        Self {
            ctx,
            topo: KernelTopology::new(),
            topo_vertex: vec![None; ctx.patch_topo.vertices.len()],
            mesh_vertex: HashMap::new(),
            straight: HashMap::new(),
            runs: Vec::new(),
            face_patch: HashMap::new(),
            runs_nurbs: 0,
            runs_curve_chain: 0,
            dropped_triangles: 0,
        }
    }

    fn add_vertex(&mut self, p: V3) -> VertexId {
        self.topo
            .add_vertex(KernelVertex::new(point(p), self.ctx.tol))
    }

    fn topo_vertex_of(&mut self, id: u32) -> Option<VertexId> {
        if let Some(Some(v)) = self.topo_vertex.get(id as usize) {
            return Some(*v);
        }
        let p = V3::from_arr(self.ctx.patch_topo.vertices.get(id as usize)?.point);
        let v = self.add_vertex(p);
        *self.topo_vertex.get_mut(id as usize)? = Some(v);
        Some(v)
    }

    /// The kernel vertex for a welded mesh vertex: the shared corner when the
    /// topology promoted it to one, a fresh vertex at the mesh point
    /// otherwise.
    fn mesh_vertex_of(&mut self, v: u32) -> VertexId {
        if let Some(&t) = self.ctx.mesh_to_topo.get(&v)
            && let Some(id) = self.topo_vertex_of(t)
        {
            return id;
        }
        if let Some(&id) = self.mesh_vertex.get(&v) {
            return id;
        }
        let p = self
            .ctx
            .geom
            .points
            .get(v as usize)
            .copied()
            .unwrap_or(V3::ZERO);
        let id = self.add_vertex(p);
        self.mesh_vertex.insert(v, id);
        id
    }

    /// The straight edge for one **mesh** edge, created once and shared.
    ///
    /// Keyed on the **kernel vertices** the mesh edge resolves to, not on the
    /// mesh edge itself. Topology recovery merges corners inside one
    /// tolerance, so two distinct mesh edges can end up between the same pair
    /// of kernel vertices; keeping them apart there leaves a pinched pair of
    /// edges the faces around them do not both reach, and the corpus loses
    /// eight parts to open shells. Sharing the edge keeps the shell closed and
    /// costs a non-manifold edge use instead, which is the cheaper of the two.
    ///
    /// Only mesh edges go through this cache at all: fitted geometry is owned
    /// by the recovered edge that produced it, because two recovered edges can
    /// legitimately join the same two corners.
    fn mesh_edge(&mut self, a: u32, b: u32) -> Option<(EdgeId, bool)> {
        let (va, vb) = (self.mesh_vertex_of(a), self.mesh_vertex_of(b));
        if va == vb {
            return None;
        }
        let forward = va.index() <= vb.index();
        let key = if forward {
            (va.index(), vb.index())
        } else {
            (vb.index(), va.index())
        };
        if let Some(&e) = self.straight.get(&key) {
            return Some((e, forward));
        }
        let (lo, hi) = if forward { (va, vb) } else { (vb, va) };
        let e = self.topo.add_edge(KernelEdge::new(lo, hi, EdgeCurve::Line));
        self.straight.insert(key, e);
        Some((e, forward))
    }

    /// A straight edge owned by one recovered edge, never shared by identity.
    fn own_edge(&mut self, a: VertexId, b: VertexId) -> Option<(EdgeId, bool)> {
        if a == b {
            return None;
        }
        let forward = a.index() <= b.index();
        let (lo, hi) = if forward { (a, b) } else { (b, a) };
        Some((
            self.topo.add_edge(KernelEdge::new(lo, hi, EdgeCurve::Line)),
            forward,
        ))
    }

    fn build_runs(&mut self, analytic: &[bool]) {
        self.runs = Vec::with_capacity(self.ctx.chains.len());
        for i in 0..self.ctx.chains.len() {
            let both_analytic = self.ctx.patch_topo.edges.get(i).is_some_and(|e| {
                [e.patches.0, e.patches.1]
                    .iter()
                    .all(|p| analytic.get(*p as usize).copied().unwrap_or(false))
            });
            let run = if both_analytic {
                self.fitted_run(i).or_else(|| self.mesh_run(i))
            } else {
                self.mesh_run(i)
            };
            match run.as_ref().map(|r| r.kind) {
                Some(RunKind::Nurbs) => self.runs_nurbs += 1,
                Some(RunKind::CurveChain) => self.runs_curve_chain += 1,
                _ => {}
            }
            self.runs.push(run);
        }
    }

    /// A run of straight edges through the chain's own mesh vertices.
    ///
    /// This is what an edge has to be whenever either side is emitted as
    /// triangles: the triangles bound themselves with the mesh polygon, so the
    /// analytic neighbour has to bound itself with the same one or the shell
    /// has a slit down that boundary.
    fn mesh_run(&mut self, index: usize) -> Option<EdgeRun> {
        let chain = self.ctx.chains.get(index)?;
        let n = chain.verts.len();
        if n < 2 {
            return None;
        }
        let count = if chain.closed { n } else { n - 1 };
        let mut segments = Vec::with_capacity(count);
        let start = self.mesh_vertex_of(chain.verts[0]);
        let mut previous_mesh = chain.verts[0];
        let mut previous = start;
        for k in 1..=count {
            let mesh_v = chain.verts[k % n];
            if let Some(seg) = self.mesh_edge(previous_mesh, mesh_v) {
                segments.push(seg);
                previous = self.mesh_vertex_of(mesh_v);
            }
            previous_mesh = mesh_v;
        }
        if segments.is_empty() {
            return None;
        }
        Some(EdgeRun {
            segments,
            start,
            end: previous,
            kind: RunKind::MeshChain,
        })
    }

    /// The fitted curve as kernel topology. `None` sends the caller to the
    /// mesh chain.
    fn fitted_run(&mut self, index: usize) -> Option<EdgeRun> {
        let edge = self.ctx.patch_topo.edges.get(index)?;
        let chain = self.ctx.chains.get(index)?;
        match &edge.curve {
            Curve::Line { .. } => {
                let (a, b) = edge.vertices?;
                let (va, vb) = (self.topo_vertex_of(a)?, self.topo_vertex_of(b)?);
                let seg = self.own_edge(va, vb)?;
                Some(EdgeRun {
                    segments: vec![seg],
                    start: va,
                    end: vb,
                    kind: RunKind::Line,
                })
            }
            Curve::Circle {
                center,
                axis,
                radius,
                start_angle,
                end_angle,
            } => self.circle_run(index, *center, *axis, *radius, *start_angle, *end_angle),
            Curve::Polyline { points } => {
                let pts: Vec<V3> = points.iter().map(|p| V3::from_arr(*p)).collect();
                // A rim the marcher could only sample is still a rim: read the
                // circle back out of it rather than laying a thousand straight
                // edges down the boundary of a periodic face. Only a marched
                // ring — a real intersection with no closed form — is read
                // back; a ring that fell back to the mesh's own samples is the
                // mesh's answer and stays it.
                if edge.vertices.is_none()
                    && edge.source == EdgeSource::Marching
                    && let Some((center, axis, radius)) =
                        periodic::ring_as_circle(&pts, self.ctx.tol)
                    && self.rim_needs_marching(edge.patches, center, axis, radius)
                    && let Ok(circle) = Circle3D::new(point(center), vector(axis), radius)
                    && let Some(run) = self.rim_edge(chain, circle)
                {
                    return Some(run);
                }
                self.polyline_run(&pts, chain.closed, edge.vertices)
            }
        }
    }

    fn circle_run(
        &mut self,
        index: usize,
        center: [f64; 3],
        axis: [f64; 3],
        radius: f64,
        start_angle: f64,
        end_angle: f64,
    ) -> Option<EdgeRun> {
        let span = end_angle - start_angle;
        if !span.is_finite() || span <= 0.0 || span > std::f64::consts::TAU {
            return None;
        }
        let circle = Circle3D::new(
            point(V3::from_arr(center)),
            vector(V3::from_arr(axis)),
            radius,
        )
        .ok()?;
        let edge = self.ctx.patch_topo.edges.get(index)?;
        let chain = self.ctx.chains.get(index)?;

        match edge.vertices {
            None => self.rim_edge(chain, circle),
            Some((a, b)) => {
                let (va, vb) = (self.topo_vertex_of(a)?, self.topo_vertex_of(b)?);
                if va == vb {
                    return None;
                }
                let pa = V3::from_arr(self.ctx.patch_topo.vertices.get(a as usize)?.point);
                let pb = V3::from_arr(self.ctx.patch_topo.vertices.get(b as usize)?.point);
                let at_start = from_point(circle.evaluate(start_angle));
                let at_end = from_point(circle.evaluate(end_angle));
                // The trim's own start may be either end vertex; the kernel
                // edge is built to match, and the run records which way that
                // leaves it pointing.
                let forward = at_start.sub(pa).norm() <= at_start.sub(pb).norm();
                let (v0, v1, p0, p1) = if forward {
                    (va, vb, pa, pb)
                } else {
                    (vb, va, pb, pa)
                };
                let residual = at_start.sub(p0).norm().max(at_end.sub(p1).norm());
                if !residual.is_finite() || residual > MAX_ARC_ENDPOINT_FACTOR * self.ctx.tol {
                    return None;
                }
                let tol = self.ctx.tol.max(residual * 1.5);
                let mut e =
                    KernelEdge::with_tolerance(v0, v1, EdgeCurve::Circle(circle), Some(tol));
                e.set_trim(Some((start_angle, end_angle)));
                let eid = self.topo.add_edge(e);
                Some(EdgeRun {
                    segments: vec![(eid, forward)],
                    start: va,
                    end: vb,
                    kind: RunKind::Circle,
                })
            }
        }
    }

    /// Whether a marched ring is a rim the marcher was the **only** route to.
    ///
    /// Both sides have to be quadrics, and the circle has to be a rim of one
    /// of them. A plane against a quadric has a closed-form arm
    /// (`exact_plane_analytic_bounded`, which returns the circle directly), so
    /// a plane-bounded ring that came back marched is one where that arm was
    /// tried and *rejected* — the fit disagreed with the chain — and the
    /// samples are then the better answer than any circle drawn through them.
    /// Measured: promoting those costs `l-bracket-gusset/mesh-coarse`,
    /// `bearing-block-608/mesh-default` and `freeform-palm-rest/mesh-coarse`
    /// their tier, all three on plane-against-cylinder bolt-hole rims.
    fn rim_needs_marching(&self, patches: (u32, u32), center: V3, axis: V3, radius: f64) -> bool {
        let prims: Vec<Primitive> = [patches.0, patches.1]
            .iter()
            .filter_map(|p| self.ctx.seg.patches.get(*p as usize).map(|x| x.primitive))
            .collect();
        prims.len() == 2
            && prims.iter().all(|p| periodic::is_periodic(*p))
            && prims
                .iter()
                .any(|p| periodic::is_rim_of(*p, center, axis, radius, self.ctx.tol))
    }

    /// A rim as the kernel wants it: **one** closed circular edge carrying its
    /// own seam vertex, not a pair of half-arcs.
    ///
    /// The seam vertex is put on the meridian every ring about this axis line
    /// seams at. Two rims of one cylinder each come from their own
    /// intersection and their circle normals can point opposite ways along the
    /// shared axis, and `Frame3::from_normal` builds `x` as `z x candidate`,
    /// which flips with `z`: anchored at each circle's own `evaluate(0)` the
    /// two would seam half a turn apart and the seam between them would cut
    /// across the body instead of running along it.
    fn rim_edge(&mut self, chain: &Chain, circle: Circle3D) -> Option<EdgeRun> {
        let axis = from_vector(circle.normal());
        let anchor = periodic::seam_reference(axis)
            .map(|r| from_point(circle.center()).add(r.mul(circle.radius())))?;
        let at = circle.project(point(anchor));
        let seam = from_point(circle.evaluate(at));
        let tangent = from_point(circle.evaluate(at + 1e-6)).sub(seam);
        let v = self.add_vertex(seam);
        let mut e = KernelEdge::with_tolerance(v, v, EdgeCurve::Circle(circle), Some(self.ctx.tol));
        e.set_trim(Some((at, at + std::f64::consts::TAU)));
        let eid = self.topo.add_edge(e);
        let forward =
            chain_direction_at(self.ctx, chain, seam).is_none_or(|d| tangent.dot(d) >= 0.0);
        Some(EdgeRun {
            segments: vec![(eid, forward)],
            start: v,
            end: v,
            kind: RunKind::Circle,
        })
    }

    fn polyline_run(
        &mut self,
        points: &[V3],
        closed: bool,
        vertices: Option<(u32, u32)>,
    ) -> Option<EdgeRun> {
        let mut pts = points.to_vec();
        if closed {
            match (pts.first().copied(), pts.last().copied()) {
                (Some(f), Some(l)) if f.sub(l).norm() > 0.0 => pts.push(f),
                _ => {}
            }
        }
        if pts.len() < 2 {
            return None;
        }

        if self.ctx.polyline_nurbs
            && pts.len() >= 4
            && let Some(run) = self.nurbs_run(&pts, closed, vertices)
        {
            return Some(run);
        }

        // Straight edges through the curve's own points. The interior points
        // are the curve's, not the mesh's — both faces on this edge are
        // analytic, so nothing else has to line up with them.
        let start = match vertices {
            Some((a, _)) if !closed => self.topo_vertex_of(a)?,
            _ => {
                let p = pts[0];
                self.add_vertex(p)
            }
        };
        let mut segments = Vec::with_capacity(pts.len() - 1);
        let mut previous = start;
        for (k, p) in pts.iter().enumerate().skip(1) {
            let last = k + 1 == pts.len();
            let v = if last && closed {
                start
            } else if last && let Some((_, b)) = vertices {
                self.topo_vertex_of(b)?
            } else {
                self.add_vertex(*p)
            };
            if let Some(seg) = self.own_edge(previous, v) {
                segments.push(seg);
                previous = v;
            }
        }
        if segments.is_empty() {
            return None;
        }
        Some(EdgeRun {
            segments,
            start,
            end: previous,
            kind: RunKind::CurveChain,
        })
    }

    fn nurbs_run(
        &mut self,
        pts: &[V3],
        closed: bool,
        vertices: Option<(u32, u32)>,
    ) -> Option<EdgeRun> {
        let kernel_points: Vec<Point3> = pts.iter().map(|p| point(*p)).collect();
        let curve = interpolate(&kernel_points, 3).ok()?;
        let (t0, t1) = remus_math::traits::ParametricCurve::domain(&curve);
        if !t0.is_finite() || !t1.is_finite() || t1 <= t0 {
            return None;
        }
        let at0 = from_point(remus_math::traits::ParametricCurve::evaluate(&curve, t0));
        let at1 = from_point(remus_math::traits::ParametricCurve::evaluate(&curve, t1));

        let (v0, v1) = if closed {
            let v = self.add_vertex(at0);
            (v, v)
        } else {
            let (a, b) = vertices?;
            (self.topo_vertex_of(a)?, self.topo_vertex_of(b)?)
        };
        let p0 = self.point_of(v0);
        let p1 = self.point_of(v1);
        let residual = at0.sub(p0).norm().max(at1.sub(p1).norm());
        if !residual.is_finite() || residual > MAX_ARC_ENDPOINT_FACTOR * self.ctx.tol {
            return None;
        }
        // An interpolating spline passes through its data and can still bow
        // far away between two of them: marched samples are unevenly spaced
        // and slightly noisy, which is exactly what makes a degree-3
        // interpolation ring. Measured on the fillet block, an unchecked
        // NURBS edge put the result 0.5 mm off a 4 mm part where the same
        // points as straight edges were 0.03 mm off. So the curve has to
        // prove it stays on its own polyline before it is kept.
        let steps = pts.len() * 2;
        for i in 0..=steps {
            let t = t0 + (t1 - t0) * i as f64 / steps as f64;
            let q = from_point(remus_math::traits::ParametricCurve::evaluate(&curve, t));
            if polyline_distance(q, pts) > self.ctx.tol {
                return None;
            }
        }
        let tol = self.ctx.tol.max(residual * 1.5);
        let mut e = KernelEdge::with_tolerance(v0, v1, EdgeCurve::NurbsCurve(curve), Some(tol));
        e.set_trim(Some((t0, t1)));
        let eid = self.topo.add_edge(e);
        Some(EdgeRun {
            segments: vec![(eid, true)],
            start: v0,
            end: v1,
            kind: RunKind::Nurbs,
        })
    }

    fn point_of(&self, v: VertexId) -> V3 {
        self.topo
            .vertex(v)
            .map_or(V3::ZERO, |x| from_point(x.point()))
    }

    /// One analytic face: surface, wires, orientation.
    fn analytic_face(&mut self, patch: &Patch) -> core::result::Result<FaceId, &'static str> {
        // A plane carries the sign in its own normal, so it is never a
        // reversed face; a quadric keeps the outward normal its own
        // parameterisation defines and takes the sign on the face flag.
        let flip = self.outward_sign(patch) < 0.0;
        let surface = surface_of(patch.primitive, flip).ok_or("surface construction refused")?;
        let reversed = flip && !surface.is_planar();

        let loops = self
            .ctx
            .patch_topo
            .patch_loops
            .get(patch.id as usize)
            .ok_or("no loops recovered")?;

        let mut built: Vec<BuiltLoop> = Vec::with_capacity(loops.loops.len());
        for l in &loops.loops {
            let ids: Vec<u32> = l.edges.iter().map(|&(e, _)| e).collect();
            let walked = self.walk_loop(patch.id, &ids)?;
            let rim = self.rim_of(patch, &walked);
            built.push(BuiltLoop {
                normal: self.loop_normal(&walked.order),
                entry: walked.entry,
                wire: walked.wire,
                rim,
            });
        }

        // A periodic face is not an outer rim with the other rim as a hole:
        // the kernel expects one wire running down a doubled seam, and every
        // structured tessellation path declines a curved face that has inner
        // wires at all. Any loop that is not one of the seamed rims — a bore
        // through a cylinder wall — stays an inner wire.
        let seamed = if surface.is_planar() {
            None
        } else {
            self.periodic_loops(patch, &surface, &built)
        };
        // The seamed wire is put first and is the outer one by construction.
        let mut forced_outer = None;
        if let Some(next) = seamed {
            built = next;
            forced_outer = Some(0);
        } else if built.is_empty() {
            return Err("no loops recovered");
        }

        // On a plane the loop's own winding says whether it bounds material
        // or a hole: one loop winds with the outward normal and every other
        // one against it. Two loops winding with it is not a face with a hole
        // at all — it is a patch the segmenter merged out of two disjoint
        // regions of the same plane, and one face cannot bound both.
        let outer = if let Some(at) = forced_outer {
            at
        } else if surface.is_planar() {
            let normal = match &surface {
                FaceSurface::Plane { normal, .. } => from_vector(*normal),
                _ => V3::ZERO,
            };
            let positive: Vec<usize> = built
                .iter()
                .enumerate()
                .filter(|(_, l)| l.normal.dot(normal) > 0.0)
                .map(|(i, _)| i)
                .collect();
            match positive.as_slice() {
                [only] => *only,
                [] => return Err("no loop winds with the face normal"),
                _ => return Err("patch has two outer boundaries"),
            }
        } else {
            built
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.normal.norm().total_cmp(&b.1.normal.norm()))
                .map(|(i, _)| i)
                .ok_or("no loops recovered")?
        };

        let mut outer_wire = None;
        let mut inner_wires = Vec::new();
        for (i, BuiltLoop { wire: edges, .. }) in built.into_iter().enumerate() {
            // A face's stored winding follows its stored surface normal; a
            // reversed face carries the geometric normal, so its stored loops
            // run the other way round.
            let edges = if reversed {
                edges
                    .into_iter()
                    .rev()
                    .map(|oe| OrientedEdge::new(oe.edge(), !oe.is_forward()))
                    .collect()
            } else {
                edges
            };
            let wire = Wire::new(edges, true).map_err(|_| "empty wire")?;
            let id = self.topo.add_wire(wire);
            if i == outer {
                outer_wire = Some(id);
            } else {
                inner_wires.push(id);
            }
        }
        let outer_wire = outer_wire.ok_or("no outer wire")?;

        let face = if reversed {
            Face::new_reversed(outer_wire, inner_wires, surface)
        } else {
            Face::new(outer_wire, inner_wires, surface)
        };
        let fid = self.topo.add_face(face);
        self.face_patch.insert(fid.index(), patch.id);
        Ok(fid)
    }

    /// Whether a walked loop is a **rim** of this face's surface: a boundary
    /// that winds the surface's periodic parameter a full turn.
    ///
    /// Measured on the loop's own mesh polygon rather than on the edges under
    /// it, because a rim arrives as one closed circle only when nothing lands
    /// on it: a vertex anywhere on the rim splits it into a chain of arcs, and
    /// the kernel's band mesher takes either. What the winding excludes is a
    /// bore through the wall, which is closed but winds nothing.
    fn rim_of(&self, patch: &Patch, walked: &Walked) -> Option<Rim> {
        let points = self.loop_points(&walked.order);
        let (origin, dir) = periodic::rim_axis(patch.primitive, &points)?;
        if !periodic::winds_full_turn(&points, origin, dir) {
            return None;
        }
        Some(Rim {
            seam: walked.entry,
            point: self.point_of(walked.entry),
        })
    }

    /// A periodic face's loops re-expressed the way the kernel builds them,
    /// with the seamed wire first. `None` leaves the face on the ordinary
    /// outer-plus-inner path.
    ///
    /// * two rims -> `[rim, seam, rim⁻¹, seam⁻¹]`, every other loop kept as an
    ///   inner wire (a bore through a cylinder wall stays a hole);
    /// * one rim on a surface that closes to a point -> `[rim, seam, seam⁻¹]`,
    ///   the seam doubled out to the cone's apex;
    /// * no boundary at all on a doubly closed surface -> the fundamental
    ///   polygon `a b a⁻¹ b⁻¹` on two degenerate seam edges.
    fn periodic_loops(
        &mut self,
        patch: &Patch,
        surface: &FaceSurface,
        built: &[BuiltLoop],
    ) -> Option<Vec<BuiltLoop>> {
        let rims: Vec<usize> = built
            .iter()
            .enumerate()
            .filter(|(_, l)| l.rim.is_some())
            .map(|(i, _)| i)
            .collect();
        match rims.as_slice() {
            [] if built.is_empty() => self.closed_periodic_loop(surface),
            [only] if built.len() == 1 => self.pole_seamed_loop(patch, built, *only),
            [a, b] => self.rim_seamed_loop(patch, built, *a, *b),
            _ => None,
        }
    }

    /// `[rim, seam, rim⁻¹, seam⁻¹]`: the one wire a band between two rims has.
    fn rim_seamed_loop(
        &mut self,
        patch: &Patch,
        built: &[BuiltLoop],
        a: usize,
        b: usize,
    ) -> Option<Vec<BuiltLoop>> {
        let (first, second) = (built.get(a)?, built.get(b)?);
        let (r0, r1) = (first.rim?, second.rim?);
        let (seam, forward) = self.seam_edge(patch, r0.seam, r1.seam)?;

        let mut wire = first.wire.clone();
        wire.push(OrientedEdge::new(seam, forward));
        wire.extend(second.wire.iter().copied());
        wire.push(OrientedEdge::new(seam, !forward));

        let mut out = vec![BuiltLoop {
            normal: V3::ZERO,
            entry: first.entry,
            wire,
            rim: None,
        }];
        out.extend(
            built
                .iter()
                .enumerate()
                .filter(|(i, _)| *i != a && *i != b)
                .map(|(_, l)| l.clone()),
        );
        Some(out)
    }

    /// `[rim, seam, seam⁻¹]`: a wall that runs out to a point, which is what a
    /// cone closed at its apex is. A sphere's pole is deliberately left alone —
    /// see [`periodic::degenerate_point`].
    fn pole_seamed_loop(
        &mut self,
        patch: &Patch,
        built: &[BuiltLoop],
        at: usize,
    ) -> Option<Vec<BuiltLoop>> {
        let loop_ = built.get(at)?;
        let rim = loop_.rim?;
        let pole = periodic::degenerate_point(patch.primitive)?;
        // A pole that is not comfortably clear of the rim is not a pole this
        // face runs out to; it is the rim itself, seen twice.
        if pole.sub(rim.point).norm() <= self.ctx.tol {
            return None;
        }
        let v = self.add_vertex(pole);
        let (seam, forward) = self.seam_edge(patch, rim.seam, v)?;

        let mut wire = loop_.wire.clone();
        wire.push(OrientedEdge::new(seam, forward));
        wire.push(OrientedEdge::new(seam, !forward));
        Some(vec![BuiltLoop {
            normal: V3::ZERO,
            entry: loop_.entry,
            wire,
            rim: None,
        }])
    }

    /// The fundamental polygon `a b a⁻¹ b⁻¹` a doubly closed surface is
    /// bounded by: a whole doughnut, which has no rim to seam to.
    fn closed_periodic_loop(&mut self, surface: &FaceSurface) -> Option<Vec<BuiltLoop>> {
        let FaceSurface::Torus(torus) = surface else {
            return None;
        };
        let v = self.add_vertex(from_point(torus.evaluate(0.0, 0.0)));
        let a = self.topo.add_edge(KernelEdge::new(v, v, EdgeCurve::Line));
        let b = self.topo.add_edge(KernelEdge::new(v, v, EdgeCurve::Line));
        Some(vec![BuiltLoop {
            normal: V3::ZERO,
            entry: v,
            wire: vec![
                OrientedEdge::new(a, true),
                OrientedEdge::new(b, true),
                OrientedEdge::new(a, false),
                OrientedEdge::new(b, false),
            ],
            rim: None,
        }])
    }

    /// The seam edge between two points on a periodic surface.
    ///
    /// A **straight** edge, whatever the surface. `revolve` seams its walls
    /// with the original profile — an arc on a torus — but the
    /// tessellator does not require that: its two-rim torus band takes "the
    /// one OPEN edge used exactly twice" of any curve type and reads only its
    /// ends and its midpoint
    /// (`crates/operations/src/tessellate/nonplanar.rs:683-702`), and its
    /// cylinder/cone band wants a line outright (`nonplanar.rs:329-333`).
    /// Drawing the meridian arc instead was measured and is worse: it costs
    /// `cockpit-plug/mesh-export` its mixed tier, because two rims recovered
    /// as arc chains meet at corners the mesh put wherever it liked and the
    /// meridian through one is not the meridian through the other.
    ///
    /// Returns the edge with the flag that traverses it from `v0` to `v1`. It
    /// is created once and used twice by this one face, which is the B-Rep
    /// convention the kernel's own builders and its band tessellator both
    /// read.
    fn seam_edge(&mut self, patch: &Patch, v0: VertexId, v1: VertexId) -> Option<(EdgeId, bool)> {
        periodic::is_periodic(patch.primitive)
            .then(|| self.own_edge(v0, v1))
            .flatten()
    }

    /// Chain a patch's loop into a wire, in the face's outward sense.
    ///
    /// The traversal direction of every edge is fixed independently, by which
    /// of the two patches walks the chain counter-clockwise; the walk only has
    /// to put them in an order that joins head to tail. Two faces on one edge
    /// therefore traverse it in opposite senses by construction, which is what
    /// the kernel's shell orientation check demands.
    fn walk_loop(&self, patch: u32, ids: &[u32]) -> core::result::Result<Walked, &'static str> {
        let mut pending: Vec<(u32, bool, &EdgeRun)> = Vec::with_capacity(ids.len());
        for &id in ids {
            let run = self
                .runs
                .get(id as usize)
                .and_then(Option::as_ref)
                .ok_or("edge has no kernel geometry")?;
            let ccw = self
                .ctx
                .ccw_patch
                .get(id as usize)
                .copied()
                .flatten()
                .ok_or("edge orientation unknown")?;
            pending.push((id, ccw == patch, run));
        }

        let (first_id, first_forward, first_run) = pending[0];
        let mut out = first_run.oriented(first_forward);
        let mut order = vec![(first_id, first_forward)];
        let mut cursor = first_run.exit(first_forward);
        let closing = first_run.entry(first_forward);
        let mut used = vec![false; pending.len()];
        used[0] = true;
        for _ in 1..pending.len() {
            let next = pending
                .iter()
                .enumerate()
                .position(|(i, (_, f, run))| !used[i] && run.entry(*f) == cursor);
            let Some(i) = next else {
                return Err("loop does not chain");
            };
            let (id, forward, run) = pending[i];
            used[i] = true;
            out.extend(run.oriented(forward));
            order.push((id, forward));
            cursor = run.exit(forward);
        }
        if cursor != closing {
            return Err("loop does not close");
        }
        Ok(Walked {
            entry: closing,
            wire: out,
            order,
        })
    }

    /// The area a loop encloses, from the mesh vertices of its own chains in
    /// the order the wire walks them.
    ///
    /// Measured on the mesh rather than the fitted curves because it only has
    /// to rank the loops, and the mesh polygon is available for every edge
    /// whatever its curve turned out to be. Traversal order is what makes it a
    /// polygon at all: a loop's chains concatenated in discovery order enclose
    /// nothing, which ranks a face's outer boundary below its holes.
    fn loop_normal(&self, order: &[(u32, bool)]) -> V3 {
        polygon_normal(&self.loop_points(order))
    }

    /// The loop's mesh vertices, in the order the wire walks them.
    fn loop_points(&self, order: &[(u32, bool)]) -> Vec<V3> {
        let mut pts: Vec<V3> = Vec::new();
        for &(id, forward) in order {
            let Some(chain) = self.ctx.chains.get(id as usize) else {
                continue;
            };
            let mut run: Vec<V3> = chain
                .verts
                .iter()
                .filter_map(|v| self.ctx.geom.points.get(*v as usize).copied())
                .collect();
            if !forward {
                run.reverse();
            }
            // The chain's own last vertex is the next chain's first.
            if !chain.closed {
                run.pop();
            }
            pts.extend(run);
        }
        pts
    }

    /// Whether the fitted surface's own normal points out of the body.
    ///
    /// Area-weighted against the mesh's outward triangle normals: the fit has
    /// no side of its own, and every downstream orientation decision hangs on
    /// this sign.
    fn outward_sign(&self, patch: &Patch) -> f64 {
        let mut total = 0.0;
        for &f in &patch.faces {
            let (Some(&normal), Some(&centroid), Some(&area)) = (
                self.ctx.geom.normals.get(f as usize),
                self.ctx.geom.centroids.get(f as usize),
                self.ctx.geom.areas.get(f as usize),
            ) else {
                continue;
            };
            if let Some(g) = crate::topology::surf::gradient(patch.primitive, centroid) {
                total += area * normal.dot(g);
            }
        }
        if total < 0.0 { -1.0 } else { 1.0 }
    }

    /// A patch emitted the way the faceted tier would: one planar face per
    /// mesh triangle, on the shared vertices and edges everything else uses.
    fn triangle_faces(&mut self, patch: u32) -> Vec<FaceId> {
        let Some(entry) = self.ctx.seg.patches.get(patch as usize) else {
            return Vec::new();
        };
        let faces = entry.faces.clone();
        let mut out = Vec::with_capacity(faces.len());
        for &f in &faces {
            let Some(tri) = self.ctx.geom.triangles.get(f as usize).copied() else {
                continue;
            };
            let vs = [
                self.mesh_vertex_of(tri[0]),
                self.mesh_vertex_of(tri[1]),
                self.mesh_vertex_of(tri[2]),
            ];
            if vs[0] == vs[1] || vs[1] == vs[2] || vs[0] == vs[2] {
                self.dropped_triangles += 1;
                continue;
            }
            let mut edges = Vec::with_capacity(3);
            let mut ok = true;
            for k in 0..3 {
                match self.mesh_edge(tri[k], tri[(k + 1) % 3]) {
                    Some((e, forward)) => edges.push(OrientedEdge::new(e, forward)),
                    None => ok = false,
                }
            }
            if !ok || edges.len() != 3 {
                self.dropped_triangles += 1;
                continue;
            }
            let Ok(wire) = Wire::new(edges, true) else {
                continue;
            };
            let wid = self.topo.add_wire(wire);
            let normal = self
                .ctx
                .geom
                .normals
                .get(f as usize)
                .copied()
                .unwrap_or(V3::new(0.0, 0.0, 1.0));
            let anchor = self.point_of(vs[0]);
            let surface = FaceSurface::Plane {
                normal: vector(normal),
                d: normal.dot(anchor),
            };
            let fid = self.topo.add_face(Face::new(wid, vec![], surface));
            self.face_patch.insert(fid.index(), patch);
            out.push(fid);
        }
        out
    }
}

/// Record which patches use which kernel edge, so a validator complaint about
/// an edge can be turned back into the patches to demote.
pub(super) fn map_edge_patches(
    topo: &KernelTopology,
    solid: SolidId,
) -> BTreeMap<usize, Vec<FaceId>> {
    let mut out: BTreeMap<usize, Vec<FaceId>> = BTreeMap::new();
    let Ok(faces) = remus_topology::explorer::solid_faces(topo, solid) else {
        return out;
    };
    for fid in faces {
        let Ok(face) = topo.face(fid) else { continue };
        let wires = std::iter::once(face.outer_wire()).chain(face.inner_wires().iter().copied());
        for wid in wires {
            let Ok(wire) = topo.wire(wid) else { continue };
            for oe in wire.edges() {
                out.entry(oe.edge().index()).or_default().push(fid);
            }
        }
    }
    out
}

/// Distance from a point to a polyline, for checking a fitted curve against
/// the samples it was fitted to.
fn polyline_distance(q: V3, pts: &[V3]) -> f64 {
    let mut best = f64::INFINITY;
    for w in pts.windows(2) {
        let ab = w[1].sub(w[0]);
        let len2 = ab.dot(ab);
        let d = if len2 <= 0.0 {
            q.sub(w[0]).norm()
        } else {
            let t = (q.sub(w[0]).dot(ab) / len2).clamp(0.0, 1.0);
            q.sub(w[0].add(ab.mul(t))).norm()
        };
        best = best.min(d);
    }
    best
}

/// The chain's own direction near a point, for orienting a rim edge.
fn chain_direction_at(ctx: &Context<'_>, chain: &Chain, at: V3) -> Option<V3> {
    let n = chain.verts.len();
    if n < 2 {
        return None;
    }
    let mut best = 0_usize;
    let mut best_d = f64::INFINITY;
    for (k, &v) in chain.verts.iter().enumerate() {
        let p = ctx.geom.points.get(v as usize)?;
        let d = p.sub(at).norm();
        if d < best_d {
            best_d = d;
            best = k;
        }
    }
    let a = ctx.geom.points.get(chain.verts[best] as usize)?;
    let b = ctx.geom.points.get(chain.verts[(best + 1) % n] as usize)?;
    b.sub(*a).unit()
}

/// The fitted primitive as a kernel face surface.
///
/// The plane carries the sign directly — a plane's normal is the surface, not
/// a convention — while the quadrics keep their own outward normal and take
/// the sign on the face's `reversed` flag instead.
pub(super) fn surface_of(prim: Primitive, reversed: bool) -> Option<FaceSurface> {
    match prim {
        Primitive::Plane { normal, offset } => {
            let sign = if reversed { -1.0 } else { 1.0 };
            let n = V3::from_arr(normal).mul(sign).unit()?;
            Some(FaceSurface::Plane {
                normal: vector(n),
                d: offset * sign,
            })
        }
        Primitive::Cylinder {
            axis_point,
            axis_dir,
            radius,
            ..
        } => CylindricalSurface::new(
            point(V3::from_arr(axis_point)),
            vector(V3::from_arr(axis_dir)),
            radius,
        )
        .ok()
        .map(FaceSurface::Cylinder),
        // The kernel measures a cone's half angle from the radial plane; this
        // crate measures it from the axis.
        Primitive::Cone {
            apex,
            axis_dir,
            half_angle_deg,
        } => ConicalSurface::new(
            point(V3::from_arr(apex)),
            vector(V3::from_arr(axis_dir)),
            (90.0 - half_angle_deg).to_radians(),
        )
        .ok()
        .map(FaceSurface::Cone),
        Primitive::Sphere { center, radius } => {
            SphericalSurface::new(point(V3::from_arr(center)), radius)
                .ok()
                .map(FaceSurface::Sphere)
        }
        Primitive::Torus {
            center,
            axis_dir,
            major_radius,
            minor_radius,
        } => ToroidalSurface::with_axis(
            point(V3::from_arr(center)),
            major_radius,
            minor_radius,
            vector(V3::from_arr(axis_dir)),
        )
        .ok()
        .map(FaceSurface::Torus),
        Primitive::Unknown => None,
    }
}

pub(super) fn point(v: V3) -> Point3 {
    Point3::new(v.x, v.y, v.z)
}

pub(super) fn vector(v: V3) -> Vec3 {
    Vec3::new(v.x, v.y, v.z)
}

pub(super) fn from_point(p: Point3) -> V3 {
    V3::new(p.x(), p.y(), p.z())
}

pub(super) fn from_vector(v: Vec3) -> V3 {
    V3::new(v.x(), v.y(), v.z())
}
